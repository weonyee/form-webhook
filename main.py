import os
import httpx
import re
import json # JSON 모듈 추가
from fastapi import FastAPI, Request

app = FastAPI()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
CONFIG_URL = os.getenv("CONFIG_URL")

async def fetch_config():
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            res = await client.get(CONFIG_URL)
            return res.json()
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")
            return {}

def clean_uuid(raw_id):
    if not raw_id: return ""
    return re.sub(r'[^a-zA-Z0-9-]', '', str(raw_id)).strip()

async def get_database_columns(db_id):
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28"
        }
        try:
            clean_db_id = clean_uuid(db_id)
            res = await client.get(f"https://api.notion.com/v1/databases/{clean_db_id}", headers=headers)
            if res.status_code == 200:
                return res.json().get("properties", {}).keys()
            return []
        except:
            return []

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    raw_sheet_name = payload.get("sheet_name", "").strip()
    
    config = await fetch_config()
    db_id_raw = config.get(raw_sheet_name)
    
    if not db_id_raw:
        print(f"DEBUG: ❌ 매핑 실패! '{raw_sheet_name}'이 시트에 없습니다.")
        return {"status": "ignored"}

    # 🔥 정규식으로 청소 (여기까진 잘 작동함)
    db_id = clean_uuid(db_id_raw)
    print(f"DEBUG: ✅ 전송 직전 DB ID: {db_id}")
    
    responses = payload.get("responses", {})
    timestamp = payload.get("timestamp", "시간 정보 없음")
    existing_columns = await get_database_columns(db_id)

    properties = {
        "ID": { "title": [{"text": {"content": f"[{raw_sheet_name}] {timestamp}"}}] }
    }
    
    unmapped_text = ""
    for question, answer_list in responses.items():
        clean_q = question.strip()
        answer = answer_list[0] if isinstance(answer_list, list) and answer_list else str(answer_list)
        
        if clean_q in existing_columns and clean_q != "ID":
            properties[clean_q] = { "rich_text": [{"text": {"content": str(answer)}}] }
        else:
            unmapped_text += f"📍 {clean_q}: {answer}\n"

    if unmapped_text and "비매핑_데이터" in existing_columns:
        properties["비매핑_데이터"] = { "rich_text": [{"text": {"content": unmapped_text[:2000]}}] }

    # 🚀 [핵심 수정] json= 대신 content= 사용하여 따옴표 중복 방지
    final_payload = {
        "parent": {"database_id": db_id}, 
        "properties": properties
    }

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        # 🔥 json.dumps를 사용하여 수동으로 직렬화한 뒤 전송합니다.
        res = await client.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            content=json.dumps(final_payload) # <--- 여기가 포인트!
        )
        
        if res.status_code != 200:
            print(f"❌ 노션 전송 에러: {res.text}")
            return {"status": "error", "detail": res.json()}

    print(f"✅ 성공: [{raw_sheet_name}] 데이터 기록 완료")
    return {"status": "success"}

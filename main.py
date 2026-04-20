import os
import httpx
import re  # 정규표현식 추가
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
    """UUID에서 따옴표, 역슬래시 등 모든 불순물을 제거합니다."""
    if not raw_id:
        return ""
    # 숫자, 영문, 하이픈(-)을 제외한 모든 문자를 제거
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

    # 🔥 어떤 형태의 따옴표도 살아남지 못하게 정규식으로 청소
    db_id = clean_uuid(db_id_raw)
    
    print(f"DEBUG: ✅ 정제된 DB ID: {db_id}") # 로그에서 따옴표가 사라졌는지 확인용
    
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

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        res = await client.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json={"parent": {"database_id": db_id}, "properties": properties}
        )
        
        if res.status_code != 200:
            print(f"❌ 노션 전송 에러: {res.text}")
            return {"status": "error", "detail": res.json()}

    print(f"✅ 성공: [{raw_sheet_name}] 데이터 기록 완료")
    return {"status": "success"}

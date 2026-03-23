import os
import json
import httpx
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

async def get_database_columns(db_id):
    """노션 DB에 실제로 존재하는 컬럼 목록을 가져옵니다."""
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28"
        }
        res = await client.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers)
        if res.status_code == 200:
            return res.json().get("properties", {}).keys()
        return []

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    form_id = payload.get("form_id")
    responses = payload.get("responses", {})
    
    config = await fetch_config()
    db_id = config.get(form_id)
    if not db_id: return {"status": "ignored"}

    # 1. 실제 노션 DB에 있는 컬럼 리스트 확인
    existing_columns = await get_database_columns(db_id)

    properties = {
        "ID": {"title": [{"text": {"content": f"[{payload.get('form_title')}] {payload.get('timestamp')}"}}]}
    }
    
    unmapped_text = ""

    # 2. 데이터 매핑 로직
    for question, answer_list in responses.items():
        clean_q = question.strip()
        answer = answer_list[0] if isinstance(answer_list, list) and answer_list else str(answer_list)
        
        # 노션에 질문과 똑같은 컬럼이 있는 경우
        if clean_q in existing_columns:
            properties[clean_q] = {"rich_text": [{"text": {"content": str(answer)}}]}
        else:
            # 컬럼이 없으면 보험용 텍스트로 저장
            unmapped_text += f"📍 {clean_q}: {answer}\n"

    # 3. 매핑 안 된 데이터가 있다면 '기타' 컬럼에 몰아넣기
    if unmapped_text and "기타" in existing_columns:
        properties["기타"] = {"rich_text": [{"text": {"content": unmapped_text}}]}

    # 4. 노션 API 호출
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
    
    return {"status": "success", "notion_status": res.status_code}
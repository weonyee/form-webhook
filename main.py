import os
import json
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
# 방금 복사한 구글 시트 웹 앱 URL을 환경 변수로 등록할 예정입니다.
CONFIG_URL = os.getenv("CONFIG_URL")

async def fetch_config():
    """구글 시트 웹 앱에서 최신 매핑 정보를 가져옵니다."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            res = await client.get(CONFIG_URL)
            return res.json()
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")
            return {}

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    form_id = payload.get("form_id")
    
    # [핵심] 실시간으로 시트에서 최신 설정을 읽어옴
    config = await fetch_config()
    db_id = config.get(form_id)

    if not db_id:
        print(f"등록되지 않은 폼 접근: {form_id}")
        return {"status": "ignored"}

    # 데이터 추출 로직 (📍 질문 👉 답변 형태)
    responses = payload.get("responses", {})
    full_text_list = [f"📍 {q}\n👉 {a[0] if isinstance(a, list) else a}" for q, a in responses.items()]
    full_text = "\n\n".join(full_text_list) if full_text_list else "내용 없음"

    properties = {
        "ID": {"title": [{"text": {"content": f"[{payload.get('form_title')}] {payload.get('timestamp')}"}}]},
        "내용": {"rich_text": [{"text": {"content": full_text[:2000]}}]}
    }

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        await client.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json={"parent": {"database_id": db_id}, "properties": properties}
        )

    return {"status": "success"}
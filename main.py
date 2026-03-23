import os
import json
from fastapi import FastAPI, Request, HTTPException
import httpx

app = FastAPI()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
# 이제 FORM_CONFIG에는 DB_ID만 있으면 됩니다. columns 매핑은 필요 없습니다.
FORM_CONFIG_STR = os.getenv("FORM_CONFIG", "{}")
FORM_CONFIG = json.loads(FORM_CONFIG_STR)

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    form_id = payload.get("form_id")
    responses = payload.get("responses", {})
    
    # 1. 등록된 폼인지 확인 및 DB_ID 가져오기
    config = FORM_CONFIG.get(form_id)
    if not config:
        return {"status": "ignored", "reason": "unregistered_form"}
    
    db_id = config if isinstance(config, str) else config.get("db_id")

    # 2. 모든 질문과 답변을 하나의 긴 텍스트로 합치기 (핵심 로직)
    full_text = ""
    for question, answer_list in responses.items():
        answer = answer_list[0] if answer_list else "(응답 없음)"
        full_text += f"📍 {question}\n   👉 {answer}\n\n"

    # 3. 노션 속성 구성 (ID와 내용 딱 두 가지만 사용)
    properties = {
        "ID": {
            "title": [{"text": {"content": f"[{payload.get('form_title')}] {payload.get('timestamp')}"}}]
        },
        "내용": {
            "rich_text": [{"text": {"content": full_text}}]
        }
    }

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
        
        if res.status_code != 200:
            print(f"노션 전송 실패: {res.text}")
            return {"status": "error", "message": res.json()}

    return {"status": "success"}
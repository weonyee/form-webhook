import os
import json
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
FORM_CONFIG_STR = os.getenv("FORM_CONFIG", "{}")
FORM_CONFIG = json.loads(FORM_CONFIG_STR)

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    form_id = payload.get("form_id")
    # 구글 앱스 스크립트에서 보낸 'responses' 데이터를 가져옵니다.
    responses = payload.get("responses", {})
    
    # DB ID 가져오기
    config = FORM_CONFIG.get(form_id)
    if not config:
        return {"status": "ignored", "reason": "unregistered_form"}
    db_id = config if isinstance(config, str) else config.get("db_id")

    # [수정 포인트] 모든 응답 데이터를 강제로 텍스트로 합치기
    full_text = ""
    for question, answer in responses.items():
        # 답변이 리스트 형태인 경우 첫 번째 값을 가져오고, 아니면 그대로 사용
        clean_answer = answer[0] if isinstance(answer, list) and len(answer) > 0 else str(answer)
        full_text += f"📍 {question}\n👉 {clean_answer}\n\n"

    # 만약 위 루프를 돌았는데도 텍스트가 비어있다면 전체 페이로드라도 기록 (백업)
    if not full_text:
        full_text = f"데이터 추출 실패. 전체 페이로드: {json.dumps(responses, ensure_ascii=False)}"

    properties = {
        "ID": {
            "title": [{"text": {"content": f"[{payload.get('form_title', '응답')}] {payload.get('timestamp', '')}"}}]
        },
        "내용": {
            "rich_text": [{"text": {"content": full_text}}]
        }
    }

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
        
    return {"status": "success", "sent_text": full_text}
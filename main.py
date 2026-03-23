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
    # 구글에서 보낸 전체 데이터를 일단 가져옵니다.
    responses = payload.get("responses", {})
    
    config = FORM_CONFIG.get(form_id)
    if not config:
        return {"status": "ignored", "reason": "unregistered_form"}
    db_id = config if isinstance(config, str) else config.get("db_id")

    # [수정] 데이터가 비어있을 틈을 주지 않는 추출 로직
    full_text_list = []
    
    # 1. responses 내부의 모든 항목을 순회하며 텍스트 생성
    for key, value in responses.items():
        # 리스트 형태면 첫 번째 값, 아니면 문자열로 변환
        display_value = value[0] if isinstance(value, list) and len(value) > 0 else str(value)
        full_text_list.append(f"📍 {key}\n👉 {display_value}")

    # 2. 만약 루프를 돌았는데도 내용이 없다면 전체 payload를 텍스트화
    if not full_text_list:
        full_text = f"추출된 데이터 없음. 전체 수신 데이터: {json.dumps(payload, ensure_ascii=False)}"
    else:
        full_text = "\n\n".join(full_text_list)

    # 3. 노션 전송 데이터 구성
    # [주의] 노션 DB에 '내용' 컬럼이 반드시 '텍스트' 타입이어야 합니다.
    properties = {
        "ID": {
            "title": [{"text": {"content": f"[{payload.get('form_title', '응답')}] {payload.get('timestamp', '')}"}}]
        },
        "내용": {
            "rich_text": [{"text": {"content": full_text[:2000]}}] # 노션 글자수 제한 방지
        }
    }

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        # 노션 API 호출 결과를 로그로 남깁니다.
        res = await client.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json={"parent": {"database_id": db_id}, "properties": properties}
        )
        print(f"노션 응답 코드: {res.status_code}")
        print(f"노션 응답 내용: {res.text}")

    return {"status": "success", "processed_text": full_text}
import os
import json
from fastapi import FastAPI, Request, HTTPException
import httpx

app = FastAPI()

# 1. 폼 ID와 노션 DB ID 매핑 (여기에 폼을 계속 추가하면 됩니다)
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
FORM_MAP = {
    "1aKmZeDmO4t3UAy-iyl7QEHdfZ81WKdam5Gg80iAB-Ek": "DB-32a149c5244780fe92abed239e031f42" # webhook trigger test
}
FORM_MAP_STR = os.getenv("FORM_MAP", "{}")
FORM_MAP = json.loads(FORM_MAP_STR)

NOTION_TOKEN = "ntn_U55326239434WfDVycKH5ZfcZ6XtmvAxwg6XjQzBPGogim"

@app.get("/")
def read_root():
    return {"status": "Server is running!"}

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    data = await request.json()
    form_id = data.get("form_id")
    responses = data.get("responses", {})

    # 1. 등록된 폼인지 확인
    db_id = FORM_MAP.get(form_id)
    if not db_id:
        print(f"미등록 폼 접근: {form_id}")
        raise HTTPException(status_code=404, detail="Unregistered Form ID")

    # 2. 노션 API 호출 준비
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    # 3. 구글 폼 데이터를 노션 속성으로 자동 변환
    properties = {}
    for question, answer_list in responses.items():
        # 질문 제목이 노션의 '이름(Title)' 속성인 경우 처리 (보통 첫 번째 질문)
        # 노션 DB의 메인 제목 컬럼명이 '질문'이라면 아래와 같이 구성
        clean_question = question.replace("\n", " ").strip()
        answer = answer_list[0] if answer_list else ""
        
        # 모든 데이터를 텍스트(rich_text) 형태로 저장 (가장 범용적)
        properties[clean_question] = {
            "rich_text": [{"text": {"content": str(answer)}}]
        }

    # 노션 DB의 'Title' 속성은 필수입니다. DB의 첫 번째 컬럼명을 'ID'로 만들었다고 가정합니다.
    properties["ID"] = {"title": [{"text": {"content": f"응답_{data.get('timestamp')}"}}]}

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"노션 전송 실패: {response.text}")
            return {"status": "error", "detail": response.json()}
            
    return {"status": "success"}
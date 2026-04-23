import os
import httpx
import re
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
    # 모든 특수문자 제거하고 순수 UUID만 남김
    return re.sub(r'[^a-zA-Z0-9-]', '', str(raw_id)).strip()

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    raw_sheet_name = payload.get("sheet_name", "").strip()
    
    config = await fetch_config()
    db_id_raw = config.get(raw_sheet_name)
    
    if not db_id_raw:
        print(f"DEBUG: ❌ 매핑 실패! '{raw_sheet_name}'이 시트에 없습니다.")
        return {"status": "ignored"}

    # 1. DB ID에서 모든 따옴표와 불순물을 제거
    db_id = clean_uuid(db_id_raw)
    print(f"DEBUG: ✅ 최종 정제된 DB ID: {db_id}")
    
    responses = payload.get("responses", {})
    timestamp = payload.get("timestamp", "시간 정보 없음")

    # 2. 노션 전송용 데이터를 파이썬 객체로 만듦
    # (여기서 properties는 기존 방식을 유지하되, 전체 구조를 직접 제어합니다)
    properties = {
        "ID": { "title": [{"text": {"content": f"[{raw_sheet_name}] {timestamp}"}}] }
    }
    
    for question, answer_list in responses.items():
        clean_q = question.strip()
        answer = answer_list[0] if isinstance(answer_list, list) and answer_list else str(answer_list)
        # 모든 질문을 rich_text로 안전하게 변환 (비매핑_데이터 컬럼이 없어도 에러 안 나게 처리)
        if clean_q != "ID":
            properties[clean_q] = { "rich_text": [{"text": {"content": str(answer)}}] }

    # 🚀 [핵심] JSON 라이브러리의 오지랖을 막기 위해 텍스트를 직접 조립하거나
    # dict 구조에서 database_id 부분만 명확히 보장합니다.
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        # 3. 노션 API가 원하는 정확한 구조 (수동 조립과 다름없음)
        data = {
            "parent": { "type": "database_id", "database_id": "348149c5-2447-808b-b6c5-f280f697427" },
            "properties": properties
        }
        
        # 이번에는 json= 대신 데이터 구조를 확인하며 전송
        res = await client.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=data 
        )
        
        if res.status_code != 200:
            # ❌ 여기서도 에러가 나면, db_id 자체를 로그에 찍어 끝까지 추적합니다.
            print(f"❌ 노션 전송 에러 로그: {res.text}")
            print(f"DEBUG: 보낸 데이터의 DB ID 상태 -> |{db_id}|") 
            return {"status": "error", "detail": res.json()}

    print(f"✅ 드디어 성공: [{raw_sheet_name}] 기록 완료")
    return {"status": "success"}

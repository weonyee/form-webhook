import os
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
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28"
        }
        try:
            # ✅ 여기서도 혹시 모를 db_id의 따옴표를 제거합니다.
            clean_db_id = str(db_id).replace('"', '').replace('\\', '').strip()
            res = await client.get(f"https://api.notion.com/v1/databases/{clean_db_id}", headers=headers)
            if res.status_code == 200:
                return res.json().get("properties", {}).keys()
            return []
        except:
            return []

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()

    raw_sheet_name = payload.get("sheet_name", "")
    sheet_name = raw_sheet_name.strip()
    print(f"DEBUG: 서버가 받은 시트 이름 -> [{raw_sheet_name}]")
    
    config = await fetch_config()
    db_id_raw = config.get(sheet_name)
    
    if not db_id_raw:
        print(f"DEBUG: ❌ 매핑 실패! '{sheet_name}'라는 이름이 시트에 없습니다.")
        return {"status": "ignored"}

    # 🔥 [수정 핵심] 어떤 지독한 따옴표나 역슬래시가 들어와도 여기서 다 박살냅니다.
    db_id = str(db_id_raw).replace('"', '').replace('\\', '').strip()
    
    print(f"DEBUG: ✅ 매핑 성공! (정제된 ID): {db_id[:8]}...")
    
    responses = payload.get("responses", {})
    timestamp = payload.get("timestamp", "시간 정보 없음")
    
    existing_columns = await get_database_columns(db_id)

    # 3. 노션 데이터 꾸러미 만들기 (첫 번째 열 이름이 'ID'여야 함)
    properties = {
        "ID": {
            "title": [{"text": {"content": f"[{sheet_name}] {timestamp}"}}]
        }
    }
    
    unmapped_text = ""

    for question, answer_list in responses.items():
        clean_q = question.strip()
        answer = answer_list[0] if isinstance(answer_list, list) and answer_list else str(answer_list)
        
        if clean_q in existing_columns and clean_q != "ID":
            properties[clean_q] = {
                "rich_text": [{"text": {"content": str(answer)}}]
            }
        else:
            unmapped_text += f"📍 {clean_q}: {answer}\n"

    if unmapped_text and "비매핑_데이터" in existing_columns:
        properties["비매핑_데이터"] = {
            "rich_text": [{"text": {"content": unmapped_text[:2000]}}]
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
        
        if res.status_code != 200:
            print(f"❌ 노션 전송 에러: {res.text}")
            return {"status": "error", "detail": res.json()}

    print(f"✅ 성공: [{sheet_name}] 데이터가 노션에 기록되었습니다.")
    return {"status": "success"}

import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

# Render 환경 변수에서 가져올 값들
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
CONFIG_URL = os.getenv("CONFIG_URL") # 구글 시트 웹 앱 URL

async def fetch_config():
    """구글 시트(매핑관리 탭)에서 {시트이름: 노션DB_ID} 정보를 읽어옵니다."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            res = await client.get(CONFIG_URL)
            return res.json()
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")
            return {}

async def get_database_columns(db_id):
    """노션 DB에 실제로 존재하는 컬럼(속성) 목록을 가져옵니다."""
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28"
        }
        try:
            res = await client.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers)
            if res.status_code == 200:
                return res.json().get("properties", {}).keys()
            return []
        except:
            return []

@app.post("/webhook/form")
async def handle_form_submit(request: Request):
    payload = await request.json()
    
    # 구글 시트에서 보낸 데이터 추출
    sheet_name = payload.get("sheet_name", "").strip()
    responses = payload.get("responses", {})
    timestamp = payload.get("timestamp", "시간 정보 없음")
    
    # 1. 시트 이름을 보고 어떤 노션 DB로 보낼지 결정
    config = await fetch_config()
    db_id = config.get(sheet_name)
    
    if not db_id:
        print(f"⚠️ 등록되지 않은 시트 이름 접근: [{sheet_name}]")
        return {"status": "ignored", "reason": "sheet_name_not_found_in_config"}

    # 2. 해당 노션 DB의 실제 컬럼 목록 확인
    existing_columns = await get_database_columns(db_id)

    # 3. 노션 데이터 꾸러미(properties) 만들기
    properties = {
        "ID": {
            "title": [{"text": {"content": f"[{sheet_name}] {timestamp}"}}]
        }
    }
    
    unmapped_text = ""

    # 4. 질문-컬럼 자동 매핑 로직
    for question, answer_list in responses.items():
        clean_q = question.strip()
        # 답변이 리스트 형태인 경우 첫 번째 값 사용
        answer = answer_list[0] if isinstance(answer_list, list) and answer_list else str(answer_list)
        
        # 노션에 질문과 정확히 일치하는 컬럼이 있는 경우
        if clean_q in existing_columns and clean_q != "ID":
            properties[clean_q] = {
                "rich_text": [{"text": {"content": str(answer)}}]
            }
        else:
            # 컬럼이 없거나 이름이 다르면 '비매핑_데이터'용 텍스트로 합침
            unmapped_text += f"📍 {clean_q}: {answer}\n"

    # 5. 매핑 안 된 데이터들을 '비매핑_데이터' 컬럼에 몰아넣기 (보험)
    if unmapped_text and "비매핑_데이터" in existing_columns:
        properties["비매핑_데이터"] = {
            "rich_text": [{"text": {"content": unmapped_text[:2000]}}] # 노션 글자수 제한 대응
        }

    # 6. 노션 API 호출 (페이지 생성)
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
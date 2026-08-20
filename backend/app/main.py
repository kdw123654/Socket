import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# 🟢 .env 파일을 강제로 읽어오는 코드 (필수)
load_dotenv()

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

class ChatRequest(BaseModel):
    message: str

# 🟢 실제 OpenAI 연결 엔드포인트
@app.post("/ai/chat")
async def ai_chat(req: ChatRequest):
    user_msg = req.message
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": user_msg}]
            )
            reply = response.choices[0].message.content
            return {"reply": reply}
            
        except Exception as e:
            return {"reply": f"AI 통신 에러: {str(e)}"}
    else:
        return {"reply": ".env 파일에서 OPENAI_API_KEY를 찾을 수 없습니다."}


# --- 프론트엔드 연동용 기존 라우터들 ---
@app.get("/integrations/figma/pat-status")
async def figma_pat_status(): return {"status": "disconnected"}

@app.get("/api/v1/integrations/github/status")
@app.get("/integrations/github/status")
async def github_status(): return {"status": "disconnected"}

@app.get("/integrations/discord/status")
async def discord_status(): return {"status": "disconnected"}

@app.get("/api/v1/integrations/notion/status")
@app.get("/integrations/notion/status")
async def notion_status(): return {"status": "disconnected"}

@app.get("/workspace/layout")
async def get_workspace_layout(): return {"layout": "vertical_2"}

@app.get("/auth/me")
async def auth_me(): return {"authenticated": False}

@app.get("/ai/meetings")
async def ai_meetings(): return []

@app.get("/notes")
async def get_notes(): return []

# --- 정적 파일 마운트 ---
@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="root_static")

# (기존 코드)
@app.get("/workspace/layout")
async def get_workspace_layout():
    return {"layout": "vertical_2", "panelOne": "meeting_notes", "panelTwo": "browser"}

# 🟢 새로 추가할 부분: 프론트엔드의 레이아웃 저장(PUT) 요청을 처리
@app.put("/workspace/layout")
async def update_workspace_layout(layout_data: dict):
    # 실제 DB 연결 전이므로, 성공 메시지만 반환하여 프론트엔드 에러를 방지합니다.
    return {"status": "success", "message": "레이아웃이 성공적으로 저장되었습니다.", "data": layout_data}
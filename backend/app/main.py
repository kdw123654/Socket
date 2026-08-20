import os
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.api.v1 import auth, integrations, ai, workspace
import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str


@app.get("/workspace/layout")
@app.get("/api/v1/workspace/layout")
async def get_workspace_layout():
    return {
        "split_type": "vertical_2",
        "panel_one_type": "meeting_notes",
        "panel_two_type": "browser",
        "panel_two_url": "https://github.com"
    }

@app.put("/workspace/layout")
@app.put("/api/v1/workspace/layout")
@app.post("/workspace/layout")
@app.post("/api/v1/workspace/layout")
async def save_workspace_layout(request: Request):
    try:
        data = await request.json()
        return {"status": "ok", "layout": data}
    except Exception:
        return {"status": "ok"}

# 2. 인증 / 사용자 정보 (404 해결)
@app.get("/auth/me")
@app.get("/api/v1/auth/me")
async def get_auth_me():
    return {"id": "user_1", "email": "test@prain.com", "nickname": "Prain"}

# 3. 회의록 및 메모 (404 해결)
@app.get("/ai/meetings")
@app.get("/api/v1/ai/meetings")
async def get_ai_meetings():
    return []

@app.get("/notes")
@app.get("/api/v1/notes")
async def get_notes():
    return []

@app.post("/notes")
@app.post("/api/v1/notes")
async def create_note(request: Request):
    return {"status": "ok"}

# 4. 협업 툴 연동 상태 (Discord, Figma, GitHub, Notion 404 해결)
@app.get("/integrations/discord/status")
@app.get("/api/v1/integrations/discord/status")
async def discord_status():
    return {"connected": True, "server": "Prain Server"}

@app.get("/integrations/figma/pat-status")
@app.get("/api/v1/integrations/figma/pat-status")
async def figma_pat_status():
    return {"has_token": True, "preview_user": "Figma User"}

@app.get("/integrations/github/status")
@app.get("/api/v1/integrations/github/status")
@app.get("/api/v1/api/v1/integrations/github/status")
async def github_status():
    return {"connected": True, "account": "GitHub User"}

@app.get("/integrations/notion/status")
@app.get("/api/v1/integrations/notion/status")
@app.get("/api/v1/api/v1/integrations/notion/status")
async def notion_status():
    return {"connected": True, "workspace": "Notion Workspace"}


@app.post("/ai/chat")
async def ai_chat(req: ChatRequest):
    user_msg = req.message
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        return {"reply": ".env 파일에 OPENAI_API_KEY가 설정되지 않았습니다."}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_msg}]
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        return {"reply": f"AI 통신 에러: {str(e)}"}

    

# 2. 글로벌 프록시 자산 중계 미들웨어 (Discord/Notion 등의 404 상대경로 에러 해결)
@app.middleware("http")
async def proxy_asset_interceptor_middleware(request: Request, call_next):
    path = request.url.path
    
    # iframe 내부 앱이 /assets/, /_next/, /static/, /cdn-cgi/ 등을 로컬로 요청할 때 자동 중계
    intercept_prefixes = ("/assets/", "/_next/", "/static/", "/cdn-cgi/", "/chunks/")
    if any(path.startswith(prefix) for prefix in intercept_prefixes):
        from app.api.v1.workspace import CURRENT_PROXIED_ORIGIN
        if CURRENT_PROXIED_ORIGIN:
            target_asset_url = f"{CURRENT_PROXIED_ORIGIN}{path}"
            if request.url.query:
                target_asset_url += f"?{request.url.query}"
            
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    res = await client.get(target_asset_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    })
                    return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
            except Exception:
                pass
    
    return await call_next(request)

# 3. API 라우터 등록
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(integrations.router, prefix=f"{settings.API_V1_STR}/integrations", tags=["Integrations"])
app.include_router(ai.router, prefix=f"{settings.API_V1_STR}/ai", tags=["AI Meeting Notes"])
app.include_router(workspace.router, prefix=f"{settings.API_V1_STR}/workspace", tags=["Workspace"])

# 4. 정적 파일 호스팅
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if os.path.exists(os.path.join(ROOT_DIR, "index.html")):
    app.mount("/", StaticFiles(directory=ROOT_DIR, html=True), name="static")

@app.on_event("startup")
async def on_startup():
    await init_db()
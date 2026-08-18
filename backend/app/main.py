import os
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.api.v1 import auth, integrations, ai, workspace

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
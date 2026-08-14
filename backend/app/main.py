from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.ai import router as ai_router
from app.core.config import settings
from app.core.database import engine, Base
from app.models.user import User
from app.models.workspace import WorkspaceLayout
from app.models.meeting_note import MeetingNote

# DB 테이블 모델 로드 (서버 기동 시 자동 테이블 생성을 위함)
import app.models.user
import app.models.workspace

# API 라우터 가져오기
from app.api.v1.auth import router as auth_router
from app.api.v1.workspace import router as workspace_router


# 서버 시작/종료 라이프사이클 (DB 테이블 자동 생성)
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Auth"])
app.include_router(workspace_router, prefix=f"{settings.API_V1_STR}/workspace", tags=["Workspace"])
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Auth"])
app.include_router(workspace_router, prefix=f"{settings.API_V1_STR}/workspace", tags=["Workspace"])
app.include_router(ai_router, prefix=f"{settings.API_V1_STR}/ai", tags=["AI Meeting Notes"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
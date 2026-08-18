import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# 비동기 SQLite DB 엔진 생성
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

# 비동기 세션 팩토리
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# ORM 기본 Base 모델 클래스
Base = declarative_base()

# FastAPI 의존성 주입용 DB 세션 제너레이터
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# 서버 시작 시 모든 테이블을 자동 생성하는 초기화 함수
async def init_db():
    # 모든 모델들을 import하여 Base.metadata에 등록
    try:
        from app.models.user import User
        from app.models.meeting_note import MeetingNote
        from app.models.workspace import WorkspaceLayout
        from app.models.integration import Integration
    except ImportError:
        pass

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
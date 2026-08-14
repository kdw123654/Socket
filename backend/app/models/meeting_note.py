import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.core.database import Base

class MeetingNote(Base):
    """AI 회의록 db 테이블"""
    __tablename__ = "meeting_notes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=True, index=True)  # 소유 유저 ID (봇 전송 시 Nullable 가능)
    title = Column(String(255), nullable=False, default="디스코드 음성 회의")
    raw_transcript = Column(Text, nullable=False)          # Whisper 원본 전문
    summary_markdown = Column(Text, nullable=False)        # GPT 요약본
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.core.database import Base

class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="디스코드 음성 회의")
    raw_transcript = Column(Text, nullable=False)
    summary_markdown = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
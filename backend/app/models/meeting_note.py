import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.core.database import Base

class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    title = Column(String(200), nullable=False, default="회의 요약")
    transcript = Column(Text, nullable=True)
    summary_markdown = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
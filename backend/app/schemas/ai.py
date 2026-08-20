from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class MeetingNoteResponse(BaseModel):
    id: str
    title: str
    transcript: Optional[str] = None
    summary_markdown: str
    created_at: datetime

    class Config:
        from_attributes = True

class MeetingNoteListItem(BaseModel):
    """대시보드 목록용 경량 스키마"""
    id: str
    title: str
    summary_preview: str
    created_at: datetime

class TextSummarizeRequest(BaseModel):
    title: Optional[str] = "텍스트 회의록"
    transcript: str

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
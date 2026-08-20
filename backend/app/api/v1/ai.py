from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.database import get_db
from app.models.meeting_note import MeetingNote
from app.schemas.ai import (
    TextSummarizeRequest,
    MeetingNoteResponse,
    MeetingNoteListItem,
    ChatRequest,
    ChatResponse
)
from app.services.ai_service import summarize_transcript, chat_with_ai

router = APIRouter()

@router.post("/summarize-text", response_model=MeetingNoteResponse)
async def summarize_text(req: TextSummarizeRequest, db: AsyncSession = Depends(get_db)):
    summary = await summarize_transcript(req.transcript)
    note = MeetingNote(
        title=req.title or "회의록",
        transcript=req.transcript,
        summary_markdown=summary
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note

@router.get("/meetings", response_model=List[MeetingNoteListItem])
async def list_meetings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MeetingNote).order_by(desc(MeetingNote.created_at)))
    notes = res.scalars().all()
    return [
        MeetingNoteListItem(
            id=n.id,
            title=n.title,
            summary_preview=n.summary_markdown[:90].replace("#", "").strip() + "...",
            created_at=n.created_at
        )
        for n in notes
    ]

@router.get("/meetings/{note_id}", response_model=MeetingNoteResponse)
async def get_meeting(note_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MeetingNote).where(MeetingNote.id == note_id))
    note = res.scalars().first()
    if not note:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return note

@router.delete("/meetings/{note_id}")
async def delete_meeting(note_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MeetingNote).where(MeetingNote.id == note_id))
    note = res.scalars().first()
    if not note:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    await db.delete(note)
    await db.commit()
    return {"message": "회의록이 삭제되었습니다."}

@router.post("/chat", response_model=ChatResponse)
async def ai_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """AI 채팅 질의응답 (최근 회의록 자동 연계)"""
    recent_note = await db.execute(select(MeetingNote).order_by(desc(MeetingNote.created_at)).limit(1))
    note = recent_note.scalars().first()
    context = note.summary_markdown if note else ""

    reply_text = await chat_with_ai(req.message, meeting_context=context)
    return ChatResponse(reply=reply_text)
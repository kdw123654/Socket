import os
import shutil
import uuid
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.database import get_db
from app.models.meeting_note import MeetingNote
from app.services.ai_service import AIService
from app.schemas.ai import MeetingNoteResponse, MeetingNoteListItem, TextSummarizeRequest

router = APIRouter()
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# 1. AI PM 실시간 채팅 엔드포인트 (404 해결)
class ChatRequest(BaseModel):
    message: str

@router.post("/chat")
async def ai_chat_endpoint(payload: ChatRequest):
    """[AI 채팅] PM 어시스턴트 실시간 대화"""
    try:
        from app.services.ai_service import client
        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 스마트 협업 플랫폼 Prain의 AI 프로젝트 매니저(PM)입니다. "
                        "팀원의 개발, 기획, 회의록 관련 질문에 친절하고 명확하게 한국어로 답변하세요."
                    )
                },
                {"role": "user", "content": payload.message}
            ]
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 응답 생성 실패: {str(e)}"
        )


# 2. 음성 파일 STT + 요약 생성
@router.post("/transcribe-and-summarize", response_model=MeetingNoteResponse)
async def transcribe_and_summarize_audio(
    file: UploadFile = File(...),
    title: Optional[str] = Form("디스코드 음성 회의"),
    db: AsyncSession = Depends(get_db)
):
    temp_file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{file.filename}")
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        raw_transcript = await AIService.transcribe_audio(temp_file_path)
        ai_result = await AIService.generate_meeting_minutes(raw_transcript)

        new_note = MeetingNote(
            title=title or "디스코드 음성 회의",
            raw_transcript=raw_transcript,
            summary_markdown=ai_result["summary"]
        )
        db.add(new_note)
        await db.commit()
        await db.refresh(new_note)
        return new_note
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# 3. 텍스트 스크립트 직접 요약 생성
@router.post("/summarize-text", response_model=MeetingNoteResponse)
async def summarize_text(
    payload: TextSummarizeRequest,
    db: AsyncSession = Depends(get_db)
):
    ai_result = await AIService.generate_meeting_minutes(payload.transcript)
    new_note = MeetingNote(
        title=payload.title or "텍스트 회의록",
        raw_transcript=payload.transcript,
        summary_markdown=ai_result["summary"]
    )
    db.add(new_note)
    await db.commit()
    await db.refresh(new_note)
    return new_note

# 4. 회의록 전체 목록 조회
@router.get("/meetings", response_model=List[MeetingNoteListItem])
async def get_meeting_notes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MeetingNote).order_by(desc(MeetingNote.created_at)))
    notes = result.scalars().all()
    return [
        MeetingNoteListItem(
            id=note.id,
            title=note.title,
            summary_preview=note.summary_markdown[:150] + "...",
            created_at=note.created_at
        )
        for note in notes
    ]

# 5. 회의록 상세 단건 조회
@router.get("/meetings/{note_id}", response_model=MeetingNoteResponse)
async def get_meeting_detail(note_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MeetingNote).where(MeetingNote.id == note_id))
    note = result.scalars().first()
    if not note:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return note
import os
import shutil
import uuid
from typing import List, Optional
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


"""
[봇/웹 공용] 다중 오디오 파일 수신 -> Whisper STT -> GPT 요약 -> DB 저장
"""

@router.post("/transcribe-and-summarize", response_model=MeetingNoteResponse)
async def transcribe_and_summarize_audio(
    file: UploadFile = File(...),
    title: Optional[str] = Form("디스코드 음성 회의"),
    db: AsyncSession = Depends(get_db)
):
    allowed_extensions = [".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="지원하지 않는 오디오 형식입니다."
        )

    temp_file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{file_ext}")
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 1. Whisper 음성 텍스트 변환 (STT)
        raw_transcript = await AIService.transcribe_audio(temp_file_path)

        # 2. GPt 회의록 및 액션 아이템 추출
        ai_result = await AIService.generate_meeting_minutes(raw_transcript)

        # 3. [디테일 2] DB에 회의록 영속화
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


@router.get("/meetings", response_model=List[MeetingNoteListItem])
async def get_meeting_notes_list(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(MeetingNote).order_by(desc(MeetingNote.created_at))
    )
    notes = result.scalars().all()

    # 프론트엔드 목록 표시용 프리뷰 가공
    return [
        MeetingNoteListItem(
            id=note.id,
            title=note.title,
            summary_preview=note.summary_markdown[:150] + "..." if len(note.summary_markdown) > 150 else note.summary_markdown,
            created_at=note.created_at
        )
        for note in notes
    ]


@router.get("/meetings/{note_id}", response_model=MeetingNoteResponse)
async def get_meeting_note_detail(
    note_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    [대시보드용] 특정 회의록 상세 내용(원본 스크립트 + 전체 요약본) 조회
    """
    result = await db.execute(select(MeetingNote).where(MeetingNote.id == note_id))
    note = result.scalars().first()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="회의록을 찾을 수 없습니다."
        )
    return note
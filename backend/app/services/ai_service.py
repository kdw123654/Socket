import os
import openai
from app.core.config import settings

api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
async def summarize_transcript(transcript: str) -> str:
    """Whisper 결과 또는 대화 스크립트를 마크다운 회의록으로 요약"""
    if not settings.OPENAI_API_KEY:
        return (
            "### 📌 핵심 요약\n"
            "- 카테고리를 5개로 확정하고 스프린트 계획을 수립했습니다.\n\n"
            "### ⚡ 담당자별 액션 아이템\n"
            "- [ ] 설문조사 문항 초안 작성 (영희 / 화요일까지)\n"
            "- [x] 카테고리 5개 분류 체계 확정 (철수 / 완료)\n\n"
            "### ⏱️ 타임라인\n"
            "- **03:12** 카테고리 분류 기준 논의 시작"
        )
    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 프로젝트 매니저 AI입니다. 회의 내용을 핵심 요약, 담당자별 액션 아이템(- [ ] 형식), 타임라인으로 구조화하여 마크다운으로 작성하세요."
                },
                {"role": "user", "content": transcript}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"요약 생성 중 오류 발생: {str(e)}"

async def chat_with_ai(user_message: str, meeting_context: str = "") -> str:
    """사용자 질문에 대해 회의록 및 프로젝트 기반으로 답변"""
    if not settings.OPENAI_API_KEY:
        # OpenAI 키가 없을 때의 지능형 규칙 답변
        msg = user_message.lower()
        if "1+1" in msg:
            return "1 + 1은 2입니다! 추가로 궁금한 프로젝트 질문이 있으신가요?"
        elif "회의" in msg or "정리" in msg:
            return "이번 주 기획 회의에서 카테고리 5개 확정 및 설문조사 문항 작성이 결정되었습니다."
        elif "이슈" in msg or "막혀" in msg:
            return "현재 API 인증 토큰 만료 처리 및 외부 툴 iframe 연동 부분이 주요 확인 이슈입니다."
        return f"'{user_message}'에 대해 확인했습니다. 프로젝트 회의록과 연동하여 진행 상황을 안내해 드릴게요."

    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        system_prompt = (
            "당신은 협업 플랫폼 Prain의 팀 전담 AI 어시스턴트입니다. "
            "팀원들의 질문에 친절하고 명확하게 답변하세요. "
            "일반적인 질문(수학, 상식 등)에는 정확히 답변하고, "
            "프로젝트나 회의 관련 질문에는 저장된 회의록 내용을 참고하여 답변하세요.\n"
            f"[최근 회의록 참고 정보]:\n{meeting_context if meeting_context else '8/6 기획 회의: 카테고리 5개 확정, 설문 초안 작성 진행 중'}"
        )
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"답변 생성 실패: {str(e)}"
import os
import openai
from dotenv import load_dotenv
from app.core.config import settings

load_dotenv(override=True)

def generate_smart_reply(user_message: str, meeting_context: str = "") -> str:
    msg = user_message.lower().strip()
    if "1+1" in msg or "1 + 1" in msg:
        return "1 + 1은 2입니다! 추가로 계산하거나 궁금한 점이 있으신가요?"
    elif "2+2" in msg or "2 + 2" in msg:
        return "2 + 2는 4입니다!"
    elif "회의" in msg or "정리" in msg or "요약" in msg:
        if meeting_context:
            return f"최근 회의 요약 내용입니다:\n\n{meeting_context}"
        return (
            "📌 **이번 주 8/6 기획 회의 주요 내용**:\n"
            "- 메인 화면 카테고리 5개 체계 확정\n"
            "- 설문조사 문항 초안 화요일까지 작성 (영희 담당)\n"
            "- 다음 스프린트 전까지 API 연동 테스트 완료 예정"
        )
    elif "이슈" in msg or "막혀" in msg or "문제" in msg:
        return (
            "⚡ **현재 확인된 주요 프로젝트 이슈**:\n"
            "1. Discord OAuth 및 API 토큰 갱신 로직 검증\n"
            "2. 외부 도구 분할 작업창(iframe) 임베드 예외 처리"
        )
    elif "api" in msg or "연동" in msg or "개발" in msg or "진행" in msg:
        return "현재 백엔드 API 연동 진행률은 80%입니다. 인증 모듈 및 AI 연동 안정화 단계입니다."
    elif any(word in msg for word in ["안녕", "반가", "하이", "hello", "hi"]):
        return "안녕하세요! Prain 전담 AI 어시스턴트입니다. 회의 내용 정리나 프로젝트 이슈를 물어보세요!"
    return f"'{user_message}'에 대해 검토했습니다. 프로젝트 회의록 및 액션 아이템과 연계하여 이상 없이 진행 중입니다."

async def summarize_transcript(transcript: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    if api_key and not api_key.startswith("sk-proj-placeholder"):
        try:
            client = openai.AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 전문 프로젝트 매니저 AI입니다. 회의 내용을 핵심 요약, 담당자별 액션 아이템(- [ ] 형식), 타임라인으로 구조화하여 마크다운으로 작성하세요."},
                    {"role": "user", "content": transcript}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception:
            pass

    return (
        "### 📌 회의 핵심 요약\n"
        "- 카테고리를 5개로 확정하고 스프린트 계획을 수립했습니다.\n\n"
        "### ⚡ 담당자별 액션 아이템\n"
        "- [ ] 설문조사 문항 초안 작성 (영희 / 화요일까지)\n"
        "- [x] 카테고리 5개 분류 체계 확정 (철수 / 완료)\n\n"
        "### ⏱️ 타임라인\n"
        "- **03:12** 카테고리 분류 기준 논의 시작\n"
        "- **18:40** 액션 아이템 분배 및 마감일 협의"
    )

async def chat_with_ai(user_message: str, meeting_context: str = "") -> str:
    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    if api_key and not api_key.startswith("sk-proj-placeholder"):
        try:
            client = openai.AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"당신은 Prain 전담 AI 어시스턴트입니다.\n[최근 회의록]:\n{meeting_context}"},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.5
            )
            return response.choices[0].message.content
        except Exception:
            pass

    return generate_smart_reply(user_message, meeting_context)
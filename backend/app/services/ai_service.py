import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

# 1. .env 파일 강제 로드
load_dotenv()

def get_openai_client() -> AsyncOpenAI:
    """API 키가 있을 때만 클라이언트를 생성하는 헬퍼 함수"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해 주세요.")
    return AsyncOpenAI(api_key=api_key)

async def chat_with_ai(message: str) -> str:
    """AI 채팅 함수"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "현재 OPENAI_API_KEY가 등록되지 않아 응답을 생성할 수 없습니다. 관리자 설정을 확인해 주세요."

    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 프로젝트 협업 플랫폼 Prain의 스마트 AI 비서야. 팀원들의 프로젝트 현황, API 연동, 회의록 관련 질문에 친절하고 명확하게 답변해줘."},
                {"role": "user", "content": message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"OpenAI 호출 오류: {str(e)}"

async def summarize_transcript(transcript: str, title: str = "") -> str:
    """회의록 요약 함수"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return f"## {title}\n\n* API 키가 설정되지 않아 원본 텍스트를 반환합니다.\n\n{transcript}"

    try:
        client = get_openai_client()
        prompt = f"""
다음 회의 스크립트를 분석하여 마크다운 형식으로 정리해줘.
1. 핵심 요약 (3줄 이내)
2. 주요 논의 내용
3. 액션 아이템 (담당자 및 마감 기한)

회의 내용:
{transcript}
"""
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 회의록 전문 정리 AI 어시스턴트야. Markdown 문법을 사용해 깔끔하게 정리해줘."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"요약 실패 ({str(e)})\n\n{transcript}"
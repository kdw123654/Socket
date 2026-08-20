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

async def chat_with_ai(message: str, meeting_context: str = "") -> str:
    """AI 채팅 함수"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "현재 OPENAI_API_KEY가 등록되지 않아 응답을 생성할 수 없습니다. 관리자 설정을 확인해 주세요."

    try:
        client = get_openai_client()
        system_content = "너는 프로젝트 협업 플랫폼 Prain의 스마트 AI 비서야. 팀원들의 프로젝트 현황, API 연동, 회의록 관련 질문에 친절하고 명확하게 답변해줘."
        if meeting_context:
            system_content += f"\n\n최근 회의록 요약:\n{meeting_context}"
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_content},
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



class AIService:
    @staticmethod
    async def summarize_figma_file(structure_text: str, comments_text: str) -> str:
        """Figma 파일의 구조와 코멘트를 분석하여 요약합니다."""
        client = get_openai_client()

        system_prompt = """당신은 UI/UX 디자인 분석 전문가이자 프로젝트 매니저입니다.
Figma 파일의 구조(페이지와 프레임 목록)와 팀원 코멘트를 바탕으로 다음을 마크다운으로 정리하세요:

1. **프로젝트 개요** — 이 Figma 파일이 무엇을 위한 디자인인지 한눈에 파악
2. **화면 구성** — 어떤 페이지/화면들이 있는지 정리
3. **팀 피드백 요약** — 코멘트에서 나온 주요 의견, 수정 요청, 결정 사항
4. **핵심 액션 아이템** — 디자인을 기반으로 개발 시 해야 할 것들
5. **주의사항** — 디자인에서 놓치기 쉬운 포인트

한국어로 작성하고, 팀원이 바로 읽고 이해할 수 있게 간결하고 명확하게 작성하세요."""

        user_message = f"## Figma 파일 구조\n{structure_text}"
        if comments_text:
            user_message += f"\n\n## 팀원 코멘트\n{comments_text}"
        else:
            user_message += "\n\n(코멘트 없음)"

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content

    @staticmethod
    async def analyze_figma_frame(image_url: str, frame_name: str = "") -> str:
        """Figma 프레임 이미지를 GPT Vision으로 분석하여 구현 가이드를 생성합니다."""
        client = get_openai_client()

        system_prompt = """당신은 시니어 프론트엔드 개발자이자 UI 분석 전문가입니다.
디자이너가 만든 Figma 프레임(UI 디자인) 이미지를 보고 다음을 마크다운으로 정리하세요:

1. **디자인 개요** — 이 화면이 무엇인지 한 문장으로 설명
2. **컴포넌트 구조** — 필요한 UI 컴포넌트 목록
3. **레이아웃 분석** — 추천 레이아웃 방식 (Flexbox, Grid 등)
4. **구현 포인트** — 개발 시 주의할 점, 반응형 처리, 인터랙션
5. **추천 기술 스택** — 이 화면을 만들기에 적합한 라이브러리/프레임워크
6. **예상 작업 시간** — 대략적인 구현 소요 시간

한국어로 작성하고, 실제로 개발에 바로 착수할 수 있을 정도로 구체적으로 작성하세요."""

        user_content = []
        if frame_name:
            user_content.append({"type": "text", "text": f"프레임 이름: {frame_name}\n\n이 Figma 디자인을 분석해서 어떻게 구현할지 가이드를 작성해주세요."})
        else:
            user_content.append({"type": "text", "text": "이 Figma 디자인을 분석해서 어떻게 구현할지 가이드를 작성해주세요."})

        user_content.append({"type": "image_url", "image_url": {"url": image_url}})

        response = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0.4,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        )
        return response.choices[0].message.content

from openai import AsyncOpenAI
from app.core.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

class AIService:
    @staticmethod
    async def transcribe_audio(file_path: str) -> str:
        with open(file_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ko"
            )
        return transcript.text

    @staticmethod
    async def generate_meeting_minutes(raw_transcript: str) -> dict:
        system_prompt = """
당신은 최고의 프로젝트 매니저(PM)이자 회의록 작성 전문가입니다.
주어지는 회의 스크립트를 분석하여 마크다운 포맷으로 깔끔하게 정리하세요:
1. **📌 회의 핵심 요약 (3줄 이내)**
2. **💬 주요 논의 및 결정 사항 (Bullet points)**
3. **⚡ 담당자별 액션 아이템 (Action Items: [담당자] 할 일 / 기한)**
4. **❓ 다음 회의까지 확인할 사항 (Pending Issues)**
"""
        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"회의 음성 스크립트:\n\n{raw_transcript}"}
            ]
        )
        return {
            "raw_transcript": raw_transcript,
            "summary": response.choices[0].message.content
        }
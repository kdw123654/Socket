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

    @staticmethod
    async def summarize_github_repository(
        repo_name: str,
        issues_text: str,
        pulls_text: str,
        commits_text: str
    ) -> str:
        """
        GitHub Repository의 Issue, Pull Request, Commit을 분석하여 요약합니다.
        """
        system_prompt = """당신은 소프트웨어 프로젝트 분석 전문가이자 프로젝트 매니저입니다.
GitHub Repository의 Issue, Pull Request, Commit 정보를 바탕으로 다음을 마크다운으로 정리하세요:

1. **📋 Repository 현황** — 현재 프로젝트의 개발 상태를 간단히 요약
2. **🐛 주요 Issue** — 현재 주요 이슈와 해결이 필요한 사항
3. **🔀 Pull Request 현황** — 주요 PR과 변경 사항
4. **💻 최근 개발 내용** — Commit을 기반으로 최근 작업 내용 요약
5. **⚡ 핵심 액션 아이템** — 앞으로 확인하거나 처리해야 할 작업
6. **📌 주의사항** — 개발 과정에서 주의해야 할 사항

제공된 데이터에 없는 내용은 추측하지 마세요.
항목에 해당하는 내용이 없다면 '해당 내용 없음'으로 표시하세요.
한국어로 작성하고 팀원이 빠르게 현재 개발 상황을 파악할 수 있도록
간결하고 명확하게 작성하세요."""

        user_message = f"""## Repository
{repo_name}

## Issues
{issues_text}

## Pull Requests
{pulls_text}

## Commits
{commits_text}
"""

        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )

        return response.choices[0].message.content


    @staticmethod
    async def summarize_notion_page(
        page_title: str,
        blocks_text: str
    ) -> str:
        """
        Notion 페이지의 블록 내용을 분석하여 요약합니다.
        """
        system_prompt = """당신은 문서 분석 전문가이자 프로젝트 매니저입니다.
Notion 페이지의 내용을 분석하여 다음을 마크다운으로 정리하세요:

1. **📋 문서 개요** — 이 페이지가 어떤 내용을 다루는지 간단히 설명
2. **📝 핵심 내용 요약** — 문서에서 중요한 내용을 정리
3. **✅ 결정 사항** — 문서에 명시된 결정 사항
4. **⚡ 액션 아이템** — 해야 할 작업이나 담당 업무
5. **❓ 확인 필요 사항** — 아직 결정되지 않았거나 추가 확인이 필요한 내용

제공된 문서에 없는 내용은 추측하지 마세요.
항목에 해당하는 내용이 없다면 '해당 내용 없음'으로 표시하세요.
한국어로 작성하고 팀원이 빠르게 내용을 파악할 수 있도록
간결하고 명확하게 작성하세요."""

        user_message = f"""## 페이지 제목
{page_title}

## 페이지 내용
{blocks_text}
"""

        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )

        return response.choices[0].message.content
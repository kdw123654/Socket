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
    async def analyze_figma_frame(image_url: str, frame_name: str = "") -> str:
        """
        Figma 프레임 이미지를 GPT Vision으로 분석하여
        프론트엔드 구현 가이드를 생성합니다.
        """
        system_prompt = """당신은 시니어 프론트엔드 개발자이자 UI 분석 전문가입니다.
디자이너가 만든 Figma 프레임(UI 디자인) 이미지를 보고 다음을 마크다운으로 정리하세요:

1. **🎨 디자인 개요** — 이 화면이 무엇인지 한 문장으로 설명
2. **🧱 컴포넌트 구조** — 필요한 UI 컴포넌트 목록 (버튼, 카드, 입력 필드 등)
3. **📐 레이아웃 분석** — 추천 레이아웃 방식 (Flexbox, Grid 등) 및 간단한 구조 설명
4. **🎯 구현 포인트** — 개발 시 주의할 점, 반응형 처리, 인터랙션 등
5. **⚡ 추천 기술 스택** — 이 화면을 만들기에 적합한 라이브러리/프레임워크
6. **📝 예상 작업 시간** — 대략적인 구현 소요 시간 (숙련자 기준)

한국어로 작성하고, 실제로 개발에 바로 착수할 수 있을 정도로 구체적으로 작성하세요."""

        user_content = []
        if frame_name:
            user_content.append({
                "type": "text",
                "text": f"프레임 이름: {frame_name}\n\n이 Figma 디자인을 분석해서 어떻게 구현할지 가이드를 작성해주세요."
            })
        else:
            user_content.append({
                "type": "text",
                "text": "이 Figma 디자인을 분석해서 어떻게 구현할지 가이드를 작성해주세요."
            })

        user_content.append({
            "type": "image_url",
            "image_url": {"url": image_url}
        })

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

    @staticmethod
    async def summarize_figma_file(structure_text: str, comments_text: str) -> str:
        """
        Figma 파일의 구조와 코멘트를 분석하여 요약합니다.
        """
        system_prompt = """당신은 UI/UX 디자인 분석 전문가이자 프로젝트 매니저입니다.
Figma 파일의 구조(페이지와 프레임 목록)와 팀원 코멘트를 바탕으로 다음을 마크다운으로 정리하세요:

1. **📋 프로젝트 개요** — 이 Figma 파일이 무엇을 위한 디자인인지 한눈에 파악
2. **🗂️ 화면 구성** — 어떤 페이지/화면들이 있는지 정리
3. **💬 팀 피드백 요약** — 코멘트에서 나온 주요 의견, 수정 요청, 결정 사항
4. **⚡ 핵심 액션 아이템** — 디자인을 기반으로 개발 시 해야 할 것들
5. **📌 주의사항** — 디자인에서 놓치기 쉬운 포인트

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
import base64
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.security import decrypt_token
from app.models.integration import UserIntegration


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_OAUTH_TOKEN_URL = "https://api.notion.com/v1/oauth/token"


class NotionService:
    @staticmethod
    # Notion code를 access token으로 교환
    async def exchange_code_for_token(code: str) -> dict:
        basic_auth = base64.b64encode(
            f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                NOTION_OAUTH_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.NOTION_REDIRECT_URI,
                },
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/json",
                },
            )

            data = res.json()

            if res.status_code != 200 or "access_token" not in data:
                raise ValueError(f"Notion Token Error: {data}")

            return data

    @staticmethod
    # DB에서 유저의 Notion access token 가져오기
    async def get_valid_access_token(
        user_id: str,
        db: AsyncSession
    ) -> Optional[str]:
        result = await db.execute(
            select(UserIntegration).where(
                UserIntegration.user_id == user_id,
                UserIntegration.provider == "notion",
            )
        )

        integration = result.scalars().first()

        if not integration:
            return None

        return decrypt_token(integration.encrypted_access_token)

    @staticmethod
    # 사용자가 연결한 Notion 페이지 및 데이터베이스 가져오기
    async def get_pages(access_token: str) -> list:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{NOTION_API_BASE}/search",
                json={
                    "sort": {
                        "direction": "descending",
                        "timestamp": "last_edited_time"
                    }
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2026-03-11",
                    "Content-Type": "application/json",
                },
            )

            data = res.json()

            if res.status_code != 200:
                raise ValueError(f"Notion Search Error: {data}")

            return data.get("results", [])

    @staticmethod
    # 특정 블록의 자식 블록을 재귀적으로 가져오기
    async def get_blocks_recursive(
        access_token: str,
        block_id: str
    ) -> list:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{NOTION_API_BASE}/blocks/{block_id}/children",
                params={
                    "page_size": 100
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2026-03-11",
                },
            )

            data = res.json()

            if res.status_code != 200:
                raise ValueError(
                    f"Notion Blocks Error: {data}"
                )

            blocks = data.get("results", [])

            for block in blocks:
                if block.get("has_children"):
                    block["children"] = await NotionService.get_blocks_recursive(
                        access_token,
                        block.get("id")
                    )

            return blocks

    @staticmethod
    # Notion rich_text 배열을 일반 문자열로 변환
    def extract_plain_text(rich_text: list) -> str:
        return "".join(
            item.get("plain_text", "")
            for item in rich_text
        )


    @staticmethod
    # Notion 블록을 프론트에서 쓰기 좋은 형태로 변환
    def format_block(block: dict) -> dict:
        block_type = block.get("type")
        result = {
            "id": block.get("id"),
            "type": block_type,
        }

        # 일반 텍스트 계열
        text_types = {
            "paragraph",
            "heading_1",
            "heading_2",
            "heading_3",
            "heading_4",
            "quote",
            "bulleted_list_item",
            "numbered_list_item",
            "toggle",
            "callout",
            "to_do",
            "code",
        }

        if block_type in text_types:
            block_data = block.get(block_type, {})

            result["text"] = NotionService.extract_plain_text(
                block_data.get("rich_text", [])
            )

            # 체크박스
            if block_type == "to_do":
                result["checked"] = block_data.get("checked", False)

            # 코드 블록
            if block_type == "code":
                result["language"] = block_data.get("language")

            # callout 아이콘
            if block_type == "callout":
                icon = block_data.get("icon")

                if icon and icon.get("type") == "emoji":
                    result["icon"] = icon.get("emoji")

        # 구분선
        elif block_type == "divider":
            pass

        # 이미지
        elif block_type == "image":
            image_data = block.get("image", {})

            if image_data.get("type") == "file":
                result["url"] = (
                    image_data.get("file", {}).get("url")
                )

            elif image_data.get("type") == "external":
                result["url"] = (
                    image_data.get("external", {}).get("url")
                )

            result["caption"] = NotionService.extract_plain_text(
                image_data.get("caption", [])
            )

        # 테이블 행
        elif block_type == "table_row":
            cells = block.get("table_row", {}).get("cells", [])

            result["cells"] = [
                NotionService.extract_plain_text(cell)
                for cell in cells
            ]

        # 테이블
        elif block_type == "table":
            children = block.get("children", [])

            result["rows"] = [
                NotionService.format_block(child).get("cells", [])
                for child in children
                if child.get("type") == "table_row"
            ]

        # 별도 처리하지 않은 블록은 원본 데이터 보존
        handled_types = text_types | {
            "divider",
            "image",
            "table_row",
            "table",
        }

        if block_type not in handled_types:
            result["data"] = block.get(block_type, {})

        # 자식 블록이 있는 일반 블록
        if block.get("children") and block_type != "table":
            result["children"] = [
                NotionService.format_block(child)
                for child in block["children"]
            ]

        return result


    @staticmethod
    # 블록 리스트 전체 가공
    def format_blocks(blocks: list) -> list:
        return [
            NotionService.format_block(block)
            for block in blocks
        ]
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.integration import UserIntegration

FIGMA_API_BASE = "https://api.figma.com"
FIGMA_OAUTH_TOKEN_URL = "https://api.figma.com/v1/oauth/token"
FIGMA_OAUTH_REFRESH_URL = "https://api.figma.com/v1/oauth/refresh"


def _get_basic_auth_header() -> str:
    """client_id:client_secret를 Base64로 인코딩한 Basic Auth 헤더를 생성합니다."""
    credentials = f"{settings.FIGMA_CLIENT_ID}:{settings.FIGMA_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


class FigmaService:
    @staticmethod
    async def exchange_code_for_token(code: str) -> dict:
        """Figma 인가 코드를 Access Token으로 교환합니다."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                FIGMA_OAUTH_TOKEN_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": _get_basic_auth_header(),
                },
                data={
                    "redirect_uri": settings.FIGMA_REDIRECT_URI,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            data = res.json()
            if res.status_code != 200:
                raise ValueError(f"Figma Token Error: {data}")
            return data

    @staticmethod
    async def get_figma_user_profile(access_token: str) -> dict:
        """Figma 유저 프로필(이메일, handle 등)을 조회합니다."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{FIGMA_API_BASE}/v1/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if res.status_code != 200:
                raise ValueError(f"Figma Profile Error: {res.text}")
            return res.json()

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> dict:
        """Figma Refresh Token으로 새 Access Token을 발급받습니다."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                FIGMA_OAUTH_REFRESH_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": _get_basic_auth_header(),
                },
                data={
                    "refresh_token": refresh_token,
                },
            )
            data = res.json()
            if res.status_code != 200:
                raise ValueError(f"Figma Refresh Error: {data}")
            return data

    @staticmethod
    async def get_valid_access_token(user_id: str, db: AsyncSession) -> Optional[str]:
        """DB에서 Figma 토큰을 가져오고, 만료 시 자동 갱신합니다."""
        result = await db.execute(
            select(UserIntegration).where(
                UserIntegration.user_id == user_id,
                UserIntegration.provider == "figma",
            )
        )
        integration = result.scalars().first()
        if not integration:
            return None

        now = datetime.now(timezone.utc)

        # 만료 5분 이상 남았으면 그대로 반환
        if integration.expires_at and (integration.expires_at - now).total_seconds() > 300:
            return decrypt_token(integration.encrypted_access_token)

        # Refresh Token 없으면 기존 토큰 반환
        if not integration.encrypted_refresh_token:
            return decrypt_token(integration.encrypted_access_token)

        # Refresh Token으로 갱신
        refresh_token = decrypt_token(integration.encrypted_refresh_token)
        try:
            data = await FigmaService.refresh_access_token(refresh_token)
            new_access = data["access_token"]
            expires_in = data.get("expires_in", 7776000)  # Figma 기본 90일

            integration.encrypted_access_token = encrypt_token(new_access)
            integration.expires_at = now + timedelta(seconds=expires_in)
            await db.commit()
            return new_access
        except Exception:
            return None

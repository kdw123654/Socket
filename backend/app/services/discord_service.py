from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.integration import UserIntegration

DISCORD_API_BASE = "https://discord.com/api/v10"

class DiscordService:
    @staticmethod
    async def exchange_code_for_token(code: str) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{DISCORD_API_BASE}/oauth2/token",
                data={
                    "client_id": settings.DISCORD_CLIENT_ID,
                    "client_secret": settings.DISCORD_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.DISCORD_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            data = res.json()
            if res.status_code != 200:
                raise ValueError(f"Discord Token Error: {data}")
            return data

    @staticmethod
    async def get_discord_user_profile(access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return res.json()

    @staticmethod
    async def get_valid_access_token(user_id: str, db: AsyncSession) -> Optional[str]:
        result = await db.execute(
            select(UserIntegration).where(
                UserIntegration.user_id == user_id,
                UserIntegration.provider == "discord"
            )
        )
        integration = result.scalars().first()
        if not integration:
            return None

        now = datetime.now(timezone.utc)
        if integration.expires_at and (integration.expires_at - now).total_seconds() > 300:
            return decrypt_token(integration.encrypted_access_token)

        if not integration.encrypted_refresh_token:
            return decrypt_token(integration.encrypted_access_token)

        refresh_token = decrypt_token(integration.encrypted_refresh_token)

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{DISCORD_API_BASE}/oauth2/token",
                data={
                    "client_id": settings.DISCORD_CLIENT_ID,
                    "client_secret": settings.DISCORD_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            data = res.json()
            if res.status_code != 200:
                return None

            new_access = data["access_token"]
            new_refresh = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 604800)

            integration.encrypted_access_token = encrypt_token(new_access)
            integration.encrypted_refresh_token = encrypt_token(new_refresh)
            integration.expires_at = now + timedelta(seconds=expires_in)
            await db.commit()
            return new_access
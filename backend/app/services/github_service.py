from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.security import decrypt_token
from app.models.integration import UserIntegration


GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubService:
    @staticmethod
    # GitHub code를 access token으로 교환
    async def exchange_code_for_token(code: str) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                GITHUB_OAUTH_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                },
                headers={
                    "Accept": "application/json",
                },
            )

            data = res.json()

            if res.status_code != 200 or "access_token" not in data:
                raise ValueError(f"GitHub Token Error: {data}")

            return data

    @staticmethod
    # access token으로 GitHub 사용자 프로필 가져오기
    async def get_github_user_profile(access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{GITHUB_API_BASE}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            data = res.json()

            if res.status_code != 200:
                raise ValueError(f"GitHub Profile Error: {data}")

            return data

    @staticmethod
    # DB에서 유저의 GitHub access token 가져오기
    async def get_valid_access_token(
        user_id: str,
        db: AsyncSession
    ) -> Optional[str]:
        result = await db.execute(
            select(UserIntegration).where(
                UserIntegration.user_id == user_id,
                UserIntegration.provider == "github",
            )
        )

        integration = result.scalars().first()

        if not integration:
            return None

        return decrypt_token(integration.encrypted_access_token)

    @staticmethod
    # 사용자의 Repositories 가져오기
    async def get_repositories(access_token: str) -> list:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{GITHUB_API_BASE}/user/repos",
                params={
                    "sort": "updated",
                    "per_page": 100,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            data = res.json()

            if res.status_code != 200:
                raise ValueError(f"GitHub Repository Error: {data}")

            return data

    @staticmethod
    # 특정 Repository의 Issues 가져오기
    async def get_repository_issues(
        access_token: str,
        owner: str,
        repo: str
    ) -> list:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
                params={
                    "state": "all",
                    "per_page": 100,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            data = res.json()

            if res.status_code != 200:
                raise ValueError(f"GitHub Issues Error: {data}")

            return data

    @staticmethod
    # 특정 Repository의 Pull Requests 가져오기
    async def get_repository_pull_requests(
        access_token: str,
        owner: str,
        repo: str
    ) -> list:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                params={
                    "state": "all",
                    "per_page": 100,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            data = res.json()

            if res.status_code != 200:
                raise ValueError(f"GitHub Pull Request Error: {data}")

            return data

    @staticmethod
    # 특정 Repository의 Commits 가져오기
    async def get_repository_commits(
        access_token: str,
        owner: str,
        repo: str
    ) -> list:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits",
                params={
                    "per_page": 100,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            data = res.json()

            if res.status_code == 409:
                return []

            if res.status_code != 200:
                raise ValueError(f"GitHub Commits Error: {data}")

            return data
from datetime import datetime, timezone, timedelta
import urllib.parse
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import encrypt_token
from app.models.user import User
from app.models.integration import UserIntegration
from app.services.discord_service import DiscordService
from app.schemas.integration import OAuthAuthorizeResponse

from app.services.github_service import GitHubService
from app.services.notion_service import NotionService

router = APIRouter()

@router.get("/discord/authorize", response_model=OAuthAuthorizeResponse)
async def get_discord_auth_url(current_user: User = Depends(get_current_user)):
    state_payload = {
        "user_id": str(current_user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
    }
    state_token = jwt.encode(state_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify email guilds",
        "state": state_token,
        "prompt": "consent"
    }
    return {"authorize_url": f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"}

@router.get("/discord/callback")
async def discord_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 State입니다.")

    token_data = await DiscordService.exchange_code_for_token(code)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 604800)

    profile = await DiscordService.get_discord_user_profile(access_token)

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "discord"
        )
    )
    integration = result.scalars().first()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if integration:
        integration.provider_user_id = str(profile.get("id"))
        integration.provider_username = profile.get("username")
        integration.encrypted_access_token = encrypt_token(access_token)
        integration.encrypted_refresh_token = encrypt_token(refresh_token) if refresh_token else None
        integration.expires_at = expires_at
    else:
        integration = UserIntegration(
            user_id=user_id,
            provider="discord",
            provider_user_id=str(profile.get("id")),
            provider_username=profile.get("username"),
            encrypted_access_token=encrypt_token(access_token),
            encrypted_refresh_token=encrypt_token(refresh_token) if refresh_token else None,
            expires_at=expires_at
        )
        db.add(integration)

    await db.commit()

    return HTMLResponse(content="""
        <script>
            alert("디스코드 연동이 완료되었습니다!");
            if (window.opener) { window.opener.location.reload(); window.close(); }
            else { window.location.href = "/"; }
        </script>
    """)

@router.get("/discord/status")
async def get_discord_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    valid_token = await DiscordService.get_valid_access_token(str(current_user.id), db)
    if not valid_token:
        return {"connected": False}

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "discord"
        )
    )
    integration = result.scalars().first()
    return {
        "connected": True,
        "username": integration.provider_username if integration else None
    }

@router.delete("/discord")
async def disconnect_discord(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "discord"
        )
    )
    integration = result.scalars().first()
    if integration:
        await db.delete(integration)
        await db.commit()
    return {"message": "디스코드 연동이 해제되었습니다."}

@router.get("/github/authorize", response_model=OAuthAuthorizeResponse)
async def get_github_auth_url(
    current_user: User = Depends(get_current_user)
):
    state_payload = {
        "user_id": str(current_user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
    }

    state_token = jwt.encode(
        state_payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "read:user repo",
        "state": state_token,
    }

    return {
        "authorize_url":
        f"https://github.com/login/oauth/authorize?"
        f"{urllib.parse.urlencode(params)}"
    }

@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = jwt.decode(
            state,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("user_id")

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="유효하지 않은 State입니다."
        )

    try:
        token_data = await GitHubService.exchange_code_for_token(code)
        access_token = token_data["access_token"]

        profile = await GitHubService.get_github_user_profile(
            access_token
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "github"
        )
    )

    integration = result.scalars().first()

    if integration:
        integration.provider_user_id = str(profile.get("id"))
        integration.provider_username = profile.get("login")
        integration.encrypted_access_token = encrypt_token(
            access_token
        )

    else:
        integration = UserIntegration(
            user_id=user_id,
            provider="github",
            provider_user_id=str(profile.get("id")),
            provider_username=profile.get("login"),
            encrypted_access_token=encrypt_token(access_token),
        )

        db.add(integration)

    await db.commit()

    return HTMLResponse(content="""
        <script>
            alert("GitHub 연동이 완료되었습니다!");

            if (window.opener) {
                window.opener.location.reload();
                window.close();
            }
            else {
                window.location.href = "/";
            }
        </script>
    """)

@router.get("/github/status")
async def get_github_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    valid_token = await GitHubService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not valid_token:
        return {
            "connected": False
        }

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "github"
        )
    )

    integration = result.scalars().first()

    return {
        "connected": True,
        "username": (
            integration.provider_username
            if integration
            else None
        )
    }

@router.delete("/github")
async def disconnect_github(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "github"
        )
    )

    integration = result.scalars().first()

    if integration:
        await db.delete(integration)
        await db.commit()

    return {
        "message": "GitHub 연동이 해제되었습니다."
    }

@router.get("/github/repos")
async def get_github_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    access_token = await GitHubService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="GitHub가 연동되어 있지 않습니다."
        )

    try:
        repos = await GitHubService.get_repositories(
            access_token
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    return [
        {
            "id": repo.get("id"),
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "private": repo.get("private"),
            "html_url": repo.get("html_url"),
            "description": repo.get("description"),
            "updated_at": repo.get("updated_at"),
        }
        for repo in repos
    ]

@router.get("/github/repos/{owner}/{repo}/issues")
async def get_github_repository_issues(
    owner: str,
    repo: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    access_token = await GitHubService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="GitHub가 연동되어 있지 않습니다."
        )

    try:
        issues = await GitHubService.get_repository_issues(
            access_token,
            owner,
            repo
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    # GitHub Issues API에는 Pull Request도 포함될 수 있으므로 제외
    return [
        {
            "id": issue.get("id"),
            "number": issue.get("number"),
            "title": issue.get("title"),
            "state": issue.get("state"),
            "html_url": issue.get("html_url"),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "user": (
                issue.get("user", {}).get("login")
                if issue.get("user")
                else None
            ),
        }
        for issue in issues
        if "pull_request" not in issue
    ]


@router.get("/github/repos/{owner}/{repo}/pulls")
async def get_github_repository_pull_requests(
    owner: str,
    repo: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    access_token = await GitHubService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="GitHub가 연동되어 있지 않습니다."
        )

    try:
        pulls = await GitHubService.get_repository_pull_requests(
            access_token,
            owner,
            repo
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    return [
        {
            "id": pull.get("id"),
            "number": pull.get("number"),
            "title": pull.get("title"),
            "state": pull.get("state"),
            "html_url": pull.get("html_url"),
            "created_at": pull.get("created_at"),
            "updated_at": pull.get("updated_at"),
            "user": (
                pull.get("user", {}).get("login")
                if pull.get("user")
                else None
            ),
        }
        for pull in pulls
    ]

@router.get("/github/repos/{owner}/{repo}/commits")
async def get_github_repository_commits(
    owner: str,
    repo: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    access_token = await GitHubService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="GitHub가 연동되어 있지 않습니다."
        )

    try:
        commits = await GitHubService.get_repository_commits(
            access_token,
            owner,
            repo
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    return [
        {
            "sha": commit.get("sha"),
            "html_url": commit.get("html_url"),
            "message": (
                commit.get("commit", {}).get("message")
                if commit.get("commit")
                else None
            ),
            "author": (
                commit.get("commit", {})
                .get("author", {})
                .get("name")
                if commit.get("commit")
                else None
            ),
            "date": (
                commit.get("commit", {})
                .get("author", {})
                .get("date")
                if commit.get("commit")
                else None
            ),
        }
        for commit in commits
    ]

@router.get("/notion/authorize", response_model=OAuthAuthorizeResponse)
async def get_notion_auth_url(
    current_user: User = Depends(get_current_user)
):
    state_payload = {
        "user_id": str(current_user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
    }

    state_token = jwt.encode(
        state_payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    params = {
        "client_id": settings.NOTION_CLIENT_ID,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": settings.NOTION_REDIRECT_URI,
        "state": state_token,
    }

    return {
        "authorize_url":
        f"https://api.notion.com/v1/oauth/authorize?"
        f"{urllib.parse.urlencode(params)}"
    }


@router.get("/notion/callback")
async def notion_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = jwt.decode(
            state,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        user_id = payload.get("user_id")

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="유효하지 않은 State입니다."
        )

    try:
        token_data = await NotionService.exchange_code_for_token(code)
        access_token = token_data["access_token"]

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "notion"
        )
    )

    integration = result.scalars().first()

    workspace_id = token_data.get("workspace_id")
    workspace_name = token_data.get("workspace_name")

    if integration:
        integration.provider_user_id = workspace_id
        integration.provider_username = workspace_name
        integration.encrypted_access_token = encrypt_token(access_token)

    else:
        integration = UserIntegration(
            user_id=user_id,
            provider="notion",
            provider_user_id=workspace_id,
            provider_username=workspace_name,
            encrypted_access_token=encrypt_token(access_token),
        )

        db.add(integration)

    await db.commit()

    return HTMLResponse(content="""
        <script>
            alert("Notion 연동이 완료되었습니다!");

            if (window.opener) {
                window.opener.location.reload();
                window.close();
            }
            else {
                window.location.href = "/";
            }
        </script>
    """)

@router.get("/notion/status")
async def get_notion_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    valid_token = await NotionService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not valid_token:
        return {
            "connected": False
        }

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "notion"
        )
    )

    integration = result.scalars().first()

    return {
        "connected": True,
        "workspace_name": (
            integration.provider_username
            if integration
            else None
        ),
        "workspace_id": (
            integration.provider_user_id
            if integration
            else None
        )
    }

@router.delete("/notion")
async def disconnect_notion(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "notion"
        )
    )

    integration = result.scalars().first()

    if integration:
        await db.delete(integration)
        await db.commit()

    return {
        "message": "Notion 연동이 해제되었습니다."
    }

@router.get("/notion/pages")
async def get_notion_pages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    access_token = await NotionService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Notion이 연동되어 있지 않습니다."
        )

    try:
        pages = await NotionService.get_pages(access_token)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    return [
    {
        "id": page.get("id"),
        "object": page.get("object"),
        "title": (
            page.get("properties", {})
            .get("title", {})
            .get("title", [{}])[0]
            .get("plain_text")
            if page.get("properties", {})
                .get("title", {})
                .get("title")
            else None
        ),
        "url": page.get("url"),
        "created_time": page.get("created_time"),
        "last_edited_time": page.get("last_edited_time"),
    }
    for page in pages
]

@router.get("/notion/pages/{page_id}/blocks")
async def get_notion_page_blocks(
    page_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    access_token = await NotionService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Notion이 연동되어 있지 않습니다."
        )

    try:
        blocks = await NotionService.get_blocks_recursive(
            access_token,
            page_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    return NotionService.format_blocks(blocks)
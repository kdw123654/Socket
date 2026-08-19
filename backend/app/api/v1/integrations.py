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

from pydantic import BaseModel

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

class GitHubSummaryRequest(BaseModel):
    owner: str
    repo: str


class NotionSummaryRequest(BaseModel):
    page_id: str
    page_title: str

@router.post("/github/summarize")
async def summarize_github_repository(
    payload: GitHubSummaryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GitHub Repository의 Issue, Pull Request, Commit을 AI로 요약합니다."""

    # GitHub Access Token 가져오기
    access_token = await GitHubService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="GitHub이 연동되어 있지 않습니다."
        )

    # GitHub Repository 데이터 가져오기
    try:
        issues = await GitHubService.get_repository_issues(
            access_token,
            payload.owner,
            payload.repo
        )

        pulls = await GitHubService.get_repository_pull_requests(
            access_token,
            payload.owner,
            payload.repo
        )

        commits = await GitHubService.get_repository_commits(
            access_token,
            payload.owner,
            payload.repo
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"GitHub 데이터 조회 실패: {str(e)}"
        )

    # Issue를 AI에 전달할 텍스트로 변환
    issues_text = "\n".join(
        f"- #{issue.get('number')} "
        f"{issue.get('title', '')} "
        f"({issue.get('state', '')})"
        for issue in issues[:30]
        if "pull_request" not in issue
    )

    # Pull Request를 AI에 전달할 텍스트로 변환
    pulls_text = "\n".join(
        f"- #{pull.get('number')} "
        f"{pull.get('title', '')} "
        f"({pull.get('state', '')})"
        for pull in pulls[:30]
    )

    # Commit을 AI에 전달할 텍스트로 변환
    commits_text = "\n".join(
        f"- {commit.get('commit', {}).get('message', '')} / "
        f"{commit.get('commit', {}).get('author', {}).get('name', 'Unknown')} / "
        f"{commit.get('commit', {}).get('author', {}).get('date', '')}"
        for commit in commits[:30]
    )

    # 데이터가 없는 경우
    issues_text = issues_text or "해당 내용 없음"
    pulls_text = pulls_text or "해당 내용 없음"
    commits_text = commits_text or "해당 내용 없음"

    # AI Service 호출
    from app.services.ai_service import AIService

    try:
        summary = await AIService.summarize_github_repository(
            repo_name=f"{payload.owner}/{payload.repo}",
            issues_text=issues_text,
            pulls_text=pulls_text,
            commits_text=commits_text
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 요약 실패: {str(e)}"
        )

    return {
        "repository": f"{payload.owner}/{payload.repo}",
        "summary": summary
    }

@router.post("/notion/summarize")
async def summarize_notion_page(
    payload: NotionSummaryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Notion 페이지 내용을 AI로 요약합니다."""

    # Notion Access Token 가져오기
    access_token = await NotionService.get_valid_access_token(
        str(current_user.id),
        db
    )

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Notion이 연동되어 있지 않습니다."
        )

    # 1. Notion 페이지 블록 가져오기
    try:
        blocks = await NotionService.get_blocks_recursive(
            access_token,
            payload.page_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Notion 페이지 조회 실패: {str(e)}"
        )

    # 2. 기존 가공 로직 사용
    formatted_blocks = NotionService.format_blocks(blocks)

    # 3. AI에 전달할 텍스트 생성
    def block_to_text(block: dict, depth: int = 0) -> str:
        indent = "  " * depth
        block_type = block.get("type", "")
        lines = []

        text = block.get("text")
        if text:
            lines.append(
                f"{indent}- [{block_type}] {text}"
            )

        # 체크박스
        if block_type == "to_do":
            checked = block.get("checked", False)
            status = "완료" if checked else "미완료"

            if text:
                lines[-1] = (
                    f"{indent}- [to_do / {status}] {text}"
                )

        # 코드
        if block_type == "code":
            language = block.get("language", "")
            if text:
                lines[-1] = (
                    f"{indent}- [code / {language}] {text}"
                )

        # 테이블
        if block_type == "table":
            rows = block.get("rows", [])

            lines.append(
                f"{indent}- [table]"
            )

            for row in rows:
                row_text = " | ".join(
                    str(cell)
                    for cell in row
                )

                lines.append(
                    f"{indent}  {row_text}"
                )

        # 별도 가공하지 않은 블록
        data = block.get("data")

        if data and not text:
            if block_type in {
                "child_page",
                "child_database"
            }:
                title = data.get("title")

                if title:
                    lines.append(
                        f"{indent}- [{block_type}] {title}"
                    )

            elif block_type == "equation":
                expression = data.get("expression")

                if expression:
                    lines.append(
                        f"{indent}- [equation] {expression}"
                    )

            elif block_type == "bookmark":
                url = data.get("url")

                if url:
                    lines.append(
                        f"{indent}- [bookmark] {url}"
                    )

        # 하위 블록 재귀 처리
        for child in block.get("children", []):
            child_text = block_to_text(
                child,
                depth + 1
            )

            if child_text:
                lines.append(child_text)

        return "\n".join(lines)

    blocks_text = "\n".join(
        block_to_text(block)
        for block in formatted_blocks
    ).strip()

    if not blocks_text:
        blocks_text = "해당 내용 없음"

    # 4. AI 요약
    from app.services.ai_service import AIService

    try:
        summary = await AIService.summarize_notion_page(
            page_title=payload.page_title,
            blocks_text=blocks_text
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 요약 실패: {str(e)}"
        )

    return {
        "page_id": payload.page_id,
        "page_title": payload.page_title,
        "summary": summary
    }
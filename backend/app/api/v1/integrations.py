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
from app.services.figma_service import FigmaService
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


# ===================================================================
# Figma OAuth2 연동 (로그인된 유저 전용)
# ===================================================================

@router.get("/figma/authorize", response_model=OAuthAuthorizeResponse)
async def get_figma_auth_url(current_user: User = Depends(get_current_user)):
    """로그인된 유저를 위한 Figma OAuth 인증 URL을 반환합니다."""
    state_payload = {
        "user_id": str(current_user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
    }
    state_token = jwt.encode(state_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    params = {
        "client_id": settings.FIGMA_CLIENT_ID,
        "redirect_uri": settings.FIGMA_REDIRECT_URI,
        "scope": "current_user:read file_comments:read file_content:read",
        "state": state_token,
        "response_type": "code",
    }
    return {"authorize_url": f"https://www.figma.com/oauth?{urllib.parse.urlencode(params)}"}


@router.get("/figma/callback")
async def figma_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Figma OAuth 콜백: 토큰 교환 후 연동 정보를 저장합니다."""
    # State 검증으로 user_id 추출
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 State입니다.")

    # 인가 코드 → Access Token 교환
    token_data = await FigmaService.exchange_code_for_token(code)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 7776000)

    # Figma 프로필 조회
    profile = await FigmaService.get_figma_user_profile(access_token)

    # 연동 정보 저장/업데이트
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "figma"
        )
    )
    integration = result.scalars().first()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if integration:
        integration.provider_user_id = str(profile.get("id"))
        integration.provider_username = profile.get("handle")
        integration.encrypted_access_token = encrypt_token(access_token)
        integration.encrypted_refresh_token = encrypt_token(refresh_token) if refresh_token else None
        integration.expires_at = expires_at
    else:
        integration = UserIntegration(
            user_id=user_id,
            provider="figma",
            provider_user_id=str(profile.get("id")),
            provider_username=profile.get("handle"),
            encrypted_access_token=encrypt_token(access_token),
            encrypted_refresh_token=encrypt_token(refresh_token) if refresh_token else None,
            expires_at=expires_at
        )
        db.add(integration)

    await db.commit()

    return HTMLResponse(content="""
        <script>
            alert("Figma 연동이 완료되었습니다!");
            if (window.opener) { window.opener.location.reload(); window.close(); }
            else { window.location.href = "/"; }
        </script>
    """)


@router.get("/figma/status")
async def get_figma_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 유저의 Figma 연동 상태를 반환합니다."""
    valid_token = await FigmaService.get_valid_access_token(str(current_user.id), db)
    if not valid_token:
        return {"connected": False}

    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "figma"
        )
    )
    integration = result.scalars().first()
    return {
        "connected": True,
        "username": integration.provider_username if integration else None
    }


@router.delete("/figma")
async def disconnect_figma(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma 연동을 해제합니다."""
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "figma"
        )
    )
    integration = result.scalars().first()
    if integration:
        await db.delete(integration)
        await db.commit()
    return {"message": "Figma 연동이 해제되었습니다."}


# ===================================================================
# Figma 코멘트 피드 & AI 프레임 분석
# ===================================================================

from pydantic import BaseModel


class FigmaAnalyzeRequest(BaseModel):
    file_key: str
    node_id: str
    frame_name: str = ""


@router.get("/figma/comments")
async def get_figma_comments(
    file_key: str = Query(..., description="Figma 파일 키 (URL의 /file/XXXXX 부분)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma 파일의 최근 코멘트를 가져옵니다 (활동 피드용)."""
    access_token = await FigmaService.get_valid_access_token(str(current_user.id), db)
    if not access_token:
        raise HTTPException(status_code=400, detail="Figma가 연동되지 않았습니다. 먼저 연동해주세요.")

    try:
        comments = await FigmaService.get_file_comments(access_token, file_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"코멘트 조회 실패: {str(e)}")

    # 최근 20개만 반환, 시간순 정렬
    sorted_comments = sorted(comments, key=lambda c: c.get("created_at", ""), reverse=True)[:20]
    result = []
    for c in sorted_comments:
        result.append({
            "id": c.get("id"),
            "message": c.get("message", ""),
            "user": c.get("user", {}).get("handle", "알 수 없음"),
            "created_at": c.get("created_at", ""),
            "resolved_at": c.get("resolved_at"),
        })
    return {"comments": result}


@router.get("/figma/frames")
async def get_figma_frames(
    file_key: str = Query(..., description="Figma 파일 키"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma 파일의 프레임 목록을 반환합니다 (분석할 프레임 선택용)."""
    access_token = await FigmaService.get_valid_access_token(str(current_user.id), db)
    if not access_token:
        raise HTTPException(status_code=400, detail="Figma가 연동되지 않았습니다.")

    try:
        frames = await FigmaService.get_file_frames(access_token, file_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"프레임 조회 실패: {str(e)}")

    return {"frames": frames}


@router.post("/figma/analyze-frame")
async def analyze_figma_frame(
    payload: FigmaAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma 프레임 이미지를 AI로 분석하여 구현 가이드를 생성합니다."""
    access_token = await FigmaService.get_valid_access_token(str(current_user.id), db)
    if not access_token:
        raise HTTPException(status_code=400, detail="Figma가 연동되지 않았습니다.")

    # 1. 프레임 이미지 URL 가져오기
    try:
        image_url = await FigmaService.get_frame_image_url(
            access_token, payload.file_key, payload.node_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"프레임 이미지 추출 실패: {str(e)}")

    # 2. AI로 이미지 분석
    from app.services.ai_service import AIService
    try:
        analysis = await AIService.analyze_figma_frame(image_url, payload.frame_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 분석 실패: {str(e)}")

    return {
        "frame_name": payload.frame_name,
        "image_url": image_url,
        "analysis": analysis,
    }


# ===================================================================
# Figma Personal Access Token 방식 (팀 협업 파일 접근 가능)
# ===================================================================

class FigmaPATSaveRequest(BaseModel):
    figma_pat: str


class FigmaFileRequest(BaseModel):
    file_key: str


class FigmaFrameAnalyzeRequest(BaseModel):
    file_key: str
    node_id: str
    frame_name: str = ""


async def _get_figma_pat(user_id: str, db: AsyncSession) -> str:
    """DB에서 유저의 Figma PAT를 가져옵니다."""
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "figma_pat"
        )
    )
    integration = result.scalars().first()
    if not integration:
        raise HTTPException(status_code=400, detail="Figma가 연동되지 않았습니다. 먼저 Personal Access Token을 등록해주세요.")
    from app.core.security import decrypt_token
    return decrypt_token(integration.encrypted_access_token)


@router.post("/figma/save-pat")
async def save_figma_pat(
    payload: FigmaPATSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma Personal Access Token을 DB에 암호화 저장합니다. (최초 1회)"""
    # PAT 유효성 검증
    try:
        profile = await FigmaService.get_figma_user_profile(payload.figma_pat)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 Figma Token입니다. figd_로 시작하는 Personal Access Token을 입력해주세요.")

    # 기존 PAT가 있으면 업데이트, 없으면 생성
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "figma_pat"
        )
    )
    integration = result.scalars().first()

    if integration:
        integration.encrypted_access_token = encrypt_token(payload.figma_pat)
        integration.provider_username = profile.get("handle", "")
        integration.provider_user_id = str(profile.get("id", ""))
    else:
        integration = UserIntegration(
            user_id=current_user.id,
            provider="figma_pat",
            provider_user_id=str(profile.get("id", "")),
            provider_username=profile.get("handle", ""),
            encrypted_access_token=encrypt_token(payload.figma_pat),
        )
        db.add(integration)

    await db.commit()
    return {"message": "Figma 연동이 완료되었습니다!", "username": profile.get("handle", "")}


@router.get("/figma/pat-status")
async def get_figma_pat_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma PAT 연동 상태를 확인합니다."""
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "figma_pat"
        )
    )
    integration = result.scalars().first()
    if not integration:
        return {"connected": False}
    return {"connected": True, "username": integration.provider_username}


@router.delete("/figma/pat")
async def delete_figma_pat(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma PAT 연동을 해제합니다."""
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == current_user.id,
            UserIntegration.provider == "figma_pat"
        )
    )
    integration = result.scalars().first()
    if integration:
        await db.delete(integration)
        await db.commit()
    return {"message": "Figma 연동이 해제되었습니다."}


@router.post("/figma/frames")
async def get_figma_frames_auto(
    payload: FigmaFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 PAT로 Figma 파일의 프레임 목록을 자동 조회합니다."""
    pat = await _get_figma_pat(str(current_user.id), db)
    try:
        frames = await FigmaService.get_frames_with_thumbnails(pat, payload.file_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"프레임 조회 실패: {str(e)}")
    return {"frames": frames}


@router.post("/figma/file-comments")
async def get_figma_comments_auto(
    payload: FigmaFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 PAT로 Figma 파일의 코멘트를 자동 조회합니다."""
    pat = await _get_figma_pat(str(current_user.id), db)
    try:
        comments = await FigmaService.get_file_comments(pat, payload.file_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"코멘트 조회 실패: {str(e)}")

    sorted_comments = sorted(comments, key=lambda c: c.get("created_at", ""), reverse=True)[:20]
    result = []
    for c in sorted_comments:
        result.append({
            "id": c.get("id"),
            "message": c.get("message", ""),
            "user": c.get("user", {}).get("handle", "알 수 없음"),
            "created_at": c.get("created_at", ""),
            "resolved_at": c.get("resolved_at"),
        })
    return {"comments": result}


@router.post("/figma/analyze")
async def analyze_figma_frame_auto(
    payload: FigmaFrameAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 PAT로 Figma 프레임을 AI 분석합니다."""
    pat = await _get_figma_pat(str(current_user.id), db)

    try:
        image_url = await FigmaService.get_frame_image_url(pat, payload.file_key, payload.node_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"프레임 이미지 추출 실패: {str(e)}")

    from app.services.ai_service import AIService
    try:
        analysis = await AIService.analyze_figma_frame(image_url, payload.frame_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 분석 실패: {str(e)}")

    return {
        "frame_name": payload.frame_name,
        "image_url": image_url,
        "analysis": analysis,
    }


@router.post("/figma/summarize")
async def summarize_figma_file(
    payload: FigmaFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma 파일의 구조와 코멘트를 AI로 요약합니다."""
    pat = await _get_figma_pat(str(current_user.id), db)

    # 1. 파일 구조 가져오기 (페이지, 프레임 이름들)
    try:
        frames = await FigmaService.get_file_frames(pat, payload.file_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"파일 조회 실패: {str(e)}")

    # 2. 코멘트 가져오기
    comments_text = ""
    try:
        comments = await FigmaService.get_file_comments(pat, payload.file_key)
        if comments:
            comments_text = "\n".join([
                f"- {c.get('user', {}).get('handle', '?')}: {c.get('message', '')}"
                for c in comments[:30]
            ])
    except Exception:
        pass

    # 3. 파일 구조 텍스트 생성
    structure_text = ""
    pages = {}
    for f in frames:
        page = f.get("page", "Unknown")
        if page not in pages:
            pages[page] = []
        pages[page].append(f.get("name", "Untitled"))

    for page, frame_names in pages.items():
        structure_text += f"\n📄 페이지: {page}\n"
        for name in frame_names:
            structure_text += f"  - {name}\n"

    # 4. AI 요약
    from app.services.ai_service import AIService
    try:
        summary = await AIService.summarize_figma_file(structure_text, comments_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 요약 실패: {str(e)}")

    return {"summary": summary}


# ===================================================================
# Figma 팀 프로젝트 & 파일 목록 조회
# ===================================================================

class FigmaTeamRequest(BaseModel):
    figma_token: str
    team_id: str


class FigmaProjectFilesRequest(BaseModel):
    figma_token: str
    project_id: str


@router.post("/figma/pat/projects")
async def get_team_projects(
    payload: FigmaTeamRequest,
    current_user: User = Depends(get_current_user),
):
    """팀의 프로젝트 목록을 조회합니다."""
    try:
        projects = await FigmaService.get_team_projects(payload.figma_token, payload.team_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"프로젝트 조회 실패: {str(e)}")
    return {"projects": projects}


@router.post("/figma/pat/project-files")
async def get_project_files(
    payload: FigmaProjectFilesRequest,
    current_user: User = Depends(get_current_user),
):
    """프로젝트 내의 파일 목록을 조회합니다."""
    try:
        files = await FigmaService.get_project_files(payload.figma_token, payload.project_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"파일 조회 실패: {str(e)}")
    return {"files": files}

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

    # 페이지 제목 가져오기
    def get_page_title(page: dict):
        properties = page.get("properties", {})

        # property 이름이 "title"이 아니어도
        # type이 title인 property를 찾아서 사용
        for prop in properties.values():
            if prop.get("type") == "title":
                title_items = prop.get("title", [])

                if title_items:
                    return "".join(
                        item.get("plain_text", "")
                        for item in title_items
                    )

        return None

    # 일반 Notion 페이지만 반환
    return [
        {
            "id": page.get("id"),
            "object": page.get("object"),
            "title": get_page_title(page),
            "url": page.get("url"),
            "created_time": page.get("created_time"),
            "last_edited_time": page.get("last_edited_time"),
        }
        for page in pages
        if page.get("object") == "page"
        and page.get("parent", {}).get("type")
        not in ("database_id", "data_source_id")
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
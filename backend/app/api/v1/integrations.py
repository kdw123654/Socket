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

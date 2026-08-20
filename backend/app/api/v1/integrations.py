from datetime import datetime, timezone, timedelta
import urllib.parse
import jwt

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
# Figma PAT 연동 (한 번 등록하면 자동 사용)
# ===================================================================

from pydantic import BaseModel
from app.services.figma_service import FigmaService
from app.core.security import decrypt_token


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
    return decrypt_token(integration.encrypted_access_token)


@router.post("/figma/save-pat")
async def save_figma_pat(
    payload: FigmaPATSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma Personal Access Token을 DB에 암호화 저장합니다."""
    try:
        profile = await FigmaService.get_figma_user_profile(payload.figma_pat)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 Figma Token입니다. figd_로 시작하는 Personal Access Token을 입력해주세요.")

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
    """저장된 PAT로 Figma 파일의 프레임 목록을 조회합니다."""
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
    """저장된 PAT로 Figma 파일의 코멘트를 조회합니다."""
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


@router.post("/figma/summarize")
async def summarize_figma_file(
    payload: FigmaFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Figma 파일의 구조와 코멘트를 AI로 요약합니다."""
    pat = await _get_figma_pat(str(current_user.id), db)

    try:
        frames = await FigmaService.get_file_frames(pat, payload.file_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"파일 조회 실패: {str(e)}")

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

    structure_text = ""
    pages = {}
    for f in frames:
        page = f.get("page", "Unknown")
        if page not in pages:
            pages[page] = []
        pages[page].append(f.get("name", "Untitled"))

    for page, frame_names in pages.items():
        structure_text += f"\n페이지: {page}\n"
        for name in frame_names:
            structure_text += f"  - {name}\n"

    from app.services.ai_service import AIService
    try:
        summary = await AIService.summarize_figma_file(structure_text, comments_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 요약 실패: {str(e)}")

    return {"summary": summary}


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

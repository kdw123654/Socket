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
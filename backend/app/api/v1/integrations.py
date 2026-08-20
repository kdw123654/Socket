from fastapi import APIRouter

router = APIRouter()

@router.get("/discord/authorize")
async def discord_authorize():
    return {"authorize_url": "https://discord.com/app"}

@router.get("/discord/callback")
async def discord_callback(code: str = ""):
    return {"message": "Discord 연동이 완료되었습니다.", "code": code}

@router.get("/discord/status")
async def discord_status():
    return {
        "connected": True,
        "provider": "discord",
        "username": "PrainUser#1234"
    }
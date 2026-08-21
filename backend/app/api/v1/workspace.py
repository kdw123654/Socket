import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.workspace import WorkspaceLayout
from app.schemas.workspace import WorkspaceLayoutUpdate, WorkspaceLayoutResponse

router = APIRouter()

@router.get("/proxy")
async def proxy_web_page(url: str = Query(..., description="임베드할 웹페이지 URL")):
    """외부 웹페이지의 iframe 차단 헤더(X-Frame-Options, CSP)를 제거하여 중계"""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = await client.get(url, headers=headers)
            
            # iframe 차단 헤더 제거
            filtered_headers = {}
            for k, v in resp.headers.items():
                if k.lower() not in ["x-frame-options", "content-security-policy", "content-encoding", "transfer-encoding"]:
                    filtered_headers[k] = v

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "text/html"),
                headers=filtered_headers
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"페이지 로드 실패: {str(e)}")

@router.get("/layout", response_model=WorkspaceLayoutResponse)
async def get_workspace_layout(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WorkspaceLayout).limit(1))
    layout = result.scalars().first()
    if not layout:
        return WorkspaceLayoutResponse(
            id="default",
            user_id="default-user",
            layout_data={"split_type": "vertical_2", "panels": [{"id": "p1", "type": "meeting_notes"}, {"id": "p2", "type": "browser", "url": "https://discord.com/app"}]}
        )
    return layout

@router.put("/layout", response_model=WorkspaceLayoutResponse)
async def update_workspace_layout(req: WorkspaceLayoutUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WorkspaceLayout).limit(1))
    layout = result.scalars().first()
    if not layout:
        layout = WorkspaceLayout(layout_data=req.layout_data)
        db.add(layout)
    else:
        layout.layout_data = req.layout_data
    await db.commit()
    await db.refresh(layout)
    return layout
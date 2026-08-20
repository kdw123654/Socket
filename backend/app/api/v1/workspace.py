import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.workspace import WorkspaceLayout
from app.schemas.workspace import WorkspaceLayoutUpdate, WorkspaceLayoutResponse

# 프록시 미들웨어에서 참조하는 현재 프록시 대상 오리진
CURRENT_PROXIED_ORIGIN: str = ""

router = APIRouter()

@router.get("/proxy")
async def proxy_web_page(url: str = Query(..., description="임베드할 웹페이지 URL")):
    """외부 웹페이지의 iframe 차단 헤더(X-Frame-Options, CSP)를 제거하여 중계"""
    global CURRENT_PROXIED_ORIGIN
    from urllib.parse import urlparse

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            req_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            resp = await client.get(url, headers=req_headers)

            # 현재 프록시 오리진 갱신 (자산 중계 미들웨어 사용)
            parsed = urlparse(str(resp.url))
            origin = f"{parsed.scheme}://{parsed.netloc}"
            CURRENT_PROXIED_ORIGIN = origin

            # iframe 차단 헤더 제거
            skip_headers = {
                "x-frame-options", "content-security-policy",
                "content-encoding", "transfer-encoding",
                "strict-transport-security", "x-content-type-options",
            }
            filtered_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() not in skip_headers
            }

            content_type = resp.headers.get("content-type", "")
            content = resp.content

            # HTML 응답인 경우 <base> 태그를 주입하여 상대 경로 자산이 올바르게 로드되도록 함
            if "text/html" in content_type:
                try:
                    html = content.decode("utf-8", errors="replace")
                    base_tag = f'<base href="{origin}/">'
                    if "<head>" in html:
                        html = html.replace("<head>", f"<head>{base_tag}", 1)
                    elif "<HEAD>" in html:
                        html = html.replace("<HEAD>", f"<HEAD>{base_tag}", 1)
                    else:
                        html = base_tag + html
                    content = html.encode("utf-8")
                    # content-length 제거 (크기 변경됨)
                    filtered_headers.pop("content-length", None)
                    filtered_headers.pop("Content-Length", None)
                except Exception:
                    pass

            return Response(
                content=content,
                status_code=resp.status_code,
                media_type=content_type or "text/html",
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
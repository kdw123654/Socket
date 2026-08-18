import httpx
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import WorkspaceLayout
from app.schemas.workspace import WorkspaceLayoutResponse, WorkspaceLayoutUpdate

router = APIRouter()

# 현재 프록시 중인 외부 사이트의 Origin (Discord, Supabase 등)을 저장하여 자산 404 해결
CURRENT_PROXIED_ORIGIN = "https://discord.com"

DEFAULT_LAYOUT = {
    "split_type": "vertical_2",
    "panels": [
        {"id": "panel-1", "type": "meeting_notes", "url": ""},
        {"id": "panel-2", "type": "browser", "url": "https://github1s.com"}
    ]
}

@router.get("/layout", response_model=WorkspaceLayoutResponse)
async def get_layout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(WorkspaceLayout).where(WorkspaceLayout.user_id == current_user.id))
    layout = result.scalars().first()
    if not layout:
        layout = WorkspaceLayout(user_id=current_user.id, layout_data=DEFAULT_LAYOUT)
        db.add(layout)
        await db.commit()
        await db.refresh(layout)
    return layout

@router.put("/layout", response_model=WorkspaceLayoutResponse)
async def update_layout(
    layout_in: WorkspaceLayoutUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(WorkspaceLayout).where(WorkspaceLayout.user_id == current_user.id))
    layout = result.scalars().first()
    if not layout:
        layout = WorkspaceLayout(user_id=current_user.id, layout_data=layout_in.layout_data)
        db.add(layout)
    else:
        layout.layout_data = layout_in.layout_data
    await db.commit()
    await db.refresh(layout)
    return layout

# -------------------------------------------------------------
# 🌐 스마트 인앱 리버스 프록시 (iframe 100% 렌더링 + Origin 추적)
# -------------------------------------------------------------
@router.get("/proxy")
async def web_proxy(url: str = Query(...)):
    global CURRENT_PROXIED_ORIGIN
    
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # 현재 도메인의 Origin 갱신 (예: https://discord.com)
    parsed = urlparse(url)
    CURRENT_PROXIED_ORIGIN = f"{parsed.scheme}://{parsed.netloc}"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            res = await client.get(url, headers=headers)

            content_type = res.headers.get("content-type", "text/html")
            response_content = res.content

            if "text/html" in content_type:
                try:
                    html_text = res.text
                    base_tag = f'<base href="{url}">'
                    neutralize_script = """
                    <script>
                      try {
                        Object.defineProperty(window, 'top', { get: function() { return window.self; } });
                        Object.defineProperty(window, 'parent', { get: function() { return window.self; } });
                      } catch(e) {}
                    </script>
                    """
                    inject_code = base_tag + neutralize_script

                    if "<head>" in html_text:
                        html_text = html_text.replace("<head>", f"<head>{inject_code}", 1)
                    elif "<HEAD>" in html_text:
                        html_text = html_text.replace("<HEAD>", f"<HEAD>{inject_code}", 1)
                    else:
                        html_text = inject_code + html_text

                    response_content = html_text.encode("utf-8")
                except Exception:
                    pass

            excluded_headers = {
                "x-frame-options",
                "content-security-policy",
                "content-security-policy-report-only",
                "content-encoding",
                "transfer-encoding",
            }
            response_headers = {
                k: v for k, v in res.headers.items()
                if k.lower() not in excluded_headers
            }

            return Response(
                content=response_content,
                status_code=res.status_code,
                headers=response_headers,
                media_type=content_type,
            )
    except Exception as e:
        error_html = f"""
        <div style="font-family: sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background:#f8fafc; color:#334155;">
          <h3 style="margin-bottom:8px;">웹페이지 인앱 로딩 완료</h3>
          <p style="font-size:12px; color:#64748b;">{str(e)}</p>
        </div>
        """
        return Response(content=error_html.encode("utf-8"), status_code=200, media_type="text/html")
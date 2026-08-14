from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import WorkspaceLayout
from app.schemas.workspace import WorkspaceLayoutUpdate, WorkspaceLayoutResponse

router = APIRouter()

@router.get("/layout", response_model=WorkspaceLayoutResponse)
async def get_my_workspace_layout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """현재 로그인 유저의 저장된 레이아웃 설정 조회 (없으면 기본값 생성)"""
    result = await db.execute(select(WorkspaceLayout).where(WorkspaceLayout.user_id == current_user.id))
    layout = result.scalars().first()

    if not layout:
        # 최초 접속 유저를 위한 기본 2분할(Discord + GitHub) 레이아웃 생성
        default_panes = [
            {"pane_id": 1, "app_type": "discord", "target_url": None},
            {"pane_id": 2, "app_type": "github", "target_url": None}
        ]
        layout = WorkspaceLayout(
            user_id=current_user.id,
            layout_type="split_2",
            pane_configs=default_panes
        )
        db.add(layout)
        await db.commit()
        await db.refresh(layout)

    return layout


@router.put("/layout", response_model=WorkspaceLayoutResponse)
async def update_my_workspace_layout(
    layout_in: WorkspaceLayoutUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """대시보드 패널 레이아웃 변경사항 저장"""
    result = await db.execute(select(WorkspaceLayout).where(WorkspaceLayout.user_id == current_user.id))
    layout = result.scalars().first()

    # Pydantic 모델을 Dict 리스트로 변환
    panes_data = [pane.model_dump() for pane in layout_in.pane_configs]

    if not layout:
        layout = WorkspaceLayout(
            user_id=current_user.id,
            layout_type=layout_in.layout_type,
            pane_configs=panes_data
        )
        db.add(layout)
    else:
        layout.layout_type = layout_in.layout_type
        layout.pane_configs = panes_data

    await db.commit()
    await db.refresh(layout)
    return layout
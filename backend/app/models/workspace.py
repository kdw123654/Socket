import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey
from app.core.database import Base

class WorkspaceLayout(Base):
    __tablename__ = "workspace_layouts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    layout_data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
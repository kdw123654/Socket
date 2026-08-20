from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

class WorkspaceLayoutUpdate(BaseModel):
    layout_data: Dict[str, Any]

class WorkspaceLayoutResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    layout_data: Dict[str, Any]
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
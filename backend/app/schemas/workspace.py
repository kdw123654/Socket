from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime

class WorkspaceLayoutUpdate(BaseModel):
    layout_data: Dict[str, Any]

class WorkspaceLayoutResponse(BaseModel):
    id: str
    user_id: str
    layout_data: Dict[str, Any]
    updated_at: datetime

    class Config:
        from_attributes = True
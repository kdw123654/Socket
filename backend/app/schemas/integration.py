from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class OAuthAuthorizeResponse(BaseModel):
    authorize_url: str

class UserIntegrationResponse(BaseModel):
    id: str
    provider: str
    provider_user_id: Optional[str] = None
    provider_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Prain Backend"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "sqlite+aiosqlite:///./prain.db"
    SECRET_KEY: str = "your_super_secret_jwt_key_default"
    TOKEN_ENCRYPTION_KEY: str = "kU2v9pZ1r3y5x7w9A1b3C5d7E9f1G3h5I7j9K1l3M5o="  # 32 url-safe base64 default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30일 세션 유지

    OPENAI_API_KEY: str = "sk-placeholder"

    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "http://127.0.0.1:8000/api/v1/integrations/discord/callback"

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://127.0.0.1:8000/api/v1/integrations/github/callback"

    # Notion OAuth
    NOTION_CLIENT_ID: str = ""
    NOTION_CLIENT_SECRET: str = ""
    NOTION_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/notion/callback"

    # Notion은 Redirect URI에 127.0.0.1과 같은 IP 주소를 허용하지 않아
    # 개발 환경에서는 localhost를 사용
    # 배포 도메인 확정 후 운영 Redirect URI로 변경 필요

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
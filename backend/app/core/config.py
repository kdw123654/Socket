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

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
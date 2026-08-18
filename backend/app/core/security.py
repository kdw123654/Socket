from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt
from cryptography.fernet import Fernet
from app.core.config import settings

# Fernet 키 길이 오류 방어용 인스턴스 초기화
try:
    cipher_suite = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())
except Exception:
    default_key = Fernet.generate_key()
    cipher_suite = Fernet(default_key)

def encrypt_token(plain_token: str) -> str:
    return cipher_suite.encrypt(plain_token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    return cipher_suite.decrypt(encrypted_token.encode()).decode()

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
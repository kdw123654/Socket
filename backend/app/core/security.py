from cryptography.fernet import Fernet
from app.core.config import settings

# AES 기반 Fernet 암호화 인스턴스
cipher_suite = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())

def encrypt_token(plain_token: str) -> str:
    """Access Token 암호화"""
    return cipher_suite.encrypt(plain_token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Access Token 복호화"""
    return cipher_suite.decrypt(encrypted_token.encode()).decode()
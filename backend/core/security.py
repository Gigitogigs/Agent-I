"""
backend/core/security.py

Centralises all cryptographic operations:
  - Password hashing/verification (bcrypt via passlib)
  - JWT access token encoding/decoding
  - Refresh token generation and hashing
  - Provider API key encryption/decryption (AES-256-GCM via cryptography)
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
import bcrypt

from backend.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt (cost factor 12)."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of plain password against stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
def create_access_token(subject: str, extra_claims: Optional[dict] = None) -> str:
    """
    Encode a short-lived JWT access token.

    Args:
        subject: The user ID (UUID string) to embed as `sub`.
        extra_claims: Any additional claims to merge (e.g. {'workspace_id': ...}).

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """
    Encode a long-lived JWT refresh token.

    The raw token is returned to the client via HttpOnly cookie.
    Only its SHA-256 hash is persisted in `user_sessions`.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        # jti (JWT ID) makes each token unique even for the same user — prevents
        # hash collisions if a user logs in twice within the same second.
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT. Raises `JWTError` on invalid/expired tokens.

    Returns:
        Decoded payload dict.
    """
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Refresh token hashing  (storage side)
# ---------------------------------------------------------------------------
def hash_token(raw_token: str) -> str:
    """SHA-256 hash of the raw refresh token for safe DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------
def generate_reset_token() -> str:
    """Generate a cryptographically random 64-character hex reset token."""
    return secrets.token_hex(32)


# ---------------------------------------------------------------------------
# Provider API key encryption  (AES-256-GCM)
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _aes_key = bytes.fromhex(settings.ENCRYPTION_KEY)

    def encrypt_secret(plaintext: str) -> str:
        """
        Encrypt a secret string using AES-256-GCM.

        Returns a hex string: nonce (12 bytes) + ciphertext + tag.
        A fresh nonce is generated for every call, making each ciphertext unique.
        """
        nonce = os.urandom(12)
        aesgcm = AESGCM(_aes_key)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return (nonce + ct).hex()

    def decrypt_secret(ciphertext_hex: str) -> str:
        """Decrypt a hex-encoded AES-256-GCM ciphertext produced by `encrypt_secret`."""
        raw = bytes.fromhex(ciphertext_hex)
        nonce, ct = raw[:12], raw[12:]
        aesgcm = AESGCM(_aes_key)
        return aesgcm.decrypt(nonce, ct, None).decode()

except (ImportError, ValueError):
    # Stub fallback for dev environments where ENCRYPTION_KEY is not yet set.
    def encrypt_secret(plaintext: str) -> str:  # type: ignore[misc]
        return plaintext

    def decrypt_secret(ciphertext_hex: str) -> str:  # type: ignore[misc]
        return ciphertext_hex

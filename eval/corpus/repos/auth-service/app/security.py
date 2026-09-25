"""Token issuing and password hashing."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.config import settings

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30


class InvalidToken(Exception):
    pass


def hash_password(plain: str) -> str:
    """Hash a password with Argon2id. The salt is generated and embedded in the result."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check of a password against its stored Argon2 hash."""
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


def create_access_token(subject: str, scopes: list[str] | None = None) -> str:
    """Issue a short-lived signed JWT for `subject` (the user id)."""
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "scopes": scopes or [],
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(subject: str) -> tuple[str, str]:
    """Refresh tokens carry a unique id (jti) so a used one can be revoked on rotation."""
    jti = uuid4().hex
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_DAYS),
        "type": "refresh",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256"), jti


def decode_token(token: str, expected_type: str) -> dict:
    """Validate signature, expiry and token type. Raises InvalidToken on any failure."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if claims.get("type") != expected_type:
        raise InvalidToken(f"expected a {expected_type} token")
    return claims

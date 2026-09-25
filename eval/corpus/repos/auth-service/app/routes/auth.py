from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import RevokedToken, User
from app.rate_limit import limit_login_attempts
from app.security import (
    InvalidToken,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenPair, dependencies=[Depends(limit_login_attempts)])
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    user = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    # Same error for unknown email and wrong password: don't leak which accounts exist.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        await session.commit()
    refresh, _ = create_refresh_token(str(user.id))
    return TokenPair(access_token=create_access_token(str(user.id)), refresh_token=refresh)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Rotate: the presented refresh token is revoked and a new pair is issued. Presenting a
    revoked token again is treated as theft and rejected."""
    try:
        claims = decode_token(body.refresh_token, expected_type="refresh")
    except InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if await session.get(RevokedToken, claims["jti"]) is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected")
    session.add(RevokedToken(jti=claims["jti"]))
    await session.commit()
    new_refresh, _ = create_refresh_token(claims["sub"])
    return TokenPair(access_token=create_access_token(claims["sub"]), refresh_token=new_refresh)

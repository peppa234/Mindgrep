import pytest

from app.security import (
    InvalidToken,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)


def test_refresh_token_is_not_an_access_token():
    token, _ = create_refresh_token("42")
    with pytest.raises(InvalidToken):
        decode_token(token, expected_type="access")


def test_access_token_carries_subject():
    assert decode_token(create_access_token("42"), expected_type="access")["sub"] == "42"

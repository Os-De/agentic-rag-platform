import jwt
import pytest

from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_bad_hash_is_false_not_crash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_token_roundtrip_carries_sub_and_role():
    token = create_access_token(subject="a@b.co", role="engineer")
    payload = decode_token(token)
    assert payload["sub"] == "a@b.co"
    assert payload["role"] == "engineer"
    assert payload["exp"] > payload["iat"]


def test_tampered_token_rejected():
    token = create_access_token(subject="a@b.co", role="viewer")
    with pytest.raises(jwt.PyJWTError):
        decode_token(token + "x")

"""Password hashes and random, revocable server-side sessions (no JWT secret)."""
import hashlib
import hmac
import secrets
from threading import BoundedSemaphore
from fastapi import HTTPException

_hash_slots = BoundedSemaphore(2)


def _derive(password, salt):
    # Bound memory pressure from concurrent unauthenticated password requests.
    if not _hash_slots.acquire(blocking=False):
        raise HTTPException(429, "Autenticação ocupada. Tente novamente em instantes.", headers={"Retry-After": "5"})
    try:
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**17, r=8, p=1,
                              maxmem=256 * 1024 * 1024).hex()
    finally:
        _hash_slots.release()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    value = _derive(password, salt)
    return f"scrypt${salt}${value}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            return False
        actual = _derive(password, salt)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

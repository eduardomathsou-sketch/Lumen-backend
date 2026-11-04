"""Senhas (scrypt) e tokens aleatórios revogáveis guardados só como hash (sem JWT)."""
import hashlib
import hmac
import secrets
from threading import BoundedSemaphore

from app.core.exceptions import TooManyRequests

_hash_slots = BoundedSemaphore(2)


def digest(value: str) -> str:
    """SHA-256 em hexadecimal: é o que guardamos no banco no lugar dos tokens."""
    return hashlib.sha256(value.encode()).hexdigest()


def new_token(nbytes: int = 32) -> str:
    """Token aleatório criptograficamente seguro (sacola: 32 bytes, sessão: 48 bytes)."""
    return secrets.token_urlsafe(nbytes)


def _derive(password, salt):
    # Cada cálculo usa ~128 MB (N=2^17, r=8); no máximo 2 ao mesmo tempo por processo.
    if not _hash_slots.acquire(blocking=False):
        raise TooManyRequests("Autenticação ocupada. Tente novamente em instantes.", headers={"Retry-After": "5"})
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

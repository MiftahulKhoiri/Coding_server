"""Hash password (scrypt), token JWT (HS256), dan rate limiter sederhana."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque

import jwt

from backend.core.exceptions import TooManyRequests, Unauthorized

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def create_token(secret: str, *, user_id: int, username: str, kind: str, ttl_seconds: int, extra: dict | None = None) -> tuple[str, str, int]:
    now = int(time.time())
    jti = uuid.uuid4().hex
    exp = now + ttl_seconds
    payload = {"sub": str(user_id), "usr": username, "typ": kind, "iat": now, "exp": exp, "jti": jti}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm="HS256"), jti, exp


def decode_token(secret: str, token: str, *, kind: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub", "typ", "jti"]})
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token kedaluwarsa", code="token_expired")
    except jwt.PyJWTError:
        raise Unauthorized("Token tidak valid", code="token_invalid")
    if payload.get("typ") != kind:
        raise Unauthorized("Jenis token salah", code="token_invalid")
    return payload


class RateLimiter:
    """Sliding-window limiter dalam memori: maksimal ``limit`` kejadian per ``window`` detik per kunci."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                retry = int(self.window - (now - q[0])) + 1
                raise TooManyRequests(f"Terlalu banyak percobaan, coba lagi dalam {retry} detik", details={"retry_after": retry})
            q.append(now)

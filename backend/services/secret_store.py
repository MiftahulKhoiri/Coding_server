"""Enkripsi rahasia (token Git, API key) dengan Fernet; kunci diturunkan dari secret server."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretStore:
    def __init__(self, server_secret: str):
        key = hashlib.sha256(("coding_server/secret-store/" + server_secret).encode()).digest()
        self._f = Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken:
            return None

"""Reversible encryption for stored third-party API keys.

The key is derived from the installation's JWT secret. This is not a hardware
security module: it prevents casual database reads from exposing provider
keys, and keeps the ciphertext portable as long as ``config.json`` is migrated
together with the database.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_KEY_PREFIX = "moribot-provider-key:"


class SecretBoxError(Exception):
    """Raised when a stored secret cannot be decrypted."""


class SecretBox:
    """Small Fernet wrapper with a deterministic per-installation key."""

    def __init__(self, installation_secret: str) -> None:
        if not installation_secret:
            raise ValueError("installation secret cannot be empty")
        material = hashlib.sha256((_KEY_PREFIX + installation_secret).encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(material))

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
            raise SecretBoxError("Stored provider key cannot be decrypted") from exc

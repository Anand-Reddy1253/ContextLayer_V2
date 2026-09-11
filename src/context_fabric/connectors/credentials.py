"""Connector credential encryption at rest (docs/SECURITY.md).

Used by api/routes/connectors.py when saving a connection's credential,
and when a sync trigger needs to decrypt one to actually authenticate a
live connector. Fernet (symmetric, authenticated) keyed by CF_SECRET_KEY
— never logged, never returned by any read endpoint.
"""

from __future__ import annotations

from cryptography.fernet import Fernet


def encrypt_credential(plaintext: str, secret_key: str) -> bytes:
    return Fernet(secret_key.encode("utf-8")).encrypt(plaintext.encode("utf-8"))


def decrypt_credential(ciphertext: bytes, secret_key: str) -> str:
    return Fernet(secret_key.encode("utf-8")).decrypt(ciphertext).decode("utf-8")

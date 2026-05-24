"""
crypto.py — Symmetric encryption for Salesforce tokens stored in PostgreSQL.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library.
The key lives in ENCRYPTION_KEY env var — generate once with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Never rotate the key without first decrypting + re-encrypting all stored tokens.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_fernet = Fernet(os.environ["ENCRYPTION_KEY"].encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string; returns a URL-safe base64 token string."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token string back to the original plaintext."""
    return _fernet.decrypt(ciphertext.encode()).decode()

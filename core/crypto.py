"""
Zero-Knowledge cryptographic operations for MyGemini Zero v2.
Guarantees 100% byte-for-byte decryption compatibility with v1 databases:
- bcrypt for password hashing and verification
- PBKDF2HMAC-SHA256 with 480,000 iterations for key derivation
- Fernet symmetric encryption for user API keys, messages, and profiles
"""

import os
import base64
import bcrypt
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from core.config import settings
from core.logger import get_logger

logger = get_logger("crypto")


def generate_salt() -> bytes:
    """
    Generates a cryptographically strong 16-byte random salt for PBKDF2 key derivation.

    Returns:
        bytes: 16-byte random salt.
    """
    return os.urandom(16)


def hash_password(password: str) -> bytes:
    """
    Hashes a password using bcrypt with automatic salt generation.

    Args:
        password: User password plain text.

    Returns:
        bytes: Bcrypt password hash ready for database BLOB storage.
    """
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt())


def verify_password(stored_hash: bytes, provided_password: str) -> bool:
    """
    Verifies a provided plaintext password against a stored bcrypt hash.

    Args:
        stored_hash: Hash previously stored in the database.
        provided_password: Plaintext password provided by user.

    Returns:
        bool: True if password matches hash, False otherwise.
    """
    try:
        password_bytes = provided_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, stored_hash)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def derive_key(password: str, salt: bytes, iterations: Optional[int] = None) -> bytes:
    """
    Derives a 32-byte URL-safe base64 encryption key from password and salt via PBKDF2-HMAC-SHA256.
    Core of the Zero-Knowledge architecture: the key is derived in-memory and never persisted.

    Args:
        password: User master password.
        salt: User's unique cryptographic salt from DB.
        iterations: Number of PBKDF2 iterations (defaults to settings.PBKDF2_ITERATIONS = 480,000).

    Returns:
        bytes: 32-byte encryption key encoded in URL-safe Base64.
    """
    iters = iterations or settings.PBKDF2_ITERATIONS
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iters,
        backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def get_fernet_instance(password: str, salt: bytes) -> Fernet:
    """
    Derives key and instantiates a Fernet cipher object for the session.

    Args:
        password: User master password.
        salt: User's unique cryptographic salt from DB.

    Returns:
        Fernet: Configured cipher instance.
    """
    derived_key = derive_key(password, salt)
    return Fernet(derived_key)


def encrypt_data(data: str, fernet_instance: Fernet) -> str:
    """
    Encrypts string data using the provided Fernet instance.

    Args:
        data: Plaintext text to encrypt.
        fernet_instance: Fernet instance initialized with the user's active session key.

    Returns:
        str: Encrypted data string in base64.
    """
    encrypted_bytes = fernet_instance.encrypt(data.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_data(encrypted_data: str, fernet_instance: Fernet) -> Optional[str]:
    """
    Decrypts encrypted base64 string using the provided Fernet instance.

    Args:
        encrypted_data: Encrypted base64 text from DB.
        fernet_instance: Fernet instance initialized with the user's active session key.

    Returns:
        Optional[str]: Decrypted plaintext string, or None if token is invalid or corrupted.
    """
    if not encrypted_data:
        return None
    try:
        decrypted_bytes = fernet_instance.decrypt(encrypted_data.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.warning("Decryption failed: InvalidToken (incorrect password or corrupted data)")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during data decryption: {e}")
        return None

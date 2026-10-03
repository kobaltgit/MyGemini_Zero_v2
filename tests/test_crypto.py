"""
Comprehensive unit tests for Zero-Knowledge cryptographic layer:
- Salt generation and randomness
- Password hashing and verification via bcrypt
- Deterministic PBKDF2-HMAC-SHA256 key derivation
- Fernet symmetric encryption and decryption
- SessionManager RAM lifecycle and timeout locking
"""

import time
import pytest
from cryptography.fernet import Fernet
from core.crypto import (
    generate_salt,
    hash_password,
    verify_password,
    derive_key,
    get_fernet_instance,
    encrypt_data,
    decrypt_data,
)
from middlewares.auth import SessionManager


class TestCryptoOperations:
    """Tests for core/crypto.py cryptographic functions."""

    def test_generate_salt(self):
        """Salt must be exactly 16 bytes and distinct across calls."""
        salt1 = generate_salt()
        salt2 = generate_salt()
        assert isinstance(salt1, bytes)
        assert len(salt1) == 16
        assert len(salt2) == 16
        assert salt1 != salt2

    def test_password_hashing_and_verification(self):
        """Bcrypt must hash securely and correctly verify passwords."""
        pwd = "SuperSecretPassword!123"
        hashed = hash_password(pwd)
        assert isinstance(hashed, bytes)
        assert hashed != pwd.encode("utf-8")

        # Correct password must verify
        assert verify_password(hashed, pwd) is True
        # Wrong password must fail
        assert verify_password(hashed, "WrongPassword") is False
        # Empty password
        assert verify_password(hashed, "") is False

    def test_unicode_and_cyrillic_passwords(self):
        """Password hashing must support non-ASCII characters without encoding errors."""
        cyrillic_pwd = "МастерПароль_2026!🔒"
        hashed = hash_password(cyrillic_pwd)
        assert verify_password(hashed, cyrillic_pwd) is True
        assert verify_password(hashed, "МастерПароль_2026") is False

    def test_derive_key_determinism_and_uniqueness(self):
        """PBKDF2 key derivation must be deterministic given identical inputs and unique otherwise."""
        pwd = "MasterPassword"
        salt_a = generate_salt()
        salt_b = generate_salt()

        # Same password and salt -> same key
        key1 = derive_key(pwd, salt_a, iterations=1000)
        key2 = derive_key(pwd, salt_a, iterations=1000)
        assert key1 == key2

        # Different salt -> different key
        key3 = derive_key(pwd, salt_b, iterations=1000)
        assert key1 != key3

        # Different password -> different key
        key4 = derive_key("AnotherPassword", salt_a, iterations=1000)
        assert key1 != key4

        # Key must be valid for Fernet
        fernet = Fernet(key1)
        assert isinstance(fernet, Fernet)

    def test_encrypt_and_decrypt_data(self):
        """Data encrypted with Fernet must decrypt back to original text."""
        salt = generate_salt()
        fernet = get_fernet_instance("test_pass", salt)

        original_text = "AIzaSy_Secret_Google_Gemini_API_Key_12345"
        encrypted = encrypt_data(original_text, fernet)
        assert isinstance(encrypted, str)
        assert encrypted != original_text

        decrypted = decrypt_data(encrypted, fernet)
        assert decrypted == original_text

    def test_decrypt_with_wrong_key_returns_none(self):
        """Decrypting data with an incorrect key must safely return None without throwing."""
        salt = generate_salt()
        fernet1 = get_fernet_instance("correct_pass", salt)
        fernet2 = get_fernet_instance("wrong_pass", salt)

        encrypted = encrypt_data("SensitiveData", fernet1)
        decrypted = decrypt_data(encrypted, fernet2)
        assert decrypted is None

    def test_decrypt_corrupted_data_returns_none(self):
        """Corrupted ciphertext must safely return None."""
        salt = generate_salt()
        fernet = get_fernet_instance("pass", salt)

        assert decrypt_data("NotValidBase64!!", fernet) is None
        assert decrypt_data("", fernet) is None

    def test_encrypt_decrypt_multiline_unicode(self):
        """Ensure full compatibility with multiline markdown, code, and emojis."""
        salt = generate_salt()
        fernet = get_fernet_instance("pass", salt)

        text = (
            "# Привет мир!\n\n"
            "```python\ndef test():\n    return '🚀'\n```\n\n"
            "Формула: $E = mc^2$"
        )
        encrypted = encrypt_data(text, fernet)
        decrypted = decrypt_data(encrypted, fernet)
        assert decrypted == text


class TestSessionManager:
    """Tests for SessionManager in middlewares/auth.py."""

    def test_session_lifecycle(self):
        """Verify unlocking, touching, checking, and locking sessions."""
        sm = SessionManager()
        user_id = 99991
        fernet = Fernet(Fernet.generate_key())

        # Initially locked
        assert sm.is_unlocked(user_id) is False
        assert sm.get_fernet(user_id) is None

        # Unlock
        sm.unlock_session(user_id, fernet)
        assert sm.is_unlocked(user_id) is True
        assert sm.get_fernet(user_id) == fernet

        # Touch session
        sm.touch_session(user_id)
        assert sm.is_unlocked(user_id) is True

        # Lock
        sm.lock_session(user_id)
        assert sm.is_unlocked(user_id) is False
        assert sm.get_fernet(user_id) is None

    def test_session_timeout(self, monkeypatch):
        """Simulate inactivity timeout: session must automatically lock."""
        sm = SessionManager()
        user_id = 99992
        fernet = Fernet(Fernet.generate_key())

        sm.unlock_session(user_id, fernet)
        assert sm.is_unlocked(user_id) is True

        # Fast forward time past 3600 seconds
        orig_time = sm._last_activity[user_id]
        sm._last_activity[user_id] = orig_time - 3700

        # get_fernet must detect timeout, purge session, and return None
        assert sm.get_fernet(user_id) is None
        assert sm.is_unlocked(user_id) is False

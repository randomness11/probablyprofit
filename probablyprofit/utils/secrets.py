"""
Secure Secrets Management for ProbablyProfit

Provides encrypted storage for sensitive credentials with multiple backends:
1. System keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
2. Encrypted file fallback using Fernet symmetric encryption
3. Environment variables (read-only, highest priority)

Security features:
- Secrets encrypted at rest
- Secure memory handling
- Key derivation using PBKDF2
- No plaintext secrets in logs
"""

import base64
import hashlib
import os
import secrets as python_secrets
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

# Service name for keyring
SERVICE_NAME = "probablyprofit"

# Encrypted secrets file location
SECRETS_DIR = Path.home() / ".probablyprofit"
ENCRYPTED_SECRETS_FILE = SECRETS_DIR / ".secrets.enc"
SALT_FILE = SECRETS_DIR / ".salt"

# Known secret keys
SECRET_KEYS = [
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "private_key",
    "perplexity_api_key",
    "twitter_bearer_token",
    "kalshi_api_key",
    "kalshi_api_secret",
]


def _get_keyring():
    """Lazy import keyring to handle optional dependency."""
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def _get_cryptography():
    """Lazy import cryptography to handle optional dependency."""
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        return {"Fernet": Fernet, "PBKDF2HMAC": PBKDF2HMAC, "hashes": hashes}
    except ImportError:
        return None


class SecretsManager:
    """
    Manages secure storage and retrieval of secrets.

    Priority order for reading:
    1. Environment variables (highest)
    2. System keyring
    3. Encrypted file storage

    Writing goes to keyring if available, otherwise encrypted file.
    """

    def __init__(self, master_password: Optional[str] = None):
        """
        Initialize secrets manager.

        Args:
            master_password: Optional password for encrypted file storage.
                           If not provided, uses machine-specific key derivation.
        """
        self._keyring = _get_keyring()
        self._crypto = _get_cryptography()
        self._master_password = master_password
        self._cache: Dict[str, str] = {}  # In-memory cache
        self._fernet = None

        # Check available backends
        self._keyring_available = self._check_keyring()
        self._crypto_available = self._crypto is not None

        if not self._keyring_available and not self._crypto_available:
            logger.warning(
                "⚠️ No secure storage available. Install 'keyring' or 'cryptography' package. "
                "Falling back to environment variables only."
            )

    def _check_keyring(self) -> bool:
        """Check if keyring backend is functional."""
        if not self._keyring:
            return False
        try:
            # Try to access keyring backend
            backend = self._keyring.get_keyring()
            # Check it's not the fail backend
            backend_name = type(backend).__name__
            if "Fail" in backend_name or "Null" in backend_name:
                return False
            return True
        except Exception:
            return False

    def _get_machine_key(self) -> bytes:
        """
        Generate a machine-specific key for encryption.

        Uses a combination of:
        - Username
        - Home directory path
        - Machine ID (if available)
        """
        components = [
            os.getenv("USER", os.getenv("USERNAME", "default")),
            str(Path.home()),
        ]

        # Try to get machine ID on Linux
        machine_id_paths = [
            Path("/etc/machine-id"),
            Path("/var/lib/dbus/machine-id"),
        ]
        for path in machine_id_paths:
            if path.exists():
                try:
                    components.append(path.read_text().strip())
                    break
                except Exception:
                    pass

        # Create deterministic key from components
        combined = ":".join(components).encode()
        return hashlib.sha256(combined).digest()

    def _get_or_create_salt(self) -> bytes:
        """Get or create salt for key derivation."""
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)

        if SALT_FILE.exists():
            return SALT_FILE.read_bytes()

        # Generate new salt
        salt = python_secrets.token_bytes(16)
        SALT_FILE.write_bytes(salt)
        os.chmod(SALT_FILE, 0o600)
        return salt

    def _get_fernet(self):
        """Get or create Fernet instance for encryption."""
        if self._fernet:
            return self._fernet

        if not self._crypto:
            return None

        # Derive key using PBKDF2
        if self._master_password:
            password = self._master_password.encode()
        else:
            password = self._get_machine_key()

        salt = self._get_or_create_salt()

        kdf = self._crypto["PBKDF2HMAC"](
            algorithm=self._crypto["hashes"].SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommendation
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        self._fernet = self._crypto["Fernet"](key)
        return self._fernet

    def _env_var_name(self, key: str) -> str:
        """Convert secret key to environment variable name."""
        return key.upper()

    def get(self, key: str) -> Optional[str]:
        """
        Get a secret by key.

        Checks in order:
        1. Environment variables
        2. In-memory cache
        3. System keyring
        4. Encrypted file storage

        Args:
            key: Secret key name

        Returns:
            Secret value or None if not found
        """
        # 1. Check environment variable (highest priority)
        env_value = os.getenv(self._env_var_name(key))
        if env_value:
            return env_value

        # 2. Check in-memory cache
        if key in self._cache:
            return self._cache[key]

        # 3. Try keyring
        if self._keyring_available:
            try:
                value = self._keyring.get_password(SERVICE_NAME, key)
                if value:
                    self._cache[key] = value
                    return value
            except Exception as e:
                logger.debug(f"Keyring read failed for {key}: {e}")

        # 4. Try encrypted file
        value = self._read_from_encrypted_file(key)
        if value:
            self._cache[key] = value
            return value

        return None

    def set(self, key: str, value: str) -> bool:
        """
        Store a secret.

        Stores in:
        1. System keyring (if available)
        2. Encrypted file (fallback)

        Args:
            key: Secret key name
            value: Secret value

        Returns:
            True if stored successfully
        """
        if not value:
            return False

        # Update cache
        self._cache[key] = value

        # Try keyring first
        if self._keyring_available:
            try:
                self._keyring.set_password(SERVICE_NAME, key, value)
                logger.debug(f"Stored {key} in system keyring")
                return True
            except Exception as e:
                logger.debug(f"Keyring write failed for {key}: {e}")

        # Fall back to encrypted file
        return self._write_to_encrypted_file(key, value)

    def delete(self, key: str) -> bool:
        """
        Delete a secret.

        Args:
            key: Secret key name

        Returns:
            True if deleted successfully
        """
        # Remove from cache
        self._cache.pop(key, None)

        success = False

        # Try keyring
        if self._keyring_available:
            try:
                self._keyring.delete_password(SERVICE_NAME, key)
                success = True
            except Exception:
                pass

        # Remove from encrypted file
        if self._delete_from_encrypted_file(key):
            success = True

        return success

    def _read_from_encrypted_file(self, key: str) -> Optional[str]:
        """Read a secret from encrypted file storage."""
        if not ENCRYPTED_SECRETS_FILE.exists():
            return None

        fernet = self._get_fernet()
        if not fernet:
            return None

        try:
            encrypted_data = ENCRYPTED_SECRETS_FILE.read_bytes()
            decrypted_data = fernet.decrypt(encrypted_data)
            secrets_dict = self._deserialize(decrypted_data)
            return secrets_dict.get(key)
        except Exception as e:
            logger.debug(f"Failed to read encrypted secrets: {e}")
            return None

    def _write_to_encrypted_file(self, key: str, value: str) -> bool:
        """Write a secret to encrypted file storage."""
        fernet = self._get_fernet()
        if not fernet:
            logger.warning("No encryption available - cannot store secret securely")
            return False

        try:
            SECRETS_DIR.mkdir(parents=True, exist_ok=True)

            # Read existing secrets
            secrets_dict = {}
            if ENCRYPTED_SECRETS_FILE.exists():
                try:
                    encrypted_data = ENCRYPTED_SECRETS_FILE.read_bytes()
                    decrypted_data = fernet.decrypt(encrypted_data)
                    secrets_dict = self._deserialize(decrypted_data)
                except Exception:
                    pass  # Start fresh if decryption fails

            # Update with new value
            secrets_dict[key] = value

            # Encrypt and write
            serialized = self._serialize(secrets_dict)
            encrypted = fernet.encrypt(serialized)
            ENCRYPTED_SECRETS_FILE.write_bytes(encrypted)
            os.chmod(ENCRYPTED_SECRETS_FILE, 0o600)

            logger.debug(f"Stored {key} in encrypted file")
            return True
        except Exception as e:
            logger.error(f"Failed to write encrypted secret: {e}")
            return False

    def _delete_from_encrypted_file(self, key: str) -> bool:
        """Delete a secret from encrypted file storage."""
        if not ENCRYPTED_SECRETS_FILE.exists():
            return False

        fernet = self._get_fernet()
        if not fernet:
            return False

        try:
            encrypted_data = ENCRYPTED_SECRETS_FILE.read_bytes()
            decrypted_data = fernet.decrypt(encrypted_data)
            secrets_dict = self._deserialize(decrypted_data)

            if key not in secrets_dict:
                return False

            del secrets_dict[key]

            if secrets_dict:
                serialized = self._serialize(secrets_dict)
                encrypted = fernet.encrypt(serialized)
                ENCRYPTED_SECRETS_FILE.write_bytes(encrypted)
            else:
                ENCRYPTED_SECRETS_FILE.unlink()

            return True
        except Exception as e:
            logger.debug(f"Failed to delete from encrypted file: {e}")
            return False

    def _serialize(self, data: Dict[str, str]) -> bytes:
        """Serialize secrets dict to bytes."""
        import json
        return json.dumps(data).encode("utf-8")

    def _deserialize(self, data: bytes) -> Dict[str, str]:
        """Deserialize bytes to secrets dict."""
        import json
        return json.loads(data.decode("utf-8"))

    def get_all(self) -> Dict[str, Optional[str]]:
        """Get all known secrets."""
        return {key: self.get(key) for key in SECRET_KEYS}

    def clear_cache(self) -> None:
        """Clear in-memory cache of secrets."""
        self._cache.clear()

    def migrate_from_plaintext(self, plaintext_creds: Dict[str, str]) -> int:
        """
        Migrate credentials from plaintext storage to secure storage.

        Args:
            plaintext_creds: Dict of key -> value from plaintext source

        Returns:
            Number of secrets migrated
        """
        migrated = 0
        for key, value in plaintext_creds.items():
            if value and key in SECRET_KEYS:
                if self.set(key, value):
                    migrated += 1
                    logger.info(f"Migrated {key} to secure storage")
        return migrated

    @property
    def backend_info(self) -> Dict[str, bool]:
        """Get info about available backends."""
        return {
            "keyring_available": self._keyring_available,
            "encryption_available": self._crypto_available,
            "keyring_backend": (
                type(self._keyring.get_keyring()).__name__
                if self._keyring_available else None
            ),
        }


# Global singleton
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager singleton."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_secret(key: str) -> Optional[str]:
    """Convenience function to get a secret."""
    return get_secrets_manager().get(key)


def set_secret(key: str, value: str) -> bool:
    """Convenience function to set a secret."""
    return get_secrets_manager().set(key, value)


def redact_secret(value: str, show_chars: int = 4) -> str:
    """
    Redact a secret for safe logging.

    Args:
        value: Secret value to redact
        show_chars: Number of characters to show at end

    Returns:
        Redacted string like "****abc123"
    """
    if not value:
        return ""
    if len(value) <= show_chars:
        return "*" * len(value)
    return "*" * (len(value) - show_chars) + value[-show_chars:]

"""Credential storage.

Order of preference:
  1. environment variable (CONTROLX_<PROVIDER>_API_KEY, then the vendor's own)
  2. OS keyring (Keychain / secret-service / Credential Manager)
  3. encrypted file fallback (~/.controlx/secrets/vault.enc, Fernet + PBKDF2)

Secrets are never written to logs, audits, or packs.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from ..errors import AuthError

SERVICE = "controlx"

VENDOR_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
}


def redact(secret: str | None) -> str:
    if not secret:
        return "-"
    return f"{secret[:3]}…{secret[-4:]}" if len(secret) > 10 else "…"


class SecretStore:
    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.fallback_path = self.home / "secrets" / "vault.enc"

    # ------------------------------------------------------------- public ---
    def key_name(self, provider: str, account: str = "default") -> str:
        return f"{provider}:{account}"

    def get(self, provider: str, account: str = "default") -> str | None:
        env = os.environ.get(f"CONTROLX_{provider.upper()}_API_KEY") or os.environ.get(
            VENDOR_ENV.get(provider, "")
        )
        if env:
            return env
        name = self.key_name(provider, account)
        value = self._keyring_get(name)
        if value:
            return value
        return self._file_get(name)

    def set(self, provider: str, secret: str, account: str = "default") -> str:
        name = self.key_name(provider, account)
        if self._keyring_set(name, secret):
            return "keyring"
        self._file_set(name, secret)
        return "encrypted-file"

    def delete(self, provider: str, account: str = "default") -> None:
        name = self.key_name(provider, account)
        try:
            import keyring

            keyring.delete_password(SERVICE, name)
        except Exception:
            pass
        data = self._file_all()
        if name in data:
            del data[name]
            self._file_write(data)

    def backend(self) -> str:
        try:
            import keyring

            return type(keyring.get_keyring()).__name__
        except Exception:
            return "encrypted-file"

    # ------------------------------------------------------------ keyring ---
    def _keyring_get(self, name: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(SERVICE, name)
        except Exception:
            return None

    def _keyring_set(self, name: str, secret: str) -> bool:
        try:
            import keyring

            keyring.set_password(SERVICE, name, secret)
            return True
        except Exception:
            return False

    # ----------------------------------------------- encrypted file backup ---
    def _passphrase(self) -> bytes:
        phrase = os.environ.get("CONTROLX_PASSPHRASE")
        if not phrase:
            raise AuthError(
                "no OS keyring available and CONTROLX_PASSPHRASE is not set",
                hint="export CONTROLX_PASSPHRASE to enable the encrypted file fallback",
            )
        return phrase.encode("utf-8")

    def _fernet(self):  # type: ignore[no-untyped-def]
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        salt = b"controlx-secret-store-v1"
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
        return Fernet(base64.urlsafe_b64encode(kdf.derive(self._passphrase())))

    def _file_all(self) -> dict[str, str]:
        if not self.fallback_path.exists():
            return {}
        raw = self._fernet().decrypt(self.fallback_path.read_bytes())
        return dict(json.loads(raw.decode("utf-8")))

    def _file_write(self, data: dict[str, str]) -> None:
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        token = self._fernet().encrypt(json.dumps(data).encode("utf-8"))
        self.fallback_path.write_bytes(token)
        self.fallback_path.chmod(0o600)

    def _file_get(self, name: str) -> str | None:
        try:
            return self._file_all().get(name)
        except Exception:
            return None

    def _file_set(self, name: str, secret: str) -> None:
        data = self._file_all() if self.fallback_path.exists() else {}
        data[name] = secret
        self._file_write(data)

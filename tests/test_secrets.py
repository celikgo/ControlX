from __future__ import annotations

from pathlib import Path

import pytest

from controlx.adapters.secrets import SecretStore, redact
from controlx.errors import AuthError


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SecretStore:
    # force the encrypted-file fallback so the test never touches the real keyring
    monkeypatch.setattr(SecretStore, "_keyring_get", lambda self, name: None)
    monkeypatch.setattr(SecretStore, "_keyring_set", lambda self, name, secret: False)
    monkeypatch.setenv("CONTROLX_PASSPHRASE", "test-passphrase")
    for var in ("CONTROLX_OPENAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return SecretStore(tmp_path)


def test_encrypted_file_round_trip(store: SecretStore):
    assert store.set("openai", "sk-secret") == "encrypted-file"
    assert store.get("openai") == "sk-secret"
    assert store.fallback_path.exists()
    assert b"sk-secret" not in store.fallback_path.read_bytes()  # never stored in the clear


def test_delete_removes_the_entry(store: SecretStore):
    store.set("xai", "xai-key")
    store.delete("xai")
    assert store.get("xai") is None


def test_accounts_are_separate(store: SecretStore):
    store.set("openai", "key-a", "work")
    store.set("openai", "key-b", "personal")
    assert store.get("openai", "work") == "key-a"
    assert store.get("openai", "personal") == "key-b"


def test_environment_wins_over_storage(store: SecretStore, monkeypatch: pytest.MonkeyPatch):
    store.set("anthropic", "stored")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert store.get("anthropic") == "from-env"


def test_missing_passphrase_is_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SecretStore, "_keyring_set", lambda self, name, secret: False)
    monkeypatch.delenv("CONTROLX_PASSPHRASE", raising=False)
    with pytest.raises(AuthError):
        SecretStore(tmp_path).set("openai", "sk")


def test_redaction():
    assert redact("sk-1234567890abcd") == "sk-…abcd"
    assert redact(None) == "-"
    assert "short" not in redact("short")

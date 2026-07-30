from __future__ import annotations

import keyring
import keyring.backend
import keyring.errors
import pytest

from openchem.plugins.context import _PluginSecrets


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    """A tiny in-memory fake backend so these tests never touch the real
    OS keychain."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError("not found") from None


@pytest.fixture
def fake_keyring():
    original = keyring.get_keyring()
    fake = _InMemoryKeyring()
    keyring.set_keyring(fake)
    try:
        yield fake
    finally:
        keyring.set_keyring(original)


def test_secrets_roundtrip(fake_keyring):
    secrets = _PluginSecrets("plugin_a")
    assert secrets.get("api_key") is None

    secrets.set("api_key", "sk-12345")
    assert secrets.get("api_key") == "sk-12345"

    secrets.delete("api_key")
    assert secrets.get("api_key") is None


def test_secrets_are_namespaced_per_plugin(fake_keyring):
    secrets_a = _PluginSecrets("plugin_a")
    secrets_b = _PluginSecrets("plugin_b")

    secrets_a.set("api_key", "a-secret")
    secrets_b.set("api_key", "b-secret")

    assert secrets_a.get("api_key") == "a-secret"
    assert secrets_b.get("api_key") == "b-secret"


def test_delete_missing_key_does_not_raise(fake_keyring):
    secrets = _PluginSecrets("plugin_a")
    secrets.delete("never_set")  # must not raise

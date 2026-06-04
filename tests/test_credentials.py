"""Tests for Keychain-backed credential storage.

Uses an in-memory fake keyring so tests never touch the real macOS Keychain.
"""

import pytest

from leetcode_enforcer import credentials


class FakeKeyring:
    """Minimal in-memory stand-in for the `keyring` module's functions."""

    def __init__(self):
        self.store = {}

    def set_password(self, service, key, value):
        self.store[(service, key)] = value

    def get_password(self, service, key):
        return self.store.get((service, key))

    def delete_password(self, service, key):
        self.store.pop((service, key), None)


@pytest.fixture
def fake_keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(credentials.keyring, "set_password", fake.set_password)
    monkeypatch.setattr(credentials.keyring, "get_password", fake.get_password)
    monkeypatch.setattr(credentials.keyring, "delete_password", fake.delete_password)
    return fake


def test_no_credentials_initially(fake_keyring):
    assert credentials.load_credentials() is None
    assert credentials.has_credentials() is False


def test_save_and_load_roundtrip(fake_keyring):
    credentials.save_credentials("sess-abc", "csrf-xyz")
    assert credentials.has_credentials() is True
    creds = credentials.load_credentials()
    assert creds == {"session": "sess-abc", "csrf": "csrf-xyz"}


def test_partial_credentials_treated_as_missing(fake_keyring):
    # only the session set, no csrf -> not usable
    fake_keyring.set_password(credentials.SERVICE, credentials._SESSION_KEY, "sess-only")
    assert credentials.load_credentials() is None


def test_clear_credentials(fake_keyring):
    credentials.save_credentials("sess-abc", "csrf-xyz")
    credentials.clear_credentials()
    assert credentials.load_credentials() is None
    # clearing again must not raise
    credentials.clear_credentials()

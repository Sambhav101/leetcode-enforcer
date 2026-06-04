"""Secure storage for the LeetCode session, backed by the macOS Keychain.

LeetCode's submit endpoint authenticates with the ``LEETCODE_SESSION`` cookie plus
a ``csrftoken`` (sent as the ``X-CSRFToken`` header). Both are bearer secrets, so we
keep them in the OS Keychain (encrypted, access-controlled) via ``keyring`` — never
in a plaintext file, never logged, never committed. See DESIGN.md §4a.

Setup is a one-time manual paste (run ``python -m leetcode_enforcer.credentials``):
the user copies the two values from their browser's cookies and pastes them here.
"""

from getpass import getpass

import keyring

SERVICE = "leetcode-enforcer"
_SESSION_KEY = "LEETCODE_SESSION"
_CSRF_KEY = "csrftoken"


def save_credentials(session: str, csrf: str) -> None:
    """Store the session cookie and CSRF token in the Keychain."""
    keyring.set_password(SERVICE, _SESSION_KEY, session)
    keyring.set_password(SERVICE, _CSRF_KEY, csrf)


def load_credentials() -> dict | None:
    """Return ``{"session": ..., "csrf": ...}`` or ``None`` if not fully set."""
    session = keyring.get_password(SERVICE, _SESSION_KEY)
    csrf = keyring.get_password(SERVICE, _CSRF_KEY)
    if not session or not csrf:
        return None
    return {"session": session, "csrf": csrf}


def has_credentials() -> bool:
    return load_credentials() is not None


def clear_credentials() -> None:
    """Remove stored credentials (e.g. on logout or expired cookie)."""
    for key in (_SESSION_KEY, _CSRF_KEY):
        try:
            keyring.delete_password(SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass  # already absent — fine


def _prompt_and_store() -> None:
    """Interactive one-time setup. Values are read without echoing to the terminal."""
    print(
        "Paste your LeetCode credentials (from your browser cookies on leetcode.com).\n"
        "  DevTools → Application → Cookies → https://leetcode.com\n"
    )
    session = getpass("LEETCODE_SESSION: ").strip()
    csrf = getpass("csrftoken: ").strip()
    if not session or not csrf:
        raise SystemExit("Both LEETCODE_SESSION and csrftoken are required.")
    save_credentials(session, csrf)
    print(f"Stored in the macOS Keychain under service '{SERVICE}'.")


if __name__ == "__main__":
    _prompt_and_store()

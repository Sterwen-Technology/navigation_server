#-------------------------------------------------------------------------------
# Name:        user_management
# Purpose:     User authentication and session management for the web server
#
#              This module provides the UserStore, Authenticator, and _NullUserStore
#              classes for handling web user authentication.
#
# Author:      Vibe Code
#
# Created:     15/08/2025
# Copyright:   (c) Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import base64
import hashlib
import hmac
import logging
import os
import threading
import time

_logger = logging.getLogger("ShipDataServer." + __name__)

# PBKDF2 parameters for web user password hashing (stdlib only, no deps).
_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ITERATIONS = 200_000
_PBKDF2_DKLEN = 32
# Lifetime of a session token, in seconds.
DEFAULT_SESSION_TIMEOUT = 3600
_SESSION_COOKIE = "navsession"


class UserStore:
    """File-backed store of web users.

    The credentials file holds one user per line as::

        username:base64(salt):base64(hash):iterations

    Passwords are never stored in clear text: only a PBKDF2-HMAC-SHA256
    hash (with an independent per-user salt) is persisted. The file itself
    lives on the device at a path set in the YAML configuration, so no
    secret is ever committed to the repository.

    ``UserStore`` is a low-level data layer: it loads, saves and looks up
    user records. Password verification and session management live in
    :class:`Authenticator`.
    """

    def __init__(self, credentials_file: str):
        self._path = credentials_file
        self._lock = threading.Lock()
        self._users = {}
        self._load()

    def _load(self):
        self._users = {}
        if not self._path or not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for lineno, raw in enumerate(f, 1):
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(":")
                    if len(parts) != 4:
                        _logger.warning("Ignored malformed line %d in %s",
                                        lineno, self._path)
                        continue
                    username, salt_b64, hash_b64, iters_s = parts
                    try:
                        salt = base64.b64decode(salt_b64)
                        digest = base64.b64decode(hash_b64)
                        iterations = int(iters_s)
                    except (ValueError, TypeError):
                        _logger.warning("Ignored undecodable line %d in %s",
                                        lineno, self._path)
                        continue
                    self._users[username] = (salt, digest, iterations)
        except OSError as err:
            _logger.error("Cannot read credentials file %s: %s", self._path, err)

    def save(self):
        with self._lock:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for username, (salt, digest, iterations) in self._users.items():
                    f.write("%s:%s:%s:%d\n" % (
                        username,
                        base64.b64encode(salt).decode("ascii"),
                        base64.b64encode(digest).decode("ascii"),
                        iterations,
                    ))
            os.replace(tmp, self._path)

    def has_user(self, username: str) -> bool:
        with self._lock:
            return username in self._users

    def list_users(self):
        with self._lock:
            return list(self._users.keys())

    def get(self, username: str):
        with self._lock:
            return self._users.get(username)

    def set(self, username: str, password: str, iterations: int = _PBKDF2_ITERATIONS):
        with self._lock:
            salt = os.urandom(16)
            digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM,
                                         password.encode("utf-8"),
                                         salt, iterations, _PBKDF2_DKLEN)
            self._users[username] = (salt, digest, iterations)

    def delete(self, username: str) -> bool:
        with self._lock:
            if username not in self._users:
                return False
            del self._users[username]
            return True


class Authenticator:
    """Optional HTTP authentication for the web API.

    When enabled (``auth['enabled']`` in the web server YAML), every
    ``/api/*`` route except ``/api/login`` requires a valid session token
    delivered as an ``HttpOnly`` cookie. Authentication is entirely optional:
    when disabled (the default, or when the ``auth`` block is absent) the
    guard is a no-op and the server behaves exactly as before.

    The authenticator owns the session token store (in-memory, protected by a
    lock) and delegates password verification to a :class:`UserStore` backed by
    a device-local credentials file. No password is ever hardcoded in source
    or committed to the repository.
    """

    def __init__(self, store: UserStore, session_timeout: int = DEFAULT_SESSION_TIMEOUT,
                 enabled: bool = False):
        self._store = store
        self.enabled = enabled
        self._session_timeout = session_timeout
        self._sessions = {}  # token -> {username, expires_at}
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, auth_config: dict):
        """Build an Authenticator from the ``auth`` YAML dictionary.

        ``auth_config`` is the value of the ``auth`` key in the web server
        YAML section (or ``None`` when absent). Returns a disabled
        authenticator when the block is missing or ``enabled`` is false.
        """
        if not auth_config:
            return cls(enabled=False, store=_NullUserStore())
        enabled = bool(auth_config.get("enabled", False))
        credentials_file = auth_config.get("credentials_file")
        if not enabled or not credentials_file:
            return cls(enabled=False, store=_NullUserStore())
        if not os.path.isfile(credentials_file):
            _logger.error("Web authentication without credentials file: %s", credentials_file)
            return cls(enabled=False, store=_NullUserStore())
        timeout = int(auth_config.get("session_timeout", DEFAULT_SESSION_TIMEOUT))
        return cls(UserStore(credentials_file), session_timeout=timeout, enabled=enabled)

    def login(self, username: str, password: str) -> str | None:
        """Verify credentials and return a fresh session token, or ``None``."""
        import secrets
        record = self._store.get(username)
        if record is None:
            # Constant-time-ish failure: run a dummy derivation.
            hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM, password.encode("utf-8"),
                                b"\x00" * 16, _PBKDF2_ITERATIONS, _PBKDF2_DKLEN)
            return None
        salt, expected, iterations = record
        digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM, password.encode("utf-8"),
                                     salt, iterations, _PBKDF2_DKLEN)
        if not hmac.compare_digest(digest, expected):
            return None
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {
                "username": username,
                "expires_at": time.time() + self._session_timeout,
            }
        return token

    def logout(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)

    def is_valid(self, token: str) -> bool:
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return False
            if session["expires_at"] < time.time():
                del self._sessions[token]
                return False
            return True

    def check_request(self, handler) -> bool:
        """Return True if the request is authorized.

        When authentication is disabled this always returns True, preserving
        the historical open behaviour.
        """
        if not self.enabled:
            return True
        cookies = handler.headers.get("Cookie", "")
        token = None
        for part in cookies.split(";"):
            part = part.strip()
            if part.startswith(_SESSION_COOKIE + "="):
                token = part[len(_SESSION_COOKIE) + 1:]
                break
        return self.is_valid(token) if token else False

    @property
    def session_timeout(self) -> int:
        return self._session_timeout


class _NullUserStore(UserStore):
    """No-op store used when authentication is disabled."""

    def __init__(self):
        # Skip the file-backed initialiser entirely.
        self._path = None
        self._lock = threading.Lock()
        self._users = {}

    def _load(self):
        pass

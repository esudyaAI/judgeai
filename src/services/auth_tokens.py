"""Opaque session identifiers and session-bound CSRF values; no persisted plaintext."""

import hashlib
import secrets


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_for(token: str) -> str:
    return hashlib.sha256(b"judgeai-csrf-v1:" + token.encode()).hexdigest()


def login_bucket_keys(client_host: str, username: str) -> tuple[str, str]:
    return (
        token_digest("account:" + username.strip().lower()),
        token_digest("host:" + client_host),
    )


def registration_bucket_key(client_host: str) -> str:
    return token_digest("register:" + client_host)

"""Windows Credential Manager storage for provider secrets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

KEYRING_SERVICE = "advp.providers"


class CredentialError(Exception):
    """Stable error for credential-store failures."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.status_code = 503


@dataclass(slots=True)
class SecretPayload:
    """Secret values kept outside the project database."""

    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def has_secret(self) -> bool:
        return bool(self.api_key or self.headers)


def load_secret(provider_id: str) -> SecretPayload:
    """Load a provider secret payload from the OS credential store."""
    try:
        raw = keyring.get_password(KEYRING_SERVICE, provider_id)
    except KeyringError as exc:
        raise CredentialError(
            "credential_store_unavailable",
            "the OS credential store is unavailable",
            "run ADVP in a signed-in Windows desktop session and retry",
        ) from exc
    if raw is None:
        return SecretPayload()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise CredentialError(
            "credential_store_corrupt",
            f"stored credentials for provider {provider_id!r} are corrupt",
            "delete and re-save the provider credentials",
        ) from exc
    if not isinstance(data, dict):
        raise CredentialError(
            "credential_store_corrupt",
            f"stored credentials for provider {provider_id!r} are corrupt",
        )
    api_key = data.get("api_key")
    headers = data.get("headers") or {}
    if api_key is not None and not isinstance(api_key, str):
        raise CredentialError("credential_store_corrupt", "stored API key is invalid")
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
    ):
        raise CredentialError("credential_store_corrupt", "stored headers are invalid")
    return SecretPayload(api_key=api_key, headers=dict(headers))


def save_secret(
    provider_id: str,
    *,
    api_key: str | None = None,
    headers: dict[str, str] | None = None,
    clear_key: bool = False,
    clear_headers: bool = False,
) -> SecretPayload:
    """Merge and persist provider secrets.

    Omitted values are preserved. `clear_key`/`clear_headers` remove them.
    """
    payload = load_secret(provider_id)
    if clear_key:
        payload.api_key = None
    if api_key is not None:
        payload.api_key = api_key
    if clear_headers:
        payload.headers = {}
    if headers is not None:
        payload.headers = dict(headers)

    if not payload.has_secret:
        delete_secret(provider_id)
        return payload

    encoded = json.dumps(
        {"api_key": payload.api_key, "headers": payload.headers},
        ensure_ascii=False,
    )
    try:
        keyring.set_password(KEYRING_SERVICE, provider_id, encoded)
    except KeyringError as exc:
        raise CredentialError(
            "credential_store_unavailable",
            "the OS credential store is unavailable",
            "run ADVP in a signed-in Windows desktop session and retry",
        ) from exc
    return payload


def delete_secret(provider_id: str) -> None:
    """Delete a provider secret; missing entries are ignored."""
    try:
        keyring.delete_password(KEYRING_SERVICE, provider_id)
    except PasswordDeleteError:
        return
    except KeyringError as exc:
        raise CredentialError(
            "credential_store_unavailable",
            "the OS credential store is unavailable",
            "run ADVP in a signed-in Windows desktop session and retry",
        ) from exc


def mask_key(api_key: str | None) -> str | None:
    """Return only the last four characters for display."""
    if not api_key:
        return None
    if len(api_key) < 4:
        return "****"
    return api_key[-4:]

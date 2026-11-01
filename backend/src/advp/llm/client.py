"""HTTP clients for OpenAI-compatible and Anthropic-compatible providers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

RETRYABLE_CODES = {"rate_limit", "server_error", "network_error"}


class ProviderError(Exception):
    """A classified upstream provider failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.retryable = retryable
        self.status_code = 502


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Raw text plus token usage from one provider call."""

    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: float
    model: str
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelListResult:
    """Models returned by an optional /models endpoint."""

    models: list[str]
    latency_ms: float


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    """Result of a provider connectivity test."""

    ok: bool
    latency_ms: float
    models_supported: bool
    message: str | None = None


class ProviderClient:
    """Small synchronous client with retries and stable error codes."""

    def __init__(
        self,
        *,
        kind: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        proxy_url: str | None = None,
        anthropic_version: str = "2023-06-01",
        organization: str | None = None,
        project: str | None = None,
        transport: httpx.BaseTransport | None = None,
        retry_backoff: float = 0.5,
    ) -> None:
        if kind not in {"openai", "anthropic"}:
            raise ValueError(f"unsupported provider kind: {kind}")
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.headers = dict(headers or {})
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.proxy_url = proxy_url
        self.anthropic_version = anthropic_version
        self.organization = organization
        self.project = project
        self.transport = transport
        self.retry_backoff = max(0.0, retry_backoff)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Send one completion request and return text plus usage."""
        payload = self._completion_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        path = "/chat/completions" if self.kind == "openai" else "/messages"
        response, latency_ms = self._send("POST", path, payload)
        data = self._decode_json(response)
        text, usage = self._parse_completion(data)
        return CompletionResult(
            text=text,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cached_tokens=usage["cached_tokens"],
            latency_ms=latency_ms,
            model=self.model,
            raw=data,
        )

    def list_models(self) -> ModelListResult:
        """List models when the provider exposes a compatible endpoint."""
        started = time.perf_counter()
        try:
            response, _ = self._send("GET", "/models", None)
        except ProviderError as exc:
            if exc.code == "protocol_error":
                raise ProviderError(
                    "models_unsupported",
                    "the provider does not expose a compatible /models endpoint",
                    hint="enter the model name manually",
                ) from exc
            raise
        data = self._decode_json(response)
        raw_models = data.get("data", [])
        models = [
            str(item["id"])
            for item in raw_models
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        return ModelListResult(
            models=models,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    def test_connection(self) -> ConnectionResult:
        """Test reachability; a missing /models endpoint still counts as reachable."""
        started = time.perf_counter()
        try:
            result = self.list_models()
        except ProviderError as exc:
            if exc.code == "models_unsupported":
                return ConnectionResult(
                    ok=True,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    models_supported=False,
                    message="provider is reachable but does not support model listing",
                )
            raise
        return ConnectionResult(
            ok=True,
            latency_ms=result.latency_ms,
            models_supported=True,
            message=f"{len(result.models)} models available",
        )

    def _send(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> tuple[httpx.Response, float]:
        started = time.perf_counter()
        last_error: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with self._http_client() as client:
                    response = client.request(
                        method,
                        self.base_url + path,
                        json=payload,
                        headers=self._headers(),
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = ProviderError(
                    "network_error",
                    f"provider network error: {exc.__class__.__name__}",
                    hint="check the base URL, proxy, and network connection",
                    retryable=True,
                )
            else:
                if response.is_success:
                    return response, round((time.perf_counter() - started) * 1000, 2)
                last_error = self._classify_error(response)
                if not last_error.retryable:
                    raise last_error
            if attempt < self.max_retries:
                time.sleep(self.retry_backoff * (2**attempt))
        assert last_error is not None
        raise last_error

    def _http_client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": self.timeout_seconds}
        if self.transport is not None:
            kwargs["transport"] = self.transport
        if self.proxy_url:
            kwargs["proxy"] = self.proxy_url
        return httpx.Client(**kwargs)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.kind == "openai":
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            if self.organization:
                headers["OpenAI-Organization"] = self.organization
            if self.project:
                headers["OpenAI-Project"] = self.project
        else:
            if self.api_key:
                headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = self.anthropic_version
        headers.update(self.headers)
        return headers

    def _completion_payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> dict[str, Any]:
        if self.kind == "openai":
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            return payload
        system_parts = [item["content"] for item in messages if item["role"] == "system"]
        chat_messages = [item for item in messages if item["role"] != "system"]
        payload = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)
        return payload

    def _classify_error(self, response: httpx.Response) -> ProviderError:
        body = response.text[:1000].lower()
        status = response.status_code
        if status in {401, 403}:
            return ProviderError(
                "auth_error",
                f"provider rejected the credentials (HTTP {status})",
                hint="check the API key and provider account",
            )
        if status == 429:
            if "insufficient_quota" in body or "quota" in body:
                return ProviderError(
                    "quota_error",
                    "provider quota is exhausted",
                    hint="check billing or switch to another provider",
                )
            return ProviderError(
                "rate_limit",
                "provider rate limit reached",
                hint="retry later or lower the request rate",
                retryable=True,
            )
        if status >= 500:
            return ProviderError(
                "server_error",
                f"provider server error (HTTP {status})",
                retryable=True,
            )
        if status == 408:
            return ProviderError(
                "network_error",
                "provider request timed out",
                retryable=True,
            )
        if status in {404, 405}:
            return ProviderError(
                "protocol_error",
                f"provider endpoint not found (HTTP {status})",
                hint="check the base URL and provider kind",
            )
        if status == 400 and ("content_filter" in body or "safety" in body):
            return ProviderError(
                "content_filter",
                "the provider rejected the request because of content policy",
            )
        return ProviderError(
            "protocol_error",
            f"provider returned an unexpected response (HTTP {status})",
        )

    @staticmethod
    def _decode_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "protocol_error",
                "provider returned a non-JSON response",
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError("protocol_error", "provider response must be a JSON object")
        return data

    def _parse_completion(self, data: dict[str, Any]) -> tuple[str, dict[str, int]]:
        if self.kind == "openai":
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderError(
                    "protocol_error", "provider response is missing choices[0].message.content"
                ) from exc
            text = _content_text(content)
            usage = data.get("usage") or {}
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        else:
            blocks = data.get("content")
            if not isinstance(blocks, list):
                raise ProviderError("protocol_error", "provider response is missing content")
            text = "".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
            usage = data.get("usage") or {}
            cached = usage.get("cache_read_input_tokens", 0)
        return text, {
            "input_tokens": _int_value(usage.get("prompt_tokens", usage.get("input_tokens", 0))),
            "output_tokens": _int_value(
                usage.get("completion_tokens", usage.get("output_tokens", 0))
            ),
            "cached_tokens": _int_value(cached),
        }


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "".join(parts)
    raise ProviderError("protocol_error", "provider message content is not text")


def _int_value(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0

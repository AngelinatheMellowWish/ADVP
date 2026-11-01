"""Collect a bounded window from WebSocket and Kafka streams."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl
import websockets
from confluent_kafka import Consumer, KafkaError

from advp.ingest.files import IngestError, InvalidSourceError
from advp.ingest.remote import auth_headers

MAX_STREAM_MESSAGES = 1000
MAX_STREAM_TIMEOUT = 120.0


class StreamError(IngestError):
    code = "stream_error"
    status_code = 422


def normalize_payload(payload: Any) -> list[dict[str, Any]]:
    """Convert a decoded message into one or more tabular records."""
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
        return records or [{"value": payload}]
    return [{"value": payload}]


def _decode(value: bytes | str | None) -> Any:
    if value is None:
        return None
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def _collect_websocket(
    url: str,
    *,
    max_messages: int,
    timeout: float,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    records: list[dict[str, Any]] = []
    try:
        async with websockets.connect(
            url,
            additional_headers=headers or None,
            open_timeout=timeout,
        ) as socket:
            while len(records) < max_messages:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=min(remaining, 1.0))
                except TimeoutError:
                    continue
                records.extend(normalize_payload(_decode(raw)))
    except Exception as exc:
        raise StreamError(
            f"WebSocket stream failed: {exc}",
            hint="check the ws/wss URL, headers, and server availability",
        ) from exc
    return records[:max_messages]


def collect_websocket(
    url: str,
    *,
    max_messages: int = 100,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"ws", "wss"}:
        raise InvalidSourceError(
            "only ws and wss URLs are supported",
            hint="use a WebSocket endpoint",
        )
    request_headers = dict(headers or {})
    request_headers.update(auth_headers(auth))
    limit = min(max(max_messages, 1), MAX_STREAM_MESSAGES)
    window = min(max(timeout, 1.0), MAX_STREAM_TIMEOUT)
    records = asyncio.run(
        _collect_websocket(
            url,
            max_messages=limit,
            timeout=window,
            headers=request_headers,
        )
    )
    return records


def collect_kafka(
    bootstrap: str,
    topic: str,
    *,
    group: str | None = None,
    max_messages: int = 100,
    timeout: float = 10.0,
    auto_offset_reset: str = "earliest",
    security_protocol: str | None = None,
    sasl_mechanism: str | None = None,
    sasl_username: str | None = None,
    sasl_password: str | None = None,
    ssl_ca_location: str | None = None,
) -> list[dict[str, Any]]:
    if not bootstrap.strip() or not topic.strip():
        raise InvalidSourceError("Kafka bootstrap and topic are required")
    if auto_offset_reset not in {"earliest", "latest"}:
        raise InvalidSourceError("auto_offset_reset must be earliest or latest")
    limit = min(max(max_messages, 1), MAX_STREAM_MESSAGES)
    window = min(max(timeout, 1.0), MAX_STREAM_TIMEOUT)
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap,
        "group.id": group or f"advp-stream-{uuid.uuid4().hex}",
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": False,
        "session.timeout.ms": 10000,
    }
    if security_protocol:
        config["security.protocol"] = security_protocol
    if sasl_mechanism:
        config["sasl.mechanism"] = sasl_mechanism
    if sasl_username:
        config["sasl.username"] = sasl_username
    if sasl_password:
        config["sasl.password"] = sasl_password
    if ssl_ca_location:
        config["ssl.ca.location"] = ssl_ca_location
    consumer = Consumer(config)
    records: list[dict[str, Any]] = []
    deadline = time.monotonic() + window
    try:
        consumer.subscribe([topic])
        while len(records) < limit and time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None:
                continue
            error = message.error()
            if error is not None:
                if error.code() == KafkaError._PARTITION_EOF:
                    continue
                raise StreamError(
                    f"Kafka consume error: {error}",
                    hint="check topic, group, offsets, and broker availability",
                )
            payload = _decode(message.value())
            new_records = normalize_payload(payload)
            key = message.key()
            key_text = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else key
            timestamp = message.timestamp()
            timestamp_ms = timestamp[1] if timestamp and timestamp[0] >= 0 else None
            for record in new_records:
                record.setdefault("_kafka_topic", message.topic())
                record.setdefault("_kafka_partition", message.partition())
                record.setdefault("_kafka_offset", message.offset())
                if key_text is not None:
                    record.setdefault("_kafka_key", key_text)
                if timestamp_ms is not None:
                    record.setdefault("_kafka_timestamp_ms", timestamp_ms)
            records.extend(new_records)
    except StreamError:
        raise
    except Exception as exc:
        message_text = str(exc)
        if sasl_password:
            message_text = message_text.replace(sasl_password, "***")
        raise StreamError(
            f"Kafka stream failed: {message_text}",
            hint="check bootstrap servers, topic, and security settings",
        ) from exc
    finally:
        consumer.close()
    return records[:limit]


def materialize_stream(records: list[dict[str, Any]], output: Path) -> Path:
    if not records:
        raise InvalidSourceError(
            "no stream messages were received",
            hint="check the stream URL/topic, timeout, and offset policy",
        )
    try:
        frame = pl.DataFrame(
            records,
            infer_schema_length=max(len(records), 1),
            strict=False,
        )
    except Exception as exc:
        raise StreamError(
            f"cannot convert stream messages to a table: {exc}",
            hint="ensure messages are JSON objects or arrays of objects",
        ) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(output)
    return output

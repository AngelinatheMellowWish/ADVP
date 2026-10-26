"""In-memory live WebSocket/Kafka sessions for realtime chart windows."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from confluent_kafka import Consumer, KafkaError
from websockets.sync.client import connect as ws_connect

from advp.ingest.remote import auth_headers
from advp.ingest.streams import _decode, normalize_payload

CONSUMER_FACTORY: Callable[..., Consumer] = Consumer


class LiveError(Exception):
    """A live session cannot be created or is no longer available."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class LiveSession:
    id: str
    kind: str
    config: dict[str, Any]
    max_messages: int
    sample_interval_ms: int = 0
    status: str = "connecting"
    paused: bool = False
    error: str | None = None
    records: deque[dict[str, Any]] = field(default_factory=deque)
    sequence: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_emit: float = 0.0
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def snapshot(self, since: int | None = None) -> dict[str, Any]:
        records = list(self.records)
        oldest_sequence = self.sequence - len(records) + 1 if records else 0
        reset = since is None or since >= self.sequence or since < oldest_sequence - 1
        if reset:
            selected = records
            from_sequence = oldest_sequence
        else:
            assert since is not None
            offset = max(0, since - oldest_sequence + 1)
            selected = records[offset:]
            from_sequence = oldest_sequence + offset
        return {
            "session_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "paused": self.paused,
            "error": self.error,
            "sequence": self.sequence,
            "count": len(selected),
            "buffer_count": len(records),
            "records": selected,
            "reset": reset,
            "oldest_sequence": oldest_sequence,
            "from_sequence": from_sequence,
            "to_sequence": self.sequence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class LiveSessionManager:
    """Own live source threads and bounded ring buffers."""

    def __init__(self, *, ttl_seconds: float = 1800.0) -> None:
        self._sessions: dict[str, LiveSession] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds

    def create(
        self,
        *,
        kind: str,
        config: dict[str, Any],
        max_messages: int = 1000,
        sample_interval_ms: int = 0,
    ) -> LiveSession:
        self.cleanup()
        session_id = uuid.uuid4().hex
        session = LiveSession(
            id=session_id,
            kind=kind,
            config=dict(config),
            max_messages=min(max(max_messages, 10), 5000),
            sample_interval_ms=min(max(sample_interval_ms, 0), 60_000),
            records=deque(maxlen=min(max(max_messages, 10), 5000)),
        )
        with self._lock:
            self._sessions[session_id] = session
        thread = threading.Thread(
            target=self._run,
            args=(session,),
            name=f"advp-live-{session_id[:8]}",
            daemon=True,
        )
        session.thread = thread
        thread.start()
        return session

    def get(self, session_id: str) -> LiveSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise LiveError("live_session_not_found", "live session was not found", 404)
        return session

    def snapshot(self, session_id: str, since: int | None = None) -> dict[str, Any]:
        return self.get(session_id).snapshot(since=since)

    def pause(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        session.paused = True
        session.updated_at = time.time()
        return session.snapshot()

    def resume(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        session.paused = False
        session.updated_at = time.time()
        if session.status == "paused":
            session.status = "live"
        return session.snapshot()

    def stop(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        self._stop_session(session)
        return session.snapshot()

    def cleanup(self) -> None:
        now = time.time()
        expired: list[LiveSession] = []
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                if session.status == "stopped" or now - session.updated_at > self.ttl_seconds:
                    expired.append(session)
                    self._sessions.pop(session_id, None)
        for session in expired:
            self._stop_session(session)

    def _stop_session(self, session: LiveSession) -> None:
        session.stop_event.set()
        session.paused = False
        if session.status not in {"stopped", "error"}:
            session.status = "stopped"
        session.updated_at = time.time()

    def _run(self, session: LiveSession) -> None:
        if session.kind == "websocket":
            self._run_websocket(session)
        else:
            self._run_kafka(session)

    def _run_websocket(self, session: LiveSession) -> None:
        url = str(session.config.get("url", ""))
        headers = dict(session.config.get("headers") or {})
        headers.update(auth_headers(session.config.get("auth")))
        backoff = 0.5
        while not session.stop_event.is_set():
            try:
                with ws_connect(
                    url,
                    additional_headers=headers or None,
                    open_timeout=float(session.config.get("open_timeout", 10)),
                ) as socket:
                    session.status = "live"
                    session.error = None
                    session.updated_at = time.time()
                    backoff = 0.5
                    while not session.stop_event.is_set():
                        try:
                            raw = socket.recv(timeout=1.0)
                        except TimeoutError:
                            continue
                        self._append(session, normalize_payload(_decode(raw)))
            except Exception as exc:  # noqa: BLE001 - live source errors are surfaced
                if session.stop_event.is_set():
                    break
                session.status = "reconnecting"
                session.error = _safe_error(exc, session.config)
                session.updated_at = time.time()
                session.stop_event.wait(backoff)
                backoff = min(5.0, backoff * 2)
        session.updated_at = time.time()

    def _run_kafka(self, session: LiveSession) -> None:
        config = dict(session.config.get("consumer_config") or {})
        topic = str(session.config.get("topic", ""))
        backoff = 0.5
        while not session.stop_event.is_set():
            consumer: Consumer | None = None
            try:
                consumer = CONSUMER_FACTORY(config)
                consumer.subscribe([topic])
                session.status = "live"
                session.error = None
                session.updated_at = time.time()
                backoff = 0.5
                while not session.stop_event.is_set():
                    message = consumer.poll(1.0)
                    if message is None:
                        continue
                    error = message.error()
                    if error is not None:
                        if error.code() == KafkaError._PARTITION_EOF:
                            continue
                        raise RuntimeError(f"Kafka consume error: {error}")
                    payload = _decode(message.value())
                    records = normalize_payload(payload)
                    for record in records:
                        record.setdefault("_kafka_topic", message.topic())
                        record.setdefault("_kafka_partition", message.partition())
                        record.setdefault("_kafka_offset", message.offset())
                    self._append(session, records)
                    consumer.commit(message=message, asynchronous=True)
            except Exception as exc:  # noqa: BLE001 - live source errors are surfaced
                if session.stop_event.is_set():
                    break
                session.status = "reconnecting"
                session.error = _safe_error(exc, session.config)
                session.updated_at = time.time()
                session.stop_event.wait(backoff)
                backoff = min(5.0, backoff * 2)
            finally:
                if consumer is not None:
                    consumer.close()
        session.updated_at = time.time()

    def _append(self, session: LiveSession, records: list[dict[str, Any]]) -> None:
        if not records or session.paused or session.stop_event.is_set():
            return
        now = time.monotonic()
        if (
            session.sample_interval_ms > 0
            and now - session.last_emit < session.sample_interval_ms / 1000
        ):
            return
        session.last_emit = now
        for record in records:
            session.records.append(record)
        session.sequence += len(records)
        session.status = "live"
        session.updated_at = time.time()


def _safe_error(exc: Exception, config: dict[str, Any]) -> str:
    text = str(exc)[:300]
    for value in _secret_values(config):
        if len(value) >= 4:
            text = text.replace(value, "***")
    lowered = text.lower()
    if any(key in lowered for key in ("password", "token", "secret", "sasl")):
        return "live source error (details redacted)"
    return text


def _secret_values(config: dict[str, Any]) -> list[str]:
    values: list[str] = []
    consumer = config.get("consumer_config") or {}
    if isinstance(consumer, dict):
        values.extend(
            str(value)
            for key, value in consumer.items()
            if any(part in str(key).lower() for part in ("password", "secret", "token"))
        )
    headers = config.get("headers") or {}
    if isinstance(headers, dict):
        values.extend(str(value) for value in headers.values())
    auth = config.get("auth") or {}
    if isinstance(auth, dict):
        values.extend(
            str(value)
            for key, value in auth.items()
            if any(part in str(key).lower() for part in ("token", "password", "value"))
        )
    return values


MANAGER = LiveSessionManager()

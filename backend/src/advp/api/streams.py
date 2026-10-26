"""Preview bounded WebSocket and Kafka stream windows."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException

from advp.api.schemas import (
    KafkaRequest,
    StreamPreviewResponse,
    WebSocketRequest,
)
from advp.ingest.files import IngestError
from advp.services import projects as project_service

router = APIRouter(prefix="/streams", tags=["streams"])


def _raise_stream(exc: IngestError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


@router.post("/websocket/preview", response_model=StreamPreviewResponse)
def preview_websocket(payload: WebSocketRequest) -> dict[str, object]:
    try:
        return project_service.preview_websocket(
            payload.url,
            headers=payload.headers,
            auth=(payload.auth.model_dump(exclude_none=True) if payload.auth is not None else None),
            max_messages=payload.max_messages,
            timeout=payload.timeout,
        )
    except IngestError as exc:
        _raise_stream(exc)


@router.post("/kafka/preview", response_model=StreamPreviewResponse)
def preview_kafka(payload: KafkaRequest) -> dict[str, object]:
    try:
        return project_service.preview_kafka(
            bootstrap=payload.bootstrap,
            topic=payload.topic,
            group=payload.group,
            max_messages=payload.max_messages,
            timeout=payload.timeout,
            auto_offset_reset=payload.auto_offset_reset,
            security_protocol=payload.security_protocol,
            sasl_mechanism=payload.sasl_mechanism,
            sasl_username=payload.sasl_username,
            sasl_password=(
                payload.sasl_password.get_secret_value()
                if payload.sasl_password is not None
                else None
            ),
            ssl_ca_location=payload.ssl_ca_location,
        )
    except IngestError as exc:
        _raise_stream(exc)

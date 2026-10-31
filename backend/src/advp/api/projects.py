"""Project CRUD, dataset import, inspection, and manifest endpoints."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.orm import Session

from advp import audit
from advp.api.deps import DbSession
from advp.api.schemas import (
    DatasetCreate,
    DatasetDetail,
    DatasetSummary,
    DocumentImportRequest,
    DocumentRequest,
    DocumentTablesResponse,
    ImportOptionsModel,
    InspectResponse,
    KafkaImportRequest,
    ManifestResponse,
    MultiFilePreviewResponse,
    MultiFileRequest,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
    RemoteImportRequest,
    S3ImportRequest,
    SqlImportRequest,
    TextStatsAIRequest,
    TextStatsAIResponse,
    TextStatsImportRequest,
    WebImportRequest,
    WebRequest,
    WebSocketImportRequest,
    WebTablesResponse,
)
from advp.config import get_settings
from advp.ingest import multifile as multifile_service
from advp.ingest.files import ImportOptions, IngestError, sha256_source
from advp.ingest.sql import SqlError
from advp.ingest.text_readers import read_text_document
from advp.ingest.textstats import TextSourceChangedError
from advp.llm import providers as provider_service
from advp.llm import textstats as textstats_ai
from advp.models import Project
from advp.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])


def _not_found(kind: str, identifier: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={"code": f"{kind}_not_found", "message": f"{kind} was not found: {identifier}"},
    )


def _raise_ingest(exc: IngestError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


def _raise_sql(exc: SqlError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


def _options(model: ImportOptionsModel) -> ImportOptions:
    return ImportOptions(
        encoding=model.encoding,
        delimiter=model.delimiter,
        has_header=model.has_header,
        sheet=model.sheet,
        variable=model.variable,
        shape=model.shape,
        dtype=model.dtype,
        byte_order=model.byte_order,
        raw_offset=model.raw_offset,
        sample_rows=model.sample_rows,
        preview_rows=model.preview_rows,
    )


def _project_or_404(session: Session, project_id: str) -> Project:
    project = project_service.get_project(session, project_id)
    if project is None:
        _not_found("project", project_id)
    return project


def _reveal_in_file_manager(path: Path, select_file: bool) -> None:
    if os.name != "nt":
        raise HTTPException(
            status_code=501,
            detail={
                "code": "reveal_unsupported",
                "message": "opening a containing folder is only supported on Windows",
            },
        )
    try:
        if select_file:
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(path))
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "reveal_failed",
                "message": "the containing folder could not be opened",
            },
        ) from exc


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(payload: ProjectCreate, session: DbSession) -> dict[str, object]:
    project = project_service.create_project(session, payload.name)
    return project_service.project_detail(project)


@router.get("", response_model=list[ProjectSummary])
def list_projects(session: DbSession, include_archived: bool = False) -> list[dict[str, object]]:
    return [
        project_service.project_summary(project)
        for project in project_service.list_projects(session, include_archived=include_archived)
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, session: DbSession) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    migration = project_service.migrate_project(session, project, get_settings().backup_dir)
    return project_service.project_detail(project, migration)


@router.post("/{project_id}/reveal")
def reveal_project(project_id: str, session: DbSession) -> dict[str, str]:
    project = _project_or_404(session, project_id)
    if project.datasets:
        source = Path(project.datasets[0].source_path).expanduser()
        if source.is_dir():
            _reveal_in_file_manager(source, select_file=False)
            return {"path": str(source)}
        _reveal_in_file_manager(source, select_file=True)
        return {"path": str(source.parent)}
    target = get_settings().workspace_dir / "derived" / project.id
    target.mkdir(parents=True, exist_ok=True)
    _reveal_in_file_manager(target, select_file=False)
    return {"path": str(target)}


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    project = project_service.update_project(
        session, project, name=payload.name, archived=payload.archived
    )
    return project_service.project_detail(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: DbSession) -> Response:
    project = _project_or_404(session, project_id)
    project_name = project.name
    project_service.delete_project(session, project)
    audit.record_event(
        session,
        "project_deleted",
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        detail={"name": project_name},
    )
    return Response(status_code=204)


@router.get("/{project_id}/manifest", response_model=ManifestResponse)
def project_manifest(project_id: str, session: DbSession) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    return project_service.project_manifest(project)


@router.get("/{project_id}/datasets", response_model=list[DatasetSummary])
def list_datasets(project_id: str, session: DbSession) -> list[dict[str, object]]:
    project = _project_or_404(session, project_id)
    return [project_service.dataset_summary(dataset) for dataset in project.datasets]


@router.post("/{project_id}/datasets/inspect", response_model=InspectResponse)
def inspect_dataset(
    project_id: str,
    payload: DatasetCreate,
    session: DbSession,
) -> dict[str, object]:
    _project_or_404(session, project_id)
    try:
        return project_service.inspect_source(payload.path, _options(payload.options))
    except IngestError as exc:
        _raise_ingest(exc)


@router.post("/{project_id}/datasets", response_model=DatasetDetail, status_code=201)
def create_dataset(
    project_id: str,
    payload: DatasetCreate,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_dataset(
            session,
            project,
            path=payload.path,
            name=payload.name,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/multifile/preview", response_model=MultiFilePreviewResponse)
def preview_multifile(
    project_id: str,
    payload: MultiFileRequest,
    session: DbSession,
) -> dict[str, object]:
    _project_or_404(session, project_id)
    try:
        return multifile_service.preview_multifile(
            payload.paths,
            mode=payload.mode,
            left_key=payload.left_key,
            right_key=payload.right_key,
            how=payload.how,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)


@router.post(
    "/{project_id}/datasets/multifile",
    response_model=DatasetDetail,
    status_code=201,
)
def import_multifile(
    project_id: str,
    payload: MultiFileRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = multifile_service.import_multifile(
            session,
            project,
            paths=payload.paths,
            mode=payload.mode,
            left_key=payload.left_key,
            right_key=payload.right_key,
            how=payload.how,
            name=payload.name,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/datasets/sql", response_model=DatasetDetail, status_code=201)
def import_sql_dataset(
    project_id: str,
    payload: SqlImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_sql_dataset(
            session,
            project,
            url=payload.url,
            query=payload.query,
            name=payload.name,
            max_rows=payload.max_rows,
        )
    except SqlError as exc:
        _raise_sql(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/documents/inspect", response_model=DocumentTablesResponse)
def inspect_document(
    project_id: str,
    payload: DocumentRequest,
    session: DbSession,
) -> dict[str, object]:
    _project_or_404(session, project_id)
    try:
        return project_service.inspect_document(payload.path, force_text=payload.force_text)
    except IngestError as exc:
        _raise_ingest(exc)


@router.post("/{project_id}/datasets/document", response_model=DatasetDetail, status_code=201)
def import_document_dataset(
    project_id: str,
    payload: DocumentImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_document_dataset(
            session,
            project,
            path=payload.path,
            table_index=payload.table_index,
            name=payload.name,
            has_header=payload.has_header,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/documents/text/ai", response_model=TextStatsAIResponse)
def enhance_text_stats(
    project_id: str,
    payload: TextStatsAIRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    if not payload.allow_ai:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "ai_consent_required",
                "message": "AI enhancement requires explicit consent for this request",
                "hint": "confirm the snippet preview before sending numeric text",
            },
        )
    resolved = project_service.resolve_document_path(payload.path)
    actual_sha256 = sha256_source(resolved)
    if actual_sha256 != payload.source_sha256:
        _raise_ingest(
            TextSourceChangedError(
                "source document changed after inspection",
                hint="run the document check again before AI enhancement",
            )
        )
    try:
        document = read_text_document(resolved, max_chars=get_settings().text_max_chars)
    except IngestError as exc:
        _raise_ingest(exc)
    document_text = "\n".join(line.text for block in document.blocks for line in block.lines)
    providers = provider_service.list_providers(session)
    provider = None
    if payload.provider_id is not None:
        provider = next((item for item in providers if item.id == payload.provider_id), None)
    elif providers:
        provider = providers[0]
    if provider is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "ai_provider_missing",
                "message": "no AI provider is configured",
                "hint": "configure a provider before enabling AI enhancement",
            },
        )
    facts = [fact.model_dump() for fact in payload.facts]
    enhancement = textstats_ai.enhance_facts(
        session,
        provider,
        facts=facts,
        document_text=document_text,
        max_snippets=get_settings().text_ai_max_snippets,
        project_id=project.id,
    )
    audit.record_event(
        session,
        "text_stats_ai_enhance",
        project_id=project.id,
        target_type="provider",
        target_id=provider.id,
        detail={
            "model": enhancement.model,
            "used": enhancement.used,
            "fragments_sent": enhancement.fragments_sent,
            "input_tokens": enhancement.input_tokens,
            "output_tokens": enhancement.output_tokens,
            "estimated_cost": enhancement.estimated_cost,
        },
    )
    return {
        "source_sha256": actual_sha256,
        "facts": enhancement.facts,
        "warnings": enhancement.warnings,
        "ai": enhancement.summary(),
    }


@router.post("/{project_id}/datasets/text", response_model=DatasetDetail, status_code=201)
def import_text_stats_dataset(
    project_id: str,
    payload: TextStatsImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_text_stats_dataset(
            session,
            project,
            path=payload.path,
            source_sha256=payload.source_sha256,
            shape=payload.shape,
            name=payload.name,
            facts=[fact.model_dump() for fact in payload.facts],
            ai=payload.ai,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    audit.record_event(
        session,
        "text_stats_import",
        project_id=project.id,
        target_type="dataset",
        target_id=dataset.id,
        detail={
            "shape": payload.shape,
            "row_count": dataset.row_count,
            "source_sha256": payload.source_sha256,
        },
    )
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/web/inspect", response_model=WebTablesResponse)
def inspect_web(
    project_id: str,
    payload: WebRequest,
    session: DbSession,
) -> dict[str, object]:
    _project_or_404(session, project_id)
    try:
        return project_service.inspect_web(
            payload.url,
            headers=payload.headers,
            auth=(payload.auth.model_dump(exclude_none=True) if payload.auth is not None else None),
        )
    except IngestError as exc:
        _raise_ingest(exc)


@router.post("/{project_id}/datasets/web", response_model=DatasetDetail, status_code=201)
def import_web_dataset(
    project_id: str,
    payload: WebImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_web_dataset(
            session,
            project,
            url=payload.url,
            table_index=payload.table_index,
            name=payload.name,
            headers=payload.headers,
            auth=(payload.auth.model_dump(exclude_none=True) if payload.auth is not None else None),
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/datasets/remote", response_model=DatasetDetail, status_code=201)
def import_remote_dataset(
    project_id: str,
    payload: RemoteImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_remote_dataset(
            session,
            project,
            url=payload.url,
            name=payload.name,
            filename=payload.filename,
            headers=payload.headers,
            auth=(payload.auth.model_dump(exclude_none=True) if payload.auth is not None else None),
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{project_id}/datasets/s3", response_model=DatasetDetail, status_code=201)
def import_s3_dataset(
    project_id: str,
    payload: S3ImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_s3_dataset(
            session,
            project,
            bucket=payload.bucket,
            key=payload.key,
            endpoint=payload.endpoint,
            region=payload.region,
            access_key=payload.access_key,
            secret_key=(
                payload.secret_key.get_secret_value() if payload.secret_key is not None else None
            ),
            name=payload.name,
            filename=payload.filename,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post(
    "/{project_id}/datasets/websocket",
    response_model=DatasetDetail,
    status_code=201,
)
def import_websocket_dataset(
    project_id: str,
    payload: WebSocketImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_websocket_dataset(
            session,
            project,
            url=payload.url,
            name=payload.name,
            headers=payload.headers,
            auth=(payload.auth.model_dump(exclude_none=True) if payload.auth is not None else None),
            max_messages=payload.max_messages,
            timeout=payload.timeout,
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post(
    "/{project_id}/datasets/kafka",
    response_model=DatasetDetail,
    status_code=201,
)
def import_kafka_dataset(
    project_id: str,
    payload: KafkaImportRequest,
    session: DbSession,
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    try:
        dataset = project_service.import_kafka_dataset(
            session,
            project,
            bootstrap=payload.bootstrap,
            topic=payload.topic,
            group=payload.group,
            name=payload.name,
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
            options=_options(payload.options),
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)

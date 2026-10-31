"""Pydantic request and response models for M2 project and dataset APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from advp.charts.registry import ChartIntent
from advp.eu2_settings import NON_NULLABLE_FIELDS
from advp.ingest.files import MAX_PREVIEW_ROWS, MAX_SAMPLE_ROWS


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class ImportOptionsModel(BaseModel):
    encoding: str | None = None
    delimiter: str | None = Field(default=None, min_length=1, max_length=1)
    has_header: bool | None = None
    sheet: int | str | None = None
    variable: str | None = None
    shape: list[int] | None = None
    dtype: str | None = None
    byte_order: str | None = None
    raw_offset: int = Field(default=0, ge=0)
    sample_rows: int = Field(default=MAX_SAMPLE_ROWS, ge=1, le=MAX_SAMPLE_ROWS)
    preview_rows: int = Field(default=20, ge=1, le=MAX_PREVIEW_ROWS)


class DatasetCreate(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class RelocateRequest(BaseModel):
    path: str = Field(min_length=1)
    force: bool = False


class DocumentRequest(BaseModel):
    path: str = Field(min_length=1)
    force_text: bool = False


class TextFactInfo(BaseModel):
    fact_id: str
    subject_path: str
    metric: str
    value_text: str = ""
    value_number: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    unit: str | None = None
    qualifier: str | None = None
    relation: str = "standalone"
    note: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.5
    include: bool = True
    edited: bool = False
    canonical_group: str | None = None
    ai_enhanced: bool = False


class TextStatsLongPreview(BaseModel):
    facts: list[TextFactInfo] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class TextStatsWidePreview(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class TextDocumentInfo(BaseModel):
    char_count: int
    paragraph_count: int
    has_numbers: bool
    truncated: bool
    extractor: dict[str, str]
    long: TextStatsLongPreview
    wide: TextStatsWidePreview


class DocumentTableInfo(BaseModel):
    index: int
    source: str
    page: int | None
    table_index: int
    row_count: int
    column_count: int
    confidence: float
    headers: list[str]
    preview: list[list[str]]


class DocumentTablesResponse(BaseModel):
    path: str
    format: str
    source_sha256: str
    tables: list[DocumentTableInfo]
    text: TextDocumentInfo | None = None


class DocumentImportRequest(DocumentRequest):
    table_index: int = Field(default=0, ge=0)
    name: str | None = Field(default=None, max_length=200)
    has_header: bool = True
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class TextFactInput(BaseModel):
    fact_id: str | None = None
    subject_path: str = Field(min_length=1, max_length=300)
    metric: str = Field(min_length=1, max_length=300)
    value_text: str | None = None
    value_number: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    unit: str | None = Field(default=None, max_length=50)
    qualifier: str | None = Field(default=None, max_length=50)
    relation: str = "standalone"
    note: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0, le=1)
    include: bool = True
    edited: bool = False
    canonical_group: str | None = None
    ai_enhanced: bool = False


class TextStatsImportRequest(BaseModel):
    path: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    shape: Literal["long", "wide"] = "long"
    name: str | None = Field(default=None, max_length=200)
    facts: list[TextFactInput] = Field(min_length=1)
    ai: dict[str, Any] | None = None
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class TextStatsAIRequest(BaseModel):
    path: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    facts: list[TextFactInput] = Field(min_length=1)
    allow_ai: bool = False
    provider_id: str | None = None


class TextStatsAIResponse(BaseModel):
    source_sha256: str
    facts: list[TextFactInfo]
    warnings: list[dict[str, str]] = Field(default_factory=list)
    ai: dict[str, Any] = Field(default_factory=dict)


class RemoteAuth(BaseModel):
    type: str
    token: str | None = None
    username: str | None = None
    password: str | None = None
    header: str | None = None
    value: str | None = None


class WebSocketRequest(BaseModel):
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    auth: RemoteAuth | None = None
    max_messages: int = Field(default=100, ge=1, le=1000)
    timeout: float = Field(default=10.0, ge=1, le=120)


class WebSocketImportRequest(WebSocketRequest):
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class KafkaRequest(BaseModel):
    bootstrap: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    group: str | None = None
    max_messages: int = Field(default=100, ge=1, le=1000)
    timeout: float = Field(default=10.0, ge=1, le=120)
    auto_offset_reset: str = "earliest"
    security_protocol: str | None = None
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: SecretStr | None = None
    ssl_ca_location: str | None = None


class KafkaImportRequest(KafkaRequest):
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class StreamPreviewResponse(BaseModel):
    records: list[dict[str, Any]]
    count: int
    source: str


class LiveSessionCreate(BaseModel):
    kind: Literal["websocket", "kafka"]
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth: RemoteAuth | None = None
    bootstrap: str | None = None
    topic: str | None = None
    group: str | None = None
    auto_offset_reset: str = "latest"
    security_protocol: str | None = None
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: SecretStr | None = None
    ssl_ca_location: str | None = None
    max_messages: int = Field(default=1000, ge=10, le=5000)
    sample_interval_ms: int = Field(default=0, ge=0, le=60000)
    timeout: float = Field(default=10.0, ge=1, le=120)


class LiveSnapshotImportRequest(BaseModel):
    project_id: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class LiveSessionResponse(BaseModel):
    session_id: str
    kind: str
    status: str
    paused: bool
    error: str | None
    sequence: int
    count: int
    records: list[dict[str, Any]]
    created_at: float
    updated_at: float


class WebRequest(BaseModel):
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    auth: RemoteAuth | None = None


class WebTableInfo(BaseModel):
    index: int
    row_count: int
    column_count: int
    confidence: float
    headers: list[str]
    preview: list[list[str]]


class WebTablesResponse(BaseModel):
    url: str
    format: str
    tables: list[WebTableInfo]


class WebImportRequest(WebRequest):
    table_index: int = Field(default=0, ge=0)
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class RemoteImportRequest(BaseModel):
    url: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    filename: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth: RemoteAuth | None = None
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class S3ImportRequest(BaseModel):
    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)
    endpoint: str | None = None
    region: str | None = None
    access_key: str | None = None
    secret_key: SecretStr | None = None
    name: str | None = Field(default=None, max_length=200)
    filename: str | None = None
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class SqlConnectionRequest(BaseModel):
    url: str = Field(min_length=1)


class SqlColumnsRequest(SqlConnectionRequest):
    table: str = Field(min_length=1)


class SqlPreviewRequest(SqlConnectionRequest):
    query: str = Field(min_length=1)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SqlImportRequest(SqlConnectionRequest):
    query: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    max_rows: int = Field(default=100_000, ge=1, le=1_000_000)


class SqlConnectionResponse(BaseModel):
    ok: bool
    dialect: str
    database: str
    label: str


class SqlTableInfo(BaseModel):
    name: str
    schema_name: str | None
    type: str


class SqlTablesResponse(BaseModel):
    dialect: str
    tables: list[SqlTableInfo]


class SqlColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    default: str | None


class SqlColumnsResponse(BaseModel):
    dialect: str
    table: str
    columns: list[SqlColumnInfo]


class SqlPreviewResponse(BaseModel):
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    limit: int
    offset: int
    truncated: bool
    dialect: str


class ProjectSummary(BaseModel):
    id: str
    name: str
    schema_version: int
    archived: bool
    created_at: datetime
    updated_at: datetime
    dataset_count: int
    source_types: list[str]


class DatasetSummary(BaseModel):
    id: str
    project_id: str
    name: str
    version: int
    kind: str
    format: str
    source_path: str
    source_sha256: str
    source_size: int
    row_count: int
    row_count_estimated: bool
    column_count: int
    sampled: bool
    quality_score: int
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectSummary):
    settings: dict[str, Any]
    datasets: list[DatasetSummary]
    migration: dict[str, Any] | None = None


class DatasetDetail(DatasetSummary):
    options: dict[str, Any]
    schema_definition: dict[str, Any]
    profile: dict[str, Any]
    preview: list[dict[str, Any]]
    ignored_issues: list[str] = Field(default_factory=list)


class QualityApplyRequest(BaseModel):
    code: str = Field(min_length=1)
    column: str | None = Field(default=None, max_length=200)


class QualityIgnoreRequest(BaseModel):
    code: str = Field(min_length=1)


class QualityApplyResponse(BaseModel):
    code: str
    steps: list[dict[str, Any]]
    columns: list[str]
    affected_rows: int
    before_rows: int
    after_rows: int
    truncated: bool
    preview: list[dict[str, Any]]
    log: list[dict[str, Any]]


class InspectResponse(BaseModel):
    kind: str
    path: str
    format: str
    size_bytes: int
    mtime: float
    row_count: int
    column_count: int
    row_count_estimated: bool
    sampled: bool
    options: dict[str, Any]
    detected: dict[str, Any]
    schema_definition: dict[str, Any]
    profile: dict[str, Any]
    preview: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    variables: list[dict[str, Any]]


class PreviewResponse(BaseModel):
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    limit: int
    offset: int
    total_rows: int
    sampled: bool


class ManifestResponse(BaseModel):
    manifestVersion: int
    appVersion: str
    project: dict[str, Any]
    datasets: list[dict[str, Any]]


class TableChartCandidatesRequest(BaseModel):
    kind: Literal["table"]
    row_count: int = Field(ge=0)
    sampled: bool = False
    schema_definition: dict[str, Any]


class ArrayChartSchema(BaseModel):
    variable: str = Field(min_length=1)
    shape: list[int] = Field(min_length=1)
    dims: list[str] = Field(default_factory=list)
    dtype: str = Field(min_length=1)
    units: str | None = None
    sampled: bool = False


class ArrayChartCandidatesRequest(BaseModel):
    kind: Literal["array"]
    array: ArrayChartSchema


ChartCandidatesRequest = Annotated[
    TableChartCandidatesRequest | ArrayChartCandidatesRequest,
    Field(discriminator="kind"),
]


class DatasetChartCandidatesRequest(BaseModel):
    intent: ChartIntent | None = None


class ChartCandidateInfo(BaseModel):
    id: str
    name: dict[str, str]
    family: str
    backend: str
    rule_rank: int
    suggested_fields: dict[str, str] = Field(default_factory=dict)
    array_mapping: dict[str, Any] | None = None
    why: str
    supports: list[str]
    accessibility_notes: str
    notes: str


class ExcludedChartInfo(BaseModel):
    id: str
    reason_code: str
    message: str


class ChartCandidatesResponse(BaseModel):
    kind: str
    dataset_id: str | None = None
    intent: ChartIntent | None = None
    registry_version: int
    row_count: int | None = None
    candidates: list[ChartCandidateInfo]
    excluded: list[ExcludedChartInfo]


class ChartRegistryResponse(BaseModel):
    registry_version: int
    charts: list[dict[str, Any]]


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["openai", "anthropic"]
    base_url: str | None = Field(default=None, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr | None = None
    headers: dict[str, str] | None = None
    organization: str | None = Field(default=None, max_length=200)
    project: str | None = Field(default=None, max_length=200)
    anthropic_version: str = Field(default="2023-06-01", max_length=50)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_retries: int = Field(default=2, ge=0, le=10)
    proxy_url: str | None = Field(default=None, max_length=500)
    input_price_per_million: float = Field(default=0.0, ge=0)
    output_price_per_million: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", min_length=1, max_length=10)
    priority: int = Field(default=100, ge=0)
    is_default: bool = False


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Literal["openai", "anthropic"] | None = None
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: SecretStr | None = None
    headers: dict[str, str] | None = None
    clear_key: bool = False
    clear_headers: bool = False
    organization: str | None = Field(default=None, max_length=200)
    project: str | None = Field(default=None, max_length=200)
    anthropic_version: str | None = Field(default=None, max_length=50)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    proxy_url: str | None = Field(default=None, max_length=500)
    input_price_per_million: float | None = Field(default=None, ge=0)
    output_price_per_million: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=1, max_length=10)
    priority: int | None = Field(default=None, ge=0)
    is_default: bool | None = None


class ProviderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    base_url: str
    model: str
    organization: str | None
    project: str | None
    anthropic_version: str
    timeout_seconds: float
    max_retries: int
    proxy_url: str | None
    input_price_per_million: float
    output_price_per_million: float
    currency: str
    priority: int
    is_default: bool
    key_last4: str | None
    has_key: bool
    header_names: list[str]
    created_at: datetime
    updated_at: datetime


class ProviderTestResponse(BaseModel):
    ok: bool
    latency_ms: float
    models_supported: bool
    message: str | None = None


class ProviderModelsResponse(BaseModel):
    models: list[str]
    latency_ms: float


class ChartSelectionRequest(BaseModel):
    intent: ChartIntent | None = None
    provider_id: str | None = None
    max_reselects: int = Field(default=2, ge=0, le=2)


class ChartCorrectionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    provider_id: str | None = None


class ChartBuilderRequest(BaseModel):
    chart_id: str = Field(min_length=1, max_length=50)
    fields: dict[str, str] = Field(default_factory=dict)
    aggregation: Literal["sum", "mean", "median", "min", "max", "count"] | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    parent_selection_id: str | None = Field(default=None, max_length=32)
    reason: str | None = Field(default=None, max_length=500)


class SelectedChartInfo(BaseModel):
    chart_id: str
    name: dict[str, str]
    family: str
    backend: str
    fields: dict[str, str]
    aggregation: str | None = None
    reason: str
    confidence: float | None = None
    style: dict[str, Any] | None = None
    score: float
    dimensions: dict[str, float]


class SelectionTop3Entry(BaseModel):
    chart_id: str
    name: dict[str, str]
    score: float
    selected: bool
    reason: str


class SelectionUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    estimated_cost: float
    currency: str


class ChartSelectionResult(BaseModel):
    id: str
    dataset_id: str
    project_id: str
    provider_id: str | None
    provider_name: str | None
    model: str | None
    prompt_version: str
    source: str = "ai"
    intent: str | None
    selected: SelectedChartInfo
    top3: list[SelectionTop3Entry]
    attempts: int
    reselects: int
    degraded: bool
    degradation_reason: str | None
    needs_confirmation: bool
    budget: dict[str, Any] | None = None
    parent_selection_id: str | None = None
    correction_instruction: str | None = None
    usage: SelectionUsage
    created_at: datetime


class CleanStep(BaseModel):
    operation: str
    columns: list[str] = Field(default_factory=list)
    column: str | None = None
    strategy: str | None = None
    value: Any = None
    method: str | None = None
    factor: float = 1.5
    subset: list[str] | None = None
    mapping: dict[str, str] | None = None
    target: str | None = None


class CleanRequest(BaseModel):
    steps: list[CleanStep] = Field(min_length=1, max_length=20)
    dry_run: bool = False
    confirm_high_risk: bool = False


class CleanResponse(BaseModel):
    source_dataset_id: str
    derived_dataset_id: str | None
    cleaning_run_id: str | None
    dry_run: bool
    before_rows: int
    after_rows: int
    truncated: bool
    log: list[dict[str, Any]]
    preview: list[dict[str, Any]]


class CleaningRunSummary(BaseModel):
    id: str
    dataset_id: str
    derived_dataset_id: str | None
    parent_run_id: str | None
    before_rows: int
    after_rows: int
    truncated: bool
    created_at: datetime


class CleanUndoResponse(BaseModel):
    dataset_id: str
    cleaning_run_id: str | None
    message: str


class BudgetUpdate(BaseModel):
    project_limit: float | None = Field(default=None, ge=0)
    monthly_limit: float | None = Field(default=None, ge=0)
    warning_ratio: float = Field(default=0.8, ge=0, le=1)
    currency: str = Field(default="USD", min_length=1, max_length=10)


class BudgetStatusResponse(BaseModel):
    project_limit: float | None
    monthly_limit: float | None
    project_spend: float
    monthly_spend: float
    warning_ratio: float
    currency: str
    warning: bool
    exceeded: bool
    reason: str | None


class CostSummaryResponse(BaseModel):
    project_id: str
    period: str
    total_cost: float
    retry_cost: float = 0.0
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    currency: str
    by_provider: list[dict[str, Any]]
    by_model: list[dict[str, Any]]
    by_day: list[dict[str, Any]]
    by_tag: list[dict[str, Any]] = []
    by_operation: list[dict[str, Any]] = []
    by_run: list[dict[str, Any]] = []
    by_chart: list[dict[str, Any]] = []
    budget: BudgetStatusResponse


class DatasetAnalysisResponse(BaseModel):
    dataset_id: str
    analysis: dict[str, Any]


class ChartFigureResponse(BaseModel):
    selection_id: str
    dataset_id: str
    chart_id: str
    renderer: str
    figure: dict[str, Any]
    row_count: int
    sampled: bool
    max_rows: int


class ChartSelectionSummary(BaseModel):
    id: str
    dataset_id: str
    selected_chart_id: str
    score: float
    degraded: bool
    needs_confirmation: bool
    provider_name: str | None
    created_at: datetime


class PipelineRunCreate(BaseModel):
    intent: ChartIntent | None = None
    provider_id: str | None = None
    max_reselects: int = Field(default=2, ge=0, le=2)
    clean_steps: list[CleanStep] = Field(default_factory=list)
    confirm_high_risk: bool = False
    report_language: str = Field(default="zh", pattern="^(zh|en)$")
    report_template: str = Field(default="standard", pattern="^(standard|compact)$")
    report_conclusion: str | None = None
    report_include_chart: bool = False
    auto_start: bool = True


class ReportRegenerate(BaseModel):
    language: str = Field(default="zh", pattern="^(zh|en)$")
    template: str = Field(default="standard", pattern="^(standard|compact)$")
    conclusion: str | None = None
    include_chart: bool = True


class ExportJobCreate(BaseModel):
    kind: str = Field(pattern="^(report|selection)$")
    target_id: str
    format: str = Field(pattern="^(html|pdf)$")
    options: dict[str, Any] = Field(default_factory=dict)


class TargetExportCreate(BaseModel):
    format: str = Field(default="pdf", pattern="^(html|pdf)$")
    options: dict[str, Any] = Field(default_factory=dict)


class ImportJobCreate(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class ImportJobDetail(BaseModel):
    id: str
    project_id: str
    status: str
    stage: str
    progress: float
    message: str | None
    payload: dict[str, Any]
    result_dataset_id: str | None
    error: str | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime


class MultiFileSourceInfo(BaseModel):
    path: str
    name: str
    row_count: int
    column_count: int
    sampled: bool


class MultiFileRequest(BaseModel):
    paths: list[str]
    mode: Literal["union", "join"] = "union"
    left_key: str | None = Field(default=None, max_length=200)
    right_key: str | None = Field(default=None, max_length=200)
    how: Literal["inner", "left", "right", "full"] = "inner"
    name: str | None = Field(default=None, max_length=200)
    options: ImportOptionsModel = Field(default_factory=ImportOptionsModel)


class MultiFilePreviewResponse(BaseModel):
    mode: str
    files: list[MultiFileSourceInfo]
    columns: list[str]
    left_rows: int | None = None
    right_rows: int | None = None
    result_rows: int
    match_rate: float | None = None
    duplicate_keys: dict[str, int] | None = None
    conflicts: list[str]
    sampled: bool
    preview: list[dict[str, Any]]


class PipelineStepInfo(BaseModel):
    id: str
    key: str
    name: str
    position: int
    status: str
    attempts: int
    placeholder: bool
    output: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class PipelineRunSummary(BaseModel):
    id: str
    dataset_id: str
    parent_run_id: str | None = None
    status: str
    current_step: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class PipelineRunDetail(PipelineRunSummary):
    project_id: str
    pause_requested: bool
    cancel_requested: bool
    options: dict[str, Any]
    started_at: datetime | None
    steps: list[PipelineStepInfo]


class ProviderUsageRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str | None
    provider_name: str
    kind: str
    model: str
    operation: str
    tag: str = "initial"
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: float
    estimated_cost: float
    currency: str
    attempts: int
    created_at: datetime


class SettingValue(BaseModel):
    value: Any
    source: Literal["env", "settings", "default"]


class Eu2SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["zh", "en"] | None = None
    workspace: str | None = None
    analysis_sample_rows: int | None = Field(default=None, ge=1, le=100_000)
    render_sample_rows: int | None = Field(default=None, ge=1, le=100_000)
    default_provider_id: str | None = None
    global_budget: float | None = Field(default=None, ge=0)
    monthly_budget: float | None = Field(default=None, ge=0)
    search_raw_content: bool | None = None
    search_sensitive: bool | None = None
    search_excluded_projects: list[str] | None = None
    sandbox_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    log_redaction: bool | None = None
    update_channel: Literal["stable", "beta"] | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_null_non_nullable(cls, data: Any) -> Any:
        if isinstance(data, dict):
            invalid = sorted(
                name for name in NON_NULLABLE_FIELDS if name in data and data[name] is None
            )
            if invalid:
                raise ValueError(f"fields may not be null: {', '.join(invalid)}")
        return data

# Changelog

All notable changes to ADVP are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every atomic commit is one version and one entry below; the patch number increments
by the number of files added, deleted, or modified, excluding only the daily work
record. `VERSION`, this file, and the release tag must always agree. See
`docs/版本管理细则.md`.

## [Unreleased]

## [1.0.0] - 2026-10-28

### Added

- release: ADVP 1.0.0, including text statistics extraction, local service
  lifecycle management, portable runtime packaging, and Inno Setup installer.
- test(report): add a browser regression for inline share-page chart capture and
  PDF rendering.

### Fixed

- fix(report): render share chart images and PDFs from the inline single-file
  share page, avoiding `file://` ES-module CORS blocking.

### Changed

- build(installer): support reproducible portable-runtime builds via
  `build_installer.ps1 -Portable -PythonHome`, with conda-pack as fallback.
- build(installer): ship the Chinese Simplified installer language file and the
  installer README/license notices from the repository.
- docs: add the M7 exit acceptance report and synchronize release documentation.

## [0.8.371] - 2026-10-27

### Added

- feat(system): add `GET /api/system/lifecycle` and `POST /api/system/shutdown`
  with active pipeline/export/3D/live counts and graceful uvicorn exit.
- feat(ui): add a top-right shutdown control with idle confirmation, active-task
  warning and second confirmation, closed-state overlay, and a browser leave hint.
- test(system): cover disabled development mode, authorization, force shutdown,
  task counts, delayed callback, and a real subprocess exit.
- build(release): produce the 0.8.371 portable ZIP and Inno Setup installer,
  with a bundled README and silent install/uninstall verification.

### Changed

- build(launcher): run uvicorn through `uvicorn.Server` and install the shutdown
  callback; source development mode keeps shutdown disabled.
- docs: update the SRS, acceptance criteria, page specification, technical summary,
  compatibility checklist, installer guide, README, and daily work record for D46.

## [0.8.355] - 2026-10-27

### Changed

- docs(srs): add D46 local service shutdown requirement

## [0.8.349] - 2026-10-27

### Added

- test(text): add the real `test1.docx` fixture and a default-suite regression
  covering 23 facts, key values, long/wide import, manifest, and preview.
- test(text): add an Edge browser E2E for the document check, inline editing,
  long-table import, pipeline run, AI opt-in default, and report download.

### Changed

- docs(compat): update C-11 evidence with the backend fixture and Edge UI E2E.

## [0.8.345] - 2026-10-27

### Added

- feat(text): read local TXT/DOCX/PDF text layers, Markdown, RTF, and HTML into
  heading-aware blocks with page and paragraph positions.
- feat(text): extract subjects, metrics, numeric ranges, approximations, units,
  alternatives, and total/part relationships with rule-first confidence and warnings.
- feat(api): return text statistics candidates from `documents/inspect` and import
  edited long/wide tables with source hashes, manifests, and audit events.
- feat(ui): add editable long/wide candidates, warnings, import controls, and
  explicit opt-in AI enhancement.
- feat(ai): add `documents/text/ai` with numeric-snippet-only payloads, unknown-fact
  rejection, value immutability, cost tracking, and rule fallback on failure.

### Changed

- docs(report): label text-statistics datasets and their extraction method/limitations.
- build(deps): add `striprtf` and record its BSD-3-Clause license.

## [0.8.292] - 2026-10-27

### Added

- docs(text): add the text statistics extraction design for local DOCX/TXT/PDF/MD/RTF/HTML,
  including editable long/wide candidates, rule-first extraction, opt-in AI enhancement,
  and a seven-task TDD implementation plan.
- feat(ui): add provider name and base URL presets while keeping manual input.

### Changed

- docs: extend the SRS, acceptance criteria, page specification, technology summary,
  development plan, compatibility checklist, and READMEs for FR-ING-017 / D45.

### Fixed

- fix(ingest): explain documents without tables instead of returning an empty candidate list.
- fix(ui): route PDF/DOCX paths to the document/text panel and clear stale document candidates.

## [0.8.261] - 2026-10-27

### Changed

- build(public): add sanitized public export and snapshot

## [0.8.238] - 2026-10-27

### Changed

- docs(readme): rewrite as user-facing product manual

## [0.8.219] - 2026-10-27

### Changed

- test(m7): add blind evaluation tooling

## [0.8.198] - 2026-10-27

### Changed

- build(m7): add installer scripts and packaged launcher

## [0.8.171] - 2026-10-27

### Changed

- docs(test): record full-system test results

## [0.8.151] - 2026-10-27

### Changed

- test(m7): add browser main-flow smoke and compatibility checklist

## [0.8.127] - 2026-10-27

### Changed

- perf(m7): add benchmark harness and small baseline

## [0.8.102] - 2026-10-27

### Changed

- feat(m7): add same-origin launcher and session authentication

## [0.8.70] - 2026-10-27

### Changed

- test(m6): add tiered parallel test suite and close M6

## [0.8.45] - 2026-10-26

### Changed

- fix(m6): complete residual compare, logging, cost, exports, and sandbox hardening

## [0.8.0] - 2026-10-26

### Changed

- feat(m6): add reports, traceability, security, audit, and cost

## [0.7.37] - 2026-10-26

### Changed

- fix(m5): complete residual sampling, render recovery, and animation resume

## [0.7.0] - 2026-10-26

### Changed

- feat(m5): complete 3D scientific visualization

## [0.6.388] - 2026-10-26

### Changed

- feat(m5): add 3D animation and scene code export

## [0.6.361] - 2026-10-26

### Changed

- feat(m5): add trame SciView sessions

## [0.6.330] - 2026-10-26

### Changed

- feat(m5): add independent 3D renderer and jobs

## [0.6.294] - 2026-10-26

### Changed

- feat(m5): add VTK.js 3D scene viewer

## [0.6.268] - 2026-10-26

### Changed

- feat(m5): add 3D geometry payloads and LOD

## [0.6.241] - 2026-10-26

### Changed

- feat(m5): add versioned Scene JSON and persistence

## [0.6.214] - 2026-10-26

### Changed

- docs(m5): add 3D scientific visualization design and plan

## [0.6.193] - 2026-10-26

### Changed

- feat(m4): add incremental SSE and global admin-1 region maps

## [0.6.128] - 2026-10-26

### Changed

- feat(m4): make code exports runnable

## [0.6.106] - 2026-10-26

### Changed

- feat(m4): harden live Kafka reconnect and backlog

## [0.6.82] - 2026-10-26

### Changed

- feat(m4): support 4D DICOM slices

## [0.6.59] - 2026-10-26

### Changed

- feat(m4): add per-renderer share bundles and single-file HTML

## [0.6.21] - 2026-10-26

### Changed

- docs(m4): add residual remediation design and plan

## [0.6.0] - 2026-10-26

### Changed

- feat(m4): complete chart families, live streams, and exports

## [0.5.270] - 2026-10-26

### Changed

- feat(m4): add offline share, PDF, and code exports

## [0.5.236] - 2026-10-26

### Changed

- feat(m4): add live stream sessions and SSE realtime chart

## [0.5.204] - 2026-10-26

### Changed

- feat(m4): add imaging slice API and VTK viewer

## [0.5.173] - 2026-10-26

### Changed

- feat(m4): render map families with deck.gl

## [0.5.144] - 2026-10-26

### Changed

- feat(m4): add network, sankey, and sunburst rendering

## [0.5.109] - 2026-10-26

### Changed

- feat(m4): add registry v3 and family selection contracts

## [0.5.72] - 2026-10-26

### Changed

- docs(m4): add implementation design and plan

## [0.5.51] - 2026-10-26

### Fixed

- Markdown reports now state the configurable render/analysis windows instead of
  the obsolete 200-row preview limit.
- Report tests and the technical-selection document now match the current
  `ADVP_RENDER_SAMPLE_ROWS` / `ADVP_ANALYSIS_SAMPLE_ROWS` behavior.

### Changed

- Code/document consistency pass: registry v2, `geo_scatter`, version fields,
  work-record status, and stale M3/M4 statements are aligned.

## [0.5.28] - 2026-10-26

### Added

- M4 map-family first slice: `geo_scatter` with latitude/longitude roles,
  optional value/size/label mappings, offline Plotly `scattergeo` rendering, and
  PNG/SVG export through the existing figure path.
- Registry version 2 adds the `map` family and `geo` semantic group; rule
  candidates, AI context, scoring, and semantic validation support the new roles.

### Changed

- Geographic point charts use a 50,000-row limit and natural-earth projection
  with offline land/ocean/country/coastline styling.
- Chart registry, selector, scoring, render, API, and end-to-end tests now cover
  the map slice.

## [0.5.0] - 2026-10-26

### Added

- M3 end-to-end acceptance harness covering 10 datasets across CSV, JSON,
  JSONL, Parquet, Excel, HDF5, NetCDF, FITS, NIfTI, and SQLite SQL.
- Deterministic mock-provider path for AI selection, scoring, usage, and cost
  assertions, plus explicit rule-fallback checks when no provider is configured.
- Manual `scripts/m3_real_provider_smoke.py` for a real OpenAI-compatible
  provider; it reads a local key file at runtime and never logs or persists the
  credential.
- M3 exit acceptance report with per-dataset results, real-provider usage, and
  known limitations.

### Changed

- M3 exit version is `v0.5.0`; the real-provider smoke uses
  `deepseek-flash` because model `1017` is not available on the configured
  endpoint (HTTP 400).

## [0.4.498] - 2026-10-26

### Changed

- feat(m3): make analysis and render windows configurable

### Added

- Configurable data windows: `ADVP_RENDER_SAMPLE_ROWS` (default 20,000, max
  100,000) for chart rendering and `ADVP_ANALYSIS_SAMPLE_ROWS` (default 10,000,
  max 100,000) for analysis summaries.
- Render responses report the effective window as `max_rows`.

### Changed

- Chart rendering now uses a 20,000-row window instead of the previous 200-row
  preview, reducing sampling artifacts in 2D charts.
- `.env.example` documents both sampling settings.

## [0.4.473] - 2026-10-25

### Added

- Frontend chart export buttons for PNG and SVG using Plotly's image download.
- Exported images use 1200×700 at 2× scale with an `advp-<selection>` filename.

### Changed

- The `plotly.js-dist-min` type declaration now includes `downloadImage`.

## [0.4.451] - 2026-10-25

### Added

- Advanced chart style hints: colorscale range (`min`/`max`), legend position,
  and up to 10 annotations with optional x/y coordinates.
- Plotly applies annotation layout, legend placement, and heatmap `zmin`/`zmax`.
- Frontend style chips show annotation count and legend position.

### Changed

- `colorscale_min` must be lower than `colorscale_max`.

## [0.4.426] - 2026-10-25

### Added

- Pipeline `report` step writes a Markdown report into
  `ADVP_WORKSPACE/exports/<project_id>` with profile, quality, analysis,
  selection/Top3, pipeline steps, cost, lineage, and limitations.
- `GET /api/pipeline-runs/{id}/report` downloads the completed Markdown report.
- Frontend pipeline panel offers a Markdown report download link.

### Changed

- The report step is no longer a placeholder; the pipeline chain is fully
  materialized through Markdown.
- PDF export and static chart embedding remain deferred.

## [0.4.398] - 2026-10-25

### Added

- Optional chart style hints on selections and corrections: title, x/y axis
  titles, `#RRGGBB` color, colorscale, legend visibility, and log axes.
- Plotly rendering applies selection styles to titles, axes, trace colors, and
  heatmap colorscales.
- Frontend style chips show the active title, color, and log-axis hints.

### Changed

- Style colors are validated as six-digit hex values.
- Annotation editing remains deferred.

## [0.4.370] - 2026-10-25

### Added

- Natural-language chart corrections: re-run structured selection against the
  same candidate set/schema, recompute scores/Top3, and persist a child selection
  with `parent_selection_id` and the correction instruction.
- `POST /api/chart-selections/{id}/correct` and a frontend correction input on the
  AI selection result card.
- Correction usage is recorded under the dataset project; exhausted budgets block
  corrections.

### Changed

- `chart_selections.parent_selection_id` is added with an additive SQLite
  migration.
- Corrections are limited to chart/field/aggregation changes; styling-only edits
  remain deferred.

## [0.4.338] - 2026-10-25

### Added

- Project/monthly cost budgets with warning ratio and currency, plus cost
  aggregation by provider, model, and day.
- `llm_usage.project_id` with an additive SQLite migration; AI selection usage is
  attributed to the dataset's project.
- `GET/PATCH /api/projects/{id}/budgets` and `GET /api/projects/{id}/costs`.
- Frontend cost panel with budget limits, spend, token totals, and breakdowns.
- AI selection degrades to the rule top1 when a project or monthly budget is
  exceeded, and includes budget status in the persisted result.

### Changed

- Budget warnings are surfaced in selection results; task-level budgets and
  queued pause/resume remain deferred.

## [0.4.300] - 2026-10-25

### Added

- Pipeline `clean` step: accept `clean_steps` and `confirm_high_risk`, create a
  derived dataset, and switch `working_dataset_id` for downstream steps.
- Pipeline frontend accepts an optional cleaning recipe JSON and a high-risk
  confirmation checkbox.

### Changed

- Pipeline chain is now
  `profile → clean → candidates → analyze → selection → render → report`.
- Empty cleaning recipes mark the `clean` step as skipped and keep the source
  dataset as the working dataset.
- Downstream pipeline steps reload the working dataset after cleaning.

## [0.4.273] - 2026-10-25

### Added

- Deterministic cleaning recipes: drop/fill missing, IQR/z-score/quantile/
  winsorize outlier clipping, deduplication, type casting, column renaming, and
  confirmed column deletion.
- Derived Parquet datasets with lineage metadata, a bounded 100,000-row cleaning
  window, and a per-step change log.
- Cleaning APIs for preview/apply, history, undo-last-step, and rollback.
- Frontend cleaning panel with a step builder, preview/apply, change log,
  undo, and rollback.

### Changed

- Column deletion requires explicit high-risk confirmation.
- Source files are never modified; cleaning writes derived datasets into the
  workspace and records `derived_from`, cleaning run id, recipe version, and
  truncation state.
- Cleaning is currently separate from the fixed pipeline step chain.

## [0.4.241] - 2026-10-25

### Added

- Deterministic analysis summaries: numeric distribution/skewness, strong
  correlations (`|r| >= 0.5`), temporal span/gaps, geographic ranges, and
  categorical top values, using up to 10,000 preview rows.
- `POST /api/datasets/{id}/analysis` and `GET /api/datasets/{id}/analysis`;
  results are cached in `profile_json.analysis`.
- Pipeline `analyze` step between candidates and selection; the summary is fed
  into the AI selection context.
- Frontend analysis panel with correlations, numeric distributions, temporal
  gaps, geo ranges, and an explicit "generate summary" action.

### Changed

- Pipeline step chain is now
  `profile → candidates → analyze → selection → render → report`.
- Sensitive semantic columns are excluded from categorical analysis summaries.

## [0.4.207] - 2026-10-25

### Changed

- Align the frontend home copy and footer with current M3 capabilities.
- Make the release guide refer to the current `VERSION` and full tag history
  instead of stale `v0.2.102` values.
- Update the documentation index date and the render status in the technology
  summary (table rendering is implemented; report remains a placeholder).
- Record the code/documentation synchronization audit in the daily work log.

## [0.4.187] - 2026-10-25

### Added

- Plotly 2D figure rendering for persisted chart selections: bar, horizontal
  bar, line/area, scatter/bubble, histogram, box, violin, heatmap, pie/donut,
  radar, parallel coordinates, and regression.
- `GET /api/chart-selections/{id}/figure` returns Plotly figure JSON built from
  a 200-row preview window.
- Frontend `Plotly.js` rendering with a dynamically loaded chart bundle and a
  "show chart" action on the AI selection result.
- Pipeline `render` now produces a real figure for table selections; `report`
  remains a placeholder.

### Changed

- Table render results mark `sampled=true` when the source is larger than the
  preview window; larger array heatmaps return explicit errors until sampled
  array access is implemented.
- Added the Python `plotly` dependency and `plotly.js-dist-min` frontend
  dependency.

## [0.4.151] - 2026-10-25

### Added

- Persisted pipeline runs and steps with a linear DAG:
  `profile → candidates → selection → render → report`.
- Pipeline APIs for create/list/detail, pause/resume/cancel, and retrying a
  failed step with downstream reset; BackgroundTasks execution with polling.
- Frontend pipeline panel showing step states, outputs, errors, and lifecycle
  controls.
- Explicit placeholder render/report steps until M4/M6.

### Changed

- Pause/cancel are cooperative and apply after the current step.
- Failed-step retry resets that step and all downstream steps to `pending`.

## [0.4.119] - 2026-10-25

### Added

- AI chart selection: structured provider output constrained to the rule
  candidate set, semantic validation, seven-dimension scoring, Top3, automatic
  reselection, provider failover, and rule fallback.
- Persisted `chart_selections` records with candidate/context snapshots, prompt
  version, provider/model, scores, Top3, attempts, reselects, degradation state,
  and token/cost totals.
- Dataset selection endpoints and a frontend AI selection result card with
  scores, Top3, provider metadata, cost, and degraded/confirmation states.

### Changed

- Selection context sends metadata plus up to three masked samples per column;
  full rows are not sent.
- Reselection thresholds use 0.75 total score and 0.08 top1/top2 gap, with at
  most two reselects and a rule top1 fallback when all providers fail.

## [0.4.82] - 2026-10-25

### Added

- Provider foundation: OpenAI-compatible and Anthropic-compatible clients,
  Windows Credential Manager storage, provider CRUD, connection tests, model
  listing, structured JSON output with one repair retry, and usage/cost records.
- SQLite `providers` and `llm_usage` tables plus `/api/providers` endpoints.
- Temporary P08-preview provider settings panel with masked keys, connection
  tests, model lists, and recent usage.

### Changed

- API keys and custom header values are stored only in `keyring`; the database
  keeps last-four metadata and header names.
- Provider errors are classified and transient failures retry with backoff.
- Estimated cost uses editable per-million-token prices per provider/model.

### Verified

- Backend provider credential/client/structured/API tests and full backend suite
  pass; frontend lint, typecheck, tests, and build pass.

## [0.4.41] - 2026-10-25

### Added

- M3 first slice: versioned chart capability registry with 16 `2d` Plotly chart
  specs and deterministic rule-based candidate selection.
- `GET /api/charts/registry`, `POST /api/charts/candidates`, and
  `POST /api/datasets/{id}/chart-candidates` with explainable exclusions.
- Numeric 1D/2D/3D scientific-array heatmap candidates; 3D arrays default to a
  first-dimension slice.
- Temporary front-end "chart candidates (rule preview)" panel in the data
  workbench.

### Changed

- Chart selection uses `ruleRank` as a 1-based rule ordering, explicitly not the
  FR-SEL-004 score or an AI confidence.
- Registry contract in `docs/技术选型摘要.md` §3.3 now documents `dataKinds`,
  `intents`, `maxCardinality`, `arrayDims`, `constraints`, and accessibility
  notes.
- Mypy compatibility fixes for existing document/stream type ignores and model
  annotations.

### Verified

- Backend: ruff/format, mypy (43 files), and 64 pytest tests pass.
- Frontend: ESLint, tsc, Vitest (3 tests), and production build pass.
- Array boundary: 1D/2D/3D numeric heatmap mapping; non-numeric, empty, and
  4D arrays return explicit errors.

## [0.4.0] - 2026-10-25

### Added

- M2 milestone: project/dataset persistence with schema migration, JSON backups,
  portable manifests, and source relocation.
- Tabular ingestion (CSV/TSV/JSON/JSONL/Parquet/XLSX/XLS), scientific arrays
  (HDF5/NetCDF/FITS), and imaging/volume sources (DICOM/NIfTI/RAW).
- Read-only SQL connectors (SQLite/PostgreSQL/MySQL) with derived-Parquet import.
- Remote HTTP(S)/S3 files, PDF/DOCX table candidates, static HTML tables, and
  bounded WebSocket/Kafka windows.
- Profiling: semantic types, statistics, quality issues, sensitive-field
  detection, sampling, and estimated row counts.
- Frontend data workbench: projects, file/SQL/remote/document/web/stream panels,
  previews, quality reports, and array summaries.

### Changed

- External sources materialize into `ADVP_WORKSPACE/derived` and reuse the
  table/array pipeline; original sources are never modified.
- Credentials for remote/S3/SQL/streams are request-scoped and never persisted.
- Large files use sampled profiles and estimated counts rather than full loads.

### Verified

- 34 backend tests, frontend lint/typecheck/tests/build, 10 open datasets, a live
  single-node Kafka smoke, gitleaks, and public-snapshot checks pass.
- Documented limits: dynamic JavaScript web pages are not rendered yet; S3 is
  tested with a fake client; 5 GB physical files are not tested; Kafka is
  single-node only.

## [0.2.231] - 2026-10-25

### Added

- DICOM series directory/single-file, NIfTI (`.nii/.nii.gz`), and RAW
  (`.raw/.bin`) imaging/volume ingestion as array datasets.
- RAW `shape`, `dtype`, `byte_order`, and `raw_offset` options plus a front-end
  RAW advanced-options panel.
- Directory hashing for DICOM series as a sorted manifest of relative paths and
  file hashes.

### Changed

- Scientific source routing and hashing now support directories; DICOM/NIfTI
  auto-profile their single series/volume while HDF5/NetCDF/FITS still list
  variables first.
- Backend dependencies: pydicom and nibabel.
- `README.md` and `backend/README.md`: imaging/volume support and RAW example.

### Verified

- Backend ruff/format/mypy/pytest pass (22 tests, including 3 imaging tests).
- NIfTI 2x3x4 float32, DICOM 3x4x5 series, and RAW 3x4 int16 pass
  inspect/import; missing RAW options and undersized files return
  `invalid_source`.
- Frontend ESLint, tsc, Vitest, and production build pass.

## [0.2.201] - 2026-10-24

### Added

- Project and dataset persistence (SQLite + SQLAlchemy) with schemaVersion
  migration, JSON backups, and portable manifests.
- M2 REST API: project CRUD, dataset inspect/import/list/detail/preview,
  reprofile, relocate, and source-change detection.
- Tabular ingestion for CSV/TSV/JSON/JSONL/Parquet/XLSX/XLS with encoding,
  delimiter, and header detection plus manual overrides; 5 GiB limit and
  path/SHA-256 references without copying source data.
- Data profiling: semantic types, null/unique/statistics/outliers, quality
  issues with blocking/warning/info severities, sensitive-field detection and
  masking, sampling, and estimated row counts.
- Scientific-array ingestion: HDF5, NetCDF, and FITS variable browsing, sampled
  reads, array profiles, units/dims metadata, and index/value previews.
- `Dataset.kind` (`table`/`array`) with an additive SQLite migration for local
  databases created before scientific-array support.
- Read-only SQL connectors for SQLite, PostgreSQL, and MySQL: connection test,
  table/view browsing, column metadata, query preview, and import.
- SQL imports materialize read-only `SELECT`/`WITH` results to derived Parquet
  under the workspace, with a 100,000-row default cap and truncation warning.
- Frontend data workbench: project create/select, path inspection/import,
  preview table, quality issues, sensitive columns, reprofile, scientific
  variable selection with array summaries, and a SQL import panel.

### Changed

- `.gitignore`: make runtime `data`, `derived`, `exports`, `workspace`, and
  `logs` paths root-relative so `backend/src/advp/ingest` is tracked.
- `README.md` and `backend/README.md`: M2 status, endpoints, and data behavior.
- Backend dependencies: Polars, fastexcel, charset-normalizer, openpyxl,
  types-openpyxl, h5py, netCDF4, xarray, astropy, numpy, psycopg, and pymysql.
- `ADVP_WORKSPACE` now controls the derived-data root; project deletion removes
  the project's derived directory.
- SQL connection URLs and passwords are used per request and never persisted;
  error messages redact passwords.
- Quality scores cap the warning penalty at 80 so advisory-heavy datasets do not
  collapse to zero; blocking issues still force a zero score.

### Verified

- Backend ruff/format/mypy/pytest pass (19 tests, including HDF5/NetCDF/FITS
  and SQLite SQL connectors).
- Frontend ESLint, tsc, Vitest, and production build pass.
- End-to-end smoke: create project -> inspect CSV -> import -> preview;
  3 rows, 3 columns, quality score 90.
- Scientific fixtures: HDF5 3x4 K array, NetCDF 2x2x3 degC array, FITS 2x3 Jy
  image; variable selection, profiles, import, and preview pass.
- SQLite SQL smoke: connection test, table browsing, paginated preview, derived
  Parquet import, and read-only/password-redaction checks pass.
- PostgreSQL and MySQL live servers are not available on this machine; shared
  SQLAlchemy paths are covered by the SQLite tests only.

## [0.2.152] - 2026-10-24

### Added

- `spikes/s07_kafka/run_extended.py`: three-broker KRaft (RF=3, minISR=2),
  SASL_SSL/PLAIN, reconnect backoff, and 20k backlog harness.
- `.gitleaks.toml`: repository-wide allowlist for dependencies, caches, build
  output, and local artifacts; exported with the public snapshot.
- `--require-software` and OpenGL vendor/renderer/version reporting in the
  S-01 offscreen harness.

### Changed

- `spikes/s01_mayavi_vtk`: conda-pack 0.9.2 packaging, cross-path relocation,
  `conda-unpack`, and Mesa3D 26.2.4 llvmpipe software-rendering evidence.
- `spikes/s07_kafka`: extended Windows Kafka evidence (3-node RF=3 ISR
  3->2->3, SASL_SSL + PLAIN, 8.7 s outage recovery, 20k backlog drain).
- `spikes/s06_public_export`: gitleaks 8.30.1 working-tree, full-history, and
  public-snapshot scans recorded.
- `scripts/export_public.ps1`: export `.gitleaks.toml` and pass it explicitly
  to gitleaks.

### Verified

- S-01: pack 1,248,514,451 B; relocated renders 38,334 B / 70,627 B; software
  renders 38,240 B / 70,639 B with Mesa llvmpipe OpenGL 4.6.
- S-07: baseline offset resume; 3-node ISR 3->2->3; SASL_SSL 60/60 with
  plaintext rejected; reconnect recovery 15.67 s without replay; 20k backlog
  drained at 6,159 msg/s.
- gitleaks: 0 findings in the working tree, 20-commit history, and public
  snapshot.
- Public snapshot: 0.91 MB; version, links, and prototype checks pass.

## [0.2.123] - 2026-10-24

### Fixed

- `docs/GitHub发布指南.md`: replace stale v0.2.8 status, tag ranges, and sync
  notes with the current v0.2.123 state and the public-snapshot marker rule.
- `docs/版本管理细则.md`: state that the P0 scaffold is ready while product
  features are still pending, and document `.advp-public-snapshot`.
- `docs/技术选型摘要.md` and `docs/验收标准.md`: remove hard-coded v0.2.8
  cross-references.
- `docs/内部文档索引.md`: include S-06 in the spike index entry.
- `frontend/src/App.tsx` and `App.test.tsx`: remove the stale 0.2.8 fallback and
  mock version so the UI cannot display an outdated release number.

### Verified

- Private and public-snapshot `check_version.py`, `check_links.py`,
  `check_prototype.py`, and markdownlint all pass.
- Frontend lint, typecheck, Vitest, and production build pass.
- `git grep` finds no stale release version in application code.

## [0.2.102] - 2026-10-24

### Added

- `spikes/s06_public_export/REPORT.md`: export, sanitization, exclusion, and
  snapshot self-check evidence for P0-09/S-06.

### Fixed

- `scripts/check_version.py` no longer requires maintainer-only documents or a
  daily work log in a public snapshot, so the public repository CI can pass.
- `scripts/export_public.ps1` now writes an explicit `.advp-public-snapshot`
  marker; private checkouts still validate every versioned document and the
  latest daily work log.

### Verified

- Private `check_version.py`: version 0.2.102 consistent.
- Public snapshot: version, links, and prototype checks pass; internal docs,
  work logs, and `spikes/` are absent.
- gitleaks and the second human reviewer remain outstanding for P0-09.

## [0.2.79] - 2026-10-24

### Added

- `spikes/s01_mayavi_vtk/`: reproducible VTK + Mayavi offscreen render harness
  with pinned Python 3.12 dependencies and a JSON verdict.
- `spikes/s07_kafka/`: single-node KRaft Windows harness covering produce,
  consume, broker restart, committed-offset resume, and automatic short-path
  mapping for the Kafka launcher.
- `spikes/README.md` and per-spike reports with environment, evidence, verdicts,
  and remaining risks.

### Changed

- `docs/需求说明书.md`: remove the stale hard-coded v0.2.8 sentence so the
  document control table is the single version reference.
- `docs/内部文档索引.md`: add the internal spike index entry.

### Verified

- S-01 offscreen render: VTK 9.7.1 and Mayavi 4.9.0 each produced a valid
  640x480 PNG on Python 3.12.13.
- S-07: Kafka 3.9.1 KRaft survived a forced restart; the consumer group resumed
  at committed offsets 80/80/80 without replaying the first 120 messages.
- S-01 conda-pack packaging remains unverified; tracked as an M1 follow-up.

## [0.2.51] - 2026-10-23

### Added

- `backend/`: FastAPI + Pydantic v2 + SQLAlchemy scaffold with SQLite and
  `GET /api/health`.
- `backend/tests/test_health.py` and ruff/mypy/pytest gates.
- `frontend/`: React 19 + TypeScript + Vite scaffold with a dark health page,
  `/api` proxy, ESLint, tsc, Vitest, and production build.
- Local development instructions in `CONTRIBUTING.md`.

### Changed

- Version synchronization now covers `backend/pyproject.toml`,
  `frontend/package.json`, and `frontend/package-lock.json`.
- First patch using the file-count rule: 43 files, version `0.2.8` to `0.2.51`.

## [0.2.8] - 2026-10-23

### Added

- `docs/版本管理细则.md`: version format, file-based revision counting, daily
  work log, tag, push, milestone, and rollback rules.
- `docs/README.md` and `docs/内部文档索引.md`: public and maintainer document indexes.
- `docs/【2026-10-23】开发工作记录.md`: confirmation and governance session log.
- FR-LOG-007 and FR-LOG-008: daily development work log and version-management
  requirements.

### Changed

- Reworked `README.md` into a minimal user-facing project introduction; moved
  engineering, CI, versioning, dual-repository, and technology details to
  `CONTRIBUTING.md`, `docs/版本管理细则.md`, and the internal index.
- Reordered milestone versions: M1 0.3.0, M2 0.4.0, M3 0.5.0, M4 0.6.0,
  M5 0.7.0, M6 0.8.0, P6 0.9.0, M7 1.0.0.
- v0.2.8 is the rule-establishing baseline; file counting starts with the next
  change.
- Synchronized version fields across all versioned documents.

## [0.2.7] - 2026-10-23

### Changed

- docs(confirm): confirm requirements batches B-D; requirements baseline is now locked.
- Batch B: functional requirements 3.1–3.16, NFRs, and data requirements confirmed.
- Batch C: interfaces, architecture, UI, TBD-01–TBD-32, and ADR-0008–0010 confirmed.
- Batch D: acceptance criteria, plan, risks, and EXT-04–EXT-06 confirmed.
- SRS, confirmation register, technology summary, acceptance criteria, page spec,
  plan, README, and GitHub guide synchronized to v0.2.7.

## [0.2.6] - 2026-10-23

### Changed

- docs(confirm): confirm batch A and archive work log

## [0.2.5] - 2026-10-23

### Changed

- docs(log): add 2026-10-22 development work record

## [0.2.4] - 2026-10-23

### Changed

- fix(ci): force UTF-8 Python output on Windows runners

## [0.2.3] - 2026-10-23

### Changed

- fix(ci): replace Windows-incompatible lychee action with local link checker

## [0.2.2] - 2026-10-23

### Changed

- fix(ci): correct frontend working-directory and document private protection limit

## [0.2.1] - 2026-10-22

### Changed

- docs(repo): add GitHub publication guide and ignore local agent state

## [0.2.0] - 2026-10-22

### Added

- `LICENSE` switched to Apache-2.0, with `NOTICE` and `THIRD_PARTY_NOTICES.md`.
- Kafka is now a required v1 realtime connector alongside WebSocket.

### Changed

- License changed from MIT to Apache-2.0 (patent grant and compatibility).
- Delivery plan changed to single-developer, full-scope, 40–48 weeks.
- SRS, technology, acceptance, page, and confirmation documents synchronized
  to v0.2.0.

### Security

- Public export allowlist now includes `NOTICE` and `THIRD_PARTY_NOTICES.md`.
- Kafka offset/reconnect acceptance added to the security and reliability scope.

## [0.1.1] - 2026-10-22

### Changed

- fix(repo): sanitize public export paths and checks

## [0.1.0] - 2026-10-22

### Added

- `docs/需求说明书.md` and `docs/需求说明书.docx`: ADVP v1 requirements baseline
  (D01–D44), 13 chapters, 40 tables, acceptance criteria, traceability matrix.
- `docs/技术选型摘要.md`: 3D hybrid backend, AI provider adapter, sandbox,
  packaging, licensing, CI, and dual-repository strategy.
- `docs/验收标准.md`: functional, performance, chart-selection blind review,
  security, compatibility, documentation, and repository acceptance cases.
- `docs/页面清单与交互说明.md`: 10-page information architecture, interactions,
  states, and dark scientific design tokens.
- `docs/prototype/index.html`: offline single-file high-fidelity prototype with
  10 pages (P01–P10), no external dependencies.
- `docs/开发计划与里程碑.md`: 16–24 week phased plan, milestones M1–M7, risks.
- `docs/需求确认清单.md`: D01–D44 decision register, TBD-01–TBD-32 defaults,
  external information requests, and sign-off workflow.
- Repository governance: `VERSION`, `CHANGELOG.md`, `.gitignore`, CI workflow,
  commitlint, markdownlint, version checker, version bump script, ADR index.
- Documentation tooling: `scripts/build_docx.py`, `scripts/check_prototype.py`,
  `scripts/check_version.py`, `scripts/bump_version.py`,
  `scripts/export_public.ps1`.

### Changed

- Established the local-first, single-user Windows web app architecture.
- Established the rule-filter + AI selection + scoring + Top3 chart strategy.
- Established SemVer patch-per-change and squash-merge workflow (pending user
  confirmation of the exact granularity).

### Security

- Plaintext `api_key.txt` is removed and ignored; API keys must use Windows
  Credential Manager. If the removed key was real, rotate it at the provider.
- gitleaks, dependency audit, and public-repository export checks are wired into
  the delivery process.

# Changelog

All notable changes to ADVP are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every logical change is one atomic commit, one patch version, and one entry below.
`VERSION`, this file, and the release tag must always agree.

## [Unreleased]

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

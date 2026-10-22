# ADVP — Automated Data Visualization Platform

ADVP 是一个面向科研与分析的 AI 辅助数据可视化工具：导入数据后，由大模型驱动完成**提取 → 分析 → 清洗 → 图表选型 → 渲染 → 报告**的全自动管线；面向 3D 科学可视化提供 Mayavi/VTK 级能力，同时保留 2D、地图、网络、时序与影像图表家族。

> 当前状态：**v0.2.4 需求基线，待用户确认**。本仓库当前包含需求、技术选型、验收标准、页面原型、开发计划与版本治理脚手架；产品代码尚未开始实现。

## 快速开始

| 目标 | 操作 |
|---|---|
| 查看高保真原型 | 直接用浏览器打开 `docs/prototype/index.html`（单文件、离线可用） |
| 阅读需求书 | `docs/需求说明书.md`，或打开 `docs/需求说明书.docx` |
| 生成 Word 版 | `python scripts/build_docx.py`；如需自动目录与页码，运行 `powershell -ExecutionPolicy Bypass -File scripts/build_docx.ps1`（需已安装 Word） |
| 校验原型结构 | `python scripts/check_prototype.py` |
| 校验版本一致性 | `python scripts/check_version.py` |
| 递增版本 | `python scripts/bump_version.py --message "docs: ..."` |

## 交付物

| 文档 | 说明 |
|---|---|
| [需求说明书](docs/需求说明书.md) | 功能/非功能/数据/接口/验收/追溯，D01–D44 决策基线 |
| [需求说明书 Word](docs/需求说明书.docx) | 评审用版本，含封面、目录、页眉页脚 |
| [技术选型摘要](docs/技术选型摘要.md) | 3D 双后端、AI 适配、沙箱、打包、许可、双仓库 |
| [验收标准](docs/验收标准.md) | 功能、性能、盲评、安全、兼容、文档验收用例 |
| [页面清单与交互说明](docs/页面清单与交互说明.md) | 10 页信息架构、交互、状态、设计令牌 |
| [高保真原型](docs/prototype/index.html) | 深色科研风，P01–P10，离线单文件 |
| [开发计划与里程碑](docs/开发计划与里程碑.md) | 单人 40–48 周阶段、M1–M7、风险与关键路径 |
| [需求确认清单](docs/需求确认清单.md) | 逐项确认矩阵、TBD 默认值、需提供的外部信息 |

## 核心范围（v1）

- Windows 10/11 本地 Web 应用，单用户，内置运行环境。
- OpenAI 兼容 + Anthropic 兼容接口，自定义 Base URL / API Key / 模型。
- 数据：CSV/Excel/JSON/Parquet/HDF5/NetCDF/FITS/DICOM/NIfTI/RAW、SQL、远程 URL/云、WebSocket + Kafka 实时流；PDF/Word 表格与网页抽取（无 OCR）。
- 图表：统计 2D、3D 科学、地图、网络/桑基/旭日、时序/实时、影像切片。
- 3D：VTK.js（浏览器交互）+ Mayavi/VTK（服务端体渲染/流场/动画），统一 Scene JSON。
- 选图：规则硬筛 → AI 决策 → 自动评分重选 → 低置信度 Top3 兜底。
- 产出：交互视图、PNG/SVG/PDF、MP4/GIF、独立 HTML、Python/Notebook、Markdown/PDF 报告。
- 全链路可追溯、成本预算、离线只读、Windows 凭据管理器、受限子进程沙箱。
- 中英双语界面，深色科研风；开源（Apache-2.0）。
- 单人开发，全范围不削减，计划 40–48 周（v1.0）。

## 版本与提交规范

本项目采用严格的“最小版本变动”：

1. 一次逻辑修改 = 一个原子 commit = 一次 **patch** 版本递增（如 `0.1.0 → 0.1.1`）。
2. 每个 PR 使用 **squash merge**，合并后只产生一个 commit。
3. 每个 patch 必须同时更新 `VERSION`、`CHANGELOG.md` 与 SRS 文档版本行。
4. 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)。
5. `main` 受保护，必须通过 CI（ruff/mypy/pytest、eslint/tsc/vitest、gitleaks、commitlint、markdownlint、链接检查、依赖审计）。
6. 发布时打 `vX.Y.Z` tag；公开仓库与私有仓库保持同版本 tag。

推荐流程：

```powershell
python scripts/bump_version.py --message "docs: clarify chart selection threshold"
python scripts/build_docx.ps1
git add -A
git commit -m "docs: clarify chart selection threshold"
git tag v0.1.1
```

> 当前基线（v0.2.4）尚未完成用户逐项确认；确认后按同一流程递增 patch。

## 双仓库策略

| 仓库 | 可见性 | 内容 |
|---|---|---|
| `advp` | Public | 源码、文档、原型、CI、脱敏示例 |
| `advp-private` | Private | 全量源码、内部文档、实验记录、非敏感样本 |

公开仓库通过白名单导出，不包含密钥、`.env`、日志、派生数据、用户样本或绝对路径：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_public.ps1 -Target ..\advp-public
```

导出脚本会执行敏感信息扫描，并在目标目录初始化 Git、提交快照并打同版本 tag。推送前请人工复核 `git diff`。

## 安全

- 密钥只存 **Windows Credential Manager**；界面仅显示掩码与末 4 位。
- 任何日志、工程、导出物、Git 历史中不得出现明文密钥。
- 生成代码在本地受限子进程中执行：禁网、仅工作区读写、CPU/内存/时长限制。
- 默认仅向模型发送元数据与样本；全量外发需二次确认并留痕。
- 原 `api_key.txt` 已删除；如果它曾是真实密钥，请立即到供应商后台轮换。

安全策略详见 [SECURITY.md](SECURITY.md)。

## 技术栈（摘要）

- 前端：React + TypeScript + Vite + Tailwind；Plotly.js、ECharts、VTK.js、deck.gl、Cytoscape.js。
- 后端：Python 3.12 + FastAPI + Pydantic v2 + SQLite + Huey。
- 数据：Polars/DuckDB、xarray、h5py、netCDF4、Astropy、pydicom、nibabel。
- 3D：VTK.js + Mayavi/VTK + trame；conda-pack + Inno Setup 打包。
- 质量：ruff、mypy、pytest、eslint、tsc、vitest、Playwright、gitleaks。

详见 [技术选型摘要](docs/技术选型摘要.md)。

## 目录

```text
.
├── docs/                 # 需求、技术、验收、页面、计划、原型、ADR
├── scripts/              # 文档构建、校验、版本递增、公开仓库导出
├── .github/workflows/    # CI（文档、质量、安全、版本）
├── VERSION               # SemVer
├── CHANGELOG.md          # Keep a Changelog
├── LICENSE               # Apache-2.0
├── NOTICE                # Apache NOTICE
├── THIRD_PARTY_NOTICES.md
└── README.md
```

## 许可

本项目使用 **Apache License 2.0**（见 `LICENSE` 与 `NOTICE`）。第三方组件与许可清单见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)；发布前必须从实际锁文件重新生成并审计。Qt/PySide6 仅动态链接，FFmpeg 使用 LGPL 构建。

## 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。所有贡献必须通过 CI 与代码审查，并遵守版本规则与安全约定。

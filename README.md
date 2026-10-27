# ADVP — 自动化数据可视化平台

ADVP（Automated Data Visualization Platform）是一款面向科研与数据分析的本地 AI 可视化工作台。导入数据后，ADVP 帮助你完成数据理解、质量检查、清洗、图表选型、渲染与报告，并重点提供科研级 3D 可视化能力。

> 当前版本：需求基线已确认（v1.0.0）；已正式发布。按用户决定跳过代码签名与人工验收；自动化与当前机发布物验证通过。

## 产品定位

- **本地优先**：数据、工程、日志与导出默认保存在本机，不需要上传到云端。
- **科研导向**：支持表格、科学数组、影像/体数据、SQL、远程文件与实时流。
- **AI 辅助而非黑盒**：规则筛选 + AI 选型 + 七维评分；预算、降级与追溯可见。
- **可交付**：报告、静态图、分享包、可复现 Python/Notebook、Scene JSON 与 manifest。
- **Windows 桌面体验**：仅监听回环地址，浏览器界面，中英双语文案。

## 核心能力

| 能力 | 说明 |
|---|---|
| 数据接入 | CSV/TSV/JSON/JSONL/Parquet/Excel、HDF5/NetCDF/FITS、DICOM/NIfTI/RAW、SQLite/PostgreSQL/MySQL、HTTP(S)/S3、PDF/DOCX 表格、静态网页表格、WebSocket/Kafka |
| 文本统计 | 本地 DOCX/TXT/PDF/MD/RTF/HTML 正文抽取统计事实；长/宽表候选、编辑确认、规则优先与可选 AI 增强 |
| 数据理解 | Schema 推断、画像、质量评分、缺失/重复/异常/敏感字段识别、分析摘要 |
| 清洗 | 缺失填充、异常裁剪、去重、类型转换、重命名、删列、撤销与回滚 |
| 图表选型 | 规则候选 → AI 选型/修正 → 七维评分 → Top3 → 降级与预算控制 |
| 2D 图表 | 柱/条/折线/面积/散点/气泡/直方图/箱线/小提琴/热力/饼图/雷达/平行坐标/回归 |
| 地图 | deck.gl 点位、轨迹、六边形密度、区域填色，内置离线国界 |
| 网络/层级 | Cytoscape 网络；ECharts 桑基图、旭日图 |
| 时序/实时 | 静态时间序列；WebSocket/Kafka 实时会话与 SSE 增量窗口 |
| 影像 | HDF5/NetCDF/FITS/DICOM/NIfTI/RAW 影像切片、窗宽窗位、伪彩、三视图 |
| 科研 3D | Scene JSON v1、VTK.js、Mayavi/VTK 离屏渲染、trame SciView、动画、LOD/采样 |
| 报告 | Markdown/HTML/PDF、中英文、模板、自定义结论、图表截图、追溯附录 |
| 追溯/复现 | 管线 DAG、血缘、模型/Token/费用、代码查看/diff、从步重跑、manifest |
| 安全/运维 | 回环服务、会话令牌、CSP、脱敏 JSONL 日志、审计事件、诊断包、受限沙箱、本地服务关闭 |
| 成本 | Provider/模型/日期/任务/图表/标签聚合、预算预警、CSV 导出、重选/重试标记 |

## 快速开始

### 安装包

提供便携 ZIP 与 Inno Setup 安装器（未签名）。安装器为每用户安装，默认数据目录为 `%USERPROFILE%\.advp`，卸载默认保留用户数据。当前开发机也可从源码运行。

### 从源码运行

前置：Windows 10/11、Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22。

```powershell
cd backend
uv sync
uv run python scripts/advp_launcher.py
```

启动器会自动选择空闲回环端口、生成一次性令牌并打开浏览器。前端构建存在时，后端会直接托管 SPA。

开发模式（前后端分离）：

```powershell
# 终端 1
cd backend
uv run uvicorn advp.main:app --reload --host 127.0.0.1 --port 8765

# 终端 2
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。

### 首次使用

1. 新建工程。
2. 输入本地文件路径，点击“检查文件”，确认后导入。
3. 在数据工作台运行分析管线。
4. 查看图表、报告与追溯信息。
5. 按需导出 HTML/PDF/Python/Notebook 或 3D Scene。
6. 在成本面板查看 Token、费用与预算。

使用完毕后，可在页面右上角点击“关闭本地服务”释放资源。启动器/安装包模式下，关闭前会检查运行中的管线、导出、3D 渲染与实时流并二次确认；关闭浏览器标签页不会停止后端。

## 数据接入说明

- 原始文件只保存路径、哈希与大小，不复制到工程。
- 表格：CSV/TSV/JSON/JSONL/Parquet/XLSX/XLS。
- 科学数组：HDF5（`.h5/.hdf5/.he5`）、NetCDF（`.nc/.nc4/.cdf`）、FITS（`.fits/.fit/.fts`）。
- 影像/体数据：DICOM 目录或 `.dcm`、NIfTI（`.nii/.nii.gz`）、RAW（需 shape 与 dtype）。
- SQL：只允许 `SELECT`/`WITH`，连接信息按请求使用，不持久化。
- 远程：HTTP(S)/S3 下载到派生工作区；凭据按请求使用。
- 文档/网页：PDF/DOCX 表格候选；静态 HTML 表格。
- 文本统计：DOCX/TXT/PDF（文本层）/MD/RTF/HTML 正文中的“主体 + 指标 + 数值 + 单位”事实；生成长表与宽表候选，确认后导入。
- 实时：WebSocket/Kafka 有界窗口与内存态实时会话。

默认限制：单文件 5 GiB；画像最多 100,000 行；分析窗口 10,000 行；渲染窗口 20,000 行；3D 最大元素 50,000,000；浏览器内联体素 2,000,000。

## 3D 科学可视化

- **Scene JSON v1**：数据、几何、相机、光照、色标、传输函数、裁剪、动画、后端与采样统一描述。
- **浏览器**：VTK.js 点云、切片、等值面、体渲染；适合中等规模与实时交互。
- **服务端**：独立 VTK/Mayavi 离屏渲染进程；适合体渲染、大网格与动画。
- **trame SciView**：本机会话内探索体/点云，支持窗宽与不透明度调整。
- **动画**：相机旋转/关键帧路径、断点续渲、MP4/GIF。
- **LOD**：超出预算自动步长采样，并在结果中标注 `sampled`/`lod`。

## 报告、追溯与复现

- 报告：Markdown/HTML/PDF，含数据概览、质量、分析、图表、结论、管线/成本、限制与追溯附录。
- 追溯：每步状态、耗时、尝试、错误；AI 步骤显示模型、提示词版本、Token 与费用。
- 血缘：原始文件 → 派生数据集 → 图表 → 报告。
- 复现：Python/Notebook、Scene JSON、Mayavi 脚本与导出 manifest。
- 重跑：可从任一步骤创建子运行，保留旧运行并对比状态/耗时/费用。

## 安全与隐私

- 仅监听 `127.0.0.1`，校验 Host、Origin 与可选会话令牌。
- Provider API Key 只存 Windows 凭据管理器；界面只显示掩码。
- 日志为 JSON Lines，14 天滚动；密钥与绝对路径默认脱敏。
- 诊断包只包含脱敏配置与日志。
- 生成代码在本地受限子进程沙箱中验证；不是容器级隔离。
- AI 功能需要联网；查看、重渲染非 AI 图表与导出已有结果可离线使用。
- 数据外发默认仅元数据与样本；不会自动上传原始文件。

## 成本与预算

- 每次模型请求记录输入/输出/缓存 Token、耗时与估算费用。
- 支持项目级与月度预算、预警比例；达到上限时 AI 选型降级为规则 Top1。
- 成本面板按 Provider、模型、日期、任务运行、图表、操作/标签聚合，可导出 CSV。
- 重选、修正与重试费用单独标记，不与首次生成混淆。

## 配置

通过环境变量或 `.env` 调整；完整模板见 [.env.example](.env.example)。

| 变量 | 默认 | 说明 |
|---|---|---|
| `ADVP_HOST` / `ADVP_PORT` | `127.0.0.1` / `8765` | 本地服务地址；启动器会改用随机端口 |
| `ADVP_DATABASE_PATH` | `~/.advp/advp.db` | SQLite 数据库 |
| `ADVP_WORKSPACE_DIR` | `~/.advp/workspace` | 派生数据、报告与导出 |
| `ADVP_BACKUP_DIR` | `~/.advp/backups` | Schema 迁移备份 |
| `ADVP_STATIC_DIR` | 自动发现 | 打包前端目录 |
| `ADVP_SHARE_DIR` | 自动发现 | 分享包 bundle 目录 |
| `ADVP_MAX_FILE_BYTES` | `5368709120` | 单文件上限 |
| `ADVP_PROFILE_SAMPLE_ROWS` | `100000` | 画像采样行数 |
| `ADVP_ANALYSIS_SAMPLE_ROWS` | `10000` | 分析采样行数 |
| `ADVP_RENDER_SAMPLE_ROWS` | `20000` | 渲染采样行数 |
| `ADVP_3D_MAX_ELEMENTS` | `50000000` | 3D 元素上限 |
| `ADVP_LOG_LEVEL` / `ADVP_LOG_DIR` | `INFO` / 自动 | 日志级别与目录 |
| `ADVP_AUTH_TOKEN` | 空 | 可选本地令牌；启动器自动生成 |
| `ADVP_RENDER_PYTHON` | 空 | 独立 VTK/Mayavi/trame 解释器 |

## 系统要求

| 项目 | 最低 | 推荐 |
|---|---|---|
| 操作系统 | Windows 10/11 | Windows 11 |
| CPU / 内存 | 4 核 / 16 GB | 8 核 / 32 GB |
| 显卡 | 集成显卡（软件渲染） | NVIDIA 8 GB+ |
| 磁盘 | SSD 50 GB 可用 | NVMe 100 GB+ |
| 浏览器 | Edge / Chrome 当前版本 | Edge / Chrome 当前版本 |
| 源码运行 | Python 3.12、Node.js 22、uv | 同上 |

## 故障排查

- **页面提示后端未连接**：确认服务已启动；源码模式检查 `127.0.0.1:8765/api/health`。
- **启动器打开空白页**：确认 `frontend/dist` 或 `ADVP_STATIC_DIR` 存在，或使用 `npm run dev`。
- **PDF/图表截图失败**：需要 Playwright + Edge/Chromium；Markdown/HTML 仍可用。
- **3D 服务端渲染不可用**：配置 `ADVP_RENDER_PYTHON`，并运行 `uv run python scripts/render3d_worker.py --probe`。
- **AI 选型降级**：检查 Provider 配置、凭据、网络与预算；降级结果会在选型中标注。
- **大数据变慢**：查看 `sampled`/`lod` 提示；可调整采样窗口或使用 Parquet/按需列。

## 已知限制

- 仅支持 Windows 10/11；v1 不提供 OCR、本地模型、多用户、实时协作或 SaaS。
- 代码沙箱为本地受限子进程，不是容器级隔离。
- trame 会话仅本机回环；4D DICOM 假定同一 series 内多帧文件帧数一致。
- 大体积浏览器体/等值面依赖采样 values；超大体积建议服务端 Mayavi。
- 文本统计不做 OCR；仅本地规则 + 可选 AI 增强，AI 默认关闭且只发送含数字片段，结果必须人工确认。
- 安装器未签名；干净机、代表硬件 5GB/1GB 全量与人工盲评按用户决定跳过，作为已知风险保留。

## 路线图

| 阶段 | 状态 | 内容 |
|---|---|---|
| M1–M4 | 完成 | 规范/CI、数据接入、AI 编排、2D/地图/网络/时序/影像 |
| M5 | 完成 | 3D 双后端与 Scene JSON |
| M6 | 完成 | 报告、追溯、安全、审计与成本 |
| M7 | 已发布 | 性能、安装包、兼容、盲评、文本统计抽取与 v1.0.0；签名与人工验收按用户决定跳过 |

## 文档

| 内容 | 入口 |
|---|---|
| 文档索引 | [docs/README.md](docs/README.md) |
| 需求说明 | [docs/需求说明书.md](docs/需求说明书.md) |
| 技术选型 | [docs/技术选型摘要.md](docs/技术选型摘要.md) |
| 页面与交互 | [docs/页面清单与交互说明.md](docs/页面清单与交互说明.md) |
| 高保真原型 | [docs/prototype/index.html](docs/prototype/index.html) |
| 变更记录 | [CHANGELOG.md](CHANGELOG.md) |
| 安全策略 | [SECURITY.md](SECURITY.md) |
| 第三方许可 | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

## 许可与反馈

- 安全策略：[SECURITY.md](SECURITY.md)
- 第三方许可：[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- 许可证：[Apache-2.0](LICENSE)
- 问题反馈：请附版本、操作系统、复现步骤与脱敏诊断包；不要在 issue 中粘贴 API Key。

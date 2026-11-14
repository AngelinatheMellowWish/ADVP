# ADVP 2.1 页面一致性矩阵

| 项目 | 内容 |
|---|---|
| 文档编号 | ADVP-EU21-PARITY-20261114 |
| 版本 | v0.1 |
| 日期 | 2026-11-14 |
| 目标版本 | ADVP 2.1.0 |
| 原型基线 | `docs/prototype/index.html`（P01–P10） |
| 状态 | Task 20 交付；P01–P10 控件逐项标注 |

> 本矩阵只判断信息架构、控件、交互与状态语义，不要求像素级复刻。状态取值：
> **已实现**、**替代实现**（能力存在但形态不同）、**设计演进**（2.1 新增/调整）、
> **受环境限制**（缺少外部运行时或端点时明确禁用/skip）、**明确不做**（用户已确认排除）。

---

## 1. 全局外壳与跨页面

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 侧边栏 P01–P10、工作流/工具分组 | 已实现 | `frontend/src/app/Sidebar.tsx` | 导航与路由一致 |
| 顶栏面包屑、搜索、命令面板、语言、通知、帮助、系统状态、关闭服务 | 已实现 | `Topbar.tsx`、`SearchDialog.tsx`、`CommandPalette.tsx`、`NotificationCenter.tsx` | 仅回环、会话令牌 |
| 刷新保留工程上下文；无工程空状态 | 已实现 | `ProjectProvider.tsx`、各页面空状态 | `startup_behavior` 控制首页/上次工程 |
| 任务条（导入/管线/导出/3D/实时流） | 已实现 | `TaskBar.tsx`、`TaskProvider.tsx` | 计数与跳转 |
| 通知未读/历史/全部已读/清空/上限 | 已实现 | 通知 API 与 `NotificationCenter` | 1000 条/30 天 |
| 中英切换与词条同步 | 已实现 | `i18n/locales/zh.ts`、`en.ts`、`i18n.test.tsx` | 新增文案均双语 |
| 键盘焦点、Esc 关闭对话框、表单 label | 已实现 | `shell.css`、`test_eu21_accessibility.py` | `:focus-visible`；P10 控件均有 label |
| 全局错误含原因/影响/建议/诊断 | 已实现 | 稳定 `code`/`message`/`hint`、诊断包 | 新增端点遵循同一约定 |
| 四档宽度 1440/1280/1024/768 无横向溢出 | 已实现 | `backend/tests/test_eu21_visual.py`、`build/eu21-visual/` | P01–P10 截图证据 |

---

## 2. P01 工程首页

原型：`docs/prototype/index.html#page-p01`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 欢迎区、主标题、副标题 | 已实现 | `P01Home.tsx` | 对齐原型文案 |
| 新建工程 | 已实现 | `P01Home.tsx` | 创建对话框 |
| 导入数据快捷入口 | 已实现 | `P01Home.tsx` | 进入最近工程 P02，无工程时新建 |
| 查看全部 | 已实现 | `P01Home.tsx` | 完整任务/活动列表 |
| 最近工程卡片：打开/重命名/归档/删除/打开所在文件夹 | 已实现 | `ProjectCard.tsx`、`ProjectCard.test.tsx` | 文件与目录源均可定位 |
| 系统状态：服务/Provider/GPU/磁盘/数据库/CPU/内存/网络 | 已实现 | `SystemStatusCard.tsx` | 缺失网络显示 unknown |
| 最近活动/任务列表与筛选 | 已实现 | `P01Home.tsx` | 任务 + 审计事件合并 |
| 示例工程入口 | 已实现 | `sample.py`、`P01Home.tsx` | 合成表/体数据/DOCX |
| 启动行为：首页/上次工程 | 设计演进 | `router.tsx`、`startup_behavior` | 默认上次工程；可切回首页 |

---

## 3. P02 数据导入

原型：`docs/prototype/index.html#page-p02`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 六类来源页签：文件/数据库/远程/文档/网页/实时流 | 已实现 | `P02Import.tsx`、`test_eu21_visual.py` | 2026-11-05 用户确认保留“网页” |
| 文件路径、选择文件、拖拽、预览、确认导入 | 已实现 | `P02Import.tsx`、`AdvancedFileOptions.tsx` | 原生选择器 + 上传副本 |
| 编码/分隔符/表头/采样行数/工作表/变量 | 已实现 | `AdvancedFileOptions.tsx`、`import_options.py` | 真实影响 inspect/import |
| 缺失值标记、类型覆盖 | 已实现 | `ImportOptions`、`test_import_options.py` | 非法值置空 + `invalid_type_override_value` warning |
| 多文件：独立/纵向合并/Join | 已实现 | `MultiFileDialog.tsx`、`multifile.py` | Join 冲突列 `_left/_right` |
| 逐文件进度、取消、重试 | 已实现 | `P02Import.tsx`、`import_jobs.py` | 独立 job 列表 |
| 数据库：测试连接/浏览表列/只读预览/物化导入 | 已实现 | `SqlImportPanel.tsx`、SQL API | 仅 SELECT/WITH |
| 可选“记住此连接”、删除、忘记凭据 | 已实现 | `sql_connections.py`、`ConnectionManager` | 默认请求级；密码仅 keyring |
| 远程 HTTP(S)/S3、认证、超时、自定义 Header | 已实现 | `RemoteSourceForm.tsx`、`remote.py` | 凭据请求级 |
| 文档表格候选、文本统计长/宽表编辑 | 已实现 | `TextStatsCandidates.tsx` | 长表编辑、宽表派生 |
| AI 增强默认关闭、仅数字片段、显式确认 | 已实现 | `textstats_ai.py`、P02 E2E | 不发送完整正文 |
| 网页静态表格 + Playwright 渲染兜底 | 已实现 | `WebSourceForm.tsx`、`web.py` | 显示 static/rendered、耗时、warning |
| SSRF 防护与可操作错误 | 已实现 | `web_guard.py`、`test_web_guard.py` | 默认阻断回环/内网 |
| 实时流 WebSocket/Kafka、窗口、试连、快照导入 | 已实现 | `LiveSourceForm.tsx`、`live.py` | 有界窗口 |
| 字段选择/重命名/排除 | 已实现 | `field_mapping`、Task 6A | 导入前重组 |
| 消息格式选择 | 受环境限制 | `LiveSourceForm.tsx` | JSON/JSONL 自动解析；Protobuf/CSV 为提示项 |
| 外部数据库/S3/Kafka 真实环境 | 受环境限制 | `test_external_services_real.py` | 无端点时显式 skip + 替代验证 |

---

## 4. P03 数据预览与质量

原型：`docs/prototype/index.html#page-p03`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 数据集摘要、字段列表、预览表 | 已实现 | `P03Data.tsx` | — |
| 分页、列宽、列头统计 | 已实现 | `P03Data.tsx`、`test_eu21_visual.py` | 服务端翻页 |
| 质量评分、问题列表、质量报告文本 | 已实现 | `QualityPanel.tsx` | blocking/warning/info |
| 应用建议、忽略问题、查看影响 | 已实现 | `QualityPanel.tsx`、quality API | 应用生成派生数据集 |
| 缺失率 Top6、相关性、分布图 | 已实现 | `AnalysisCharts.tsx` | 轻量 SVG，无新增重依赖 |
| 分析摘要（分布/偏度/时间/地理/分类） | 已实现 | `analysis.py` | 采样/截断有标记 |
| 敏感字段配置、类型覆盖、重新计算统计 | 已实现 | `profile-overrides` API、`P03Data.tsx` | 只改 profile/下游语义，不改源文件 |
| “将发送给 AI 的上下文”预览 | 已实现 | `AiContextPreview.tsx` | 只读、不发请求 |
| 导出采样 1k/10k/100k/全量 | 已实现 | `export/sample` API、Task 7A | 全量二次确认；敏感列掩码 |
| Parquet 导出 | 明确不做（2.1） | `P03Data.tsx` | 禁用并显示 `parquet_export_unavailable` |
| 采样/截断/脱敏说明 | 已实现 | CSV 尾部说明、界面提示 | NF-10 |

---

## 5. P04 AI 管线运行

原型：`docs/prototype/index.html#page-p04`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 时间线、当前步骤、事件日志 | 已实现 | `PipelineTimeline.tsx`、`PipelineEventLog.tsx`、SSE | 实时 + 轮询兜底 |
| 运行、暂停、恢复、取消、失败重试 | 已实现 | `pipelines.py`、`P04Pipeline.tsx` | 协作式暂停/取消 |
| 步骤详情、输入输出摘要 | 已实现 | `P04Pipeline.tsx` | 输出与错误可见 |
| 预算与降级独立卡 | 已实现 | `pipeline-budget-card`、Task 11 | 预算来源/剩余/原因 |
| Top3、七维评分与理由 | 已实现 | `charts/scoring.py`、P05 评分卡 | 低分需确认 |
| 对话修正、diff、子选型 | 已实现 | `correct` API、`P04Pipeline.tsx` | 保留父选型 |
| Provider 失败/预算/并发降级 | 已实现 | `degraded`、稳定原因码 | 不静默 |
| 默认管线步骤开关 | 设计演进 | `default_pipeline_options`、Task 18 | clean/analyze/report 默认开 |
| 事件日志持久化过滤 | 已实现 | `pipeline_events`、P09 日志面板 | 等级/步骤/关键字 |

---

## 6. P05 图表工作台

原型：`docs/prototype/index.html#page-p05`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 字段、编码槽、画布、图表配置 | 已实现 | `P05Charts.tsx`、`ChartFigure.tsx` | Plotly/VTK/deck.gl 等 |
| 图表标签页与“+”、多图表 | 已实现 | `P05Charts.tsx` | 2.0 已交付 |
| 撤销/重做/重置 | 已实现 | `P05Charts.tsx` | 本地历史 |
| 筛选、聚合、X/Y/右轴、排序、缺失处理 | 已实现 | 图表构建 API、配置面板 | 支持范围以注册表为准 |
| 标题、颜色、图例、柱模式、对数轴、双轴、色盲配色 | 已实现 | `style` hints、渲染器 | 色盲配色沿用 2.0 |
| 选型评分、说明、Top3 | 已实现 | `scoring-card`、Task 10 | 七维分数 |
| 添加计算字段 | 已实现 | `CalculatedFieldDialog.tsx`、`calculated.py` | 安全 AST DSL + 派生数据集 |
| 数值函数扩展 | 已实现 | Task 10A | abs/round/floor/ceil/sqrt/exp/log/log10/clip/min/max/pow |
| 派生数据集可见、血缘、叠算、撤销冲突 | 已实现 | `calculated.py`、数据集列表 | `calculated_dependency_conflict` |
| 代码、Notebook、导出图表 | 已实现 | `code_export.py`、导出 API | PNG/SVG/HTML/PDF |
| 加入报告 | 已实现 | Task 11 | 必须已有运行；写入 `chart_selection_ids` |
| 查看候选 | 已实现 | 候选 API、P05 面板 | 规则候选 |

---

## 7. P06 3D 科学视图

原型：`docs/prototype/index.html#page-p06`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 数据源、几何类型、渲染后端、标量字段 | 已实现 | `P06Scene.tsx`、`scene.py` | Scene JSON v1.1 |
| 色标、范围上下限 | 已实现 | `RenderPanel` | — |
| 传输函数（双曲线） | 已实现 | `TransferFunctionEditor`、EU2-4 | 服务端渲染对等 |
| 裁剪、光照、标注 | 已实现 | `P06Scene.tsx` | — |
| 动画与断点续渲 | 已实现 | `render3d.py`、动画导出 | MP4/GIF（环境可用时） |
| 性能/采样提示 | 已实现 | `sampled`/`lod` 标记 | LOD/步长采样 |
| 顶部工具条：切换后端/重置/截图/导出动画/保存 Scene JSON | 已实现 | `scene-toolbar`、Task 11 | 切换保留相机/传输函数 |
| 服务端不可用时禁用并提示 `ADVP_RENDER_PYTHON` | 已实现 | `RenderPanel`、probe | — |
| 真实 Mayavi/VTK/trame 渲染 | 受环境限制 | `render3d_worker.py --probe` | 无 `ADVP_RENDER_PYTHON` 时 skip |

---

## 8. P07 报告与导出

原型：`docs/prototype/index.html#page-p07`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 报告大纲：摘要/质量/图表/结论/局限/附录 | 已实现 | `ReportOutline.tsx`、`reports.py` | 拖拽/上移/下移 |
| 自定义章节：新增/编辑/排序/删除 | 已实现 | `ReportCustomSections.tsx`、Task 12/13 | 顶层章节、Markdown 正文 |
| `include_charts=true` 嵌入已选图表 | 已实现 | Task 12/13 | 附报告图表清单 |
| 中部渲染预览 | 已实现 | `ReportPreview.tsx`、后端 HTML 草稿预览 | 防抖、不落盘、失败可重试 |
| 导出设置：语言/模板/分辨率/代码/追溯 | 已实现 | `P07Reports.tsx` | 语言/模板/结论/图表/派生数据 |
| 导出队列：状态/进度/重试/下载 | 已实现 | `ExportQueue.tsx`、`export_jobs` | 最近 100 条/30 天 |
| manifest 预览 | 已实现 | `P07Reports.tsx` | manifest 可见 |
| 导出 PDF/HTML/Markdown | 已实现 | 报告下载端点 | PDF 需 Playwright |
| 可复现包 | 已实现 | `report/package` | 默认不含原始数据 |
| 报告图表列表/父选型/血缘 | 已实现 | `report-chart-list`、manifest | — |
| 多图截图 | 替代实现 | `reports.py`、manifest | 当前嵌入首图，其余以清单/血缘记录 |

---

## 9. P08 Provider 设置

原型：`docs/prototype/index.html#page-p08`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| Provider 列表、状态徽标、主/备、优先级拖拽 | 已实现 | `ProviderPanel.tsx`、Task 15 | 拖拽写回 `priority` |
| 表单：名称/协议/Base URL/Key/模型/超时/重试/代理/并发/Header | 已实现 | `ProviderPanel.tsx`、Provider API | 密钥仅 keyring |
| 并发上限、等待阈值 | 已实现 | Task 15 | 1–16；1–120s；超时 `provider_concurrency_timeout` |
| 任务预算 | 已实现 | Task 15 | 每 Provider；单次选型/修正（含重试/重选） |
| 连接测试、模型列表 | 已实现 | Provider API | `/models` 缺失返回 `models_unsupported` |
| 能力探测 | 替代实现 | 连接测试 + 模型列表 | 不依赖原生 tool use/JSON Schema |
| 价格表、成本预估示例 | 已实现 | Task 15 | 可编辑 Token/单价 + 7 天均值 |
| 数据外发 metadata/sample/full | 已实现 | EU2-4 | full 需二次确认 + 审计 |
| 预算：任务/月度、超限降级 | 已实现 | 三级预算 + Task 15 | 稳定原因码 |
| 删除同步凭据、清除全部凭据 | 已实现 | Provider/数据库凭据分类清除 | 分别确认与审计 |
| 添加/删除/保存/测试 | 已实现 | `P08Providers.tsx` | — |

---

## 10. P09 追溯与审计

原型：`docs/prototype/index.html#page-p09`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 运行选择、时间范围、导出追溯 | 已实现 | `P09Trace.tsx`、trace API | JSON/Markdown |
| DAG、步骤详情、输入输出摘要 | 已实现 | `TracePanel.tsx` | — |
| 模型/提示词/Token/费用/耗时 | 已实现 | trace 节点 | — |
| 代码查看、diff、复制/下载 | 已实现 | `code_export.py`、TracePanel | — |
| 血缘 | 已实现 | `trace.py` | 原始文件→派生→图表→报告 |
| 日志筛选（级别/步骤/关键字） | 已实现 | `TracePanel.tsx`、Task 16 | 当前运行持久化事件；不读原始 JSONL |
| 成本时间线、按步骤/模型聚合 | 已实现 | `TraceCostTimeline.tsx` | 与 trace 汇总一致 |
| 运行对比、从步重跑 | 已实现 | compare/rerun API | — |
| 审计筛选/搜索/导出/复制诊断 | 已实现 | `AuditPanel.tsx`、Task 16 | JSON+CSV、脱敏 |
| 原始 JSONL 日志浏览 | 明确不做 | Task 16 决策 | 仅暴露脱敏运行事件 |

---

## 11. P10 设置与关于

原型：`docs/prototype/index.html#page-p10`

| 原型控件/能力 | 状态 | 实现/证据 | 说明 |
|---|---|---|---|
| 通用：语言、启动行为、更新通道 | 已实现 | `P10Settings.tsx`、Task 18 | `startup_behavior=last_project` 默认 |
| 分析：采样窗口、重选次数、并发、默认管线 | 已实现 | Task 18 | `max_reselects=2`、`analysis_concurrency=2` |
| 安全与沙箱：超时、内存、CPU、日志脱敏 | 已实现 | Task 18 | 8192 MB / 300 s；运行时生效 |
| 关于：版本、许可、第三方声明、诊断包、更新 | 已实现 | `LicensePanel.tsx`、About API | 仓库仅脱敏标签 |
| 版本与仓库：版本、Python/Node/浏览器、仓库（脱敏） | 已实现 | About + 前端运行时信息 | 不暴露私有仓库 URL |
| 开发者：日志级别、诊断、清理、危险操作 | 已实现 | Task 18、`CleanupPanel.tsx` | 二次确认 + 审计 |
| 恢复默认 | 已实现 | `POST /api/settings/reset` | 保留 ENV 字段；不改工程/数据集 |
| 保存设置 | 已实现 | `PATCH /api/settings` | 仅提交脏字段；ENV 只读 |
| 清理：五类、干跑、确认、保护引用 | 已实现 | Task 19 | 原文件永不删除 |
| 检查更新 | 已实现 | `updates.py`、About 面板 | 未签名更新链 |
| 日志保留 7/14/30 天、级别 INFO/DEBUG/WARN | 已实现 | Task 18 | 运行时生效 |

---

## 12. 明确不做与用户决定

| 项 | 状态 | 依据 |
|---|---|---|
| 代码签名与 SmartScreen 消除 | 明确不做 | 用户决定跳过；作为已知风险 |
| 人工盲评、干净机 5GB/1GB 全量、代表硬件人工验收 | 明确不做 | 用户决定跳过 |
| 像素级复刻原型 | 明确不做 | 仅要求信息架构/控件/交互/状态语义一致 |
| OCR、本地模型、多用户、实时协作、SaaS | 明确不做 | 2.0/2.1 非目标 |
| 浅色主题、手机端布局 | 明确不做 | 2.1 非目标 |
| 原始 JSONL 日志浏览器 | 明确不做 | 仅暴露脱敏运行事件 |
| P03 Parquet 样本导出 | 明确不做（2.1） | 显示 `parquet_export_unavailable` |

---

## 13. 证据索引

| 证据 | 位置 |
|---|---|
| 四档宽度无溢出与截图 | `backend/tests/test_eu21_visual.py`、`build/eu21-visual/` |
| 无障碍与表单 label | `backend/tests/test_eu21_accessibility.py` |
| 中英导航与主操作 | `backend/tests/test_eu21_bilingual.py` |
| 设计令牌对比度 | `frontend/src/styles/contrast.test.ts` |
| 页面与交互口径 | `docs/页面清单与交互说明.md` |
| 2.1 需求与决策 | `docs/ADVP2.1升级改进需求.md` |
| 2.1 实施计划 | `docs/plans/2026-11-02-advp2.1-implementation.md` |
| 开发工作记录 | `docs/【2026-11-14】开发工作记录.md` |

# ADVP 2.1 验收报告

| 项目 | 内容 |
|---|---|
| 文档编号 | ADVP-ACCEPT-2.1.0 |
| 版本 | v2.1.0 |
| 日期 | 2026-11-14 |
| 分支 | `ADVP2.1` |
| 基线 | ADVP 2.0.0 |
| 状态 | 发布候选；自动化与安装包验证通过 |

## 1. 范围

ADVP 2.1 在 2.0.0 基础上完成 EU21-1..5 共 25 个任务：

- P02 六类来源真实接入、文件高级选项、文档编辑/AI 增强与 2026-11-05 增量。
- P03 分析图、AI 上下文、指定行数导出、画像覆盖与质量闭环。
- P04/P05/P06 预算卡、计算字段、评分卡、加入报告与 3D 工具栏。
- P07 后端 HTML 草稿预览、自定义章节、报告/图表导出队列与浏览器 E2E。
- P08 并发、任务预算、凭据分类清除、优先级拖拽与成本预估。
- P09 成本时间线、运行日志筛选、审计搜索/导出与诊断复制。
- P10 安全清理 API、设置恢复默认、新设置项、关于/许可/诊断/开发者分区。
- P01–P10 四档宽度、无障碍、双语检查与页面一致性矩阵。

页面一致性逐项状态见 [ADVP 2.1 页面一致性矩阵](ADVP2.1页面一致性矩阵.md)。

## 2. 自动化证据

| 检查 | 结果 |
|---|---|
| 后端默认套件（xdist，JUnit） | **572 passed, 1 skipped** |
| browser + real lane | **23 passed, 14 skipped** |
| 前端 Vitest | **49 文件 / 153 tests** |
| 前端 typecheck / lint / build / build:share | 通过 |
| 后端 ruff check / format / mypy `src` | 通过（109 source files） |
| `check_version.py` | 2.1.0 一致（157 个 CHANGELOG 版本） |
| `check_links.py` | 73 个 Markdown 无断链 |
| `check_prototype.py` | 10 页、45 个 id、无外部依赖 |
| markdownlint | 变更/受控文档 0 error |
| P01–P10 响应式截图 | 1440/1280/1024/768 无横向溢出；`build/eu21-visual/` 40 张 |
| 对比度 | 主/次文本、强调色、状态色共 4 项 ≥ 4.5:1 |

浏览器用例覆盖：EU2 shell、P02 导入六类来源、P07 报告与导出队列、P08/P09、P06/P07/P08、2.1 视觉/无障碍/双语。跳过项均带原因：

- 无便携 PostgreSQL/MySQL/S3 端点：`test_external_services_real.py` skip。
- 无 Kafka broker：Kafka 导入用例 skip，WebSocket 替代覆盖。
- 无 `ADVP_RENDER_PYTHON`：真实 VTK/Mayavi/trame 用例 skip。
- 无 OpenNeuro/1GB M5 fixture：对应 real 用例 skip。

## 3. 安装包验证（Windows 11，本机）

| 步骤 | 结果 |
|---|---|
| 安装 2.0.0 | 退出码 0；`version.txt=2.0.0` |
| 覆盖升级 2.1.0（同一目录） | 退出码 0；`version.txt=2.1.0`；显示名 `ADVP 2.1` |
| 安装后运行时 | `advp.__version__=2.1.0`；仅保留 `advp_backend-2.1.0.dist-info` |
| 健康检查 | `{"status":"ok","version":"2.1.0","database":"ok"}` |
| About | 版本 2.1.0、Python 3.12.13、许可 Apache-2.0、仓库 URL 为空 |
| 首页 | HTTP 200，SPA index 可加载 |
| 用户数据 | `%USERPROFILE%\.advp\release-test-marker.txt` 升级后保留 |
| 卸载 2.1.0 | 退出码 0；`env/`、`version.txt`、安装目录与卸载注册项移除 |
| 卸载后用户数据 | `%USERPROFILE%\.advp\release-test-marker.txt` 保留 |

修复记录：首次升级测试发现旧 `advp_backend-2.0.0.dist-info` 未被覆盖，运行时仍报告 2.0.0。安装器新增 `[InstallDelete]` 清理旧后端包/元数据，并在卸载时清理 `env/static/static-share`，复测通过。

## 4. 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `build/installer/ADVP-2.1.0-setup.exe` | 176,887,942 B | `0baaa2509748163651e7be14dccdd7f67d41224e050dfe09a1094317b0f34abb` |
| `build/release/ADVP-2.1.0-win64.zip` | 270,365,422 B | `332ac67795bf5997b39d569bc1f9ca7a4b7b0305cabf1f90f4e7b1efd9b152f9` |

便携包顶层目录 `ADVP-2.1.0-win64/`，包含 `python/`、`static/`、`static-share/`、`ADVP.bat`、`启动 ADVP.bat`、README、LICENSE、SECURITY、THIRD_PARTY_NOTICES 与 `version.txt`。

## 5. 已知风险与跳过项

- 安装器与更新链未签名；SmartScreen 警告与供应链完整性不作为已消除风险。
- 5GB/1GB 全量、人工盲评与代表硬件人工验收按用户 2026-11-04 决定跳过。
- 真实 3D 渲染仍依赖 `ADVP_RENDER_PYTHON`；无环境时 real 用例跳过。
- PostgreSQL/MySQL/S3/Kafka 真实端点未在本机配置；跳过并保留替代验证。
- P03 Parquet 样本导出仍禁用并显示 `parquet_export_unavailable`。
- 报告多图截图当前嵌入首图，其余图表以清单和 manifest 血缘记录。
- 公开仓库缺少随快照发布的 CI 工作流；公开 PR 的分支保护检查需在合并前确认。

## 6. 结论

ADVP 2.1.0 的自动化门禁、P01–P10 页面一致性检查、四档宽度/无障碍/双语检查与 2.0 → 2.1 覆盖升级/卸载验证均通过。按用户决定保留未签名安装器与跳过项作为已知风险，可以发布。

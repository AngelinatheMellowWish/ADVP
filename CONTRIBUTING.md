# 贡献指南

ADVP 采用严格的最小版本变动与双仓库策略。提交前请完整阅读本文件。

## 环境

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | 3.12 | 文档构建、脚本、后续后端 |
| Node.js | 22 | commitlint、markdownlint、后续前端 |
| Git | 2.40+ | 版本管理 |
| Microsoft Word | 可选 | 自动更新 DOCX 目录与页码 |
| gitleaks | 最新 | 本地密钥扫描 |

## 分支与提交

1. 从 `main` 创建功能分支：`feat/<topic>`、`fix/<topic>`、`docs/<topic>`、`chore/<topic>`。
2. 一个逻辑修改只做一个原子 commit；PR 使用 **squash merge**。
3. 提交信息遵循 Conventional Commits，例如：
   - `docs(srs): clarify chart selection threshold`
   - `feat(pipeline): add provider fallback`
   - `fix(sandbox): block subprocess creation`
4. `main` 受保护，PR 必须通过 CI 与至少一次审查。

## 版本流程

每个合并后的逻辑修改 = 一个 patch 版本：

```powershell
python scripts/bump_version.py --message "docs(srs): clarify chart selection threshold"
powershell -ExecutionPolicy Bypass -File scripts/build_docx.ps1
python scripts/check_version.py
git add -A
git commit -m "docs(srs): clarify chart selection threshold"
git tag v0.1.1
```

规则：

- `VERSION`、`CHANGELOG.md`、`package.json`、SRS 文档控制必须一致。
- 里程碑可升级 minor；不兼容变更升级 major。
- 文档修改同样递增 patch 版本。
- 不提交自动生成的临时文件、日志、密钥、数据或构建产物。

## 文档

- 需求文档：`docs/需求说明书.md`；修改后运行 `scripts/build_docx.ps1` 更新 Word 版。
- 原型：`docs/prototype/index.html`；必须保持单文件、无外部依赖，并通过 `python scripts/check_prototype.py`。
- 图表/接口变更：同步更新技术选型、验收标准与确认清单。
- 决策变更：在 `docs/adr/` 新增或更新 ADR。

## 安全

- 禁止提交任何真实 API Key、Token、密码、私有数据或绝对路径。
- 本地提交前建议运行 `gitleaks detect --source . --redact`。
- 生成代码沙箱不是容器级隔离；安全相关变更必须补充逃逸测试。
- 发现泄露立即轮换密钥，并按 `SECURITY.md` 流程处理。

## CI 门禁

PR 必须通过：

- markdownlint + 离线链接检查。
- `scripts/check_prototype.py` 与 DOCX 构建校验。
- `scripts/check_version.py`。
- ruff、mypy、pytest（后端存在时）。
- eslint、tsc、vitest（前端存在时）。
- gitleaks 全历史扫描。
- commitlint。
- 依赖漏洞审计。

## 双仓库

- 私有仓库 `advp-private` 保存全量内容。
- 公开仓库 `advp` 只能通过 `scripts/export_public.ps1` 白名单导出。
- 导出后必须人工复核 `git diff`，确认无密钥、无数据、无内部记录。
- 公开与私有仓库使用同一版本 tag。

## 许可

当前为 Apache-2.0。贡献即表示同意以项目许可发布；新增依赖必须通过许可审计，禁止 GPL/AGPL 进入核心；Qt/PySide6 仅动态链接，FFmpeg 使用 LGPL 构建。

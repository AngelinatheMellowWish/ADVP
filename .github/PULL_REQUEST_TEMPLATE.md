# Pull Request

## 变更摘要

<!-- 一句话说明本 PR 做了什么，以及为什么。 -->

## 类型

- [ ] feat
- [ ] fix
- [ ] docs
- [ ] refactor
- [ ] test
- [ ] chore
- [ ] security

## 版本与变更记录

- [ ] 已运行 `python scripts/bump_version.py --message "..."`
- [ ] 已更新 `VERSION`、`CHANGELOG.md`、SRS 文档版本
- [ ] 已运行 `python scripts/build_docx.ps1`
- [ ] 已运行 `python scripts/check_version.py`
- 目标版本：`v0.1.x`

## 验证

- [ ] `npm run lint:md`
- [ ] `python scripts/check_prototype.py`
- [ ] `python scripts/check_version.py`
- [ ] 后端：ruff / mypy / pytest
- [ ] 前端：eslint / tsc / vitest
- [ ] 手工验证步骤与截图（UI 变更必填）

## 安全

- [ ] 无密钥、无真实数据、无绝对路径
- [ ] 已运行 gitleaks
- [ ] 涉及沙箱/外发/凭据的变更已补充安全测试与说明

## 文档与追溯

- [ ] 需求/技术/验收/页面文档已同步
- [ ] 重大决策已新增或更新 ADR
- [ ] 公开仓库导出影响已评估

## 关联 Issue

<!-- Closes #123 -->

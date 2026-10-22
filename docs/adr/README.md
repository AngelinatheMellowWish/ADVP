# 架构决策记录（ADR）

本目录记录 ADVP 的关键架构决策、上下文、备选方案与后果。每个决策一个文件；编号递增，不修改历史结论，只追加新的 ADR。

## 状态

| 状态 | 含义 |
|---|---|
| Proposed | 待确认 |
| Accepted | 已采纳 |
| Superseded | 被新 ADR 取代 |
| Deprecated | 已弃用 |

## 索引

| ADR | 决策 | 状态 | 关联 |
|---|---|---|---|
| ADR-0001 | 采用本地 Web 应用，而非桌面应用或 SaaS | Accepted（D01） | 需求 2.3 |
| ADR-0002 | Python 后端 + React 前端 | Accepted（D05） | 技术选型 10/11 |
| ADR-0003 | 3D 采用 WebGL + Mayavi/VTK/trame 混合双后端 | Accepted（D08） | 技术选型 2 |
| ADR-0004 | 图表选型采用规则筛选 + AI 决策 + 评分重选 + Top3 | Accepted（D17） | 需求 3.6 |
| ADR-0005 | 生成代码在本地受限子进程执行，不引入 Docker | Accepted（D11/D33） | 技术选型 7 |
| ADR-0006 | API Key 存 Windows Credential Manager | Accepted（D10） | 技术选型 8 |
| ADR-0007 | 公开脱敏仓库 + 私有全量仓库 | Accepted（D40/D43） | 技术选型 12.3 |
| ADR-0008 | SemVer + 每次修改 patch+1 + squash merge | Proposed（D38） | 技术选型 12.1 |
| ADR-0009 | 后台队列使用 Huey + SQLite | Proposed | 技术选型 6 |
| ADR-0010 | 公开仓库通过白名单导出脚本同步 | Proposed | 技术选型 12.3 |

> D 编号见《需求确认清单》。ADR-0008–0010 待用户确认后转为 Accepted。

## 新增 ADR

复制以下模板为 `NNNN-short-title.md`，并更新索引：

```markdown
# ADR-NNNN: 标题

- 状态：Proposed
- 日期：YYYY-MM-DD
- 决策人：
- 关联需求：

## 背景

## 决策

## 备选方案

## 后果

### 正面

### 负面

## 验证与复审
```

## 与需求文档的关系

- ADR 解释“为什么这样选”；需求书定义“必须做什么”；技术选型摘要给出实现对比。
- 若 ADR 改变需求行为，必须同步更新需求书、验收标准与确认清单，并递增 minor/major 版本。

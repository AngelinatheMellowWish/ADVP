# GitHub 发布指南（双仓库）

| 项目 | 内容 |
|---|---|
| 文档编号 | ADVP-OPS-001 |
| 版本 | v0.2.5 |
| 状态 | 待执行 |
| 账号 | `AngelinatheMellowWish` |
| 公开仓库 | `ADVP`（Public，脱敏快照） |
| 私有仓库 | `Object1691`（Private，全量备份） |
| 当前版本 | v0.2.5 |

> 原则：私有仓库是唯一全量来源；公开仓库只能通过 `scripts/export_public.ps1` 白名单导出。任何时候都不要把当前私有工作树直接推到公开仓库。

---

## 1. 前置条件

- 本机已安装 Git 与 GitHub CLI（`gh`）。
- 已登录 GitHub 网页账号：`AngelinatheMellowWish`。
- 当前项目目录为 `%USERPROFILE%\Object1691`，`main` 分支干净，已有 `v0.1.0`–`v0.2.5` tag。
- 已确认 `api_key.txt` 不存在；若曾包含真实密钥，先到供应商后台轮换。
- 本机 Git 身份已配置（当前为 `AngelinatheMellowWish`）。

---

## 2. 方案 A：授权 CLI（推荐）

网页登录不会自动授权 `gh`。在项目目录打开 PowerShell：

```powershell
gh auth login
```

依次选择：

1. `GitHub.com`
2. `HTTPS`
3. `Login with a web browser`
4. 复制一次性代码，在浏览器粘贴并授权
5. 确认：`gh auth status`

授权后，执行私有仓库推送：

```powershell
gh repo create AngelinatheMellowWish/Object1691 --private --source . --remote origin --push --description "ADVP full private repository"
git push origin --tags
```

生成并推送公开脱敏仓库：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_public.ps1 -Target ..\ADVP -Force
gh repo create AngelinatheMellowWish/ADVP --public --source ..\ADVP --remote origin --push --description "ADVP open-source edition"
git -C ..\ADVP push origin --tags
```

如果仓库已存在，改用：

```powershell
git remote add origin https://github.com/AngelinatheMellowWish/Object1691.git
git push -u origin main --tags

git -C ..\ADVP remote add origin https://github.com/AngelinatheMellowWish/ADVP.git
git -C ..\ADVP push -u origin main --tags
```

---

## 3. 方案 B：网页手动建仓

1. 打开 [GitHub 新建仓库](https://github.com/new)。
2. 创建 `Object1691`：选择 **Private**，不要勾选 README、.gitignore、license。
3. 创建 `ADVP`：选择 **Public**，同样保持空仓库。
4. 在项目目录执行私有仓库推送：

   ```powershell
   git remote add origin https://github.com/AngelinatheMellowWish/Object1691.git
   git push -u origin main --tags
   ```

5. 生成并推送公开仓库：

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/export_public.ps1 -Target ..\ADVP -Force
   git -C ..\ADVP remote add origin https://github.com/AngelinatheMellowWish/ADVP.git
   git -C ..\ADVP push -u origin main --tags
   ```

首次 HTTPS 推送会调用 Git Credential Manager，按浏览器提示登录即可。

---

## 4. 分支保护（两个仓库都配置）

仓库 **Settings → Branches → Add branch protection rule**：

| 选项 | 设置 |
|---|---|
| Branch name pattern | `main` |
| Require a pull request before merging | 开启；单人项目审批数可设 0 |
| Require status checks to pass | `quality-gates`、`secret-scan`、`commitlint`、`dependency-audit` |
| Require branches to be up to date | 开启 |
| Do not allow force pushes | 开启 |
| Do not allow deletions | 开启 |

> 单人项目无法自我审批；将 required approvals 设为 0，但仍强制 PR 与 CI。若未来增加协作者，再改为 1。

**私有仓库限制：** GitHub 免费账户不支持私有仓库的分支保护，API 会返回 `403 Upgrade to GitHub Pro or make this repository public`。当前 `ADVP`（公开）已启用保护；`Object1691`（私有）无法启用。可选方案：升级 GitHub Pro；或在本地使用 pre-push hook；或将私有仓库改为公开（不推荐）。在升级前，私有仓库依靠本地流程与 CI 结果约束，不能强制阻止直接推送。

---

## 5. CI 与密钥

- `.github/workflows/ci.yml` 会在 push/PR 时运行。
- 公开仓库：`gitleaks-action` 对公开仓库通常无需许可证。
- 私有仓库：若 gitleaks 提示需要许可证，在 `Settings → Secrets and variables → Actions` 添加 `GITLEAKS_LICENSE`。
- 不要在任何 workflow、issue、PR 或 commit 中写入真实密钥。
- 若 CI 失败：先修本地，再递增 patch 版本，禁止直接改 `main` 绕过。

---

## 6. 发布后验证

```powershell
gh repo view AngelinatheMellowWish/Object1691
gh repo view AngelinatheMellowWish/ADVP
git ls-remote --tags https://github.com/AngelinatheMellowWish/Object1691.git
git ls-remote --tags https://github.com/AngelinatheMellowWish/ADVP.git
```

检查清单：

- [ ] `Object1691` 为 Private，`ADVP` 为 Public。
- [ ] 两个仓库的 `main` 均有最新 commit。
- [ ] 私有仓库包含 `v0.1.0`–`v0.2.5`；公开仓库包含 `v0.2.5`（脱敏快照从该版本开始）。
- [ ] 公开仓库无 `api_key.txt`、`.env`、`node_modules`、`logs/`、`data/`、绝对路径。
- [ ] 公开仓库 `LICENSE` 为 Apache-2.0，包含 `NOTICE` 与 `THIRD_PARTY_NOTICES.md`。
- [ ] Actions 中 `quality-gates`、`secret-scan`、`commitlint`、`dependency-audit` 通过。
- [ ] `main` 已开启分支保护与必需检查。

---

## 7. 常见问题

**公开仓库推送被拒绝（non-fast-forward）**

网页建仓时勾选了 README/license，导致远端已有 commit。删除该仓库重新创建空仓库，或先 `git pull --rebase` 再 push。

**HTTPS 推送反复要求登录**

运行 `gh auth setup-git`，或使用 `gh auth login` 后重试；也可切换 SSH。

**公开仓库出现敏感文件**

立即停止推送，删除远端仓库或强制清理历史，轮换相关密钥，重新执行导出脚本并人工复核。

**CI 中 gitleaks 报 license**

为私有仓库添加 `GITLEAKS_LICENSE` secret；公开仓库一般不需要。

---

## 8. 版本与回滚

- 每次修改：递增 patch → 更新 `CHANGELOG` → 构建 docx → commit → tag → 双仓库同版本 tag。
- 发布失败：不要删除 tag 后重用；递增新 patch 修复。
- 公开仓库泄露：删除并重建公开仓库，使用已验证的导出快照；私有仓库保留全量历史用于审计。
- 任何回滚都必须记录在 `CHANGELOG.md` 与私有仓库的发布记录中。

# 飞书 Inbound Skill — 组员环境（不必 clone 整个 monorepo）

面向 **全体 ASP 组员**。按你在流水线中的角色参与各段 → **[全员参与指南](inbound_pipeline_team_guide.md)**。  
本文说明如何 **获取 asp 仓库 + CLI**，无需 Marvin 的 `rootgrove` monorepo。

---

## 你要什么、不要什么

| 需要 | 不需要 |
|------|--------|
| `AI-MYG/asp` 里的 `scripts/`、`tools/feishu_inbound/`、`config/` | 整个 `rootgrove` monorepo |
| 本机 `venv` + `feishu-inbound` 引擎（wheel） | 各 surface 全量 worktree（除非你自己要改代码） |
| `gh auth login`（你的 GitHub 账号） | 在 issue 上**只发评论**就当验收完成 |
| Cursor 打开 **asp 仓库根目录**（要用 Cursor Skill 时） | 只在 `asp-backend` 仓库里指望 Skill 自动出现 |

---

## 三种获取方式（由轻到全）

### 方式 A — 推荐：浅 clone 全仓库（体积小）

```bash
git clone --depth 1 https://github.com/AI-MYG/asp.git ~/CursorWorks/asp-infra
cd ~/CursorWorks/asp-infra
bash scripts/bootstrap_inbound_cli.sh
```

约几 MB 文档/skills；不含业务代码。装好后用 `scripts/run_accept.sh`（见下文）。

### 方式 B — 更轻：sparse checkout（只要 CLI + Skill）

适合磁盘/带宽极敏感，只要跑 `accept` / 读 skill：

```bash
mkdir -p ~/CursorWorks/asp-infra && cd ~/CursorWorks/asp-infra
git init
git remote add origin https://github.com/AI-MYG/asp.git
git fetch --depth 1 origin main
git sparse-checkout init --cone
git sparse-checkout set \
  scripts \
  tools/feishu_inbound \
  config \
  requirements-feishu-inbound.txt \
  .env.example \
  .cursor/skills \
  skills \
  docs/onboarding_inbound_skills.md \
  docs/inbound_pipeline_team_guide.md
git checkout main
bash scripts/bootstrap_inbound_cli.sh
```

**Cursor**：用 **File → Open Folder** 打开 `~/CursorWorks/asp-infra`，即可发现 `.cursor/skills/feishu-inbound-acceptance` 等。

### 方式 C — 不装本地 CLI

1. 请 **总监机 / release owner**（默认 `@369795172`）代跑：  
   `bash scripts/run_accept.sh pass --issue N --repo AI-MYG/asp-backend`
2. 或等 lead tick（`:20` / `:50`）扫描你在 issue 上的 `## Dev Acceptance` 评论（慢、不可控，**不推荐**）。

---

## 一次性引导：`bootstrap_inbound_cli.sh`

在 **asp 仓库根目录**执行（方式 A/B 完成后）：

```bash
bash scripts/bootstrap_inbound_cli.sh
```

会做：

1. 创建 `venv/`（若不存在）
2. 安装 `requirements-feishu-inbound.txt` 里 pin 的 `feishu-inbound` wheel（需 `gh auth login` 且能读 `369795172/feishu-inbound-skill` Release）
3. 打印验收示例命令

**凭证**：优先 `gh auth login` 的 token；可选 macOS Keychain `rootgrove/GITHUB_TOKEN`（与 monorepo 共用）。  
**不依赖** `~/CursorWorks/rootgrove`；若你有 monorepo，可设 `ASP_WORKTREE_ROOT` 指向它以便 `load_asp_env.sh` 加载更多密钥。

---

## 日常：验收一条 issue

```bash
cd ~/CursorWorks/asp-infra

# 通过
bash scripts/run_accept.sh pass --issue 148 --repo AI-MYG/asp-backend

# 不通过
bash scripts/run_accept.sh fail --issue 148 --repo AI-MYG/asp-backend --reason "dev 仍复现 xxx"
```

成功标志：

- issue 出现 label `dev-accepted`（pass）
- 评论 `## Dev Acceptance — Recorded`（含 promote PR 链接）
- **不要**只在 issue 手写 `## Dev Acceptance` 就离开（除非走方式 C 且已约好代跑）

---

## Cursor Skill 使用注意

完整表见 [inbound_pipeline_team_guide.md](inbound_pipeline_team_guide.md)。核心规则：

1. **Open Folder → asp 仓库根**（不是 surface repo）
2. Agent **跑终端脚本**，不要只用 `gh issue comment` 代替引擎（尤其 D / E / Acceptance）
3. 首次：`bash scripts/bootstrap_inbound_cli.sh`

| Skill | 参与者 |
|-------|--------|
| `feishu-inbound-triage` | 总监机 |
| `feishu-inbound-agent` | Assignee（C） |
| `feishu-inbound-plan-approval` | 审方案（C→D） |
| `feishu-inbound-executor` | Assignee（D） |
| `feishu-inbound-gate-review` | Assignee（E AI） |
| `feishu-inbound-acceptance` | 提需人 / 验收 |
| `feishu-inbound-human-gate` | Legacy 存量 issue |

---

## 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `feishu-inbound: command not found` | 未 bootstrap | `bash scripts/bootstrap_inbound_cli.sh` |
| wheel 安装失败 | 无 private Release 读权限 | `gh auth login`，或找 Marvin 开 repo 权限 |
| `gh auth status` 失败 | 未登录或账号不对 | 用 **issue 提需人 / assignee** 账号登录 |
| 发了评论但无 `dev-accepted` | 只评论未跑 CLI，且 lead tick 未扫到 | 跑 `run_accept.sh pass` |
| Cursor 找不到 skill | workspace 是 `asp-backend` 不是 `asp` | Open Folder → asp 仓库根 |

---

## 相关

- [**全员参与指南**](inbound_pipeline_team_guide.md)
- [Dev Acceptance workflow](../skills/workflow_acceptance.md)
- [Human Gate (Legacy)](../skills/workflow_human_gate.md)
- [Inbound Pipeline 总览](../skills/workflow_inbound_pipeline.md)
- [CI/CD 与 F handback 节点](cicd_pipeline.md)

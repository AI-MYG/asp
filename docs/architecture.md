# ASP Architecture

## 系统全景

ASP 是一个多 surface 儿童英语教育产品，由 6 个独立 repo 构成业务代码，1 个中央 repo（本 repo）构成 context infrastructure。

```
                    ┌─────────────────────────┐
                    │   Feishu Bitable        │
                    │   (需求池入口)            │
                    └────────────┬────────────┘
                                 │ Pipeline A (HTTP → GitHub Actions)
                                 ↓
                    ┌─────────────────────────┐
                    │   AI-MYG/asp            │
                    │   (中央 Context Infra)   │
                    │   - 需求级 Issue SSOT    │
                    │   - Memory 系统          │
                    │   - Persona 画像         │
                    │   - Skill 定义           │
                    └────────────┬────────────┘
                                 │ Pipeline B (综合 Agent 分诊)
                    ┌────────────┼────────────┐
                    ↓            ↓            ↓
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │ backend  │ │   app    │ │  admin   │  ... (+ wecom, websites, canonical)
            │ dev→prd  │ │ dev→main │ │ dev→main │
            └────┬─────┘ └────┬─────┘ └────┬─────┘
                 │            │            │
                 ↓            ↓            ↓
            Team Lead 本地 Agent (Pipeline C)
            Analysis → (Pipeline D) Smart PR + executed
                                 │
                                 ↓
            Pipeline E Gate Review (review model ≠ executor)
              ├─ 通过 → review-dev-pass + 飞书私信 → 人合 dev
              └─ 打回 → 去 executed + Gate Review comment → 回 D 修订
                                 │
                                 ↓
            Dev CI/CD → promote PR（每 issue 一条）→ Pipeline F 验收评论
                                 │
                                 ↓
            merge promote → production deploy → 飞书 PRD/Admin Deploy
```

**CI/CD 与用户可感知节点**: [cicd_pipeline.md](cicd_pipeline.md)

## Pipeline 架构（A → F）

A 入站、B 分诊、C 分析、D 执行、E gate review、F dev handback。A 在云端，B–F 在本地 Mac 由 launchd 调度（SSOT: `tools/feishu_inbound/config.yaml` → `launchd_schedules`）。

### Pipeline A: 飞书 → 中央 Issue (Cloud)

- **触发**: Bitable 自动化 HTTP POST
- **执行**: GitHub Actions (`.github/workflows/feishu-inbound.yml`)
- **产出**: AI-MYG/asp 中创建需求级 issue
- **回写**: Bitable 记录 issue URL + 状态

### Pipeline B: 分诊 (Central Mac)

- **触发**: 定时扫描（launchd, 每 30 分钟）
- **执行**: OpenCode Server 调用综合 Agent (`scripts/triage_dispatch.py`)
- **输入**: 中央 issue（`feishu-inbound` 标签, 非 `triaged`）
- **产出**: 各 surface repo 创建执行级 issue + 指派 Team Lead
- **配置**: `config/triage.yaml`

### Pipeline C: 分析 + 交付 (Per-developer)

- **触发**: Team Lead 被指派执行 issue
- **执行**: 本地 Agent（OpenCode Server）
- **流程**: Deep Analysis → 实现 → Smart PR (`tools/smart_pr.py`) → Review → Deploy → 飞书通知 (`scripts/completion_notify.py`)
- **配置**: `config/surfaces.yaml`

### Pipeline D: 自动执行 (Per-developer)

- **触发**: surface execution issue 带 `analyzed` + 通过难度 gate（Lead tick 链内或手动 CLI）
- **执行**: 在隔离 git worktree 内跑 AgentClient 实现推荐方案，再 Smart PR
- **产出**: open PR + `executed` 标签，交接给 Pipeline E
- **重入**: E 打回（去 `executed`）后，D 读 `## Pipeline E Gate Review` 反馈注入 prompt，复用同一 PR 修订
- **脚本**: `tools/feishu_inbound/issue_executor.py`

### Pipeline E: PR Gate Review (dev 门)

- **触发**: surface execution issue 带 `executed` + open linked PR + 无 `review-dev-pass`（Lead tick 链内或手动 CLI）
- **执行**: 经 rootgrove AgentClient **委托到与 Pipeline D 不同的 Agent 平台**（如 D=OpenCode、E=Cursor Composer 2.5）读 PR diff + analysis 做 gate review；**只 review，不改代码/不 merge**
- **状态机**:
  - 通过 → 打 `review-dev-pass`（保留 `executed`，不 merge）+ 业务语言飞书私信 → 人工合入 dev
  - 打回 → 去 `executed` + 打 `review-changes-requested` + `## Pipeline E Gate Review` comment + 飞书私信 → 回 Pipeline D 修订
  - 异常（结论无法解析）→ 不改 label + 私信 + comment，待人工
- **并发**: `--batch N --parallel`，`repo#issue` 粒度并行，per-issue 锁 = `review-in-progress` 标签
- **边界**: integration → production 经 scoped promote PR；E/F 不 merge、不改代码。部署与飞书卡片见 [cicd_pipeline.md](cicd_pipeline.md)
- **脚本**: `tools/feishu_inbound/issue_pr_reviewer.py`；配置 `config.yaml` → `pipeline_e` / `launchd_schedules.issue_pr_reviewer`

### Pipeline F: Dev Handback（验收指派）

- **触发**: `review-dev-pass`；integration PR 已 merge 到 `dev`；`pipeline_f.dev_cicd` 配置的 workflow 在 merge commit 上 **success**；由 **Lead tick**（`:20/:50`）链式调用
- **执行**: 读 GitHub Actions 结论 + `handback_to_requester`（sole assignee → GitHub 负责人 + `## Pipeline F Dev Handback` 评论）
- **幂等**: 已有 F 验收评论则跳过（**不再**使用 `ready-for-acceptance` label）
- **不做**: merge、改代码、production 部署确认
- **与飞书群区别**: F 发 **GitHub Issue 评论**；dev/prd 部署结果发 **CHATOPS 群卡片**（见 [cicd_pipeline.md](cicd_pipeline.md)）
- **脚本**: `tools/feishu_inbound/issue_dev_handback.py`；workflow 名称 SSOT：`config.yaml` → `pipeline_f.dev_cicd`

## Memory 系统

```
GitHub API signals ──→ Observer (日频) ──→ OBSERVATIONS.md (L1)
                                                  ↓
                                          Reflector (周频) ──→ MEMORY.md (L2)
                                                  ↓
                                          archive/YYYY-MM.md (过期归档)
```

Observer 扫描 AI-MYG 组织下所有 ASP repo 的：issue 创建/关闭、PR 创建/合并、commit 活动、部署事件。

Reflector 从 L1 观察中蒸馏：架构趋势、流程改进点、团队协作模式（persona 演化素材）。

## 自包含设计

本 repo 包含运行所有自动化所需的全部工具和配置。组员若**只需验收 / Cursor Skill**、不必 clone rootgrove monorepo，见 [onboarding_inbound_skills.md](onboarding_inbound_skills.md)（浅 clone 或 sparse checkout 本仓库即可）。

| 组件 | 位置 | 用途 |
|------|------|------|
| 组员验收引导 | `docs/onboarding_inbound_skills.md` | 最小 CLI + Skill 环境 |
| 验收 CLI 引导 | `scripts/bootstrap_inbound_cli.sh` | 一次性安装 `feishu-inbound` |
| 验收执行 | `scripts/run_accept.sh` | `accept pass\|fail` 封装 |
| Surface 配置 | `config/surfaces.yaml` | repo/branch/reviewer SSOT |
| 分诊配置 | `config/triage.yaml` | 关键词路由规则 |
| Smart PR | `tools/smart_pr.py` | 自动创建 PR + reviewer 指派 |
| OpenCode 客户端 | `tools/opencode_client.py` | Agent API 调用 |
| 分诊脚本 | `scripts/triage_dispatch.py` | Pipeline B 执行 |
| 执行脚本 | `tools/feishu_inbound/issue_executor.py` | Pipeline D 执行 |
| Gate review 脚本 | `tools/feishu_inbound/issue_pr_reviewer.py` | Pipeline E 执行 |
| Dev handback 脚本 | `tools/feishu_inbound/issue_dev_handback.py` | Pipeline F 执行 |
| 通知脚本 | `scripts/completion_notify.py` | 可选：中央 issue 完成飞书通知（与 F handback 互补） |
| Observer | `scripts/observer.sh` | 日频信号采集 |
| Reflector | `scripts/reflector.sh` | 周频记忆蒸馏 |

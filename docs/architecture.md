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
            │ (dev)    │ │ (main)   │ │ (main)   │
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
                    飞书通知需求方 (需求完成后)
```

## Pipeline 架构（A → E）

A 入站、B 分诊、C 分析、D 执行、E gate review。A 在云端，B–E 在本地 Mac 由 launchd 调度（SSOT: `tools/feishu_inbound/config.yaml` → `launchd_schedules`）。

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

- **触发**: surface execution issue 带 `analyzed` + 通过难度 gate（launchd `:05/:35`）
- **执行**: 在隔离 git worktree 内跑 AgentClient 实现推荐方案，再 Smart PR
- **产出**: open PR + `executed` 标签，交接给 Pipeline E
- **重入**: E 打回（去 `executed`）后，D 读 `## Pipeline E Gate Review` 反馈注入 prompt，复用同一 PR 修订
- **脚本**: `tools/feishu_inbound/issue_executor.py`

### Pipeline E: PR Gate Review (dev 门)

- **触发**: surface execution issue 带 `executed` + open linked PR + 无 `review-dev-pass`（launchd `:15/:45`，在 D 之后）
- **执行**: 用 **不同于 executor 的模型** 读 PR diff + analysis 做 gate review；**只 review，不改代码/不 merge**
- **状态机**:
  - 通过 → 打 `review-dev-pass`（保留 `executed`，不 merge）+ 业务语言飞书私信 → 人工合入 dev
  - 打回 → 去 `executed` + 打 `review-changes-requested` + `## Pipeline E Gate Review` comment + 飞书私信 → 回 Pipeline D 修订
  - 异常（结论无法解析）→ 不改 label + 私信 + comment，待人工
- **并发**: `--batch N --parallel`，`repo#issue` 粒度并行，per-issue 锁 = `review-in-progress` 标签
- **边界**: dev → prod 部署始终人工；E 永不 merge、永不改代码
- **脚本**: `tools/feishu_inbound/issue_pr_reviewer.py`；配置 `config.yaml` → `pipeline_e` / `launchd_schedules.issue_pr_reviewer`

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

本 repo 包含运行所有自动化所需的全部工具和配置，团队成员 clone 后配置 `.env` 即可独立运行：

| 组件 | 位置 | 用途 |
|------|------|------|
| Surface 配置 | `config/surfaces.yaml` | repo/branch/reviewer SSOT |
| 分诊配置 | `config/triage.yaml` | 关键词路由规则 |
| Smart PR | `tools/smart_pr.py` | 自动创建 PR + reviewer 指派 |
| OpenCode 客户端 | `tools/opencode_client.py` | Agent API 调用 |
| 分诊脚本 | `scripts/triage_dispatch.py` | Pipeline B 执行 |
| 执行脚本 | `tools/feishu_inbound/issue_executor.py` | Pipeline D 执行 |
| Gate review 脚本 | `tools/feishu_inbound/issue_pr_reviewer.py` | Pipeline E 执行 |
| 通知脚本 | `scripts/completion_notify.py` | Pipeline C 尾段（E 复用其 Feishu 函数） |
| Observer | `scripts/observer.sh` | 日频信号采集 |
| Reflector | `scripts/reflector.sh` | 周频记忆蒸馏 |

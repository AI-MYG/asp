# Feishu Inbound Pipeline Workflow

> **Migration Notice (2026-05-30)**: Pipeline B/C agent 脚本已迁移到 ASP 自有 repo `AI-MYG/asp`。
> ASP repo 内运行：`python tools/feishu_inbound/triage_agent.py` / `issue_scanner.py`。
> rootgrove 侧 `tools/feishu_inbound/` 文件保留但 launchd 调度已由 ASP repo `launchd/install.sh` 接管。

## 元数据

- **类型**: Workflow（顶层编排）
- **适用场景**: 飞书需求池 → GitHub Issue → Agent 深度分析的**完整入站流水线**
- **触发**: 飞书入站、feishu inbound pipeline、入站流水线、inbound 全流程
- **创建日期**: 2026-05-26

---

## 架构原则

1. **多段解耦**：A–F 各段独立调度，通过 Issue labels + comment 交接
2. **唯一交接物**：GitHub Issue（labels + assignee + comment sections）
3. **宽进严出**：扫描条件尽可能松（不漏），已处理则内部跳过（幂等可重扫）
4. **任一段故障不影响其它段**：A 失败不阻 B/C；B 失败不阻 C
5. **每段可独立触发、独立测试、独立部署**
6. **角色分轨**：**飞书提需人**（业务验收）与 **GitHub 负责人**（issue 操作）在 ASP 场景分离；personal 常合一。段间 Skill 见 B–F 各 workflow，不另建冗余 Meta Skill。

### 角色（全 pipeline 共用名词）

| 角色 | 职责 |
|------|------|
| 飞书提需人 | 飞书提需求；业务侧验收 |
| 流水线执行人 | 本机跑 C/D/E/F（`GITHUB_ASSIGNEE`） |
| GitHub 建单人 | 创建 issue 的账号（可为机器人） |
| GitHub 负责人 | F 之后持有 issue；代录业务验收 gate 评论 |

详见 [Pipeline F](./workflow_feishu_inbound_dev_handback.md#角色personal-与-asp-共用) 与 [Pipeline E](./workflow_feishu_inbound_gate_review.md#角色与-pipeline-f-共用)。

---

## 流程总览（A → F）

```
飞书 Bitable
     │ A  (GitHub Actions)
     ▼
中央 / Surface Issue ── B 分诊 (:10/:40)
     │
     ▼
Lead tick (:20/:50) 链式 C → D → E → D' → E' → F dev → **accept** → F prod
     │
     ├─ C 深度分析 → analyzed
     ├─ D 自动执行 + Smart PR → executed（assignee 仍是 lead）
     ├─ E Gate Review → review-dev-pass 或打回（`-executed` + `review-changes-requested`）
     ├─ D' 修订（E 打回后同 tick；补 `executed` + revision queue）
     ├─ E' 再审（`review --re-review-queue`，标准 Pipeline E）
     └─ F dev（人 merge PR + dev CI/CD success）→ sole assignee 提需人 + 验收 comment
     └─ Acceptance（`accept`）→ dev-accepted + promote PR + requester approve
     └─ F prod（prod CI/CD success）→ prod handback 通知
```

### launchd 调度（SSOT：`asp-infra/tools/feishu_inbound/config.yaml` → `launchd_schedules`）

| 段 | launchd label | 默认时刻 | 备注 |
|----|---------------|----------|------|
| B 分诊 | `com.asp.feishu-inbound-triage` | `:10` `:40` | 总监机 / lead Mac |
| **Lead tick** | `com.asp.feishu-inbound-lead-tick` | `:20` `:50` | **C→D→E→D'→E'→F 链式**（E 打回后同 tick 修订+再审） |

C/D/E/F 仍可通过 CLI 手动触发（`scan` / `execute` / `review` / `handback`），但 **不再安装独立 launchd job**。旧 job（`feishu-inbound-agent`、`issue-executor`、`issue-pr-reviewer`、`issue-dev-handback`）已于 2026-06-19 退役。

**Agent 单跳契约**: [api_feishu_inbound_engine.md](./api_feishu_inbound_engine.md)（`tools/grapeot_skills_sync.py` vendor，与 grapeot skills 同 pipeline）

重装：`bash projects/asp-infra/launchd/install.sh`

---

## Stage A — 飞书 → Issue

| 项 | 内容 |
|---|---|
| **触发** | Feishu Bitable 自动化（记录状态 → 「待处理」） |
| **运行位置** | GitHub Actions（`feishu-inbound.yml`） |
| **输入** | Bitable record payload（title, description, author, priority, type, record_id, feature_id） |
| **输出** | 新 Issue，labels: `feishu-inbound`；Bitable 状态 → 「已派发」+ Issue URL |
| **不做** | 任何分诊、分析、assignee 决策 |

**详细实现**：见 [任务文档 Pipeline A 节](../../docs/tasks/asp/20260519_feishu_inbound_requirement_pipeline.md)

---

## Stage B — 分诊 Triage

| 项 | 内容 |
|---|---|
| **触发** | launchd 定时（:10/:40）或手动 CLI |
| **运行位置** | 总监机（当前：Marvin MacBook） |
| **工具** | `./venv/bin/python tools/feishu_inbound/triage_agent.py` |
| **扫描条件** | `state=open` + label `feishu-inbound`（仅此） |
| **跳过条件（双门卫）** | `triaged` label **AND** `## Feishu Inbound Triage` comment 同时存在 → 跳过（`--force` 可覆盖） |
| **防御修复** | 仅有 `triaged` label 无 comment → 重跑（补发 comment）；仅有 comment 无 label → 重跑（`apply_github_updates` 补加 label） |
| **输出** | labels: surface + `scope-*` + `difficulty-*` + `triaged`；assignee；`## Feishu Inbound Triage` comment |
| **不做** | 调用 AgentClient、读代码、写 Analysis comment |

**解耦保证**：只读 Issue title/body 做关键词匹配，不依赖 Stage A 的实现细节。任何来源的 `feishu-inbound` Issue（手建也行）都能被 triage。

**详细 workflow**：[workflow_feishu_inbound_triage.md](./workflow_feishu_inbound_triage.md)

---

## Stage C — 深度分析（多 Issue 并行）

| 项 | 内容 |
|---|---|
| **触发** | Lead tick 链内（:20/:50）或手动 CLI |
| **运行位置** | 各 lead 本机（`GITHUB_ASSIGNEE`） |
| **工具** | `./venv/bin/python tools/feishu_inbound/issue_scanner.py` |
| **扫描条件** | `state=open` + assignee 含 `GITHUB_ASSIGNEE`（仅此） |
| **跳过条件（双门卫）** | `analyzed` label **AND** `## Feishu Inbound Analysis` comment 同时存在 → 跳过（`--force` 可覆盖） |
| **防御修复** | 仅有 analysis comment 无 `analyzed` label → 补加 label，**跳过**（避免重复昂贵 LLM 调用和重复 comment）；仅有 label 无 comment → 重跑（分析未完成） |
| **输出** | `## Feishu Inbound Analysis` comment（8 章，ASP Debug 契约）+ `analyzed` label |
| **不做** | 调用 Feishu API、修改 triage 标签、re-assign |

**并行模型**：`--parallel --batch N` 时为每条 issue spawn 独立子进程（独立 Agent 会话）。单 issue 内部是否 delegate / 开 subagent，Agent 自行决定。

**解耦保证**：只看 `open` + `assignee = me`，不要求特定 label 才能扫到。`difficulty-*` / `triaged` 等 label 作为参考但非必须（缺省按 `standard` 处理）。不依赖 Stage B 的实现方式。

**详细 workflow**：[workflow_feishu_inbound_agent.md](./workflow_feishu_inbound_agent.md)

---

## Stage D — 自动执行 + Smart PR

| 项 | 内容 |
|---|---|
| **触发** | Lead tick 链内（:20/:50）或手动 CLI |
| **运行位置** | 各 lead 本机（`GITHUB_ASSIGNEE`） |
| **工具** | `python tools/feishu_inbound/issue_executor.py` |
| **扫描条件** | `state=open` + assignee 含 `GITHUB_ASSIGNEE` + `analyzed` label |
| **Gate** | `difficulty-trivial` 自动执行；`standard`/`complex` 需 `approved-to-execute` label |
| **跳过条件** | `executed` 或 `execution-in-progress` label 存在 → 跳过 |
| **输出** | Surface worktree 实现 + Smart PR + `executed` label |
| **不做** | 修改 Analysis comment、re-assign 给提需人、调用 Feishu API |

**执行流程**：解析 Analysis comment → sync worktree → 创建 issue 分支 → AgentClient 实现推荐方案 → Smart PR → 标记 `executed`。

**引擎契约（v0.1.15+）**：D prompt 强制 API 文档同步与 App 版本 bump（有 App 交付时）；E 对两项均可 blocking 打回。single-repo 下 E/F 通过 `_find_linked_pr` 匹配裸分支 `issue-{N}`（#29）。

**并行模型**：`--parallel --batch N` 时为每条 issue spawn 独立子进程，与 Stage C 模式一致。

**解耦保证**：只读 `analyzed` label + Analysis comment，不依赖 Stage C 的内部实现。任何来源的 analyzed issue（手动分析也行）都能被执行。

**详细 workflow**：[workflow_feishu_inbound_executor.md](./workflow_feishu_inbound_executor.md)

---

## Stage E — 统一 Gate（AI 门禁 + 人测 gate）

| 项 | 内容 |
|---|---|
| **触发** | Lead tick 链内（:20/:50）或手动 CLI |
| **运行位置** | 各 lead 本机（`GITHUB_ASSIGNEE`） |
| **工具** | `python tools/feishu_inbound/issue_pr_reviewer.py` |
| **AI 扫描** | `open` + assignee 含 lead + `executed` + 无 `review-dev-pass` |
| **AI 输出** | `review-dev-pass` 或打回 D；飞书私信 lead |
| **不做** | 改代码、merge；不处理 dev 人工验收（见 Acceptance） |

**详细 workflow**：[workflow_feishu_inbound_gate_review.md](./workflow_feishu_inbound_gate_review.md)（AI 门禁）。存量人测 gate：[workflow_feishu_inbound_human_gate.md](./workflow_feishu_inbound_human_gate.md)。新 dev 验收：[workflow_feishu_inbound_acceptance.md](./workflow_feishu_inbound_acceptance.md)（引擎 [#35](https://github.com/369795172/feishu-inbound-skill/issues/35)）。

---

## Stage Acceptance — Dev 验收（`accept`）

| 项 | 内容 |
|---|---|
| **触发** | 提需人 CLI `accept pass|fail`；或 lead tick `accept --scan-only` |
| **工具** | `feishu-inbound accept`（引擎 #35） |
| **扫描** | `review-dev-pass` + F dev handback；无 `dev-accepted` |
| **pass 输出** | `dev-accepted`；dispatch scoped promote PR；提需人 approve prod PR |
| **fail 输出** | `review-changes-requested`；打回 D |
| **不做** | merge prod；不替代 F handback |

**详细 workflow**：[workflow_feishu_inbound_acceptance.md](./workflow_feishu_inbound_acceptance.md)。引擎契约：`projects/feishu-inbound-skill/docs/acceptance_gate.md`

---

## Stage F — Dev CI/CD 后验收指派

| 项 | 内容 |
|---|---|
| **触发** | Lead tick 链内（:20/:50）或手动 CLI |
| **工具** | `python tools/feishu_inbound/issue_dev_handback.py` |
| **扫描条件** | org 内 `open` + `review-dev-pass` |
| **跳过条件** | 已有 `## Pipeline F Dev Handback` 评论（幂等） |
| **Gate** | PR merged + dev CI/CD `success` |
| **输出** | sole assignee → **GitHub 负责人** + F 验收评论（含飞书提需人/负责人字段） |

Handback 时机：人工合入 dev 且 dev CI/CD success 之后。不打 `ready-for-acceptance`。

**详细 workflow**：[workflow_feishu_inbound_dev_handback.md](./workflow_feishu_inbound_dev_handback.md)

---

## 段间契约（GitHub Issue Labels）

| Label | 谁写 | 谁读 | 性质 | 含义 |
|-------|------|------|------|------|
| `feishu-inbound` | A | B（扫描） | B 的扫描入口 | 来源标记 |
| `triaged` | B | C（参考） | 软参考，非必须 | 分诊完成 |
| `difficulty-trivial/standard/complex` | B | C（参考） | 软参考，缺省 standard | 难度 → routing_profile |
| `scope-s/m/l` | B | — | 信息性 | 范围估计 |
| surface labels (`backend`, `app`, ...) | B | — | 信息性 | 涉及代码面 |
| `analysis-in-progress` | C | C | 互斥锁 | 防并行重复 |
| `analyzed` | C | D（扫描入口） | D 的扫描入口 | 深度分析完成（成功路径 + 已分析修复路径） |
| `analysis-failed` | C | Human | 告警 | 分析校验失败 |
| `request-reanalysis` | Human | C（扫描入口） | 重分析触发 | 人工请求 Pipeline C 重跑分析；成功后自动清除并级联清理下游 label |
| `approved-to-execute` | Human | D（Gate） | Gate 条件 | 人工审核 Analysis 后授权执行（trivial 不需要） |
| `execution-in-progress` | D | D | 互斥锁 | 防并行重复 |
| `executed` | D | E（扫描入口） | 完成标记 | 自动执行 + Smart PR 完成 |
| `review-dev-pass` | E | F（扫描入口） | 完成标记 | Pipeline E dev 门通过，等待合入 dev |
| `review-changes-requested` | E | D | Gate 反馈 | E 打回，D 下一轮按 comment 修订 |
| `execution-failed` | D | Human | 告警 | 执行或 PR 失败 |
| `execution-exhausted` | D | Human | 停机 | 自动重试达上限（`pipeline_d.max_attempts` / `max_revision_rounds`），需人工运行 |

**Pipeline D 重试上限**（engine v0.1.20+，config `pipeline_d`）：

| 配置项 | 默认 | 含义 |
|--------|------|------|
| `max_attempts` | 3 | 连续执行失败次数，超限加 `execution-exhausted` 并停止 lead tick 自动拾取 |
| `max_revision_rounds` | 3 | E 打回（`## Pipeline E Gate Review`）轮次上限 |

人工恢复：移除 `execution-exhausted` 后手动 `execute --issue N`（engine v0.1.26+ 自动清本地 stale `failure_count`，无需 `--force`）；或加 `request-reanalysis` 从 C 重来。

本地 `issue_executor_state.json` 仅缓存未达上限的失败计数与成功元数据；**停机闸门以 GitHub `execution-exhausted` label 为准**，label 移除后 lead tick 会 reconcile 本地计数。

**关键设计**：B 的输出 label 对 C 是「有则用、无则降级」——C 不因缺少 `triaged` 而漏扫 issue。

### 双门卫（dual-gate）跳过规则

B 和 C 均采用「marker comment + label 双门卫」幂等模式，结构一致，适配各自约束：

| 场景 | B (`triaged`) | C (`analyzed`) |
|------|--------------|---------------|
| comment ✓ + label ✓ | 跳过 | 跳过 |
| label ✓, comment ✗ | 重跑（重发 comment，重加 label） | 重跑（重跑 LLM 分析，补发 comment） |
| comment ✓, label ✗ | 重跑（`apply_github_updates` 补加 label） | **仅补加 label，跳过**（避免重复昂贵 LLM + 重复 comment） |
| 两者均无 | 正常执行 | 正常执行 |

C 的差异在于「comment-only → repair_label 而非 re-analyze」，原因：AgentClient 调用成本高，且 `## Feishu Inbound Analysis` 重复 comment 会污染 issue；B 的 triage 为确定性低成本操作，重跑无害。

**重分析（方案 A）**：在 issue 上加 `request-reanalysis` label。C 在 lead tick / 手动 `scan` 时拾取，即使已有 Analysis comment + `analyzed` 也会重跑 LLM；成功后移除 `request-reanalysis` 并清理 `approved-to-execute`、`executed`、`review-*` 等下游 label。等价于 `scan --issue N --force`，但可被定时调度自动拾取。CLI `--force` 仍可用，且不会自动清理下游 label。

---

## 段间独立性验证

| 场景 | 预期 |
|------|------|
| A 挂了，但有人手动建了 `feishu-inbound` issue | B 正常 triage |
| B 挂了，issue 只有 assignee 没有 `triaged` | C 仍扫到并分析（按 `standard` 降级） |
| C 挂了 | Issue 保持原状，下轮自动重试 |
| 新 issue 没走 A（手建 + assign 即可） | C 直接能处理 |
| 只想跑 B 不跑 C | `--with-feishu-inbound-triage` only |
| 只想跑 C 不跑 B | `--with-feishu-inbound-agent` only |

---

## 运行方式

```bash
# 重装 ASP launchd（B–F，含 Pipeline F handback）
bash projects/asp-infra/launchd/install.sh

# 仅 B
python tools/feishu_inbound/triage_agent.py

# 仅 C
python tools/feishu_inbound/issue_scanner.py --batch 3 --parallel

# 仅 D
python tools/feishu_inbound/issue_executor.py --scan-only

# 仅 E
python tools/feishu_inbound/issue_pr_reviewer.py --scan-only

# 仅 F
python tools/feishu_inbound/issue_dev_handback.py --scan-only
```

（以上在 `source projects/asp-infra/scripts/load_asp_env.sh` 之后执行；脚本路径 symlink 自 `tools/feishu_inbound/`。）

旧 rootgrove 调度（已退役）：

```bash
# 勿再使用 — ASP repo launchd 已接管
# ./periodic_jobs/ai_heartbeat/install_launchd_jobs.sh --with-feishu-inbound
```

---

## 相关

- [任务文档（需求/架构/历史）](../../docs/tasks/asp/20260519_feishu_inbound_requirement_pipeline.md)
- [Stage B 详细 workflow](./workflow_feishu_inbound_triage.md)
- [Stage C 详细 workflow](./workflow_feishu_inbound_agent.md)
- [Stage D 详细 workflow](./workflow_feishu_inbound_executor.md)
- [Stage E Gate Review](./workflow_feishu_inbound_gate_review.md)
- [Stage F Dev Handback](./workflow_feishu_inbound_dev_handback.md)
- [Personal instance README](../../tools/feishu_inbound/README.md)
- [Agent Client Routing](./workflow_agent_client_routing.md)
- [Parallel Subagents](./workflow_parallel_subagents.md)
- [Smart PR](./workflow_smart_pr.md)
- [ASP Post Implement](./workflow_asp_post_implement.md)

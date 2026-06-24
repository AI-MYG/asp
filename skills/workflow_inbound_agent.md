# Feishu Inbound Agent Workflow

## 元数据

- **类型**: Workflow
- **适用场景**: **Pipeline C（开发者本机深度分析）**——仅读 GitHub；处理已 `triaged` 且 **assignee = `GITHUB_ASSIGNEE`** 的 Issue（来源不限，不要求 `feishu-inbound`）；根据 `difficulty-*` label 选择 routing_profile；结合 ASP Debug 契约产出 `## Feishu Inbound Analysis` comment
- **边界**: Pipeline A = 飞书 → Issue；Pipeline B = `triage_agent.py`（见 `workflow_feishu_inbound_triage.md`）；`debug-report` 自建 Issue 只要有 `triaged` + 正确 assignee 也走本 workflow
- **触发**: issue scanner、处理我的 issue、`tools/feishu_inbound/issue_scanner.py`
- **工具**: `tools/feishu_inbound/issue_scanner.py`、`tools/feishu_inbound/sync_worktrees.py`；ASP Debug SSOT: `deploy_asp_debug_report.md`
- **创建日期**: 2026-05-22

---

## Pipeline C 扫描与跳过逻辑（与 A / B 解耦）

| 类型 | 条件 | 说明 |
|------|------|------|
| **扫描** | `state=open` + assignee 含 `GITHUB_ASSIGNEE` | 宽进：只看 open + 属于我 |
| **跳过** | 已有 `## Feishu Inbound Analysis` + `analyzed` | 幂等；`--force` 或 `request-reanalysis` label 可覆盖 |
| **参考** | `difficulty-*` label | 决定 routing_profile（缺省 `standard`） |
| **参考** | `triaged` label | 若无此标签仍可处理（debug-report 等场景） |

**难度路由**：

| difficulty label | routing_profile | 并行 | 备注 |
|------------------|-----------------|------|------|
| `difficulty-trivial` | `quick_triage` | 可满额并发（≤ MAX_PARALLEL_AGENTS） | 配置/文案/简单 filter |
| `difficulty-standard` | `analysis` | 可 2 并发 | 默认 |
| `difficulty-complex` | `architecture_decision` | sequential + human gate | 跨 surface / 迁移 |

**多 Issue 并行**（已实现）：

- `--parallel --batch N` 时为每条 issue spawn 独立子进程（`subprocess.Popen`），各自独立 Agent 会话
- `MAX_PARALLEL_AGENTS`（默认 3）控制并发上限；`difficulty-complex` 不参与并行
- 互斥：`analysis-in-progress` label 防重复
- **单 issue 内部**是否开 parallel subagents / delegate：Agent 自决（参考 `workflow_parallel_subagents.md`），scanner 不规定

**ASP Debug**：分析前按 platform / environment / problem class 分类；技术结论须 Evidence（`path:line`）；API 类缺 HTTP 证据时在 comment 标明缺口（对齐 `deploy_asp_debug_report.md` Evidence Gate）。

交接物仅为 GitHub Issue（含 Pipeline B 的 Triage comment）；不调用 Feishu API。

---

## 前置条件：Worktree 与 GitHub 远端同步

**非本人负责的 surface，分析前必须与 GitHub base 分支一致**；本人负责的 surface 允许本地 WIP（未提交改动），直接读本地代码。

| Surface | Repo | Local path | Base branch | marviny（后端） | 1401554949（前端） |
|---------|------|------------|-------------|-----------------|---------------------|
| backend | `AI-MYG/asp-backend` | `projects/asp/backend/` | `dev` | **跳过 sync** | 必须 sync |
| app | `AI-MYG/asp-app` | `projects/asp/app/` | `main` | 必须 sync | **跳过 sync** |
| admin | `AI-MYG/asp-admin` | `projects/asp/admin/` | `main` | 必须 sync | **跳过 sync** |
| wecom | `AI-MYG/asp-wecom` | `projects/asp/wecom/` | `main` | **跳过 sync** | 必须 sync |
| websites | `AI-MYG/asp-websites` | `projects/asp/websites/` | `main` | **跳过 sync** | 必须 sync |

判定依据：`contexts/team_registry.yaml` → `projects.asp_<surface>.default_reviewers[0]`。

操作者身份：`GITHUB_ASSIGNEE`（默认 `marviny`）。

**自动同步**（`issue_scanner.py` 在 AgentClient 分析前执行；`--skip-sync` 可跳过）：

- **owned surfaces**（操作者负责）：不 pull，允许 dirty tree
- **non-owned surfaces**：working tree 须 clean → `git fetch` + `pull --ff-only origin <base>`

```bash
# 手动（按当前 GITHUB_ASSIGNEE 跳过 owned）
./venv/bin/python tools/feishu_inbound/sync_worktrees.py --all

# 指定操作者（如胡剑飞机器上跑）
./venv/bin/python tools/feishu_inbound/sync_worktrees.py --all --operator 1401554949
```

---

## Comment 契约（下游 Agent 零犹豫）

入站 Agent 写入 Issue 的 `## Feishu Inbound Analysis` **不是讨论稿**，而是执行规格。下游 Agent 读到后应直接开工，不应在「选方案」上停顿。

### 禁止

| 禁止项 | 原因 |
|--------|------|
| 「根因假设」「可能」「或许」「待验证」类技术表述 | 除生产 SSH 改数据外，必须先读代码再下结论 |
| 方案 A/B、多选一、alternatives | 方案审核是 **Human** 职责（三角分工） |
| 收敛后用问句问过程（「是否 dry-run」「需要的话我可以查库」） | Mandatory Gate 写进步骤；Human 只审整条方案一次（T03） |
| 「前端也可以/后端也可以」并列 | 必须按最小 effort 选定唯一落点 |
| 模糊待办（「需要进一步确认代码位置」） | Agent 应自行检索代码库 |

### 必须

| 必须项 | 说明 |
|--------|------|
| **平台与环境判定** | 先判断 issue 属于 backend/API、数据/COS/VOD 管线、inputbaby_app、nativesense-admin、wecom、websites、canonical_frontend 或跨端；再判断 local / staging / production / unknown |
| **问题类别判定** | 明确 operation/usage、data/state、code defect、configuration/deployment、external dependency、permissions/auth、device/network/cache、product-spec ambiguity 中最可能的类别 |
| **诊断顺序** | 先排除操作/使用问题，再排查数据/状态，最后进入代码缺陷；数据问题必须沿 source-of-truth 与处理链路找不变锚点 |
| **Evidence** | 每条技术结论附 `文件路径:行号或符号名`（来自**已同步**的 `projects/asp/` worktree 实际阅读） |
| **唯一推荐方案** | 一条实现路径：改哪些文件、什么顺序、为何是该 surface；预检/dry-run/环境阶梯写为强制步骤，不用「可选」语气 |
| **最小 effort** | 数据过滤/聚合/大列表加工优先 **backend**；前端只展示已加工结果 |
| **固定执行路径** | worktree 对应 surface → 分支 `issue-{N}/{surface}`（single-repo：`issue-{N}`）→ Smart PR |
| **API 文档** | 涉及 HTTP API 变更时，「推荐方案」与「改动文件」**必须**含 Swagger/OpenAPI（或 surface AGENTS.md 声明的 API 文档 SSOT）及同步步骤；无 API 变更则写「无需更新 Swagger」 |
| **App 版本** | 涉及可安装 App 交付时，「推荐方案」**必须**列版本文件路径与 bump 步骤（如 Android `versionCode`/`versionName`）；无 App 构建则写「无 App 构建，无需 bump 版本」 |

### 唯一允许「无法本地验证」的例外

- 需 **SSH 生产服务器** 做数据修复/迁移/一次性脚本，且本地无法复现数据状态
- 此时明确写：生产操作步骤 + 回滚 + 谁授权（Human）

### 产品口径歧义（非技术）

- 需求描述矛盾、业务规则不清 → 单独 **「待确认（产品）」** 小节
- 在 issue comment 写清待确认点；由需求负责人在 **issue 上回复**澄清（不要只走飞书私聊）
- Pipeline D 检测到 `待确认（产品）` 非「无」时**跳过执行**，直到 Analysis 更新或歧义消除
- **不得**把产品歧义与技术未读混为一谈

---

## 输出模板（Issue comment 内 Analysis 部分）

```markdown
### 1. 需求概述
（2-3 句，仅复述 Issue 事实）

### 2. 去重判断
（完全重复 / 部分相关 / 无重复 + 理由）

### 3. 影响模块（Evidence）
- **平台/Surface**: backend/API | data/COS/VOD | inputbaby_app | nativesense-admin | wecom | websites | canonical_frontend | cross-surface
- **环境**: local | staging/test | production | unknown（写明 base URL、版本、branch/commit、账号角色、设备/浏览器，未知则说明缺口）
- `path/to/file.py:123` — 说明
- ...

### 4. 问题类别与根因（Evidence）
- **问题类别**: operation/usage | data/state | code defect | configuration/deployment | external dependency | permissions/auth | device/network/cache | product-spec ambiguity
- **操作/使用排除**: 已排除/未排除 + 证据或缺口
- **数据/状态排查**: source-of-truth -> pipeline checkpoint -> 当前状态；非数据问题写 N/A
- **代码结论**: 基于已读代码的数据流结论；禁止在未排除操作和数据路径时把代码缺陷当默认根因

### 5. 推荐方案（唯一）
1. 步骤一 …
2. 步骤二 …
**改动文件**: `...`, `...`
**文档/API**: API 有变更 → Swagger/OpenAPI 路径与要点；无 API 变更 →「无 API 变更，无需更新 Swagger」
**App/版本**: 有 App 构建 → 版本文件路径与 bump 步骤；无 App 交付 →「无 App 构建，无需 bump 版本」
**为何不用其他 surface**: 一句（如「过滤逻辑已在 API 层，改 backend 一处即可」）

### 6. 执行路径
- **Worktree**: `projects/asp/` → `<surface 目录>`（见 `projects/asp/AGENTS.md`）
- **分支**: `issue-{N}/{surface}`
- **提 PR**: `./venv/bin/python tools/smart_pr.py --issue {N} --surface {surface}`
- **Base / Reviewer**: 由 `contexts/team_registry.yaml` 自动解析

### 7. Scope
S/M/L + 一句依据

### 8. 三角分工
| 角色 | 本 issue 产出 |
|------|---------------|
| Human | 审核本节推荐方案（一次 Gate）；授权生产；验收 PR。不逐步确认 dry-run、查库等过程步骤 |
| Agent | worktree 实现 + Smart PR |
| Script | CI / 回归 / 部署脚本（如有）|

### 待确认（产品）（可选）
- 仅当存在产品口径歧义；列出问题并 @ 需求负责人，要求在 issue 回复
```

---

## 运行方式

```bash
# 单条（推荐测试）
export GITHUB_ASSIGNEE=marviny   # 或本机对应 GitHub login
./venv/bin/python tools/feishu_inbound/issue_scanner.py --issue <N> --force

# 或通过 GitHub label 触发（lead tick 自动拾取，无需 --force）
# 在 issue 上加 request-reanalysis；成功后引擎自动清除该 label 及下游 gate labels
```

脚本会校验输出：必须含 `### 1. 需求概述`，且不得含 Progress/Goal 等 planning dump；不合格则 AgentClient 自动请求终稿，仍失败则不写 comment。

分析 backend 由 [Agent Client Routing](./workflow_agent_client_routing.md) 路由（根据 `difficulty-*` label 决定 intent / routing_profile）。

```bash
# 自动处理本账户队列中最新 1 条（默认 --batch 1）
./venv/bin/python tools/feishu_inbound/issue_scanner.py

# trivial 并行批量
./venv/bin/python tools/feishu_inbound/issue_scanner.py --parallel --batch 5

# 各开发者本机定时（每人设置自己的 GITHUB_ASSIGNEE）
./periodic_jobs/ai_heartbeat/install_launchd_jobs.sh --with-feishu-inbound-agent
```

## 相关

- [**Feishu Inbound Pipeline（顶层编排）**](./workflow_feishu_inbound_pipeline.md) — 全流程总览 A–E
- [**Stage D: Feishu Inbound Executor**](./workflow_feishu_inbound_executor.md) — 自动执行 + Smart PR（本 workflow 的下游）
- [Feishu Inbound Pipeline 任务文档](../../docs/tasks/asp/20260519_feishu_inbound_requirement_pipeline.md)
- [Smart PR Workflow](./workflow_smart_pr.md)
- [ASP Post Implement](./workflow_asp_post_implement.md)

# Feishu Inbound Executor Workflow

## 元数据

- **类型**: Workflow
- **适用场景**: **Pipeline D（自动执行 + Smart PR）**——读取已分析 Issue 的 Analysis comment，在 surface worktree 中 spawn Agent 实现推荐方案，提交 Smart PR
- **边界**: Pipeline A = 飞书 → Issue；Pipeline B = 分诊；Pipeline C = 深度分析；本 workflow 仅在 C 完成后触发
- **触发**: issue executor、自动执行 issue、execute analyzed issues
- **工具**: `tools/feishu_inbound/issue_executor.py`（ASP repo）
- **创建日期**: 2026-06-02

---

## Pipeline D 扫描与 Gate 逻辑

| 类型 | 条件 | 说明 |
|------|------|------|
| **扫描** | `state=open` + assignee 含 `GITHUB_ASSIGNEE` + `analyzed` label | 宽进：只看 open + 属于我 + 已分析 |
| **跳过** | 已有 `executed` 或 `execution-in-progress` | 幂等 / 互斥 |
| **Gate** | `difficulty-trivial` 自动；其他需 `approved-to-execute` label | Human 审核分析报告后手动加 label |
| **跳过** | `待确认（产品）` 非「无」 | 产品歧义未解决，不自动执行 |

### 难度 Gate

| difficulty label | 自动执行？ | 说明 |
|------------------|-----------|------|
| `difficulty-trivial` | 是 | 配置/文案/简单修改，Analysis comment 即指令 |
| `difficulty-standard` | 否 | 需 Human 在 issue 加 `approved-to-execute` label |
| `difficulty-complex` | 否 | 需 Human 加 `approved-to-execute` label；sequential 执行 |

### Label 生命周期

```
C 完成 → analyzed
Human 审核 → approved-to-execute（trivial 不需要）
D 开始 → execution-in-progress（互斥锁）
D 成功 → executed + 移除 lock
D 失败 → execution-failed + 移除 lock
```

---

## 执行流程

1. **解析 Analysis comment**：从 `## Feishu Inbound Analysis` 提取 surface、分支、推荐方案、影响文件
2. **Worktree 同步**：`sync_asp_worktrees([surface])`
3. **创建 issue 分支**：`git checkout -B issue-{N}/{surface}` from `origin/{base_branch}`
4. **Spawn Agent**：`AgentClient.run(prompt, workdir=surface_worktree, intent="execution")`
   - prompt 包含 issue 原文 + Analysis comment 全文
   - Agent 严格按推荐方案实现，不扩展范围
   - **API 变更时必须在同一 PR 更新 Swagger/OpenAPI**（或 Analysis 列出的 API 文档 SSOT），与实现保持一致
   - **App 交付时必须在同一 PR bump 版本号**（如 Android `versionCode`/`versionName`，以 surface `AGENTS.md` 为准）
   - 实现完成后 git add + commit
5. **验证**：检查 branch 有 commits ahead of base
6. **Smart PR**：`python tools/smart_pr.py --issue {N} --surface {surface}`（不 handback；assignee 保持 lead 直至 Pipeline F）
7. **标记完成**：加 `executed` label，移除 `execution-in-progress`

---

## 运行方式

```bash
# 扫描可执行 issue（不执行）
python tools/feishu_inbound/issue_executor.py --scan-only

# 单条 dry-run（解析 Analysis，打印执行计划）
python tools/feishu_inbound/issue_executor.py --issue 441 --dry-run

# 单条执行
python tools/feishu_inbound/issue_executor.py --issue 441

# 只实现不提 PR（调试用）
python tools/feishu_inbound/issue_executor.py --issue 441 --skip-pr

# 批量并行执行
python tools/feishu_inbound/issue_executor.py --batch 3 --parallel

# 跳过 gate（强制执行未审批的 issue）
python tools/feishu_inbound/issue_executor.py --issue 441 --force
```

---

## Agent Prompt 约束

执行 Agent 收到的 prompt 包含以下硬性规则：

1. 严格按推荐方案步骤和文件列表实现，不扩展范围
2. 实现后 `git add` + `git commit -m "fix: #{N} — <简述>"`
3. 不做 deploy / migration / 生产操作
4. 不修改与推荐方案无关的文件
5. 若某步骤无法实现（文件不存在、接口已变），commit message 注明差异
6. **API 文档**：涉及 HTTP API 变更时，同一 PR 内更新 Swagger/OpenAPI（或 Analysis 所列 API 文档 SSOT）；仅改代码不更文档视为未完成
7. **App 版本**：涉及 App 构建/安装包交付时，同一 PR 内按 surface 约定 bump 版本号；仅改代码不 bump 视为未完成

---

## 相关

- [**Feishu Inbound Pipeline（顶层编排）**](./workflow_feishu_inbound_pipeline.md) — 全流程总览 A→F
- [Stage E: Gate Review](./workflow_feishu_inbound_gate_review.md)
- [Stage F: Dev Handback](./workflow_feishu_inbound_dev_handback.md)
- [Stage C: Feishu Inbound Agent](./workflow_feishu_inbound_agent.md) — 深度分析（D 的上游）
- [Smart PR Workflow](./workflow_smart_pr.md) — PR 自动化
- [ASP Post Implement](./workflow_asp_post_implement.md) — PR 合入后收尾

# ASP Skills Index

ASP 项目级 skill，专注于需求闭环（分诊 → 分析 → PR → 部署 → 验收）。

## Workflow

- [Triage Routing](./workflow_triage_routing.md) — 综合 Agent 分诊：中央 issue → surface 判定 + difficulty + assignee → 各 repo 创建执行 issue
- [Inbound Pipeline](./workflow_inbound_pipeline.md) — 飞书入站全流程 A→F（给人读的 ASP 版）
- [Inbound Pipeline（完整 SSOT 副本）](./workflow_inbound_pipeline_full.md) — rootgrove 同步的完整编排文档
- [Inbound Agent（C）](./workflow_inbound_agent.md) — 深度分析 comment 契约
- [Inbound Executor（D）](./workflow_inbound_executor.md) — 自动执行 + Smart PR
- [Gate Review（E）](./workflow_gate_review.md) — AI 门禁 + 人测 gate 入口
- [Gate Review（完整）](./workflow_gate_review_full.md)
- [Human Gate（E 人测，Legacy）](./workflow_human_gate.md) — `/gate pass|fail`，存量 issue
- [Dev Acceptance](./workflow_acceptance.md) — **新** dev 验收：`accept pass|fail` → `dev-accepted` + promote PR
- [Dev Handback（F）](./workflow_dev_handback.md) — dev CI/CD 成功后验收指派
- [Dev Handback（完整）](./workflow_dev_handback_full.md)
- [Post Implement](./workflow_post_implement.md) — issue 完成收尾（PR 合入 + 飞书通知 + 中央 issue 关闭）
- [Smart PR](./workflow_smart_pr.md) — Smart PR 在 ASP 多 repo 下的约定（`tools/smart_pr.py`）

## Cursor Skills（`.cursor/skills/`）

团队 clone 本 repo 后，Cursor 自动发现：

| Skill | 用途 |
|-------|------|
| `feishu-inbound-agent` | Pipeline C 分析 |
| `feishu-inbound-human-gate` | E 人测 gate（Legacy） |
| `feishu-inbound-acceptance` | F 之后 dev 验收 |

同步命令（在 rootgrove 执行）：`bash tools/feishu_inbound/sync_skills_to_asp_infra.sh`

## Contract

- [Debug Analysis](./contract_debug_analysis.md) — ASP Debug 分析 comment 的输出格式契约
- [Triage Comment](./contract_triage_comment.md) — 分诊 comment 的输出格式契约

## Reference

- [Surface Conventions](./reference_surface_conventions.md) — 各 surface 构建/部署/分支约定汇总

# ASP Skills Index

ASP 项目级 skill，专注于需求闭环（分诊 → 分析 → PR → 部署 → 验收）。

**全员参与**： [inbound_pipeline_team_guide.md](../docs/inbound_pipeline_team_guide.md) · 环境引导 [onboarding_inbound_skills.md](../docs/onboarding_inbound_skills.md)

## Workflow（按流水线段）

| 段 | 短指南 | 完整 SSOT | Cursor Skill |
|----|--------|-----------|--------------|
| B 分诊 | [Triage Routing](./workflow_triage_routing.md) | [inbound_triage](./workflow_inbound_triage.md) | `feishu-inbound-triage` |
| C 分析 | [Agent](./workflow_agent.md) | [inbound_agent](./workflow_inbound_agent.md) | `feishu-inbound-agent` |
| C→D 审方案 | [Plan Approval](./workflow_plan_approval.md) | [plan_approval_full](./workflow_plan_approval_full.md) | `feishu-inbound-plan-approval` |
| D 执行 | [Executor](./workflow_executor.md) | [inbound_executor](./workflow_inbound_executor.md) | `feishu-inbound-executor` |
| E 门禁 | [Gate Review](./workflow_gate_review.md) | [gate_review_full](./workflow_gate_review_full.md) | `feishu-inbound-gate-review` |
| F handback | [Dev Handback](./workflow_dev_handback.md) | [dev_handback_full](./workflow_dev_handback_full.md) | — |
| 验收 | [Dev Acceptance](./workflow_acceptance.md) | — | `feishu-inbound-acceptance` |
| Legacy 人测 | [Human Gate](./workflow_human_gate.md) | — | `feishu-inbound-human-gate` |

## 总览与其它

- [Inbound Pipeline](./workflow_inbound_pipeline.md) — ASP 版 A→F 总览
- [Inbound Pipeline（完整）](./workflow_inbound_pipeline_full.md)
- [Post Implement](./workflow_post_implement.md)
- [Smart PR](./workflow_smart_pr.md)

## Cursor Skills（`.cursor/skills/`）

用 Cursor **打开 asp 仓库根目录** 后自动加载（在 `asp-backend` 等 surface 仓库内不会出现）。

| Skill | 参与者 |
|-------|--------|
| `feishu-inbound-triage` | 总监机 |
| `feishu-inbound-agent` | Assignee / lead |
| `feishu-inbound-plan-approval` | Reviewer / assignee |
| `feishu-inbound-executor` | Assignee / lead |
| `feishu-inbound-gate-review` | Assignee / lead |
| `feishu-inbound-acceptance` | GitHub 负责人（dev 验收）；pass 后 assign release owner 做 prod |
| `feishu-inbound-human-gate` | 负责人（存量 issue） |

一次性环境：`bash scripts/bootstrap_inbound_cli.sh`

维护者同步（rootgrove）：`bash tools/feishu_inbound/sync_skills_to_asp_infra.sh`

## Contract

- [Debug Analysis](./contract_debug_analysis.md)
- [Triage Comment](./contract_triage_comment.md)

## Reference

- [Surface Conventions](./reference_surface_conventions.md)

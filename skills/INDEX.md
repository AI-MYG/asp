# ASP Skills Index

ASP 项目级 skill，专注于需求闭环（分诊 → 分析 → PR → 部署 → 通知）。

## Workflow

- [Triage Routing](./workflow_triage_routing.md) — 综合 Agent 分诊：中央 issue → surface 判定 + difficulty + assignee → 各 repo 创建执行 issue
- [Inbound Pipeline](./workflow_inbound_pipeline.md) — 飞书入站全流程 A→F
- [Gate Review（E）](./workflow_gate_review.md) — PR dev 门审查
- [Dev Handback（F）](./workflow_dev_handback.md) — dev CI/CD 成功后验收指派
- [Post Implement](./workflow_post_implement.md) — issue 完成收尾（PR 合入 + 飞书通知 + 中央 issue 关闭）
- [Smart PR](./workflow_smart_pr.md) — Smart PR 在 ASP 多 repo 下的约定（`tools/smart_pr.py`）

## Contract

- [Debug Analysis](./contract_debug_analysis.md) — ASP Debug 分析 comment 的输出格式契约
- [Triage Comment](./contract_triage_comment.md) — 分诊 comment 的输出格式契约

## Reference

- [Surface Conventions](./reference_surface_conventions.md) — 各 surface 构建/部署/分支约定汇总

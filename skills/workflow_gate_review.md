# Gate Review（Pipeline E）

给人读的 E 段说明。**完整契约 SSOT**：rootgrove `rules/skills/workflow_feishu_inbound_gate_review.md`（2026-06-20 更新：E 统一 gate = AI 门禁 + 人测 gate）。

## 这一步做什么？

**段 1 · AI 门禁（合 dev 前）**：D 已开 PR。用不同于 D 的 Agent 审查；通过 → `review-dev-pass`；打回 → D 修订。**不** assign 飞书提需人。

**段 2 · 人测 gate（F 之后）**：飞书提需人在飞书侧验收；**GitHub 负责人**在 issue 发 `## Pipeline E Gate Review` + `/gate pass|fail`；`review` 尾部 `human_gate` 处理。

## 脚本

`tools/feishu_inbound/issue_pr_reviewer.py` — Lead tick（`:20/:50`）

配置：`config.yaml` → `pipeline_e`

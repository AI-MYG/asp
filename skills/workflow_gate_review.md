# Gate Review（Pipeline E）

给人读的 E 段说明。**完整契约**： [workflow_gate_review_full.md](./workflow_gate_review_full.md)

## 这一步做什么？

**段 1 · AI 门禁（合 dev 前）**：D 已开 PR。用不同于 D 的 Agent 审查；通过 → `review-dev-pass`；打回 → D 修订。**不** assign 飞书提需人。

**段 2 · 人测 gate（F 之后，Legacy）**：飞书提需人在飞书侧验收；**GitHub 负责人**在 issue 发 `## Pipeline E Gate Review` + `/gate pass|fail`。详见 [Human Gate](./workflow_human_gate.md)。

**新 dev 验收（推荐）**：F 之后用 [Dev Acceptance](./workflow_acceptance.md)（`feishu-inbound accept pass|fail`），不用 `/gate`。

## 脚本

`tools/feishu_inbound/issue_pr_reviewer.py` — Lead tick（`:20/:50`）

配置：`config.yaml` → `pipeline_e`

# Gate Review（Pipeline E）

给人读的 E 段说明。**完整契约**： [workflow_gate_review_full.md](./workflow_gate_review_full.md)

## 这一步做什么？

**段 1 · AI 门禁（合 dev 前）**：D 已开 PR。用不同于 D 的 Agent 审查；通过 → `review-dev-pass`；打回 → D 修订。

```bash
source scripts/load_asp_env.sh
export GITHUB_ASSIGNEE=<你>
./venv/bin/python tools/feishu_inbound/issue_pr_reviewer.py --issue <N> --repo <owner/repo>
```

**Cursor Skill**：`feishu-inbound-gate-review`

**段 2 · 人测 gate（F 之后，Legacy）**：见 [Human Gate](./workflow_human_gate.md)。

**新 dev 验收**：F 之后用 [Dev Acceptance](./workflow_acceptance.md) + `bash scripts/run_accept.sh pass ...`

配置：`tools/feishu_inbound/config.yaml` → `pipeline_e`

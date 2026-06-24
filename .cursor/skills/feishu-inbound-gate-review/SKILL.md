---
name: feishu-inbound-gate-review
description: >-
  Pipeline E AI gate: read-only PR review after Pipeline D; adds review-dev-pass or
  sends back to D with review-changes-requested. Does not merge or edit code.
  Use when user says gate review、Pipeline E、PR 门禁、review-dev-pass、issue pr reviewer.
---

# Feishu Inbound Gate Review (Pipeline E — AI)

Full skill: [skills/workflow_gate_review_full.md](../../../skills/workflow_gate_review_full.md)

Dev **business** acceptance after F uses [feishu-inbound-acceptance](../feishu-inbound-acceptance/SKILL.md), not this skill.

## ASP team setup

```bash
cd ~/CursorWorks/asp-infra
bash scripts/bootstrap_inbound_cli.sh
source scripts/load_asp_env.sh
export GITHUB_ASSIGNEE=<your_github_login>
```

## Run (single issue)

```bash
./venv/bin/python tools/feishu_inbound/issue_pr_reviewer.py \
  --issue <N> --repo <owner/repo>
```

Dry-run: add `--dry-run`. Scan: `--scan-only`.

After `review-dev-pass`, a human merges PR to dev; then F handback and Acceptance follow.

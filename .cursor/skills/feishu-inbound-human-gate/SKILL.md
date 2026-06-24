---
name: feishu-inbound-human-gate
description: >-
  Legacy Pipeline E human gate after F dev handback: GitHub 负责人 records business
  acceptance on the issue with ## Pipeline E Gate Review and /gate pass or /gate fail
  after the Feishu requester confirms in Feishu. Triggers human_gate via issue_pr_reviewer.
  For new issues use feishu-inbound-acceptance (accept CLI) instead. Use when user says
  人测 gate、业务验收代确认、/gate pass、/gate fail、human gate、Pipeline E 人测、代录验收.
disable-model-invocation: true
---

# Feishu Inbound Human Gate (Legacy)

Full skill: [skills/workflow_human_gate.md](../../../skills/workflow_human_gate.md)

**Prefer** [feishu-inbound-acceptance](../feishu-inbound-acceptance/SKILL.md) for new issues (engine v0.1.17+).

## Quick path

1. Confirm F handback: `review-dev-pass` + `## Pipeline F Dev Handback` + assignee = GitHub 负责人.
2. After Feishu requester confirms, post gate comment on the issue (pass or fail template in SSOT).
3. Run reviewer so `human_gate` parses the comment:

```bash
source scripts/load_asp_env.sh
# run from asp-infra repo root
python tools/feishu_inbound/issue_pr_reviewer.py --issue <N> --repo <owner/repo>
```


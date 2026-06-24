---
name: feishu-inbound-plan-approval
description: >-
  Human gate between Pipeline C and D: review Feishu Inbound Analysis on a GitHub
  issue and add approved-to-execute label (standard/complex only; trivial skips).
  Use when user says 审核分析、授权执行、approved-to-execute、plan approval、分析通过了、可以执行了.
disable-model-invocation: true
---

# Feishu Inbound Plan Approval

Full skill: [skills/workflow_plan_approval_full.md](../../../skills/workflow_plan_approval_full.md)

ASP 组员环境: `docs/onboarding_inbound_skills.md`

## Quick path

1. Read `## Feishu Inbound Analysis` on the issue.
2. If `difficulty-trivial`, no label needed (D auto-runs).
3. If standard/complex and plan is OK:

```bash
gh issue edit <N> --repo <owner/repo> --add-label "approved-to-execute"
```

4. To request re-analysis: `gh issue edit ... --add-label "request-reanalysis"`

Do **not** approve if `待确认（产品）` section has open items.

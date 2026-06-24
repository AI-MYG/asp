---
name: feishu-inbound-acceptance
description: >-
  Dev acceptance after Pipeline F handback: record pass/fail via feishu-inbound accept CLI.
  On pass adds dev-accepted, dispatches scoped promote PR, and requester approves prod PR.
  Use when user says 验收通过、验收不通过、accept pass、accept fail、dev acceptance、
  dev-accepted、promote PR、按 Acceptance、issue 验收.
disable-model-invocation: true
---

# Feishu Inbound Acceptance

Full skill: [skills/workflow_acceptance.md](../../../skills/workflow_acceptance.md)

Engine SSOT: `projects/feishu-inbound-skill/docs/acceptance_gate.md`

## Quick path (ASP)

```bash
source scripts/load_asp_env.sh
# run from asp-infra repo root

# Pass
./venv/bin/feishu-inbound accept pass \
  --config tools/feishu_inbound/config.yaml \
  --issue <N> --repo <owner/repo>

# Fail
./venv/bin/feishu-inbound accept fail \
  --config tools/feishu_inbound/config.yaml \
  --issue <N> --repo <owner/repo> \
  --reason "<reason>"
```

Personal instances: use `config/feishu_inbound_<instance>.yaml` instead.


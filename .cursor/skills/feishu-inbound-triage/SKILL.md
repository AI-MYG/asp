---
name: feishu-inbound-triage
description: >-
  Pipeline B: triage feishu-inbound central issues — surface, scope, difficulty,
  assignee labels and triage comment. Runs on director Mac (launchd :10/:40).
  Use when user says triage、分诊、feishu inbound triage、pipeline B、triaged label.
disable-model-invocation: true
---

# Feishu Inbound Triage (Pipeline B)

Workflow: [skills/workflow_inbound_triage.md](../../../../skills/workflow_inbound_triage.md)

ASP routing SSOT: `skills/workflow_triage_routing.md` (after clone).

## ASP director Mac

```bash
cd ~/CursorWorks/asp-infra
bash scripts/bootstrap_inbound_cli.sh
source scripts/load_asp_env.sh
bash scripts/run_feishu_inbound_triage.sh
```

Single issue: `./venv/bin/python tools/feishu_inbound/triage_agent.py --issue <N>`

Scheduled: `com.asp.feishu-inbound-triage` via `bash launchd/install.sh`.

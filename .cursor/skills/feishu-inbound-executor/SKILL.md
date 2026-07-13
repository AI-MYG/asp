---
name: feishu-inbound-executor
description: >-
  Pipeline D: execute analyzed feishu-inbound issues in surface worktrees, implement
  the single recommended plan, and open Smart PR. Requires analyzed label and
  approved-to-execute (except trivial). Use when user says 执行 issue、pipeline D、
  issue executor、自动执行、execute analyzed、跑 executor.
---

# Feishu Inbound Executor (Pipeline D)

Full skill: [skills/workflow_inbound_executor.md](../../../../skills/workflow_inbound_executor.md)

## ASP team setup

```bash
cd ~/CursorWorks/asp-infra   # AI-MYG/asp
bash scripts/bootstrap_inbound_cli.sh   # first time
source scripts/load_asp_env.sh
export GITHUB_ASSIGNEE=<your_github_login>
```

Requires surface worktrees under `ASP_WORKTREE_ROOT` (see `config/surfaces.yaml`).

## Run (single issue)

```bash
./venv/bin/python tools/feishu_inbound/issue_executor.py \
  --issue <N> --repo <owner/repo>
```

Scan queue: `./venv/bin/python tools/feishu_inbound/issue_executor.py --scan-only`

Lead tick also runs D at `:20/:50` when launchd installed on lead Mac.

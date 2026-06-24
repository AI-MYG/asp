---
name: feishu-inbound-agent
description: Process feishu-inbound GitHub issues with evidence-based single-plan analysis comments. No assumptions, no multi-option proposals; execution via worktree + Smart PR. Use when user says 处理飞书需求、feishu inbound、inbound agent、Pipeline C、深度分析、issue scanner.
---

# Feishu Inbound Agent (Pipeline C)

Reference spec: [skills/workflow_inbound_agent.md](../../../skills/workflow_inbound_agent.md)

## ASP team setup

```bash
cd ~/CursorWorks/asp-infra   # GitHub: AI-MYG/asp
bash scripts/bootstrap_inbound_cli.sh
source scripts/load_asp_env.sh
export GITHUB_ASSIGNEE=<your_github_login>
```

Open **asp repo root** in Cursor for this skill. See `docs/onboarding_inbound_skills.md`.

## Run (single issue)

```bash
./venv/bin/python tools/feishu_inbound/issue_scanner.py --issue <N> --repo <owner/repo> --force
```

Scan queue: `--scan-only` or `bash scripts/run_feishu_inbound_lead_tick.sh` (full C→F chain on lead Mac).

## Contract (summary)

One recommended solution only; Evidence `path:line`; Human reviews plan then adds `approved-to-execute` (see [feishu-inbound-plan-approval](../feishu-inbound-plan-approval/SKILL.md)). Product ambiguity → issue comment, not Feishu DM.

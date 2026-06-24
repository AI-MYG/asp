---
name: feishu-inbound-agent
description: Process feishu-inbound GitHub issues with evidence-based single-plan analysis comments. No assumptions, no multi-option proposals; execution via worktree + Smart PR. Use when user says 处理飞书需求、feishu inbound、inbound agent, or when running tools/feishu_inbound/inbound_agent.py.
---

# Feishu Inbound Agent

Reference spec: [skills/workflow_inbound_agent.md](../../../skills/workflow_inbound_agent.md)

Comment contract: verify in synced `projects/asp/` worktrees; one recommended solution only; Human reviews plan; Agent implements via `issue-{N}/{surface}` + `tools/smart_pr.py`. **Sync**: non-owned surfaces only (`GITHUB_ASSIGNEE`); owned surfaces allow local WIP. Product ambiguity → [workflow_asp_pr_review_feedback.md](../../../skills/workflow_asp_pr_review_feedback.md).

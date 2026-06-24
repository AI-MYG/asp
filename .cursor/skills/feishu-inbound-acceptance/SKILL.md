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

**ASP 组员（不必 clone rootgrove）**: [docs/onboarding_inbound_skills.md](../../../docs/onboarding_inbound_skills.md) · [全员指南](../../../docs/inbound_pipeline_team_guide.md)

## 必须执行（不要只发 GitHub 评论）

ASP 仓库根目录：

```bash
bash scripts/bootstrap_inbound_cli.sh   # 首次
bash scripts/run_accept.sh pass --issue <N> --repo <owner/repo>
```

验证 `dev-accepted` + `## Dev Acceptance — Recorded`。

Engine SSOT: `369795172/feishu-inbound-skill` → `docs/acceptance_gate.md`


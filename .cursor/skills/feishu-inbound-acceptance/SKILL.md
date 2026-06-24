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

**组员环境（不必 clone rootgrove）**: [docs/onboarding_inbound_skills.md](../../../docs/onboarding_inbound_skills.md)

## 必须执行（不要只发 GitHub 评论）

1. 确认 workspace 为 **asp 仓库根**（`AI-MYG/asp`），或已按 onboarding 做 sparse checkout。
2. 首次：`bash scripts/bootstrap_inbound_cli.sh`
3. 在终端执行（将 issue/repo 换成实际值）：

```bash
bash scripts/run_accept.sh pass --issue <N> --repo <owner/repo>
# fail: bash scripts/run_accept.sh fail --issue <N> --repo <owner/repo> --reason "..."
```

4. 验证 issue 出现 `dev-accepted` 与 `## Dev Acceptance — Recorded`。

**禁止**：仅用 `gh issue comment` 贴 `## Dev Acceptance` 后结束；那不会可靠触发 promote PR。

Engine SSOT: `369795172/feishu-inbound-skill` → `docs/acceptance_gate.md`

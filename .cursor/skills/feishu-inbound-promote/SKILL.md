---
name: feishu-inbound-promote
description: >-
  After Acceptance pass (dev-accepted + Promote handoff): validate surface/repo/head_sha
  fail-closed gates, then dispatch scoped promote PR via feishu-inbound promote.
  Use when user says Promote Skill、feishu-inbound promote、promote handoff、
  创建 promote PR、生产门禁、dev-accepted 后开生产 PR.
disable-model-invocation: true
---

# Feishu Inbound Promote

Full skill: [skills/workflow_promote.md](../../../../skills/workflow_promote.md)

**ASP 组员（不必 clone rootgrove）**: `docs/onboarding_inbound_skills.md`

## 必须执行

```bash
# rootgrove personal
./venv/bin/feishu-inbound promote --config tools/feishu_inbound/config.yaml --issue <N> --repo <owner/repo>

# ASP instance
cd projects/asp-infra
./venv/bin/feishu-inbound promote --config tools/feishu_inbound/config.yaml --issue <N> --repo <owner/repo>
```

验证：门禁通过后出现 promote PR；失败则 issue 有 `⚠️ promote blocked`。

Engine SSOT: `369795172/feishu-inbound-skill` → `docs/acceptance_gate.md` · `skills/skill_feishu_inbound_promote.md`


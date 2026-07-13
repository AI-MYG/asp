# Feishu Inbound Acceptance Workflow

## 元数据

- **类型**: Workflow（人工 + 引擎 CLI）
- **适用场景**: **Pipeline Acceptance**——F dev handback 之后，**issue 负责人**记录 dev 业务验收 pass/fail；pass 后引擎打 `dev-accepted`、发 Promote handoff、**assign `acceptance.release_owner`**
- **边界**: prod merge **不**自动化；promote PR 由 **Promote Skill** 门禁后创建（v0.1.32+）
- **触发**: dev acceptance、accept pass、accept fail、验收通过、验收不通过、dev-accepted
- **工具**: `feishu-inbound accept`（引擎 v0.1.17+）；lead tick 内 `accept --scan-only`
- **创建日期**: 2026-06-24
- **引擎 SSOT**: `projects/feishu-inbound-skill/docs/acceptance_gate.md`

---

## 原则

**负责人验收 dev，Promote Skill 建 promote PR，release owner 发 prod。**

E（`review`）仅做 **AI PR 门禁**；dev 业务验收与本 workflow 绑定，不用 `## Pipeline E Gate Review`。

---

## 角色

| 角色 | 本段职责 |
|------|----------|
| 飞书提需人 | 飞书侧验收 dev（业务确认） |
| GitHub 负责人 | 执行 `accept pass/fail` CLI（须已获飞书确认） |
| release owner / Agent | 执行 Promote Skill 创建 promote PR → review/merge prod |

配置：`acceptance.release_owner`（instance `config.yaml`）

---

## 流程

```text
E AI pass → 负责人 merge dev → F dev handback
→ accept pass|fail
   ├─ fail → review-changes-requested → D 修订
   └─ pass → dev-accepted + Promote handoff + assign release owner
→ Promote Skill（门禁通过才 dispatch）
→ release owner review / approve / merge prod PR
→ F prod handback 通知
```

---

## 前置条件（pass/fail 共用）

- `review-dev-pass` label 存在
- `## Pipeline F Dev Handback` 评论存在
- 尚无 `dev-accepted` label
- 尚无 `## Dev Acceptance — Recorded` 评论

---

## CLI（ASP 团队）

**组员环境（不必 clone rootgrove monorepo）**：SSOT 在 `projects/asp-infra/docs/onboarding_inbound_skills.md`。

```bash
cd projects/asp-infra   # GitHub: AI-MYG/asp
bash scripts/bootstrap_inbound_cli.sh    # 首次
bash scripts/run_accept.sh pass --issue <N> --repo <owner/repo>
```

**禁止**仅在 issue 手写 `## Dev Acceptance` 就结束；必须跑 CLI（或 lead 代跑 / lead tick 扫描）。

底层等价：`./venv/bin/feishu-inbound accept pass --config tools/feishu_inbound/config.yaml ...`

Promote（accept 之后）：`feishu-inbound promote --config ... --issue N --repo owner/repo`

---

## Pass 行为（v0.1.32+）

1. 发 `## Dev Acceptance` 评论（`/accept pass`）
2. 加 `dev-accepted` label
3. 发 `## Promote — Handoff`（建议 surface/repo/head_sha，**不** dispatch）
4. 将 issue **assign 给 `acceptance.release_owner`**
5. 发 `## Dev Acceptance — Recorded`

Promote PR 由 [Promote Workflow](./workflow_feishu_inbound_promote.md) 创建。

---

## Fail 行为（引擎自动）

1. 发 `## Dev Acceptance`（`/accept fail`，reason 必填）
2. 加 `review-changes-requested`；移除 `executed`、`review-dev-pass`、`dev-accepted`
3. assign 回流水线执行人 → D 下轮修订

---

## 评论契约（只读参考）

```markdown
## Dev Acceptance
/accept pass
环境: dev
提需人: <name>
```

```markdown
## Promote — Handoff
（含 surface/repo/head_sha 建议）
```

```markdown
## Dev Acceptance — Recorded
promote: queued for Promote Skill
assignee: @<release_owner>
```

---

## 配置片段

```yaml
pipeline_f:
  prod_eligibility_label: dev-accepted
  promote:
    dispatch_event: feishu-inbound-promote
    branch_mapping:
      backend: { source: dev, target: production }
      admin:   { source: dev, target: main }
      app:     { source: dev, target: main }

acceptance:
  release_owner: "<github_login>"
```

---

## Legacy human_gate

`## Pipeline E Gate Review` + `/gate pass|fail` 仍由 `human_gate` 处理存量 issue。新 issue **只用** `accept`。见 [Human Gate](./workflow_feishu_inbound_human_gate.md)。

---

## 相关

- [Feishu Inbound Pipeline](./workflow_feishu_inbound_pipeline.md)
- [Promote Workflow](./workflow_feishu_inbound_promote.md)
- [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md)
- [Scoped Promote PR](./workflow_scoped_promote_pr.md)
- [Engine API](./api_feishu_inbound_engine.md)

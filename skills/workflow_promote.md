# Feishu Inbound Promote Workflow

## 元数据

- **类型**: Workflow（Agent + 引擎 CLI）
- **适用场景**: Acceptance pass（`dev-accepted`）之后，**校验 surface/repo/head_sha 门禁**并 dispatch scoped promote PR
- **边界**: prod merge **不**自动化；仅 agent/CLI 显式触发 `repository_dispatch`
- **触发**: `## Promote — Handoff`、`dev-accepted`、`feishu-inbound promote`
- **工具**: `feishu-inbound promote`（引擎 v0.1.32+）；lead tick 内 `promote --scan-only`
- **引擎 SSOT**: `projects/feishu-inbound-skill/docs/acceptance_gate.md`、`skills/skill_feishu_inbound_promote.md`

---

## 原则

**Acceptance 只记录 dev 验收；Promote Skill 负责生产门禁 + 机械创建 PR。**

v0.1.32 起 `accept pass` **不再**自动 `repository_dispatch`。改为 handoff 评论 + Promote Skill 队列。

---

## 门禁（fail-closed）

| 检查项 | 规则 |
|--------|------|
| Surface SSOT | merged `issue-{N}/{surface}` > Analysis 执行路径 > surface label |
| Repo | `surfaces.yaml` 中 surface → repo |
| head_sha | 必须存在于 **surface_repo**（禁止跨仓 central SHA） |
| branch_mapping | `pipeline_f.promote.branch_mapping` 或 surfaces.yaml |
| Surface label | 若 issue 有 surface label，须与裁决 surface 一致 |
| **Migration serial** (#316) | changeset 含 `migrations/versions/*.py` 时，`down_revision` 祖先须已上 production；否则 fail-closed 并点名阻塞 issue |

失败 → `⚠️ promote blocked` 评论 + @release_owner；**不** dispatch。

### Migration 串行 vs 代码并行 (#316)

- **migration-issue**：`down_revision` 祖先未上 production 且归属其他 issue → 阻塞，等祖先 promote 后自动通过
- **code-only**：不受他人 pending migration 影响，保持并行 promote
- accept 可并行；production merge 跟 Alembic / `dev` merge 顺序
- **禁止**用累积 `dev → production` PR 解堵

---

## Promote Plan 挡板（stopgap，#464 落地后删除）

执行 promote 前先扫 issue comments 找 `## Promote Plan` 区块。存在 plan 的 issue：**禁止标准引擎 dispatch**，一切口径以 plan 的 YAML 为准（`status` / `file_set` / `carry_files` / `net_state_ref` / `prechecks` / `follow_up` 自描述，实例见 asp-backend #408/#449）。确认信号（`## Promote Plan Confirmation` + `/promote-plan confirm|fail`）只认**提需人（GitHub 负责人）**评论，agent 不得代发。根因（引擎单锚定 PR 丢多轮 revision 文件）与引擎层修复见 asp-backend #464。

---

## 流程（标准引擎路径）

```text
accept pass → dev-accepted + ## Promote — Handoff + assign release_owner
→ promote (agent/CLI) 校验门禁
   ├─ fail → ⚠️ promote blocked
   └─ pass → repository_dispatch feishu-inbound-promote → poll promote PR
→ release owner review / approve / merge prod PR
→ F prod handback
```

> 无 Promote Plan 的 issue 才走本路径。

---

## CLI

```bash
feishu-inbound promote --config tools/feishu_inbound/config.yaml --issue <N> --repo <owner/repo>
feishu-inbound promote --config tools/feishu_inbound/config.yaml --scan-only
```

---

## 存量恢复

pre-v0.1.32 的 `promote_pr: pending`（可能错仓）：手动跑一次 Promote Skill；勿重放旧 cross-repo dispatch。

---

## 相关

- [Acceptance](./workflow_feishu_inbound_acceptance.md)
- [Scoped Promote PR](./workflow_scoped_promote_pr.md)
- [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md)

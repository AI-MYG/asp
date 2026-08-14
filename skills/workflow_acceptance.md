# Feishu Inbound Acceptance Workflow

## 元数据

- **类型**: Workflow（人工 + 引擎 CLI）
- **适用场景**: **Pipeline Acceptance**——F dev handback 之后，**issue 负责人**记录 dev 业务验收 pass/fail；pass 后引擎打 `dev-accepted`、dispatch scoped promote PR、**assign `acceptance.release_owner`** 做 prod review/approve/deploy
- **边界**: prod merge **不**自动化；release owner 人工合 prod
- **触发**: dev acceptance、accept pass、accept fail、验收通过、验收不通过、dev-accepted、promote PR
- **工具**: `feishu-inbound accept`（引擎 v0.1.17+）；lead tick 内 `accept --scan-only`
- **创建日期**: 2026-06-24
- **引擎 SSOT**: `projects/feishu-inbound-skill/docs/acceptance_gate.md`

---

## 原则

**负责人验收 dev，CI 建 promote PR，release owner 发 prod。**

E（`review`）仅做 **AI PR 门禁**；dev 业务验收与本 workflow 绑定，不用 `## Pipeline E Gate Review`。

---

## 角色

| 角色 | 本段职责 |
|------|----------|
| 飞书提需人 | 飞书侧验收 dev（业务确认） |
| GitHub 负责人 | 执行 `accept pass/fail` CLI（须已获飞书确认）；触发 promote PR |
| release owner | review / approve / merge promote PR → prod |

配置：`acceptance.release_owner`（instance `config.yaml`）

---

## 流程

```text
E AI pass → 负责人 merge dev → F dev handback
→ accept pass|fail
   ├─ fail → review-changes-requested → D 修订
   └─ pass → dev-accepted + dispatch promote + assign release owner
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

Personal / rootgrove instance：将 `config` 换为 `config/feishu_inbound_<instance>.yaml`，无 `run_accept.sh` 时用引擎 CLI 直接调用。

---

## Pass 行为（引擎自动）

1. 发 `## Dev Acceptance` 评论（`/accept pass`）
2. 加 `dev-accepted` label
3. `repository_dispatch` → `feishu-inbound-promote`
4. 轮询 open PR `promote/issue-{N}/{surface}`（超时 5min）
5. 将 issue **assign 给 `acceptance.release_owner`**
6. 发 `## Dev Acceptance — Recorded`（含 promote PR URL 与 prod 下一步）

---

## Fail 行为（引擎自动）

1. 发 `## Dev Acceptance`（`/accept fail`，reason 必填）
2. 加 `review-changes-requested`；移除 `executed`、`review-dev-pass`、`dev-accepted`
3. assign 回流水线执行人 → **默认回 Pipeline D 修订**（不是 C）

### Fail 后决策树（v0.1.40+）

| 根因 | 负责人动作 | 下一段 |
|------|------------|--------|
| 实现未对齐已批准 Analysis / dev 行为不符预期 | `run_accept.sh fail --reason "..."`（或引擎 `accept fail`） | **D** 下轮修订；D prompt 会摄入**完整** accept-fail 评论正文 |
| Analysis、数据源或产品口径本身有误 | fail 后人工加 `request-reanalysis` label | **C** 重跑分析 |
| 仅在 issue 发普通 comment | 无 | 引擎**忽略**，不触发 D/C |

Pipeline E 打回评论仅在含打回语义（`结论: 打回` / `Pipeline E 打回`）时进入 D 修订 prompt；与 accept-fail 同时存在时，accept-fail 在前。

### Fail 证据清单（提需人 / assignee）

- [ ] dev 环境已复现问题（URL / 账号 / 步骤写进 `--reason`）
- [ ] 对照已批准 Analysis 或 F handback 说明**哪条验收点未满足**
- [ ] 用 CLI 记录 fail（不要只手写 `## Dev Acceptance` 就结束）
- [ ] 若根因是方案/口径错，fail 后由负责人加 `request-reanalysis`，不要指望 D 自行改 Analysis

---

## 评论契约（只读参考）

引擎写入，人工一般不手写：

```markdown
## Dev Acceptance
/accept pass
环境: dev
提需人: <name>
```

```markdown
## Dev Acceptance — Recorded
promote PR: <url>
assignee: @<release_owner>（prod review / approve / deploy）
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
- [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md)
- [Scoped Promote PR](./workflow_scoped_promote_pr.md)
- [Engine API](./api_feishu_inbound_engine.md)

# Feishu Inbound Gate Review Workflow

## 元数据

- **类型**: Workflow
- **适用场景**: **Pipeline E（统一 gate）**——(1) **AI 门禁**：D 产出 open PR 后、合 dev 前的跨平台只读审查；(2) **人测 gate**：F 之后、业务验收由负责人在 GitHub 代录 pass/fail（与 AI 门禁共用 `## Pipeline E Gate Review` 评论契约）
- **边界**: 不改代码、不 merge；AI 阶段不 assign 飞书提需人；人测阶段不代替负责人在未收到业务确认时编造 pass
- **触发**: issue pr reviewer、gate review、Pipeline E、review-dev-pass、人测 gate、业务验收代确认
- **工具**: `tools/feishu_inbound/issue_pr_reviewer.py`（含尾部 `human_gate` 队列）
- **创建日期**: 2026-06-15
- **更新**: 2026-06-23（App 版本 bump blocking，引擎 v0.1.15 #30）

---

## 角色（与 Pipeline F 共用）

见 [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md#角色personal-与-asp-共用)。人测 gate 只认 **GitHub 负责人** 发的评论，不要求飞书提需人有 GitHub 账号。

---

## E 两段：AI 门禁与人测 gate

### 段 1：AI 门禁（合 dev 之前）

D 已实现并开了 PR，尚未合 dev。E 用**与 D 不同的 Agent 平台**（如 D=OpenCode、E=Cursor）读 PR diff + Analysis，判断：

- **通过** → `review-dev-pass` + AI 通过 comment + 飞书私信 lead
- **打回** → 去 `executed` + `review-changes-requested` + `## Pipeline E Gate Review` comment，D 下一轮修订

**文档审查（blocking）**：除代码正确性与方案符合度外，E **必须**审查「对应文档是否已更新」。API/对外行为有变更但 PR 未更新 Swagger/OpenAPI（或 Analysis 要求的 API 文档 SSOT）→ **打回**，不能仅因代码逻辑正确而通过。

**App 版本（blocking，v0.1.15+）**：Analysis 或推荐方案涉及 App 构建/安装包交付，但 PR 未按 surface 约定 bump 版本号（如 Android `versionCode`/`versionName`）→ **打回**。

此阶段 assignee 仍为流水线执行人；**不** assign 飞书提需人。

### 段 2：人测 gate（F 之后）

飞书提需人在**飞书侧**做业务验收（不进 GitHub）。负责人收到确认后，在本 issue 发 gate 评论；`review` 命令尾部 `human_gate` 解析并改 label。

- **通过** → 记录 comment；负责人可 close issue 或按项目惯例开 prod PR
- **打回** → `review-changes-requested`，去 `executed` 与 `review-dev-pass`，assignee 回流水线执行人，D 重跑

**人测 gate 触发条件（目标契约）**

1. label 含 `review-dev-pass`
2. 已有 `## Pipeline F Dev Handback` 评论（见 Pipeline F）
3. 当前 sole assignee 为评论中的 **GitHub 负责人**
4. 最新相关评论作者为负责人，且含 `## Pipeline E Gate Review` 与 `/gate pass` 或 `/gate fail`

---

## 人测 gate 评论模板（负责人代录）

负责人**仅在飞书提需人已业务确认后**填写：

```markdown
## Pipeline E Gate Review
/gate pass
飞书提需人: <与 F 验收评论一致>
代确认说明: <例：飞书 2026-06-20 确认 dev 验收通过>
```

打回时将 `/gate pass` 改为 `/gate fail`，并写明原因。

personal 可省略代确认说明，或写「本人验收」。

---

## AI 门禁：扫描与跳过

| 类型 | 条件 |
|------|------|
| **扫描** | `open` + assignee 含 `GITHUB_ASSIGNEE` + `executed` + 有 open 关联 PR + 无 `review-dev-pass` |
| **跳过** | 已有 `review-dev-pass` |
| **跳过** | `review-in-progress`（互斥锁） |
| **跳过** | 无 open 关联 PR |

调度：Lead tick `:20` / `:50` 链式调用 E（旧独立 `com.asp.issue-pr-reviewer` 已于 2026-06-19 退役）。

---

## 状态机（AI 门禁）

```
executed + open PR
        ↓
   E AI 门禁
        ↓
┌─ 通过 → review-dev-pass（保留 executed）→ 等待负责人 merge dev
└─ 打回 → review-changes-requested + 去 executed + ## Pipeline E Gate Review → D 修订
```

打回时 label 顺序：先加 `review-changes-requested`，再移除 `executed`。

---

## 状态机（人测 gate，F 之后）

```
review-dev-pass + F 验收评论 + 负责人为 assignee
        ↓
飞书提需人业务验收（飞书侧）
        ↓
负责人发 ## Pipeline E Gate Review
        ↓
human_gate（review 命令尾部）
        ↓
┌─ pass → 可 close / prod PR 手动
└─ fail → 去 executed + review-dev-pass，assign 执行人 → D 重跑
```

---

## 运行方式

```bash
source projects/asp-infra/scripts/load_asp_env.sh

python tools/feishu_inbound/issue_pr_reviewer.py --scan-only
python tools/feishu_inbound/issue_pr_reviewer.py --issue 125 --repo AI-MYG/asp-backend --dry-run
python tools/feishu_inbound/issue_pr_reviewer.py --issue 125 --repo AI-MYG/asp-backend
python tools/feishu_inbound/issue_pr_reviewer.py --batch 3 --parallel
```

配置 SSOT：`tools/feishu_inbound/config.yaml` → `pipeline_e`（AI 审查 Agent 平台池）。

人测 gate 无单独 CLI：在 F 之后再次执行 `review`（或 lead tick 链到 E 尾部）即可扫描待处理 gate 评论。

---

## 验收标准

**AI 门禁成功**：`review-dev-pass` 已打，comment 含 AI 审查结论（含**文档同步**维度），assignee 仍为执行人。

**人测 gate 成功**：负责人代录 comment 格式正确；pass/fail 后 label 与 assignee 符合上文状态机；ASP 场景下飞书提需人无需出现在 GitHub assignee 列表。

---

## 引擎对齐

- Issue #11：废弃 `ready-for-acceptance`；F marker + E 统一 gate 为 SSOT。
- 负责人代确认与 F 评论分字段：**文档已更新**；引擎 `human_gate` 仍以实现为准，下一版对齐「认 F 评论中的 GitHub 负责人，不认 GitHub 建单人」。

---

## 相关

- [Feishu Inbound Pipeline（A→F 总览）](./workflow_feishu_inbound_pipeline.md)
- [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md)
- [Pipeline D Executor](./workflow_feishu_inbound_executor.md)

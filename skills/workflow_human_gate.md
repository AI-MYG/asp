# Feishu Inbound Human Gate Workflow

## 元数据

- **类型**: Workflow（人工操作）
- **适用场景**: **Pipeline E 段 2（人测 gate）**——F dev handback 之后，飞书提需人在飞书侧完成业务验收，**GitHub 负责人**在 issue 代录 pass/fail
- **边界**: 不改代码、不 merge；仅在收到飞书业务确认后代录；**新 issue 优先走 [Acceptance](./workflow_feishu_inbound_acceptance.md)**（`accept` CLI）
- **触发**: 人测 gate、业务验收代确认、Pipeline E gate、/gate pass、/gate fail、human gate
- **工具**: `tools/feishu_inbound/issue_pr_reviewer.py`（尾部 `human_gate` 队列）；或 lead tick 链式触发
- **创建日期**: 2026-06-24
- **状态**: **Legacy**——仅处理存量 in-flight issue；新 dev 验收用 `accept`（引擎 v0.1.17+ #35）

---

## 角色

与 [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md#角色personal-与-asp-共用) 共用四角色名词。

| 角色 | 本段职责 |
|------|----------|
| 飞书提需人 | 飞书侧业务验收（不进 GitHub） |
| GitHub 负责人 | 收到飞书确认后，在 issue 发 gate 评论 |
| 流水线执行人 | pass 后可选 close / 开 prod PR；fail 后 D 修订 |

人测 gate **只认 GitHub 负责人**发的评论，不要求飞书提需人有 GitHub 账号。

---

## 何时用本 workflow（Legacy）

| 场景 | 用 |
|------|-----|
| 新 issue，引擎 ≥ v0.1.17 | [Acceptance](./workflow_feishu_inbound_acceptance.md)（`accept pass\|fail`） |
| 存量 issue 已用 `## Pipeline E Gate Review` | 本 workflow（`/gate pass\|fail`） |
| 不确定 | 看 issue 是否已有 `## Dev Acceptance` 记录；无则新 issue 走 `accept` |

---

## 前置条件

1. label 含 `review-dev-pass`
2. 已有 `## Pipeline F Dev Handback` 评论
3. 当前 sole assignee 为 F 评论中的 **GitHub 负责人**
4. 飞书提需人已在飞书侧完成业务验收（负责人不得编造 pass）

---

## 操作步骤（负责人）

### 1. 确认 F handback 已就绪

```bash
source projects/asp-infra/scripts/load_asp_env.sh   # ASP 团队
gh issue view <N> --repo <owner/repo> --json labels,assignees,comments
```

检查：`review-dev-pass`、F 验收评论、assignee 为负责人。

### 2. 飞书侧收到提需人确认后，在 issue 发评论

**通过**：

```markdown
## Pipeline E Gate Review
/gate pass
飞书提需人: <与 F 验收评论一致>
代确认说明: <例：飞书 2026-06-20 确认 dev 验收通过>
```

**打回**（将 `/gate pass` 改为 `/gate fail`，写明原因）：

```markdown
## Pipeline E Gate Review
/gate fail
飞书提需人: <与 F 一致>
原因: <业务验收不通过的具体原因>
```

personal 可省略代确认说明，或写「本人验收」。

### 3. 触发 human_gate 解析

```bash
# ASP instance
cd projects/asp-infra
source scripts/load_asp_env.sh
python tools/feishu_inbound/issue_pr_reviewer.py --issue <N> --repo <owner/repo>
```

或等待 lead tick（`:20` / `:50`）链式执行 E 尾部 `human_gate`。

---

## 状态机

```
review-dev-pass + F 验收评论 + 负责人为 assignee
        ↓
飞书提需人业务验收（飞书侧）
        ↓
负责人发 ## Pipeline E Gate Review + /gate pass|fail
        ↓
human_gate（review 命令尾部）
        ↓
┌─ pass → 可 close issue / 按项目惯例开 prod PR
└─ fail → 去 executed + review-dev-pass；assign 回执行人 → D 重跑
```

---

## 验收标准

- 评论格式含 `## Pipeline E Gate Review` 与 `/gate pass` 或 `/gate fail`
- pass/fail 后 label 与 assignee 符合状态机
- ASP 场景：飞书提需人无需出现在 GitHub assignee 列表

---

## 相关

- [Feishu Inbound Pipeline（A→F）](./workflow_feishu_inbound_pipeline.md)
- [Pipeline E Gate Review（AI + 人测总览）](./workflow_feishu_inbound_gate_review.md)
- [Dev Acceptance（新路径 SSOT）](./workflow_feishu_inbound_acceptance.md)
- [Pipeline F Dev Handback](./workflow_feishu_inbound_dev_handback.md)

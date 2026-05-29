# Triage Routing

## 元数据

- **类型**: Workflow
- **适用场景**: 综合 Agent 对中央 issue 做自动分诊，路由到对应 surface repo
- **触发**: 新 issue 带 `feishu-inbound` 标签；手动触发 `triage this issue`

## When to Use

中央 repo（AI-MYG/asp）收到新 issue 后，综合 Agent 执行本流程。

## Prerequisites

- GitHub Token 有 AI-MYG org 下所有 repo 的 issue 写权限
- `config/triage.yaml` 和 `config/surfaces.yaml` 可读

## Fixed Sequence

### 1. 读取中央 Issue

```bash
gh issue view <N> --repo AI-MYG/asp --json title,body,labels
```

### 2. Surface 判定

按 `config/triage.yaml` 的 `surface_routing` 关键词匹配：
- 单 surface 命中 → 直接路由
- 多 surface 命中 → 标记 `cross-surface`，assignee 用 `cross_surface_default`
- 无命中 → 标记 `needs-manual-triage`，不自动创建执行 issue

### 3. Difficulty 估算

按 `scope_heuristics` 评估：small / medium / large。

### 4. 创建执行 Issue

在目标 surface repo 创建 issue，body 使用 `execution_issue_body_template`：

```bash
gh issue create --repo <surface_repo> \
  --title "[ASP-<N>] <original_title>" \
  --body "<rendered_template>" \
  --assignee <assignee_id>
```

### 5. 更新中央 Issue

```bash
gh issue edit <N> --repo AI-MYG/asp --add-label "triaged,<surface>"
gh issue comment <N> --repo AI-MYG/asp --body "<triage_comment>"
```

Triage comment 格式见 `contract_triage_comment.md`。

### 6. Cross-surface 拆分（若适用）

多 surface 需求拆分为多个执行 issue，每个 issue 聚焦单一 surface。中央 issue comment 列出所有执行 issue 链接。

## Guardrails

- Agent 自主完成分诊，不打断用户（参考 rootgrove feedback: pipeline gate 自主决策）
- 无法判定 surface 时标记 `needs-manual-triage`，不猜测
- assignee 从 `config/triage.yaml` 读取，不硬编码

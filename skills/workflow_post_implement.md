# Post Implement

## 元数据

- **类型**: Workflow
- **适用场景**: ASP 执行 issue 完成后的固定收尾
- **触发**: post implement、ASP issue 收尾、执行 issue 完成

## When to Use

当某个 surface repo 的执行 issue 对应的 PR 已合并并部署后。

## Fixed Sequence

### 1. PR 合入确认

确认 PR 已合入对应 surface repo 的 base branch（从 `config/surfaces.yaml` 查询）。

### 2. 执行 Issue 关闭

```bash
gh issue close <exec_issue_N> --repo <surface_repo> --comment "Completed. PR: <pr_url>"
```

### 3. 中央 Issue 更新

检查中央 issue 关联的所有执行 issue 是否都已关闭：
- 全部关闭 → 关闭中央 issue
- 部分完成 → 在中央 issue comment 更新进度

```bash
gh issue comment <central_N> --repo AI-MYG/asp --body "Surface {surface} completed: {pr_url}"
```

### 4. 飞书通知需求方

使用 `config/notifications.yaml` 的 `requirement_completed` 模板，通知需求负责人。

### 5. Observer 信号

本次完成事件会被 Observer 在下一个扫描周期自动捕获，无需手动写入。

## Guardrails

- 确认 PR 真正合入后再关闭 issue，不要提前关闭
- 飞书通知失败不阻塞流程，记录到 `memory/OBSERVATIONS.md`

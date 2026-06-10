# Post Implement

## 元数据

- **类型**: Workflow
- **适用场景**: ASP 执行 issue 完成后的固定收尾
- **触发**: post implement、ASP issue 收尾、执行 issue 完成

## When to Use

当某个 surface repo 的执行 issue 对应的 PR 已合并并部署后。

## 前置：双闸门流程（Pipeline C/D）

PR 产生之前，issue 会经过两道闸门（见 `tools/feishu_inbound/issue_executor.py`）：

1. **人类需求确认闸门**：Pipeline C 分析后，报告含「第 0 章 给需求方的话」通俗总结。人类读懂后给 issue 打 `approved-to-execute` 标签，Pipeline D 才会改代码（difficulty-trivial 自动豁免）。一行确认命令：
   ```bash
   python tools/feishu_inbound/issue_executor.py --approve <issue> --repo <surface_repo>
   ```
2. **AI 代码互审闸门**：代码改完后，第二个 agent（`ASP_REVIEW_MODEL`，默认 sonnet）对照「需求分析 vs git diff」审查（只读、中性目录、UTF-8 stdin 传参）。
   - 符合 → push + Smart PR，交人类做最终 review/merge（本 workflow）
   - 不符合 → 打回重改，最多 `ASP_REVIEW_MAX_ROUNDS`（默认 2）轮；超限打 `review-failed` 标签、停下交人类
   - 每轮审查结论以评论形式留痕在 issue 上
   - 总开关 `ASP_REVIEW_ENABLED=false` 可整体关闭，回到「改完直接 push/PR」。

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

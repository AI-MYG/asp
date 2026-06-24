# Plan Approval（C→D 人工 Gate）

给人读的审方案说明。**完整契约**：[workflow_plan_approval_full.md](./workflow_plan_approval_full.md)

## 这一步做什么？

Pipeline C 产出 `## Feishu Inbound Analysis` 后，**standard/complex** issue 需人工加 `approved-to-execute`，Pipeline D 才会执行。`difficulty-trivial` 跳过本步。

## 操作

```bash
gh issue edit <N> --repo <owner/repo> --add-label "approved-to-execute"
```

打回重分析：`--add-label "request-reanalysis"`

## Cursor Skill

`feishu-inbound-plan-approval`

## 相关

- [Inbound Agent（C）](./workflow_inbound_agent.md)
- [Inbound Executor（D）](./workflow_inbound_executor.md)
- [全员参与指南](../docs/inbound_pipeline_team_guide.md)

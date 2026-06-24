# Inbound Executor（Pipeline D）

给人读的 D 段说明。**完整契约**：[workflow_inbound_executor.md](./workflow_inbound_executor.md)

## 这一步做什么？

读 Analysis，在 worktree 实现推荐方案，Smart PR，打 `executed`。

**Gate**：`analyzed` + assignee；standard/complex 还需 `approved-to-execute`。

## 脚本

```bash
source scripts/load_asp_env.sh
export GITHUB_ASSIGNEE=<你>
./venv/bin/python tools/feishu_inbound/issue_executor.py --issue <N> --repo <owner/repo>
```

## Cursor Skill

`feishu-inbound-executor`

## 下一步

[Gate Review（E）](./workflow_gate_review.md)

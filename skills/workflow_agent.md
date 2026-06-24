# Inbound Agent（Pipeline C）

给人读的 C 段说明。**完整契约**：[workflow_inbound_agent.md](./workflow_inbound_agent.md)

## 这一步做什么？

扫描 **assignee = 你** 的 open issue，读 surface worktree，写 `## Feishu Inbound Analysis`（唯一方案 + Evidence），打 `analyzed`。

## 脚本

```bash
source scripts/load_asp_env.sh
export GITHUB_ASSIGNEE=<你>
./venv/bin/python tools/feishu_inbound/issue_scanner.py --issue <N> --repo <owner/repo>
```

或 `bash scripts/run_feishu_inbound_lead_tick.sh`（C→F 整链，lead Mac :20/:50）

## Cursor Skill

`feishu-inbound-agent`

## 下一步

[Plan Approval](./workflow_plan_approval.md) → [Executor](./workflow_executor.md)

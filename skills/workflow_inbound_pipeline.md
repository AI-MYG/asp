# Inbound Pipeline

## 元数据

- **类型**: Workflow
- **适用场景**: 飞书需求从入站到交付的完整闭环
- **触发**: 飞书入站、ASP inbound pipeline、需求闭环

## Overview

三段解耦架构：

```
Pipeline A (Cloud)     Pipeline B (Central Mac)     Pipeline C (Per-developer)
─────────────────     ─────────────────────────     ──────────────────────────
Bitable 自动化         综合 Agent 分诊               Team Lead 本地 Agent
     ↓                      ↓                              ↓
GitHub Issue            Surface 路由                   Deep Analysis
(AI-MYG/asp)           + 执行 Issue                   + Smart PR
                       + Assignee                      + Review
                                                       + Deploy
                                                          ↓
                                                    飞书通知需求方
```

## Pipeline A: Bitable → Central Issue

1. 飞书 Bitable 需求池自动化触发 HTTP POST
2. GitHub Actions `feishu-inbound.yml` 接收 payload
3. 在 AI-MYG/asp 创建 issue，标签 `feishu-inbound`
4. Bitable 回写 issue URL + 状态"已派发"

## Pipeline B: Triage

由综合 Agent（本 Mac 的 OpenCode Server）执行：

1. 定时扫描 AI-MYG/asp 的 `feishu-inbound` 且非 `triaged` issue
2. 按 `workflow_triage_routing.md` 分诊
3. 各 surface repo 创建执行 issue + 指派 Team Lead

launchd 调度：每 30 分钟（:10/:40）扫描。

## Pipeline C: Analysis + Delivery

各 Team Lead 的本地 Agent 执行：

1. 扫描被指派的执行 issue
2. 拉取对应 surface repo 代码上下文
3. 生成 debug analysis comment（格式见 `contract_debug_analysis.md`）
4. 实现 + Smart PR（rootgrove `tools/smart_pr.py`）
5. Review → Merge → Deploy
6. 执行 `workflow_post_implement.md` 收尾
7. 飞书通知需求方（`config/notifications.yaml` → `requirement_completed`）

## 与 rootgrove 的衔接

- Pipeline A/B 的脚本在 rootgrove `tools/feishu_inbound/` 和 `periodic_jobs/ai_heartbeat/`
- 本 repo 提供配置（`config/`）和 skill 定义（`skills/`）
- Step 6 migration（将 Pipeline A 目标从 asp-backend 改为 asp）计划在下一轮 session 执行

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

执行脚本：`scripts/triage_dispatch.py`
launchd 调度：每 30 分钟（:10/:40）扫描。

## Pipeline C / D: 扫描范围（改配置，不改代码）

**SSOT**：`tools/feishu_inbound/config.yaml` → `pipeline_cd_scan`

| `mode` | 含义 |
|--------|------|
| `org` | `github.org` 下所有仓库（默认 `AI-MYG`） |
| `repo` | 仅 `pipeline_cd_scan.repo` 一个仓库 |
| `repos` | 仅 `pipeline_cd_scan.repos` 列表中的仓库 |

指派对象：本机环境变量 `GITHUB_ASSIGNEE`（Keychain）。可选 `exclude_repos` 排除仓库。

示例（扫描整个 org 下指派给你的 issue）：

```yaml
pipeline_cd_scan:
  mode: org
  github:
    org: AI-MYG
    limit: 100
    state: open
  exclude_repos: []
```

改完后 **无需改 Python**；下次 launchd 触发或手动跑 `issue_scanner.py` / `issue_executor.py` 即生效。

### launchd 触发时间（改配置 + 重装）

**SSOT**：同一文件 `config.yaml` → `launchd_schedules`（与扫描范围并列）。

| Job | 配置键 | 默认 |
|-----|--------|------|
| Pipeline B | `feishu_inbound_triage` | 每天 0–23 点 `:10` / `:40`，含周末 |
| Pipeline C | `feishu_inbound_agent` | 每天 `:20` / `:50` |
| Pipeline D | `issue_executor` | 每天 `:05` / `:35` |

```yaml
launchd_schedules:
  feishu_inbound_agent:
    hours: all          # 或 "9-18" 仅工作时间
    minutes: [20, 50]
    weekday_only: false # true 则周六日由 wrapper 跳过
```

修改后执行：

```bash
bash launchd/install.sh
```

说明：此前 **24 小时** 逻辑在 rootgrove 的 `periodic_jobs/ai_heartbeat/install_launchd_jobs.sh`（`calendar_interval_xml` 用 `seq 0 23`）；asp-infra 曾误用 9–18 硬编码。现以 `config.yaml` 为准；`com.rootgrove.feishu-inbound-*` 已退役。

验证：

```bash
source scripts/load_asp_env.sh
python tools/feishu_inbound/issue_scanner.py --scan-only
python tools/feishu_inbound/issue_executor.py --scan-only
```

## Pipeline C: Analysis + Delivery

各 Team Lead 的本地 Agent 执行：

1. 按 `pipeline_cd_scan` 扫描被指派的 issue
2. 拉取对应 surface repo 代码上下文
3. 生成 debug analysis comment（格式见 `contract_debug_analysis.md`）
4. 实现 + Smart PR（`tools/smart_pr.py`）
5. Review → Merge → Deploy
6. 执行 `workflow_post_implement.md` 收尾
7. 飞书通知需求方（`scripts/completion_notify.py` + `config/notifications.yaml`）

## 工具清单

| 工具 | 位置 | 用途 |
|------|------|------|
| GitHub Actions | `.github/workflows/feishu-inbound.yml` | Pipeline A |
| 分诊脚本 | `tools/feishu_inbound/triage_agent.py` | Pipeline B |
| 扫描配置 | `tools/feishu_inbound/config.yaml` → `pipeline_cd_scan` | Pipeline C/D 范围 |
| 分析脚本 | `tools/feishu_inbound/issue_scanner.py` | Pipeline C |
| 执行脚本 | `tools/feishu_inbound/issue_executor.py` | Pipeline D |
| Smart PR | `tools/smart_pr.py` | Pipeline D PR 创建 |
| 通知脚本 | `scripts/completion_notify.py` | Pipeline C 尾段 |
| OpenCode 客户端 | `tools/opencode_client.py` | Agent API 调用 |

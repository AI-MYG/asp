# Inbound Pipeline

## 元数据

- **类型**: Workflow
- **适用场景**: 飞书需求从入站到交付的完整闭环
- **触发**: 飞书入站、ASP inbound pipeline、需求闭环

## Overview

飞书需求从入站到**提需人验收**的自动化闭环（A→F）：

```
A 入站 → B 分诊 → C 分析 → D 执行+PR → E Gate Review
    → 人合 dev → dev CI/CD → F sole assign 提需人 + 验收 comment
```

给人读的详细说明见本文件各 Pipeline 节；E/F 亦可单独查阅：

- [Gate Review（E）](./workflow_gate_review.md)
- [Dev Handback（F）](./workflow_dev_handback.md)

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
| **Lead tick（C→F）** | `lead_tick` | 每天 `:20` / `:50` |

C/D/E/F **不再**安装独立 launchd job（2026-06-19 退役）。链式执行由 `lead-tick` / `run_personal_lead_tick.sh` 一次跑完；各段仍可手动 CLI 单跑。

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

## Pipeline E: PR Gate Review（dev 门，只 review 不改代码）

D 打完 `executed` + 建好 PR 后，E 做一轮 gate review，决定能否进入 dev 合并门。

**硬边界**：E **只**读 PR/issue 上下文做判定 + 改 label + comment + 飞书私信；**绝不**改代码、commit、push、跑 executor、merge（dev→prod 永远人工）。改代码永远回到 Pipeline D。

```
D 执行 + Smart PR + 打 executed（surface execution issue）
        ↓
E Gate Review（delegate 到与 Pipeline D 不同的 Agent 平台，如 D=OpenCode → E=Cursor Composer 2.5；只读 diff/analysis）
        ↓
   ┌─ 通过 → 打 review-dev-pass（保留 executed，不 merge）+ 飞书私信 → 人合 dev
   └─ 打回 → 去 executed + 打 review-changes-requested + 「## Pipeline E Gate Review」comment + 飞书私信
              ↓
        D 下一轮读 Gate Review comment 注入 prompt，复用 open PR 修订 → 重新打 executed → E 再审
              ↓
        人合 dev → dev CI/CD 成功 → Pipeline F sole assign 提需人 + 验收 comment
```

执行脚本：`tools/feishu_inbound/issue_pr_reviewer.py`

## Pipeline F: Dev CI/CD 后验收指派

E 通过且 PR 合入 base branch 后，等 dev CI/CD workflow 在 merge commit 上成功，再 assign 提需人。

```
review-dev-pass + PR merged + dev CI/CD success
        ↓
issue_dev_handback.py → handback_to_requester（sole assignee 提需人 + 验收 comment）
```

执行脚本：`tools/feishu_inbound/issue_dev_handback.py`（Lead tick 链内 `:20/:50`）

验证：

```bash
source scripts/load_asp_env.sh
python tools/feishu_inbound/issue_dev_handback.py --scan-only
python tools/feishu_inbound/issue_dev_handback.py --issue <N> --repo AI-MYG/asp-backend --dry-run
```

## 工具清单

| 工具 | 位置 | 用途 |
|------|------|------|
| GitHub Actions | `.github/workflows/feishu-inbound.yml` | Pipeline A |
| 分诊脚本 | `tools/feishu_inbound/triage_agent.py` | Pipeline B |
| 扫描配置 | `tools/feishu_inbound/config.yaml` → `pipeline_cd_scan` | Pipeline C/D 范围 |
| 分析脚本 | `tools/feishu_inbound/issue_scanner.py` | Pipeline C |
| 执行脚本 | `tools/feishu_inbound/issue_executor.py` | Pipeline D |
| Smart PR | `tools/smart_pr.py` | Pipeline D PR 创建 |
| Gate review 脚本 | `tools/feishu_inbound/issue_pr_reviewer.py` | Pipeline E |
| Gate review runner | `scripts/run_issue_pr_reviewer.sh` | Pipeline E launchd |
| Dev handback 脚本 | `tools/feishu_inbound/issue_dev_handback.py` | Pipeline F |
| Lead tick runner | `scripts/run_lead_tick.sh`（或 launchd `com.asp.feishu-inbound-lead-tick`） | C→F 链式 |
| 通知脚本 | `scripts/completion_notify.py` | Pipeline C 尾段（需求完成）/ E 复用其 Feishu 发送函数 |
| OpenCode 客户端 | `tools/opencode_client.py` | Agent API 调用 |

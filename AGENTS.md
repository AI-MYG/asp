# AGENTS.md — ASP Context Infrastructure

## 项目身份

本 repo 是 ASP 项目的中央 context infrastructure，不含业务代码。职责：

1. **需求级 Issue SSOT**：飞书入站需求在此创建 issue，综合 Agent 分诊后路由到各 surface repo
2. **项目记忆**：Observer（日频）+ Reflector（周频）持续积累项目洞察
3. **团队 Persona**：逐步为每个团队成员构建认知画像，提升分诊精准度
4. **项目级 Skill**：ASP 专有的分诊、收尾、通知等执行流程

## Surface 约定

6 个 surface repo，配置 SSOT 在 `config/surfaces.yaml`：

| Surface | Repo | Base Branch | Local Path |
|---------|------|-------------|------------|
| backend | AI-MYG/asp-backend | dev | projects/asp/backend |
| app | AI-MYG/asp-app | main | projects/asp/app |
| admin | AI-MYG/asp-admin | main | projects/asp/admin |
| wecom | AI-MYG/asp-wecom | main | projects/asp/wecom |
| websites | AI-MYG/asp-websites | main | projects/asp/websites |
| canonical | AI-MYG/asp-canonical | main | projects/asp/canonical |

分支命名：`issue-{N}/{surface}`，与 rootgrove `team_registry.yaml` 保持一致。

## 分诊协议

综合 Agent 分诊流程：

1. 读取新 issue（`feishu-inbound` 标签）
2. 参照 `config/triage.yaml` 判定 surface + difficulty + assignee
3. 在对应 surface repo 创建执行级 issue，关联中央 issue
4. 中央 issue 添加 `triaged` 标签 + 分诊 comment

分诊决策由 Agent 自主完成（参考 `skills/workflow_triage_routing.md`），不需人工确认。

## 执行约定

- Smart PR：各 surface repo 的 PR 使用 rootgrove `tools/smart_pr.py`，读取 `team_registry.yaml` 做分支/reviewer 路由
- Issue 收尾：执行完成后走 `skills/workflow_post_implement.md`（PR 合入 + 飞书通知）
- Debug 分析：`skills/contract_debug_analysis.md` 定义分析 comment 的输出格式

## Memory 系统

- `memory/OBSERVATIONS.md`：Observer 日频写入的 L1 信号（issue 动态、PR 合并、部署事件）
- `memory/MEMORY.md`：Reflector 周频蒸馏的 L2 原子事实
- `memory/archive/`：过期 Medium 归档

Observer 扫描范围：`AI-MYG/asp*` 所有 repo 的 issue/PR/commit 活动。

## Persona

`personas/` 目录按团队成员维护认知画像。初始只有 Marvin（CTO/后端），其他成员通过 Observer 积累交互模式后逐步形成。

切换协议：参照 `personas/INDEX.md`。

## Secrets

环境变量存 `.env`（gitignored），模板见 `.env.example`。生产凭证通过 macOS Keychain 或 CI secrets 注入。

## Python

本 repo 脚本使用系统 Python 3 或项目级 venv（若后续需要）。rootgrove 侧工具继续使用 rootgrove 的 `./venv/bin/python`。

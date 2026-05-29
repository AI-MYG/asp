# ASP Architecture

## 系统全景

ASP 是一个多 surface 儿童英语教育产品，由 6 个独立 repo 构成业务代码，1 个中央 repo（本 repo）构成 context infrastructure。

```
                    ┌─────────────────────────┐
                    │   Feishu Bitable        │
                    │   (需求池入口)            │
                    └────────────┬────────────┘
                                 │ Pipeline A (HTTP → GitHub Actions)
                                 ↓
                    ┌─────────────────────────┐
                    │   AI-MYG/asp            │
                    │   (中央 Context Infra)   │
                    │   - 需求级 Issue SSOT    │
                    │   - Memory 系统          │
                    │   - Persona 画像         │
                    │   - Skill 定义           │
                    └────────────┬────────────┘
                                 │ Pipeline B (综合 Agent 分诊)
                    ┌────────────┼────────────┐
                    ↓            ↓            ↓
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │ backend  │ │   app    │ │  admin   │  ... (+ wecom, websites, canonical)
            │ (dev)    │ │ (main)   │ │ (main)   │
            └────┬─────┘ └────┬─────┘ └────┬─────┘
                 │            │            │
                 ↓            ↓            ↓
            Team Lead 本地 Agent (Pipeline C)
            Analysis → Smart PR → Review → Deploy
                                 │
                                 ↓
                    飞书通知需求方 (Pipeline C 尾段)
```

## 三段 Pipeline 架构

### Pipeline A: 飞书 → 中央 Issue (Cloud)

- **触发**: Bitable 自动化 HTTP POST
- **执行**: GitHub Actions (`feishu-inbound.yml`)
- **产出**: AI-MYG/asp 中创建需求级 issue
- **回写**: Bitable 记录 issue URL + 状态

### Pipeline B: 分诊 (Central Mac)

- **触发**: 定时扫描（launchd, 每 30 分钟）
- **执行**: OpenCode Server 调用综合 Agent
- **输入**: 中央 issue（`feishu-inbound` 标签, 非 `triaged`）
- **产出**: 各 surface repo 创建执行级 issue + 指派 Team Lead
- **配置**: `config/triage.yaml`

### Pipeline C: 分析 + 交付 (Per-developer)

- **触发**: Team Lead 被指派执行 issue
- **执行**: 本地 Agent（OpenCode Server）
- **流程**: Deep Analysis → 实现 → Smart PR → Review → Deploy → 飞书通知
- **配置**: `config/surfaces.yaml` + rootgrove `team_registry.yaml`

## Memory 系统

```
GitHub API signals ──→ Observer (日频) ──→ OBSERVATIONS.md (L1)
                                                  ↓
                                          Reflector (周频) ──→ MEMORY.md (L2)
                                                  ↓
                                          archive/YYYY-MM.md (过期归档)
```

Observer 扫描 AI-MYG 组织下所有 ASP repo 的：issue 创建/关闭、PR 创建/合并、commit 活动、部署事件。

Reflector 从 L1 观察中蒸馏：架构趋势、流程改进点、团队协作模式（persona 演化素材）。

## 与 rootgrove 的集成点

| 集成点 | rootgrove 侧 | 本 repo 侧 |
|--------|-------------|------------|
| Smart PR | `tools/smart_pr.py` | `skills/workflow_smart_pr.md` 引用 |
| Team Registry | `contexts/team_registry.yaml` (SSOT) | `config/surfaces.yaml` (ASP 子集) |
| Feishu Inbound | `tools/feishu_inbound/` 脚本 | `config/triage.yaml` 配置 |
| Issue Scanner | `periodic_jobs/ai_heartbeat/` | Observer 复用同一 GitHub API |
| Persona | `rules/personas/` (个人级) | `personas/` (项目级) |

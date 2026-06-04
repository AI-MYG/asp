# ASP Project Context Infrastructure

ASP (A Smart Pet) 儿童英语教育产品的中央项目大脑。

本 repo 不含业务代码，而是 ASP 项目的 context infrastructure：统一管理需求分诊、项目记忆、团队协作、自动化流水线。团队成员 clone 本 repo 即可独立运行所有自动化。

## 架构

```
飞书需求池 ──→ Pipeline A (Bitable → GitHub Issue)
                         ↓
              AI-MYG/asp (本 repo，需求级 issue)
                         ↓
              Pipeline B: 综合 Agent 分诊
              (surface 判定 + difficulty + assignee)
                         ↓
              各 surface repo (执行级 issue)
              ┌─────────┼─────────┐
              ↓         ↓         ↓
         asp-backend  asp-app  asp-admin ...
              ↓         ↓         ↓
         Team Lead 本地 Agent 分析 + Smart PR
                         ↓
              Review → Merge → Deploy
                         ↓
              Pipeline C: 飞书通知需求方
```

中央 repo 的 issue 是"需求视角"（1 个需求），各 surface repo 的 issue 是"执行视角"（1:N 拆分）。

## Surface Repos

| Surface | Repo | Base Branch | Team Lead |
|---------|------|-------------|-----------|
| backend | [AI-MYG/asp-backend](https://github.com/AI-MYG/asp-backend) | `dev` | Marvin |
| app | [AI-MYG/asp-app](https://github.com/AI-MYG/asp-app) | `main` | 胡剑飞 |
| admin | [AI-MYG/asp-admin](https://github.com/AI-MYG/asp-admin) | `main` | 胡剑飞 |
| wecom | [AI-MYG/asp-wecom](https://github.com/AI-MYG/asp-wecom) | `main` | Marvin |
| websites | [AI-MYG/asp-websites](https://github.com/AI-MYG/asp-websites) | `main` | Marvin |
| canonical | [AI-MYG/asp-canonical](https://github.com/AI-MYG/asp-canonical) | `main` | Marvin |

## 目录结构

```
├── AGENTS.md              # 项目级 agent 约定
├── CONTEXT.md             # 领域词汇表
├── config/                # 分诊路由、surface 映射、通知配置
├── tools/                 # 自动化工具（Smart PR、OpenCode 客户端）
├── skills/                # 项目级 skill（分诊、入站、收尾、Smart PR）
├── personas/              # 团队成员人格（公理子集 + 决策偏好）
├── memory/                # L1/L2 项目记忆（Observer 写入，Reflector 蒸馏）
├── scripts/               # 自动化脚本（分诊、通知、Observer/Reflector）
├── docs/                  # 架构文档、ADR、OpenCode 配置指南
└── launchd/               # macOS 定时任务模板
```

## 快速开始

1. 克隆本 repo（本地路径常为 `projects/asp-infra`，GitHub 为 `AI-MYG/asp`）。

2. **凭证（macOS）**：写入 Keychain 命名空间 `rootgrove/<KEY>`（与 monorepo 共用 `tools/secrets/load_secrets.sh`）。本地 **不需要** `.env`。变量名见 `.env.example`；OpenCode 使用 `OPENCODE_BASE_URL`、`OPENCODE_USERNAME`、`OPENCODE_PASSWORD`。

3. 安装依赖（或使用 monorepo `~/CursorWorks/rootgrove/venv`）：
   ```bash
   pip install pyyaml requests
   ```

4. 本地 Agent 环境（OpenCode Server）：详见 [docs/setup_opencode.md](docs/setup_opencode.md)

5. 安装 ASP 定时任务（与 rootgrove observer/reflector **并存**，时间错开且 rootgrove 更早）：
   ```bash
   bash launchd/disable_rootgrove_feishu_inbound.sh   # 仅关 rootgrove 飞书 B/C，保留 ASP
   bash launchd/install.sh
   ```
   | Job | rootgrove | ASP (`com.asp.*`) |
   |-----|-----------|-------------------|
   | Observer | 每日 08:00 | 每日 22:00 |
   | Reflector | 周日 09:00 | 周日 10:00 |

5. Smart PR：
   ```bash
   python tools/smart_pr.py --issue 42 --surface backend
   ```

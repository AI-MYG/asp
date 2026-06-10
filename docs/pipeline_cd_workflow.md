# Pipeline C/D 自动化运行流程

> issue → AI 分析 → 审批 → AI 改代码 → PR → 合并。
> 面向 **前端负责人（app / admin）** 的日常使用与运维说明。

## 一句话

团队在 GitHub 提 issue → **AI 自动分析需求、自动改代码并开 PR** → 你只负责**审批**和**合并**。
所有 AI 自动化集中在**一台机器**后台跑（像 CI 一样），团队其他成员无需安装任何 AI、无感。

---

## 全流程

```
 团队成员提 issue（指派给对应负责人）
         │
         ▼
 ① 需求分析 ── AI 做 ──  定时任务每 15 分钟自动跑
    读 issue + 代码 → 生成「分析报告」评论 + 打 analyzed 标签
         │
         ▼
 ② 审批 ── 你做 ──  人工闸口
    看分析报告 → 给 issue 打 approved-to-execute 标签
    （trivial 难度免审批；standard / complex 需要你确认）
         │
         ▼
 ③ 改代码 ── AI 做 ──  定时任务每 15 分钟自动跑（接在分析之后）
    对已打 approved-to-execute 的 issue：
    按方案写代码 → AI 代码审查（最多 2 轮）→ push 分支 → 开 PR（自动指派给你）
    已执行(executed)/已有PR/失败(execution-failed/review-failed) 的自动跳过，不重复改
         │
         ▼
 ④ 合并 ── 你做 ──
    在 GitHub review → 合并 PR
```

## 谁做什么

| 环节 | 谁 | 怎么触发 | 是否 AI |
|---|---|---|---|
| ① 需求分析 | **AI** | 定时任务**每 15 分钟自动** | ✅ |
| ② 审批 | **你** | 手动打 `approved-to-execute` 标签 | ❌ |
| ③ 改代码 + 审查 + 开 PR | **AI** | 定时任务**每 15 分钟自动**（接在分析后） | ✅ |
| ④ 合并 PR | **你** | GitHub 上手动 | ❌ |

> **AI 做 3 件事**：需求分析、写代码、代码审查。
> **你做 2 件事**：审批（打标签）、合并 PR。
> 定时任务一轮里**先分析、后执行**：分析新 issue + 自动执行你已审批的 issue。
> PR 的 push 与创建是自动完成的，并会**自动把 PR 指派给负责人本人**。
> **失败不自动重试**：执行失败或审查没过的 issue 留给人工，下轮不再重跑。

---

## 常用操作

| 想做什么 | 操作 |
|---|---|
| 手动分析一次（补跑 / 调试） | 双击 `scripts/win/run_scanner_once.bat` |
| 手动执行一次（改代码 + 开 PR） | 双击 `scripts/win/run_executor_once.bat` |
| 审批某个 issue | 在 GitHub 给它打 `approved-to-execute` 标签 |
| 合并 | 在 GitHub review 后合并 PR |

底层命令（任意平台通用）：

```bash
# ① 分析（Pipeline C）
python tools/feishu_inbound/issue_scanner.py --batch 5 --parallel

# ③ 执行（Pipeline D）
python tools/feishu_inbound/issue_executor.py --batch 3 --parallel

# 审批快捷方式（等价于打标签）
python tools/feishu_inbound/issue_executor.py --approve 16 --repo AI-MYG/asp-admin
```

---

## 定时任务（自动分析 + 自动执行）

每 15 分钟自动跑一轮：**先分析新 issue，再执行你已审批的 issue**。你只需打标签和合并。

| 操作 | 命令 |
|---|---|
| 安装（每 15 分钟） | `powershell -ExecutionPolicy Bypass -File scripts\win\install_scanner_task.ps1` |
| 改间隔（如 30 分钟） | `... install_scanner_task.ps1 -Minutes 30` |
| 卸载 | `... install_scanner_task.ps1 -Uninstall` |

特性：
- 一轮 = ① 分析（`issue_scanner.py`）+ ② 执行已审批 issue（`issue_executor.py --batch 3`）
- 仅在**登录 + 开机**时跑；不开机自启；隐藏窗口
- **无待分析 / 无可执行时自动删除空日志**
- **失败不自动重试**：`execution-failed` / `review-failed` 的 issue 留给人工
- 只想分析不执行：`run_scanner.ps1 -NoExecute`

日志：分析在 `logs/scanner_*.log`，执行在 `logs/executor_*.log`。

---

## 三个灵活点（都只改 `.env`，不碰代码）

### 1. 换 AI 后端

```ini
ASP_AGENT_BACKEND=claude    # 默认，推荐用于后台定时任务（稳定、无 TTY 限制）
ASP_AGENT_BACKEND=cursor    # 团队用 Cursor 时（需设 CURSOR_API_KEY）
```

> ⚠️ **Cursor 无头模式需要真实 TTY**，在后台定时任务里会挂死，仅适合"人手动跑一次"。
> 后台无人值守的定时任务请用 `claude`。

### 2. 换平台（Windows ↔ macOS）

```ini
# Windows
ASP_WORKTREE_ROOT=D:\work\asp
# macOS（示例）
ASP_WORKTREE_ROOT=~/CursorWorks/rootgrove
```

surface 的本地路径在 `config/surfaces.yaml` 里用相对路径（如 admin = `asp-admin`），
跟随 `ASP_WORKTREE_ROOT` 解析，换平台只改这一行。

> macOS 调度用 `launchd/install.sh`（不是 Windows 的 .ps1）。
> macOS 上不需要 `CLAUDE_CODE_GIT_BASH_PATH`（那是 Windows 专属）。

### 3. 换调度间隔

重跑 `install_scanner_task.ps1 -Minutes <N>`。

---

## 部署形态：集中式（AI CI）

这套"AI 自动化"的本质是 **AI CI**——像 Jenkins 一样挂在**一台机器**后台跑即可：

```
团队成员（各自电脑，正常用 Cursor 写日常代码，互不影响）
   └─ 在 GitHub 提 issue、合自己的 PR   ← 本来就在 GitHub 上做，无需 AI

负责人这台机器（后台挂定时任务）
   └─ 自动分析 issue / 自动改代码开 PR   ← 只有这部分用 AI，集中一处
```

**团队成员零负担**：不装任何流水线 AI，照常提 issue / 合 PR。
**为什么不是每人本地跑**：这套流程是无人值守的后台自动化（没有 TTY），
而 Cursor 无头模式需要 TTY；集中在一处用 claude 最稳。

---

## 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 日志中文乱码 | `.ps1` 需 UTF-8 BOM；`.bat` 用英文注释（不能 UTF-8/BOM） |
| `WinError 267 目录名称无效` | surface 的 `local_path` 解析到了不存在的目录，检查 `ASP_WORKTREE_ROOT` |
| `未找到 claude/cursor CLI` | 对应 CLI 没装或不在 PATH；或用 `CLAUDE_CLI_PATH` / `CURSOR_CLI_PATH` 指定 |
| PR 显示 `pr_url=unknown` | 已修复（smart_pr 的 stdout 现在是纯 JSON） |
| issue 被跳过 | 看 `logs/*.log` 的中文跳过原因（如"未解决的产品歧义"需打 approved 标签放行） |

---

相关：项目总览见 [README.md](../README.md)；surface 映射见 [config/surfaces.yaml](../config/surfaces.yaml)。

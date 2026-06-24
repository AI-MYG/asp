# Feishu Inbound Dev Handback Workflow

## 元数据

- **类型**: Workflow
- **适用场景**: **Pipeline F（dev CI/CD 成功后验收指派）**——PR 已合入 base branch 且 dev CI/CD success 后，将 issue 交给验收链路的 GitHub 负责人，并发出 F 验收评论
- **边界**: 不 merge PR、不改代码；只读 GitHub Actions 结论 + 改 assignee + 发 comment；**不在此阶段处理业务验收结论**（业务验收由负责人在 E 人测 gate 代录，见 [Pipeline E Gate Review](./workflow_feishu_inbound_gate_review.md)）
- **触发**: dev handback、验收指派、Pipeline F、F 验收评论
- **工具**: `tools/feishu_inbound/issue_dev_handback.py`（ASP instance：`projects/asp-infra/`）
- **创建日期**: 2026-06-15
- **更新**: 2026-06-20（角色与负责人代理验收契约）

---

## 角色（personal 与 ASP 共用）

本段与 [Pipeline E](./workflow_feishu_inbound_gate_review.md) 共用同一套名词，全文不混用英文别名。

| 角色 | 含义 | personal 典型 | ASP 典型 |
|------|------|---------------|----------|
| **飞书提需人** | 在飞书多维表格提需求、从业务侧做验收判断的人 | 往往就是你自己 | 业务方同事，**多数没有 GitHub 账号** |
| **流水线执行人** | 本机跑 C/D/E/F 的人（`GITHUB_ASSIGNEE`） | 你 | lead 开发 |
| **GitHub 建单人** | 创建该 GitHub issue 的账号 | 你或机器人 | 常为执行人或 Pipeline A 机器人 |
| **GitHub 负责人** | F 之后持有 issue、在 GitHub 上代录业务验收的人 | 与飞书提需人常为同一人 | 开发同学，飞书提需人的代理人 |

**业务验收主体**是飞书提需人；**GitHub 操作主体**是负责人。ASP 里两者分开：飞书提需人在飞书确认，负责人在 issue 上更新状态。

---

## 给人看的：这一步在干什么？

前置条件链：

1. E（AI 门禁）已打 `review-dev-pass`（尚未进入业务验收）
2. 负责人**人工**把 PR merge 到 dev（backend）或 main（admin/app 等）
3. merge commit 触发 surface repo 的 **dev CI/CD workflow** 且结果为 **success**

满足后 F 应完成：

1. 将 issue **sole assignee** 改为 **GitHub 负责人**（personal：通常即飞书提需人本人；ASP：开发负责人，不是飞书提需人的 GitHub 账号）
2. 发 **F 验收评论**（含固定标题 `## Pipeline F Dev Handback`，并写明飞书提需人与负责人，见下方模板）

**不打** `ready-for-acceptance` label（已废弃）。幂等靠 **F 验收评论已存在**（`## Pipeline F Dev Handback`）判断，不靠 label。

若有 central issue（`AI-MYG/asp#N`）链接，**同时** handback central 与 surface execution issue。

### F 验收评论（目标契约）

引擎与 instance 应向此格式收敛（实现状态见文末「引擎对齐」）：

```markdown
## Pipeline F Dev Handback

飞书提需人: <姓名或飞书侧标识>
GitHub负责人: <GitHub 用户名>
验收方式: 负责人代确认

PR 已合入 dev 且 dev 环境 CI/CD 已成功：<PR URL>

请在 dev 环境验收。业务侧确认后，由 **GitHub 负责人** 在本 issue 评论，格式见 Pipeline E 人测 gate（`## Pipeline E Gate Review` + `/gate pass` 或 `/gate fail`）。
```

personal 可简写：`飞书提需人` 与 `GitHub负责人` 填同一人，`验收方式` 可写「本人验收」。

---

## 扫描与 Gate

| 类型 | 条件 |
|------|------|
| **扫描** | org 内 `open` + `review-dev-pass`（不要求 assignee = lead） |
| **跳过** | 已有 `## Pipeline F Dev Handback` 评论（幂等） |
| **Gate 1** | 关联 PR 状态为 merged（`issue-{N}/<surface>` 分支） |
| **Gate 2** | merge commit 上配置的 workflow `conclusion == success` |
| **等待** | PR 未 merge → `skip_not_merged`；CI 未跑完 → `skip_cicd_pending`；CI 失败 → `skip_cicd_failed` |

launchd：由 **Lead tick** `com.asp.feishu-inbound-lead-tick` 在 `:20` / `:50` 链式调用 F（旧独立 job `com.asp.issue-dev-handback` 已于 2026-06-19 退役）。

### dev CI/CD workflow 配置（SSOT）

`tools/feishu_inbound/config.yaml` → `pipeline_f.dev_cicd`：

| Repo | Workflow 名称 |
|------|----------------|
| `AI-MYG/asp-backend` | `Backend Dev Test Container` |
| `AI-MYG/asp-admin` | `🔍 Code Quality - Vue Admin` |
| `AI-MYG/asp-app` | `🚀 CI/CD Multi-Device Pipeline - Flutter Kiosk App` |

未配置的 repo 不会 handback（`skip_no_workflow`）。

---

## 状态生命周期（F 段）

```
E（AI）通过 → review-dev-pass
负责人 merge dev → dev CI/CD success
F → sole assignee 改为 GitHub负责人 + F 验收评论
飞书提需人在飞书侧验收 → 口头/飞书回复负责人
负责人在 issue 发 E 人测 gate 评论 → human_gate 处理（见 Pipeline E）
```

---

## 验收标准（Agent 执行 F 或代跑 F 时）

1. issue 上**没有** `ready-for-acceptance` label
2. sole assignee 为 **GitHub 负责人**（ASP 为开发负责人，不是假定「GitHub 建单人」）
3. 存在 `## Pipeline F Dev Handback` 评论，且含 `飞书提需人` 与 `GitHub负责人` 两行
4. 评论指引负责人使用 `## Pipeline E Gate Review` 模板（不另建 Meta Skill）

---

## 运行方式

```bash
source projects/asp-infra/scripts/load_asp_env.sh

python tools/feishu_inbound/issue_dev_handback.py --scan-only
python tools/feishu_inbound/issue_dev_handback.py --issue 125 --repo AI-MYG/asp-backend --dry-run
python tools/feishu_inbound/issue_dev_handback.py --issue 125 --repo AI-MYG/asp-backend
```

Personal：`source tools/feishu_inbound/load_personal_env.sh`，config 为 `config/feishu_inbound_personal.yaml`。

---

## 已知限制与引擎对齐

- **飞书提需人无 GitHub 账号**：F 仍 assign **负责人**；不得要求飞书提需人亲自在 issue 评论。业务事实来自飞书，GitHub 状态由负责人代录。
- **Bot 建单**：若 GitHub 建单人为机器人且无法解析负责人，F 不应发「完成态」F 验收评论，应告警由人处理。
- **与 rootgrove `tools/smart_pr.py` 区分**：Feishu inbound 的 D 使用 instance `smart_pr.py`，开 PR 时不 assign 飞书提需人。
- **引擎对齐**：feishu-inbound-skill PR #15 已废弃 `ready-for-acceptance`、引入 F marker；**飞书提需人 / 负责人分字段**与负责人代确认模板为文档 SSOT，引擎/instance 下一版对齐（issue #11 后续）。

---

## 相关

- [Feishu Inbound Pipeline（A→F 总览）](./workflow_feishu_inbound_pipeline.md)
- [Pipeline E Gate Review（含人测 gate）](./workflow_feishu_inbound_gate_review.md)
- [Pipeline D Executor](./workflow_feishu_inbound_executor.md)

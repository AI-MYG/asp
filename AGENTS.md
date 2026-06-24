# AGENTS.md — ASP Context Infrastructure

## 项目身份

本 repo 是 ASP 项目的中央 context infrastructure，不含业务代码。职责：

1. **需求级 Issue SSOT**：飞书入站需求在此创建 issue，综合 Agent 分诊后路由到各 surface repo
2. **项目记忆**：Observer（日频）+ Reflector（周频）持续积累项目洞察
3. **团队 Persona**：逐步为每个团队成员构建认知画像，提升分诊精准度
4. **项目级 Skill**：ASP 专有的分诊、收尾、通知等执行流程（`skills/` + Cursor wrappers 在 `.cursor/skills/`）
5. **自动化工具**：Smart PR、OpenCode 客户端等，团队成员 clone 即可使用

## 领域模型（必读）

ASP 后端是**两套平行结构**：**模板侧**（`course_level` → `course_unit` → `course_media`，与班级无关、可复用）与**班级交付侧**（`class` → `course` → `course_media_assignment`，每班级一份实例），两者经 `course.course_unit_id` 连接。

核心原则：**「模板内容」与「班级交付」必须分离**——模板挂 `course_unit`/`course_level`，按班级的排期/解锁通过 assignment 层挂 `course` 交付。`course_interactive_book` 当前 1:1 挂 `course` 是建模捷径错误，应沿用 `course_media` 模板+assignment 范式（详见 ADR 0001 与 asp-backend issue #69）。

排期（头等大事）：同一 level 不同班 `start_date` **必然不同**，`unlock_at`（绝对时间）**绝不能跨班原样拷贝**，必须由「目标班 `start_date` + `unlock_after_days`」按班重锚；相对量是 SSOT，绝对量是派生投影。这是业务回避完整 `sync-from-demo` 的**主因**（详见 ADR 0003 与 asp-backend issue #72）。

排序（次要）：`course_unit.unit_order` 是排序唯一 SSOT，`course.course_order` 只是其按班投影——但**现网二者已漂移（高阶/中阶约 363/439 不等），读取一律以 `unit_order` 为准，勿假设相等**。demo 班是等级业务内容的标准定义实例，班主任「维护课程内容」本质是维护 unit；sync 不应隐式重排 `course_order`，确需重排走「按 unit_order 提议 → 业务确认」（详见 ADR 0002）。

完整 SSOT：[`docs/domain_model.md`](docs/domain_model.md)；架构决策：[`docs/decisions/0001-course-interactive-book-as-template-media.md`](docs/decisions/0001-course-interactive-book-as-template-media.md)、[`docs/decisions/0002-course-ordering-is-unit-dimension.md`](docs/decisions/0002-course-ordering-is-unit-dimension.md)、[`docs/decisions/0003-schedule-unlock-must-reanchor-to-class-start-date.md`](docs/decisions/0003-schedule-unlock-must-reanchor-to-class-start-date.md)。

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

分支命名：`issue-{N}/{surface}`，SSOT 在 `config/surfaces.yaml`。

## 分诊协议

综合 Agent 分诊流程：

1. 读取新 issue（`feishu-inbound` 标签）
2. 参照 `config/triage.yaml` 判定 surface + difficulty + assignee
3. 在对应 surface repo 创建执行级 issue，关联中央 issue
4. 中央 issue 添加 `triaged` 标签 + 分诊 comment

分诊决策由 Agent 自主完成（参考 `skills/workflow_triage_routing.md`），不需人工确认。

## 执行约定

- Smart PR：`tools/smart_pr.py`，读取 `config/surfaces.yaml` 做分支/reviewer 路由
- Issue 收尾：执行完成后走 `skills/workflow_post_implement.md`（PR 合入 + 飞书通知）
- Debug 分析：`skills/contract_debug_analysis.md` 定义分析 comment 的输出格式

### asp-backend OpenAPI spec 维护（避坑）

asp-backend 改动若涉及路由/Pydantic model（`backend/app/**`），CI（`.github/workflows/api-docs.yml` 的 `export-openapi` job → "Verify spec is up to date"）会重生 `docs/api/openapi.json` 并 `git diff --exit-code` 校验。

**铁律：不要在本机整文件重生 spec。** `requirements.txt` 用 `>=` 不锁版本，且 CI 用 pip cache，等于 CI 的 fastapi/pydantic 被 cache 钉在某个旧版本。本机（尤其新 fastapi/py 版本）跑 `python scripts/export_openapi.py` 会把大量无关端点重新序列化（典型噪声：文件上传字段 `format:binary` ↔ `contentMediaType`、重复 `security` 块），导致 CI verify 失败。

**正确姿势**（按优先级）：
1. 优先取 CI 失败 run 的 `openapi-json` artifact（CI 在 `failure()` 时上传），直接提交——这就是 CI 期望的产物。
2. artifact 取不到时，做**增量重建**：以 `origin/<base>` 的 spec 为底，仅注入本次真实新增（新路径对象 / model 新字段），保留基线对所有未改端点的序列化。校验目标：`git diff origin/<base> -- docs/api/openapi.json` **应为纯增量（0 删除）**。
3. 终极方案才是用与 CI 一致的 py3.11 + pinned 依赖环境整体重生。

## Memory 系统

- `memory/OBSERVATIONS.md`：Observer 日频写入的 L1 信号（issue 动态、PR 合并、部署事件）
- `memory/MEMORY.md`：Reflector 周频蒸馏的 L2 原子事实
- `memory/archive/`：过期 Medium 归档

Observer 扫描范围：`AI-MYG/asp*` 所有 repo 的 issue/PR/commit 活动。

## Persona

`personas/` 目录按团队成员维护认知画像。初始只有 Marvin（CTO/后端），其他成员通过 Observer 积累交互模式后逐步形成。

切换协议：参照 `personas/INDEX.md`。

## Tools

- Pipeline C/D 扫描范围：`tools/feishu_inbound/config.yaml` → `pipeline_cd_scan`（改配置即可，见 `skills/workflow_inbound_pipeline.md`）
- Dev 验收：`./venv/bin/feishu-inbound accept pass|fail`（见 `skills/workflow_acceptance.md`、Cursor skill `feishu-inbound-acceptance`）
- Skill 同步（维护者）：在 rootgrove 执行 `bash tools/feishu_inbound/sync_skills_to_asp_infra.sh`
- `tools/smart_pr.py`：读取 `config/surfaces.yaml`，自动创建 PR 并指派 reviewer
- `tools/opencode_client.py`：OpenCode Server HTTP REST 客户端，供自动化脚本调用

## Secrets

本地 macOS：**仅 Keychain**（`rootgrove/<KEY>`，经 `scripts/load_asp_env.sh` / `tools/asp_env.py` 加载）。`.env.example` 为变量名清单；勿提交 `.env`。GitHub Actions / CI 用 repository secrets。

## Python

本 repo 脚本使用系统 Python 3。依赖：`pip install pyyaml requests`。

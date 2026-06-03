# ADR 0002：课程排序属于 unit（业务）维度，course_order 是其投影

- 状态：Accepted（方向已与 CTO 核对；实现以 asp-backend issue #72 / PR 为准）
- 日期：2026-06-03
- 关联：`docs/domain_model.md`（§二 demo 班角色、§五 排序维度）、asp-backend issue #72、asp issue #5

> 注意：业务回避完整 sync 的**主因是排期（绝对解锁时间跨班错位）**，见 ADR 0003。本 ADR 只处理**次要**的排序维度问题。

## 背景

`sync-from-demo`（班级课程同步）在 Phase 1/2 之后默认执行 `reorder_courses_after_sync`，按 `(course_unit.unit_order, created_at, id)` 将目标班全部课程的 `course_order` 重排为密集序 1..N。

业务（班主任）因此回避完整 `sync-from-demo`，改用 selective 同步——而 selective 端点硬编码 `sync_course_media_assignment=False`，导致课程内媒体不被同步。这就是 asp-backend issue #72 的直接现象：同步后课程结构在、媒体为空（生产已观测到「实操指南」班 Day22–24 三门课 `course_media_assignment` 为 0；已于 2026-06-03 按本班 cadence 补齐 14/11/17 = 42 条）。

## 领域判断

- demo 班是**等级业务内容的标准定义实例**；班主任「维护课程内容」本质是维护 **unit（业务维度）** 内容，而非某个交付班的私有数据。
- `course_unit.unit_order` 是排序的**唯一 SSOT**；`course.course_order` 只是其**按班投影**，不应承载独立业务序。
- **现网实测：`course_order` 已与 `unit_order` 漂移**（四阶 1:1 对齐，但高阶/中阶 439 门中约 363 门不等）。因此读取顺序**一律以 `unit_order` 为权威，不得假设 `course_order == unit_order`**；漂移是历史累积的症状，目标态是让 course_order 回归为 unit_order 的纯投影。
- **按班差异只允许出现在「内容」**（如家长端富文本按班版本 `course_richtext` vs 模板 `course_unit_richtext`），**不允许出现在「排序」**。

## 决策

1. 排序的权威与「真实决策」发生在 **unit / demo（业务）维度**；目标交付班继承之，后端**不在 sync 里猜测或发明** per-class 顺序。
2. **sync 不写 `course_order`、不做自动 reorder**，统一按 `unit_order ASC NULLS LAST` 排序（列表默认已如此）。**`course_order` 字段保留**——不排除未来出现「sync 后仍需在课程层重排」的需求，但那必须走**显式全量传入**的 reorder 接口，而非由 sync 隐式写入。
3. **媒体同步与排序解耦**：媒体补缺应是独立、可执行、绝不触碰排序的操作（修复 #72 的核心）。
4. 若确需调整顺序：常规情况调 **unit_order（业务侧）**；少数确需课程层重排的情况走 **propose-confirm**——接口**按 `unit_order` 给出建议顺序**，业务方**确认后**再经既有「全量传入」reorder 契约（`PUT/POST .../classes/{id}/courses/reorder`）落库，而非由 sync 隐式改写。这样保留人工干预入口，同时不会在同步时悄悄改动业务未预期的顺序。

## 理由

- **与领域模型一致**：排序是模板 / 业务属性，不是交付实例属性（见 `docs/domain_model.md`）。
- **消除业务回避 sync 的根因**：去掉隐式 reorder，业务才敢用完整同步补齐媒体。
- **与既有 reorder 模式一致**：unit / media / playlist 的 reorder 均为「显式全量传入」；sync 内的自动重排是唯一异类。

## 影响

- 后端按此方向调整 `sync-from-demo`（去隐式 reorder + 媒体同步解耦），迁移与实现细节由 **asp-backend issue #72 及其 PR** 承载。
- 前端 / admin 在涉及课程顺序时，应按「顺序 = unit_order」的领域语言理解，不依赖 `course_order` 的独立值。
- 本 repo（asp-infra）**不做迁移、不动数据库、不改业务代码**；本 ADR 仅固化领域决策与理由，供各 surface agent 入场即获正确 context。

## 备选方案（已否决）

- **维持 sync 内自动 reorder**：延续业务回避完整同步、媒体不同步的现状，否决。
- **引入 per-class 自定义课程序**（含「班主任逐班放置新课」式交互）：与「排序属业务 / unit 维度」的领域模型冲突，制造双轨心智与冗余决策点，否决。

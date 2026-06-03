# ADR 0001：course_interactive_book 沿用 course_media 模板 + assignment 范式

- 状态：Accepted（方向已与 CTO 核对；实现以 asp-backend issue #69 / RFC 为准）
- 日期：2026-06-03
- 关联：`docs/domain_model.md`、asp-backend issue #69

## 背景

ASP 后端采用「模板侧 vs 班级交付侧」两套平行结构（详见 `docs/domain_model.md`）：

- **模板侧**：`course_media` 挂在 `course_unit` / `course_level` 上，与班级无关、可复用。
- **交付侧**：`course_media_assignment` 把模板内容按班级排期 / 解锁挂到 `course` 上。

`course_interactive_book`（互动绘本 / phonics-picture）当前直接以 1:1 关系挂在每天的 `course` 上
（`course_interactive_book.course_id` 设为 UNIQUE，见 `backend/app/database_models.py` ~L2080）。
这意味着每个班级每天都要单独存一份绘本实例，绘本内容无法跨班级复用，且解锁 / 排期逻辑与 `course_media` 走两套不同路径。

## 决策

**将 `course_interactive_book` 视为一种模板媒体，纳入与 `course_media` 相同的领域范式：**

1. 互动绘本内容作为**模板**挂载在 `course_unit` / `course_level` 维度，与班级无关、可复用。
2. 按班级的可见性 / 排期 / 解锁通过 **assignment 层**交付，与 `course_media_assignment` 同构。
3. 不再为绘本保留 1:1 钉死在 `course` 上的捷径建模。

## 理由

- **一致性**：互动绘本本质是教学内容（媒体的一种形态），与 `course_media` 同类；统一范式后，内容复用、排期、解锁逻辑只有一套心智模型。
- **可复用**：模板与班级解耦后，同一份绘本可被多个班级 / 多天复用，避免重复存储与重复维护。
- **可演进**：未来新增的任何内容形态（音频书、互动游戏等）都能复用「模板挂 unit + assignment 交付」范式，避免每加一种内容就新增一张 1:1 挂 `course` 的表。
- **避免捷径债**：1:1 挂 `course` 是建模捷径，随班级数增长会放大数据冗余与逻辑分叉。

## 影响

- 后端按此方向重建模，迁移与实现细节由 **asp-backend issue #69 及其 RFC** 承载。
- 前端（app / admin / websites）在涉及绘本内容与交付时，应按「模板内容 + 按班级 assignment 交付」的领域语言理解，而非「每天 course 一份绘本」。
- 本 repo（asp-infra）**不做迁移、不动数据库、不改业务代码**；本 ADR 仅固化领域决策与理由，供各 surface agent 入场即可获得正确 context。

## 备选方案（已否决）

- **保留 1:1 挂 course**：维持现状，简单但延续捷径债，内容无法复用、逻辑双轨，否决。

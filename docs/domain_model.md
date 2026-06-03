# ASP 领域模型：模板侧 vs 班级交付侧

> **本文是 ASP 核心业务领域模型的 SSOT（Single Source of Truth）。**
> 任何 surface repo（backend/app/admin/wecom/websites/canonical）的领域模型描述都应以本文为准，分 repo 中只保留浓缩指针。
> 已与 CTO 核对，基于真实 schema（`projects/asp/backend` → `backend/app/database_models.py`）。

## 一句话原则

> **「模板内容」与「班级交付」必须分离。**
> 模板内容挂在 `course_unit` / `course_level` 上、与班级无关、可复用；
> 按班级的可见性 / 排期 / 解锁通过 **assignment 层**挂在 `course` 上交付。

ASP 后端是**两套平行结构**，「班级 / 等级」是各自的最高维度，两者通过 `course.course_unit_id` 这一根线连接。

---

## 一、内容 / 模板侧（与班级无关，可复用）

等级是内容侧的最高维度。模板内容只描述「教什么」，不关心「哪个班级、什么时候看」。

```
course_level（等级：一阶 / 二阶 / 三阶，level_order）        ← 最高维度
  └─ course_unit（课程单元 / 天，FK course_level_id，unit_order，content_kind: theory/practice）
       └─ course_media（课程媒体，FK course_unit / level / tag）
```

- `course_level`：定义课程层级（一阶 / 二阶 / 三阶），`level_order` 唯一排序。
- `course_unit`：归属某个等级（`course_level_id`），`unit_order` 在等级内排序，`content_kind` 区分 theory / practice。一个 unit 通常对应「一天」的内容。
- `course_media`：最小的模板内容单元，挂在 `course_unit` / `course_level` / `tag` 上。**与班级无关，可被任意班级复用。**

---

## 二、班级 / 交付侧（每班级一份实例）

班级是交付侧的最高维度。交付侧描述「哪个班级、在什么时间、以什么顺序看到哪些模板内容」。

```
class（班级，course_level_id「基于第一个课程推导」，班主任 = creator，start_date）   ← 最高维度
  └─ course（课程合集，class_id + course_unit_id，UNIQUE(class_id, course_unit_id) active）
       │      = 某班级对某一天（course_unit）的实例化合集
       ├─ course_media_assignment（排期 / 交付：media_order / unlock_after_days / unlock_at）→ course_media
       └─ course_interactive_book（当前 1:1 挂 course —— 这是建模捷径错误，见下）
```

- `class`：班级，最高维度。`creator_id` 为班主任，`start_date` 用于计算相对解锁时间，`course_level_id` 基于第一个课程推导。
- `course`：**某班级对某个 `course_unit`（天）的实例化合集**。`class_id + course_unit_id`，部分唯一索引 `UNIQUE(class_id, course_unit_id) WHERE is_active`。这是连接「班级侧」与「模板侧」的关键纽带。
- `course_media_assignment`：**交付 / 排期层**。把模板内容（`course_media`）按班级排期挂到 `course` 上，携带 `media_order`（顺序）、`unlock_after_days`（相对开课日解锁）、`unlock_at`（绝对解锁时间）。**班级可见性与解锁时序都在这一层表达，不污染模板内容本身。**

### demo 班的特殊角色：业务内容的载体

每个 `course_level` 有一个 **demo 班**（`class_name` 含 "demo"，`course_level_id` 指向该等级）。它**不是普通交付班级，而是该等级业务内容的「标准定义实例」**：

- 班主任「维护课程内容」时，操作入口是 demo 班的课程，但其本质是在**定义 / 更新该等级的模板内容**（`course_unit` / `course_media`），即**业务维度（unit）的内容**，而非某个学员班级的私有数据。
- 真实交付班通过 `sync-from-demo` 从 demo 班继承这份业务定义。
- 因此：**demo 班 = 业务侧内容的具体体现；普通班 = 学员侧的交付实例。**

> 推论：**unit 是业务维度实体，course 是学员维度实体。** 班主任改的是 unit（业务内容）；course 只是该 unit 在某班的实例化。这一区分决定了「排期 / 排序属于哪一侧」（见 §五排期、§六排序）。

---

## 三、对应关系表（schema 证据）

| 业务关系 | 表 / 字段 | 约束 | schema 位置 |
|----------|-----------|------|-------------|
| 班级 ↔ 等级 | `class.course_level_id` → `course_level` | 基于第一个课程推导 | `DBClass` ~L1855，`DBCourseLevel` ~L94 |
| 等级 → 单元（天） | `course_unit.course_level_id` → `course_level` | `UNIQUE(course_level_id, unit_order)` | `DBCourseUnit` ~L149 |
| 单元 → 模板媒体 | `course_media.course_unit_id` → `course_unit` | 与班级无关、可复用 | `DBCourseMedia` ~L340 |
| 课程 ↔ 课程单元（天） | `course.course_unit_id` → `course_unit` | `UNIQUE(class_id, course_unit_id)` active | `DBCourse` ~L1917 |
| 排期 ↔ 课程媒体 | `course_media_assignment` → `course_media` | 含 `unlock_after_days` / `unlock_at` 时序 | `DBCourseMediaAssignment` ~L2137 |

> schema 真实位置：`projects/asp/backend` → `backend/app/database_models.py`
> （`DBCourseLevel` ~L94, `DBCourseUnit` ~L149, `DBCourseMedia` ~L340, `DBClass` ~L1855, `DBCourse` ~L1917, `DBCourseInteractiveBook` ~L2080, `DBCourseMediaAssignment` ~L2137）

---

## 四、关键原则：模板 / 交付分离

1. **模板内容（`course_media`）挂在 `course_unit` / `course_level` 上**，与班级无关、可被多个班级复用，只描述「教什么」。
2. **班级可见性 / 排期 / 解锁通过 assignment 层（`course_media_assignment`）挂在 `course` 上交付**，描述「哪个班级、什么时候、以什么顺序」。
3. **新增任何「内容形态」时，先问：它是模板内容还是交付配置？** 模板内容沿用 `course_unit` / `course_level` 挂载范式；交付配置沿用 `assignment` 范式。

### `course_interactive_book` 的建模问题

`course_interactive_book`（互动绘本 / phonics-picture）当前 **1:1 直接挂在每天的 `course`** 上（`course_id` UNIQUE，见 `DBCourseInteractiveBook` ~L2080）。

这是一个**建模捷径错误**：互动绘本本质是一种**模板媒体**，逻辑上与 `course_media` 属于同一类，理应沿用「模板内容挂 `course_unit` + 通过 assignment 层按班级交付」的同一范式——而不是钉死在每个班级每天的 `course` 实例上。

**后端正在按此重建模**，详见 `asp-backend` issue #69 及其 RFC。本文记录该方向的领域共识；具体迁移与实现以 backend issue #69 / RFC 为准（asp-infra 不做迁移、不动数据库）。

---

## 五、排期 / 解锁：绝对时间必须按班重锚（业务回避 sync 的**主因**）

> **这是 issue #72 背后真正严重、且具普遍性的根因。** 排序问题（§六）是次要的。

- `course_media_assignment` 同时存两种解锁表达：`unlock_after_days`（**相对**开课日的天数，可移植）与 `unlock_at`（**绝对**时间戳，与某个 `start_date` 绑定）。
- **铁律（已与 CTO 核实）：同一 level 的不同班级，`start_date` 必然不同。** demo 班的 `unlock_at` 锚定的是 demo 自己的日历。
- 因此：**任何继承 / 同步都绝不能把 demo 的绝对 `unlock_at` 原样拷给真实班**——那等于把 demo 的日历强加给一个开课日不同的班，排期必然错位。
- **正确做法**：`unlock_at` 一律由**目标班 `start_date` + 相对量重新推导**（语义上 `new.unlock_at = target.start_date + unlock_after_days`，或等价地 `demo.unlock_at + (target.start_date − demo.start_date)`）。相对量 `unlock_after_days` 是可移植的 SSOT，绝对时间只是按班派生的投影。
- **已观测到的污染**：部分历史 sync 出来的班，其 `unlock_at` 与「本班 `start_date` + `unlock_after_days`」对不上（同一行 abs/rel 自相矛盾），说明排期已被错误绝对时间污染。
- 关联：asp-backend issue #72；决策见 `docs/decisions/0003-schedule-unlock-must-reanchor-to-class-start-date.md`。

---

## 六、排序维度：unit_order 是业务序，course_order 是其按班投影

排序的**权威决策属于业务 / unit 维度**，不属于学员 / 交付维度：

- `course_unit.unit_order` 是排序的**唯一权威 SSOT**，由业务在 demo / 等级维度定义（`UNIQUE(course_level_id, unit_order)`）。
- `course.course_order` 是 unit_order 的**按班投影 / 冗余**，不承载独立的业务序。
- **现网实测警告：`course_order` 已与 `unit_order` 漂移**——四阶为 1:1 对齐，但高阶 / 中阶等级中（439 门课里约 363 门）两者不等。因此**读取顺序时一律以 `unit_order` 为权威，不要假设 `course_order == unit_order`**。这种漂移正是 sync 自动 reorder + 缺乏 SSOT 纪律累积出来的症状，而非特性。

### 为什么后端不应在 sync 里「猜」排序

- 顺序由 unit_order 决定，sync 时课程位置是**已知的**，不需要后端按 `(unit_order, created_at, id)` 做密集重排去「猜」一个 course_order。
- 自动重排会把 course_order 写成密集序（1..N），可能进一步加剧与 unit_order 的漂移；读路径若直接读 `course_order` 就会「排序错乱」。
- 正确做法（已拍板）：sync **不写 `course_order`、不做自动 reorder**，统一按 `unit_order ASC NULLS LAST` 排序。`course_order` 字段**保留**，留给未来「sync 后课程层显式重排」的可能。
- **重排走 propose-confirm**：确需课程层重排时，由接口**按 `unit_order` 给出一份建议顺序**，业务方**确认后**再落库（复用既有「显式全量传入」reorder 契约 `PUT/POST .../classes/{id}/courses/reorder`），**绝不由 sync 隐式改写**。这样既保留人工干预入口，又不会在同步时悄悄改掉业务没预期的顺序。
- 关联：asp-backend issue #72；决策见 `docs/decisions/0002-course-ordering-is-unit-dimension.md`。

### 唯一的「按班差异」例外：内容，而非排序 / 排期

少数内容**允许不同班有不同版本**——典型是家长端富文本「背景」等：

- 模板版本：`course_unit_richtext`（挂 `course_unit`，`content_kind` theory / practice），是 demo / 业务侧的标准内容。
- 按班版本：`course_richtext`（挂 `course`），允许某班覆盖出自己的版本。

> 注意：这个例外是**内容（什么文字）**的按班差异，**不是顺序（第几天）**的按班差异。顺序永远以 unit_order 为准。

---

## 七、给 agent 的使用约定

- 在任何 ASP surface repo 工作、涉及课程 / 班级 / 媒体 / 绘本 / 排期 / 解锁逻辑时，先对照本文确认「这件事属于模板侧还是交付侧」。
- 不要把班级级的排期 / 解锁信息写进模板内容表（`course_media` / `course_unit`）。
- 不要为新内容形态发明 1:1 挂 `course` 的捷径；沿用模板 + assignment 范式。
- **排期是头等大事**：`unlock_at`（绝对时间）**绝不能跨班原样拷贝**。同 level 不同班 `start_date` 必然不同，绝对时间必须由「目标班 `start_date` + `unlock_after_days`」按班重锚。相对量是 SSOT，绝对量是派生投影。
- **排序属业务 / unit 维度**：`unit_order` 是 SSOT，`course_order` 只是其按班投影；但**现网二者已漂移（高阶/中阶约 363/439 不等），读取顺序一律以 `unit_order` 为准，不要假设相等**。不要在 sync 里隐式重排 `course_order`；确需重排走「按 unit_order 提议 → 业务确认」的显式全量 reorder 接口。
- **按班差异只在内容，不在排序 / 排期**：富文本等可有按班版本（`course_richtext`），但「第几天 / 先后 / 何时解锁」永远以 unit 维度 + 本班 `start_date` 为准。
- 班主任「改课程内容」= 改 unit（业务侧），入口通常是 demo 班；不要把它理解成改某个交付班的私有数据。
- 本文为 SSOT；各 surface repo 的领域模型小节只是指针，发现冲突以本文为准。

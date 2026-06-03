# ADR 0003：排期 / 解锁的绝对时间必须按目标班 start_date 重锚

- 状态：Accepted（方向已与 CTO 核对；实现以 asp-backend issue #72 / PR 为准）
- 日期：2026-06-03
- 关联：`docs/domain_model.md`（§五 排期 / 解锁）、asp-backend issue #72、ADR 0002（排序，次要）

## 背景

`course_media_assignment` 用两种字段表达解锁时序：

- `unlock_after_days`：**相对**开课日（`class.start_date`）的天数 —— 可移植、与具体日历无关。
- `unlock_at`：**绝对**时间戳 —— 与生成它时所用的某个 `start_date` 强绑定。

`sync-from-demo` 在为零媒体课程补 assignment 时，曾直接 `unlock_at = demo.unlock_at`（原样拷贝 demo 的绝对时间）。

## 领域判断（关键事实）

- **同一 level 的不同班级，`start_date` 必然不同（CTO 确认）。** demo 班的 `unlock_at` 锚定的是 demo 自己的开课日历。
- 因此**把 demo 的绝对 `unlock_at` 拷给任何真实班，结果必然错位**——这不是个案，而是结构性、普遍性问题，且大概率已在历史 sync 出来的班级中造成排期污染（已观测到 abs 与 rel 在同一行自相矛盾的班）。
- 这才是**业务回避完整 `sync-from-demo` 的主因**（排序问题 ADR 0002 是次要）。

## 决策

1. **`unlock_at` 永不跨班原样拷贝。** 任何继承 / 同步 / 补缺，绝对解锁时间一律由**目标班 `start_date` 重新推导**：
   - 语义：`new.unlock_at = target.start_date + unlock_after_days`；
   - 等价实现：`new.unlock_at = src.unlock_at + (target.start_date − src.start_date)`（delta=0 时退化为恒等，仍走重锚路径以保证正确性来源）。
2. **`unlock_after_days`（相对量）是排期 SSOT**；`unlock_at` 是按班派生的投影。读写排期一律以相对量为权威。
3. **新增 / 插入课程的排期需显式确定**，不由 sync 凭空填充；新接口的排期相关字段一律**选填**，不破坏既有调用方。
4. **媒体内容同步与排期解耦**：补媒体（media_id / media_order）是内容操作；排期是按本班重锚的独立步骤。二者不得互相挟持（#72 即因 selective 端点 `sync_course_media_assignment=False` 把内容同步连带禁掉）。

## 理由

- 与领域模型一致：排期是**交付实例属性**，必须绑定**本班**日历，而非来源班日历。
- 消除业务回避 sync 的主因：只要排期按本班重锚，业务才敢用完整同步补齐媒体。
- 可移植：以相对量为 SSOT，使同一份业务内容能在任意开课日的班级正确落地。

## 影响

- 后端按此方向调整 `sync-from-demo` 的 assignment 写入逻辑（绝对时间重锚 + 内容/排期解耦），迁移与实现细节由 **asp-backend issue #72 及其 PR** 承载。
- 历史污染班级的排期修正由业务在使用中发现并反馈，按本 ADR 逐班重锚修复；本 repo 不批量改数据库。
- 本 repo（asp-infra）**不做迁移、不动数据库、不改业务代码**；本 ADR 仅固化领域决策与理由。

## 即时修复记录（#72，2026-06-03）

- 目标班「（全能重点班）母语感四阶 · 实操指南」Day22–24 三门零媒体课，按本班 cadence 补齐媒体：14 / 11 / 17 = 42 条。
- 该班 `start_date`（2026-05-11）恰与 demo 一致（属母本性质班），故重锚 delta=0；unlock 落 06-04 / 06-05 / 06-06，衔接本班 Day21（06-03）。
- 已记录事务级回滚预案（按 inserted id 反删）。

## 备选方案（已否决）

- **原样拷贝 demo 绝对 `unlock_at`**：仅在目标班与来源班 `start_date` 巧合相同时才不出错，普遍场景必然错位，否决。
- **只信 `unlock_at`、丢弃 `unlock_after_days`**：失去可移植性，跨班无法正确落地，否决。

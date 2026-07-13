# 团队同步：游戏进度数据分层（过程事实 → 汇总投影）

> **日期**：2026-07-13  
> **作者**：袁牧  
> **对象**：Backend / App / Admin / 产品  
> **目的**：对齐「游戏进度」该怎么建，避免在错误表上继续堆接口  
> **领域 SSOT**：[ADR 0004](../decisions/0004-unit-completion-dual-model.md) · [domain_model.md §七](../domain_model.md)

---

## 1. 一句话结论

**游戏侧要先有 App 上报的过程事实（局次 / 分数 / 时长等），再汇总到用户、班级、课程（主题）等读模型。**  
管理端查进度、代补录，必须建立在同一套事实流上，不能另造一套 admin 专用表。

---

## 2. 为什么现在要讲这件事

两周内有两个相关需求撞在一起：

| Issue | 诉求 | 暴露的缺口 |
|-------|------|------------|
| [asp-backend#265](https://github.com/AI-MYG/asp-backend/issues/265) | themes 列表要 `isComplete`，与单元完成态一致 | 读了几乎无人写入的 `user_progress.completed_units`；生产出现「单元全完成、主题仍 false」 |
| [asp-backend#302](https://github.com/AI-MYG/asp-backend/issues/302) | 管理端按学员查游戏上报，并支持代补录 | 假定存在带分数/时长的 `game-sessions`；**当前并没有完整的过程事实层** |

#265 修的是「完成布尔」读错源；#302 真正需要的是「过程事实 + 汇总」。两件事相关，但**不是同一层**，不要混成一个 PR。

---

## 3. 领域共识：单元完成是双模型（勿混口径）

`course_unit.type` 只有两类：

| | mission（媒体课） | game（游戏课） |
|--|------------------|----------------|
| 子内容 | `course_media` | `game_pack` |
| 「单元完成」怎么来 | 媒体都看完 → **派生** | App 裁定过关 → **上报事件**（后端不做「是否真通关」校验） |
| 事实落点 | `user_progress.completed_media` | `user_course_unit_game_completed` / `user_game_pack_completed` |
| themes `isComplete` | 不计入 | **只计入 game** |

要点：

- 「单元是媒体的聚合」在 **mission 成立**，在 **game 不成立**（game 的子内容是游戏包）。
- `user_progress` 仍是**媒体进度**权威；`completed_units` **不是**游戏单元完成事实源（现代上报不写它）。
- 详细决策见 asp-infra **ADR 0004**（已与 CTO 核对）。

---

## 4. 正确分层（建议全员按此理解）

```
┌─────────────────────────────────────────────────────────┐
│  L0  App 游戏过程事件（ODS）                              │
│      局次 / score / duration / game_pack_id / class_id │
│      / completed / client_event_id（幂等）               │
└───────────────────────────┬─────────────────────────────┘
                            │ 投影 / 汇总
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   用户维度汇总         班级维度汇总         课程/主题维度汇总
   （次数、通关、积分）   （班内进度）         （如 themes isComplete）
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                            ▼
              管理端查询 / 代补录（走同一 ODS，source=admin）
```

| 层 | 职责 | 现状 |
|----|------|------|
| **过程事实（ODS）** | 可审计的一局一局上报 | **基本缺失**；#302 在要这一层 |
| **完成事件** | 「过关了」布尔（发奖、主题完成） | 已有 `game-pack/complete`、`course-unit/complete` |
| **汇总读模型** | 用户 / 班级 / 课程主题 | 部分读死字段或只读完成表 |

**原则：read-what-you-write。** 写在哪一层，读就对齐哪一层；汇总只能从事实投影，不能反向当权威。

---

## 5. 和两个 Issue 的对应关系

### #265（短期，可继续走入站流水线）

- **范围**：themes `isComplete` **读对齐**到 `user_course_unit_game_completed`，与 `complete-status` 同口径（含 `class_id` 规则）。
- **不做**：不改成「从媒体派生」；不反向双写 `completed_units`；不借机上完整埋点体系。
- **状态**：领域口径已写入 ADR 0004；Analysis 已按此更新，待 Human `approved-to-execute` 后 Pipeline D。

### #302（中期，建议改需求顺序）

Issue 原文直接设计：

- `GET /api/v1/admin/game-sessions`
- `POST /api/v1/admin/game-sessions`（管理员代补录）

这在**过程事实表与 App 上报契约尚未落地**时，容易变成「admin 专用假数据」。建议拆期：

| 期次 | 做什么 | 谁 |
|------|--------|-----|
| **P0** | 定 App→Backend 游戏过程事件 schema（字段、幂等键、与 `game_pack_id`/`class_id` 关系） | 产品 + Backend + App |
| **P1** | App 埋点并真实上报；Backend 落事件表 | App + Backend |
| **P2** | 投影：用户 / 班级 / 课程（主题）汇总；与现有 complete 事件关系写清 | Backend |
| **P3** | 管理端查询 + 代补录（`source=admin`，走同一投影，可触发奖励） | Admin + Backend |

**代补录补的是 ODS，不是另写一张和 App 无关的表。**

---

## 6. 请各端对齐的动作

1. **产品 / 研发负责人**：确认是否接受「先埋点事实流，再 admin 查补」的分期；若同意，在 #302 评论挂本报告并改验收顺序。  
2. **App**：评估现有 `reportGamePackComplete` 与「过程事件」差距；P0 参与 schema 评审。  
3. **Backend**：#265 按 ADR 收敛读路径；#302 在 P0 未完成前不要直接实现假想的 `game-sessions` 全套。  
4. **Admin**：学员总览「游戏上报」入口可作为 P3 UI，数据源依赖 P1 事件表。

---

## 7. 参考链接

| 文档 / Issue | 说明 |
|--------------|------|
| [asp-backend#265](https://github.com/AI-MYG/asp-backend/issues/265) | themes `isComplete`；生产验收失败与读源修正 |
| [asp-backend#302](https://github.com/AI-MYG/asp-backend/issues/302) | 管理端查游戏上报 + 代补录 |
| [ADR 0004](../decisions/0004-unit-completion-dual-model.md) | mission / game 双模型与事实源裁决 |
| [domain_model.md §七](../domain_model.md) | 进度与完成（领域 SSOT 摘要） |
| backend `docs/tasks/game/unit-game-completion-requirements.md` | 既有「前端控制上报、后端不校验」契约 |

---

## 8. 群聊可复制摘要（短版）

> 【进度数据分层同步 2026-07-13】  
> 1）游戏进度应：**App 过程事件 → 用户/班级/课程汇总**；管理端查补必须共用同一事实流。  
> 2）#265：短期只修 themes 读对齐 GameCompleted（见 ADR 0004），不扩成埋点大工程。  
> 3）#302：先定 App 上报 schema 再落事件表，最后才做 admin 查询/代补录；避免先造 admin 专用表。  
> 详情：asp-infra `docs/reports/20260713_game_progress_layering_team_sync.md`

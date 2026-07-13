# ADR 0004：单元完成是双模型 — mission 媒体派生 vs game 前端事件

- 状态：Accepted（2026-07-13 与 CTO 核对；落地以 asp-backend issue #265 及后续收敛 issue 为准）
- 日期：2026-07-13
- 关联：`docs/domain_model.md`（§八 进度与完成）、asp-backend issue #265、`docs/tasks/game/unit-game-completion-requirements.md`（backend 仓）

## 背景

`GET /api/v1/course/themes` 的 `isComplete`（#265）在生产验收失败：同一用户 Theme 1 下全部 game unit 的 `complete-status` 为 true，主题仍为 false。

表面像「读错表 / 缺参数」。深挖后发现 ASP **不存在单一「单元完成」语义**，而是按 `course_unit.type` 并行两套模型；规范叙事里的 `user_progress.completed_units` 在现代 game 上报路径上无人写入，却被 themes / app_home 当作 source of truth。

## 领域判断

`course_unit.type` 只有两类（`database_models.py` → `DBCourseUnit.type`）：

| 维度 | `mission` | `game` |
|------|-----------|--------|
| 子内容 | `course_media`（视频/音频/富文本） | `game_pack`（游戏包） |
| 「单元完成」如何得到 | **派生**：单元下全部未删除 media ∈ 用户已完成 media | **事件**：前端裁定「过关」后上报；后端**不校验**包是否真实通关 |
| 事实落点 | `user_progress.completed_media`（活跃写模型） | `user_course_unit_game_completed`（逐条、含 `class_id`） |
| 权威读 API | 媒体进度 / 等级成就路径上的媒体聚合 | `POST/GET .../course-unit/complete(-status)` |
| themes `isComplete` | **不计入** | **只计入** `type == "game"` |

关键推论：

1. **「单元是媒体的聚合」在 mission 成立，在 game 不成立。** game 的子内容是 game_pack；需求文档写明「由前端控制是否触发」「后端判定是否真的完成（明确不做）」。
2. **`user_progress` 仍是媒体进度与积分域的权威**；不得因 game 事件表的存在而否定 Progress 在 mission 域的地位。
3. **`user_progress.completed_units`（JSONB）不是单元完成事实源。** 现代 `POST /course-unit/complete` 只写 GameCompleted；`completed_units` 在活跃上报路径上基本无生产者（初始化空数组 / seed / 账号合并除外）。形态上它像 DM 投影，现状连投影都不是，是**死字段**。
4. **ODS/DM 方向**：若要做投影，只能是  
   `user_course_unit_game_completed`（高信息：class + 时间 + source）→ 可选的 `completed_units` 汇总。  
   反向（Progress → GameCompleted）不可行，无法凭空补 `class_id` / 完成时间。

## 决策

1. **确立双模型，禁止混用口径**  
   - mission 单元完成 = 媒体完成派生。  
   - game 单元完成 = `user_course_unit_game_completed` 事件记录。

2. **game 单元完成唯一事实源** = `user_course_unit_game_completed`。  
   所有主题 / 单元完成读方（含 `GET /course/themes` 的 `isComplete`、`complete-status`）必须与该表对齐。

3. **冻结 `user_progress.completed_units`**  
   - 禁止新读方依赖该字段表达「单元已完成」。  
   - 既有读方（`_compute_theme_completion`、`app_home` theme_progress、部分统计 / wecom 聚合）登记为收敛项：改为读 GameCompleted，或改为 mission 路径上的媒体派生，不得继续假装读权威。

4. **themes `isComplete` 语义（#265）**  
   - 只统计 `type == "game"` 的 unit（与现实现一致）。  
   - 完成判定读 GameCompleted，**不读** `completed_units`。  
   - **班级维度**（与 `complete-status` 对齐）：  
     - 请求带 `class_id` → 仅计该班完成记录（严格匹配）。  
     - 不带 `class_id` → 按 `user_id + course_unit_id` 匹配任意班级（兼容旧客户端）。  
   - **等级维度**：`course_level_id` 用于限定「哪些 unit 属于本次主题列表」；缺失时仍可对返回的 theme 名称做完成计算，但同名跨 level 主题存在合并风险，App 在已知 level 上下文中应传 `course_level_id`。

5. **本 repo（asp-infra）只固化领域决策**；实现与 OpenAPI 变更由 asp-backend #265（及后续收敛 issue）承载。不做迁移、不强制回填历史 `completed_units`。

## 理由

- **read-what-you-write**：game 完成写在 GameCompleted，读却在死字段 `completed_units`，是 #265 prod fail 的直接根因。
- **与已发布契约一致**：`unit-game-completion-requirements` 与 `POST /course-unit/complete` 文档已选择「前端口径、不校验」。
- **保护 Progress 叙事**：媒体域仍用 Progress；只把「一切完成都塞进一张 Progress 表」的过度外推收回来。

## 影响

- **backend #265**：`_compute_theme_completion` 切源到 GameCompleted；补齐 `class_id` / `course_level_id` 文档与可选 query；OpenAPI 同步；回归 prod 复现账号。
- **后续 issue（不并进 #265）**：`app_home` theme_progress、进度摘要里的 `completed_units_count`、wecom 同步中对 `completed_units` 的聚合。
- **App**：`getCourseThemes()` 在已知班级 / 等级上下文中应传 `class_id` 与/或 `course_level_id`（非 #265 阻塞项；后端按上节规则在缺参时仍可计算）。

## 备选方案（已否决）

- **反向双写 `completed_units`，保住「统一 Progress」叙事**：从低信息投影无法还原 class/时间；与「仅写 GameCompleted」文档冲突；双写一致性成本高。否决。
- **themes 改为从 `completed_media` 派生单元完成**：对无 media 的 game unit 派生恒 false；违背 #265「与 complete-status 一致」；否决。
- **仅逼 App 传 `course_level_id`、继续读 `completed_units`**：即使传了 level，读的仍是死字段。否决。

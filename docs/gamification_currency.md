# ASP 游戏化货币：coin 与 points 独立语义

> **适用读者**：后端、App、Admin 对接开发；飞书入站分析 Agent
> **SSOT 范围**：coin / points 定义、数据来源、遗留字段澄清、`GET /api/v1/app/points/summary` 目标契约
> **实现追踪**：asp-backend [#238](https://github.com/AI-MYG/asp-backend/issues/238)（端点实现）
> **中央 issue**：AI-MYG/asp [#110](https://github.com/AI-MYG/asp/issues/110)

---

## 1. 核心原则

**coin（金币）** 与 **points（积分）** 是**两种独立货币**：

- 不可相加，不可合并展示为单一「总分」
- `total_points` 仅统计 points 来源
- `total_coins` 仅统计 coin 来源
- game-pack 完成发放的 coin **不得**写入 `total_points`

产品决策来源：asp-backend #238 §10（2026-07，已确认）。

---

## 2. 货币定义与数据来源

| 货币 | 用户可见语义 | 权威读取路径 | 典型写入路径 |
|------|-------------|-------------|-------------|
| **points（积分）** | 学习进度与社交互动累积，用于排行榜 | `user_progress.points`（按 level 分行）+ `user_event_log` 中 `app_checkin` / `app_comment` / `app_like` / `app_featured` 的 `event_data.points` | 学习进度上报、社交互动事件 |
| **coin（金币）** | 游戏通关等奖励的金币余额 | `SUM(reward.value * user_reward.quantity)`，JOIN `reward` WHERE `reward_type = 'coin'` | `POST /api/v1/progress/game-pack/complete` → `_enqueue_game_pack_reward_grants` |

### 2.1 代码证据（asp-backend）

| 概念 | 位置 | 说明 |
|------|------|------|
| points 字段 | `backend/app/database_models.py` `DBUserProgress.points` (~1320) | 按 `user_id` + `level_id` 累积积分 |
| coins 遗留字段 | `backend/app/database_models.py` `DBUserProgress.coins` (~1321) | 存在但 **game-pack 发奖不更新** |
| coin 奖励定义 | `backend/app/database_models.py` `DBReward.reward_type` (~1390-1403) | 枚举含 `coin`；`value` 为面值 |
| 用户获奖记录 | `backend/app/database_models.py` `DBUserReward` (~1634-1664) | `source='game_pack_complete'`，`source_id` = `game_pack_id` |
| points/summary 现状 | `backend/app/routers/app_leaderboard.py` `get_personal_points_summary` (~420-504) | 仅读 `user_progress` + `user_event_log`，**不含** `user_reward` |
| game-pack 发奖 | `backend/app/routers/progress.py` `_enqueue_game_pack_reward_grants` (~286-322) | 写入 `user_reward`，不更新 `user_progress.points/coins` |
| admin stats stub | `backend/app/routers/gamification.py` (~530) | `"total_coins": 0` 硬编码，待实现 |

---

## 3. 遗留字段澄清

早期 Wiki（`contexts/survey_sessions/asp-wiki/asp_onboarding_wiki_feishu.md` §2.4）将金币描述为 `DBUser.coins` 全局钱包。与当前 game-pack coin 实现**不一致**：

| 字段 / 表 | 状态 | 说明 |
|-----------|------|------|
| `user.coins` | 遗留 | 全局钱包概念，非 game-pack coin 的 SSOT |
| `user_progress.coins` | 遗留 | 模型存在，game-pack 完成路径不写入 |
| `user_reward` + `reward(reward_type='coin')` | **SSOT** | game-pack 及奖励系统发放的金币应从此聚合 |

**推荐**：新功能读取 coin 余额时，优先 `user_reward` JOIN `reward`；勿假设 `user_progress.coins` 与 game-pack 奖励同步。

---

## 4. `user_reward.source` 与展示层 `event_type` 映射

| `user_reward.source` | 含义 | 关联 `reward_type` | `points/summary` breakdown `event_type` |
|----------------------|------|-------------------|----------------------------------------|
| `game_pack_complete` | 游戏包首通发奖 | `coin`, `card`, 等 | coin → **`game_pack_coin`** |
| `challenge` | 每日挑战 | 视配置 | 待扩展 |
| `achievement` / `bonus` | 成就 / 额外奖励 | 视配置 | 待扩展 |

卡片（`reward_type='card'`）走 `GET /api/v1/app/gamification/cards/*` 图鉴路径，**不计入** `points/summary` 的 points 或 coins。

---

## 5. API 契约：`GET /api/v1/app/points/summary`

**路径**：`/api/v1/app/points/summary`
**Query**：`period` = `week` | `month` | `all`（默认 `month`）

### 5.1 目标响应（#238 确认，实现后 OpenAPI 须同步）

```json
{
  "total_points": 120,
  "period_points": 30,
  "total_coins": 4,
  "period_coins": 4,
  "points_breakdown": [
    {
      "event_type": "app_checkin",
      "event_count": 5,
      "total_points": 50
    }
  ],
  "coins_breakdown": [
    {
      "event_type": "game_pack_coin",
      "event_count": 2,
      "total_coins": 4
    }
  ],
  "recent_activities": [],
  "class_rankings": []
}
```

### 5.2 字段规则

| 字段 | 来源 | 规则 |
|------|------|------|
| `total_points` | `user_progress.points` 全量求和 | 不含 coin |
| `period_points` | `user_event_log` 在 `period` 窗口内按 event_type 聚合 | 仅四类社交 event |
| `total_coins` | `user_reward` JOIN `reward` WHERE `reward_type='coin'` | 全量求和 `value * quantity` |
| `period_coins` | 同上 + `earned_at` 在 `period` 窗口 | 与 `period` 参数一致 |
| `points_breakdown[].event_type` | `user_event_log.event_type` | `app_checkin` 等 |
| `coins_breakdown[].event_type` | 固定 **`game_pack_coin`** | 标识游戏包金币明细 |
| `recent_activities` | 可选：合并 `user_event_log` + 近期 coin `user_reward` | 实现细节见 #238 |

### 5.3 关联端点

| 端点 | 角色 |
|------|------|
| `POST /api/v1/progress/game-pack/complete` | 写入 `user_reward`（coin + card） |
| `GET /api/v1/app/gamification/cards/*` | 卡片收集状态 |
| `GET /api/v1/app/points/summary` | 积分 + 金币总览（本文档） |
| 归档 `asp-backend/docs/archive/api/v1/app/04_gamification.md` | `updated_wallet.total_coins` 示例；须与 summary 语义对齐 |

---

## 6. App 前端约定

1. **分开展示** `total_points` 与 `total_coins`，禁止 UI 合并为「总积分」
2. 若对 `event_type` / breakdown 类型做枚举校验，须新增 **`game_pack_coin`** 及中文展示文案（如「游戏奖励金币」）
3. 协调人：App 侧 @Jonty1997（asp-backend #238）

---

## 7. 历史背景

| 锚点 | 来源 | 说明 |
|------|------|------|
| v1.10 | `contexts/survey_sessions/asp-wiki/asp_wiki_api_design.md` | 游戏化系统（成就/积分/排行榜）上线 |
| v1.5 | 同上 | 游戏包系统 |
| v2.24 / 2026-04 | `contexts/survey_sessions/asp-wiki/asp_wiki_erd.md` | `reward`、`user_reward`、`reward_game_pack` 表 |
| 2026-05 | `contexts/survey_sessions/asp-wiki/asp_wiki_game_system.md` | GamePack 生命周期与卡片奖励 |
| 2026-07 | asp-backend #238 | 暴露 points/summary 未读 `user_reward`；确认独立货币语义 |

---

## 8. Gaps checklist

| # | 项 | 状态 |
|---|-----|------|
| 1 | onboarding wiki `DBUser.coins` 与 game-pack coin SSOT 差异 | **已说明**（本文 §3） |
| 2 | `points/summary` 响应字段与 #238 实现一致 | **待实现**（#238 合入后更新 OpenAPI 链接） |
| 3 | `game_pack_coin` 列入 App 对接约定 | **已说明**（本文 §6） |
| 4 | admin `gamification` stats `total_coins: 0` stub | **已标注**（§2.1） |
| 5 | 排行榜 SQL 是否纳入 coin | **待产品确认**；当前排行榜仅基于 points event（`app_leaderboard.py` ~543-564） |

---

## 9. 交叉引用

- asp-backend [#238](https://github.com/AI-MYG/asp-backend/issues/238) — 实现 issue
- AI-MYG/asp [#110](https://github.com/AI-MYG/asp/issues/110) — 本文档来源 issue
- Wiki 导出：`contexts/survey_sessions/asp-wiki/asp_wiki_game_system.md`、`asp_onboarding_wiki_feishu.md`

# 游戏管理模块业务流程文档

> 基于管理端前端源码梳理，覆盖游戏列表、游戏类型、奖励管理、挑战管理四个核心模块。

---

## 一、术语对照

| 代码名称 | 管理端 UI 名称 | 说明 |
|----------|---------------|------|
| `GameType` | 游戏类型 | 游戏模板/分类，决定编辑器种类 |
| `GamePack` | 游戏 | 游戏实例，挂载在课程体系下 |
| `Reward` | 奖励 | 全局奖励目录（徽章/金币/道具/卡片等） |
| `DailyChallenge` | 挑战 | 日常任务，可选关联一个奖励 |
| `RewardLink` | 奖励关联 | GamePack 与 Reward 的多对多中间关系 |

---

## 二、核心实体关系

```
CourseLevel（课程等级）
    └── CourseUnit（课程单元）
            └── GamePack（游戏包）── game_type_id ──► GameType（游戏类型）
                    │
                    └── RewardLink（关联表）──► Reward（奖励）
                                                    ▲
                                        DailyChallenge（挑战）可选引用 reward_id
```

**关系要点：**

1. **GameType → GamePack**：一对多。`GameType.code` 决定进入哪个编辑器页面。
2. **GamePack ↔ Reward**：多对多，通过 `reward-links` 接口维护，覆盖写模式。
3. **Challenge → Reward**：可选一对一（`reward_id`），同时另有独立的 `reward_xp` 字段。
4. **课程体系依赖**：GamePack 必须绑定 `course_level_id` + `course_unit_id`，课程等级/单元需提前存在。

---

## 三、主流程 A：创建并发布一个游戏

```
步骤一：【游戏类型管理】创建 GameType
        填写：名称 + code（如 lets_listen_one）+ 是否展示加载模块
              ↓
步骤二：【游戏列表】新建游戏（GamePack）
        填写：游戏名称 + 游戏类型 + 课程等级 + 课程单元
        ⚠️ 创建后 game_type 不可修改
              ↓
步骤三：【游戏列表 → 预览】进入编辑器
        系统按 GameType.code 自动分流到对应编辑器页面
        在编辑器内配置画布、素材、内容
              ↓
步骤四：构建 & 发布
        createGameBuild → 轮询构建状态 → createGamePromotion（设置发布范围）
```

**发布范围（`scope_type`）：**
`global`（全局）/ `level`（等级）/ `course`（课程）/ `class`（班级）/ `user`（用户）/ `device`（设备）

---

## 四、主流程 B：奖励目录维护 + 绑定到游戏

```
步骤一：【奖励管理】新建奖励
        ├── 徽章（badge）：无需填写数量
        ├── 金币（coin）：填写数量 ≥ 1
        ├── 道具（item）/ 解锁（unlock）：填写名称描述
        └── 卡片（card）：必须上传图标图片（icon_url 必填）
              ↓
步骤二：【游戏列表】选中游戏行 → 点击「奖励设定」
              ↓
步骤三：弹窗加载已关联奖励列表
        → 点击「关联奖励」，多选奖励目录中的奖励
        → 点击「确认」→ ⚠️ 覆盖写入（先清空旧关联，再按顺序插入新关联）
        → 可对单行点击「删除」解除单条关联
```

**⚠️ 关键注意事项：**
- 奖励关联是**覆盖写**，不是增量追加
- 确认提交时会清空该游戏包所有旧关联，再建立新关联
- 提交空列表将清空该游戏包的全部奖励关联

---

## 五、主流程 C：挑战配置

```
步骤一：【挑战管理】点击新建挑战
        填写：名称 + 挑战类型 + 目标值 + 奖励 XP + 有效日期
        可选：搜索并关联一个奖励（reward_id）
              ↓
步骤二：保存后可随时「启用 / 停用」
              ↓
步骤三：过期挑战可直接删除
```

**奖励双轨机制：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `reward_xp` | 数值 | 完成挑战获得的 XP 积分，固定值 |
| `reward_id` | UUID（可选） | 引用奖励目录中的道具类奖励 |

两者互不替代，可同时存在，分别代表 XP 奖励和道具奖励。

---

## 六、辅助流程：批量操作

| 功能 | 入口 | 说明 |
|------|------|------|
| 重复创建 | 游戏列表工具栏 | 选定等级 + 单元 + 类型，按份数批量复制创建，允许同名 |
| 批量创建五阶 | 游戏列表工具栏 | 为五阶单元批量创建 `phonics_picture` 类型游戏（当前入口已关闭） |

---

## 七、异常处理场景

| 场景 | 触发条件 | 处理方式 |
|------|---------|---------|
| 删除被用户领取的奖励 | 该奖励有 `user_reward` 领取记录 | 返回 409，需二次确认后走强制删除（同时清除领取记录） |
| 删除有游戏引用的 GameType | 存在关联的 GamePack | 系统提示关联游戏的 game_type 可能被置空 |
| 覆盖写关联时传空列表 | 确认提交时选中列表为空 | 清空该游戏包所有奖励关联 |
| 游戏包编辑时不可修改类型 | 编辑已存在的 GamePack | `game_type_id` 字段置灰禁用 |

---

## 八、关键枚举速查

### 8.1 奖励类型（`reward_type`）

| 值 | 说明 | 特殊要求 |
|----|------|---------|
| `badge` | 徽章 | 数量可不填 |
| `coin` | 金币 | 数量必填 ≥ 1 |
| `item` | 道具 | — |
| `unlock` | 解锁 | — |
| `card` | 卡片 | 必须上传图标（icon_url 必填） |

### 8.2 奖励稀有度（`rarity`）

`common`（普通）/ `rare`（稀有）/ `epic`（史诗）/ `legendary`（传说）

### 8.3 游戏包状态（`status`）

| 值 | 说明 |
|----|------|
| `draft` | 草稿，编辑中 |
| `ready` | 就绪，可发布 |
| `archived` | 已归档 |

### 8.4 挑战类型（`challenge_type`）

| 值 | 说明 |
|----|------|
| `watch_video` | 观看指定数量视频 |
| `complete_unit` | 完成指定单元 |
| `streak` | 连续学习指定天数 |

---

## 九、接口速查（管理端）

### 9.1 游戏类型

| 方法 | URL | 用途 |
|------|-----|------|
| GET | `/api/v1/admin/game-types` | 列表（支持 `q`、`is_active` 筛选） |
| POST | `/api/v1/admin/game-types` | 创建 |
| PATCH | `/api/v1/admin/game-types/{id}` | 更新 |
| DELETE | `/api/v1/admin/game-types/{id}` | 删除 |

### 9.2 游戏包

| 方法 | URL | 用途 |
|------|-----|------|
| GET | `/api/v1/admin/game-packs` | 列表（支持 `q`、`course_level_id`、`course_unit_id`、`theme`、`game_type_id` 筛选） |
| GET | `/game-packs/detail?pack_id=` | 详情（含版本和内容） |
| POST | `/game-packs/create` | 创建 |
| PATCH | `/api/v1/admin/game-packs/{id}` | 更新基础信息 |
| DELETE | `/api/v1/admin/game-packs/{id}` | 软删除 |

### 9.3 奖励

| 方法 | URL | 用途 |
|------|-----|------|
| GET | `/api/v1/admin/gamification/rewards` | 列表（支持 `name_like`、`active`、`reward_type` 筛选） |
| POST | `/api/v1/admin/gamification/rewards` | 创建 |
| PATCH | `/api/v1/admin/gamification/rewards/{id}` | 更新 |
| DELETE | `/api/v1/admin/gamification/rewards/{id}` | 删除（有引用时返回 409） |
| DELETE | `/api/v1/admin/gamification/rewards/{id}?delete_user_rewards=true&confirm=DELETE_USER_REWARDS` | 强制删除（清除领取记录） |

### 9.4 奖励关联（游戏包 ↔ 奖励）

| 方法 | URL | 用途 |
|------|-----|------|
| GET | `/api/v1/admin/gamification/reward-links?game_pack_id=` | 查询游戏包已关联奖励 |
| POST | `/api/v1/admin/gamification/reward-links` | 覆盖写入关联（body: `game_pack_id` + `reward_ids[]`） |
| POST | `/api/v1/admin/gamification/reward-links/remove` | 解除指定关联 |

### 9.5 挑战

| 方法 | URL | 用途 |
|------|-----|------|
| GET | `/api/v1/admin/gamification/challenges` | 列表（支持 `name_like`、`challenge_type`、`active` 筛选） |
| POST | `/api/v1/admin/gamification/challenges` | 创建 |
| PATCH | `/api/v1/admin/gamification/challenges/{id}` | 更新 / 启停（仅传 `is_active` 即可） |
| DELETE | `/api/v1/admin/gamification/challenges/{id}` | 删除 |

---

## 十、编辑器路由与 GameType.code 分流规则

游戏列表点击「预览」时，系统按以下逻辑分流编辑器：

1. 取 `GameType.code`（或 `name`）标准化为小写 snake_case；
2. 匹配编辑器别名表（如 `lets_listen_one`、`listening_lets_listen_one` → `LetsListenOneEditor`）；
3. 未匹配时默认进入 `CollectMainEditor`；
4. 跳转 URL 携带 `?from=gamification&preview=true&gameName=...&gameTypeName=...`。

> 完整别名对照表见 `nativesense-admin/src/views/gamification/GameList.vue` `handlePreview` 函数及 `router/index.ts` 路由定义。

---

*文档生成时间：2026-07-14*
*来源：nativesense-admin 源码梳理*

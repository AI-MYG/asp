# KET 游戏流程业务文档

> 覆盖范围：游戏获取 → 游戏进行 → 游戏上报 → 单元上报  
> 主角：App ↔ 后端（FastAPI）  
> 依据版本：2026-07

---

## 一、业务阶段说明

### 阶段 01 · 获取游戏包索引

**触发时机**：用户进入树桩页（`KetLoadingPage`）

1. `GamePackRuntimeManager.refreshGameIndex()` 调用后端
2. 过滤 `show_loading_module = true` 的包
3. 按 `sort_order` 渲染树桩，`is_completed` 显示完成态

---

### 阶段 02 · 加载游戏内容

**触发时机**：用户点击树桩，进入具体游戏页

1. `KetBaseState.initState()` → `fetchPackJsonDirect()`
2. 后端返回 `pack.json`（题目结构 + 开场 Rive 路径 + 音频资源）
3. `onPackLoaded()` 解析 → 开场动画 → `playing` 状态

---

### 阶段 03 · 游戏上报

**触发时机**：末题答完 / 视频播完 / 完成条件满足

1. `runFinishFlow()` 设 `pageStatus = reporting`
2. `GamePackCompleteReporter.reportDetailed(packId)`
3. `POST /api/v1/progress/game-pack/complete`，接收奖励列表
4. `emit GamePackCompleteEvent`（树桩刷新 + 地图积分）
5. 展示 `GameFinishCelebrationOverlay` 庆祝层

---

### 阶段 04 · 单元上报

**触发时机**：当天所有树桩 `is_completed` 均变为 `true`

1. `_checkAndReportUnitCompleteIfAllDone()` 检测
2. 防重复：刷新前未完成 → 刷新后全完成才上报
3. `CourseUnitCompleteReporter.report(courseUnitId)`
4. `POST /api/v1/progress/course-unit/complete` → `emit CourseUnitCompleteEvent`
5. 用户 pop 回树桩页时显示 Toast `"Complete Today's Tasks!"`

---

## 二、App ↔ 后端 时序图

```
App                                       后端 (FastAPI)
 │                                              │
 │  ════════ 阶段一：进入树桩页 ════════        │
 │                                              │
 │──── GET /api/v1/runtime/game-packs ─────────>│
 │     query: course_unit_id · class_id         │
 │                                              │
 │<─ ─ ─ packs[ ] ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
 │   pack_id · show_loading_module · is_completed
 │                                              │
 │  ════════ 阶段二：点击树桩，进入游戏页 ═══════│
 │                                              │
 │──── GET /api/v1/runtime/game-pack/detail ───>│
 │     query: pack_id · version · device_id     │
 │                                              │
 │<─ ─ pack.json + asset_base_url ─ ─ ─ ─ ─ ─ ─│
 │   题目结构 · 开场 Rive 路径 · 音频资源        │
 │                                              │
 │  ════════ 阶段三：游戏进行中（本地）════════  │
 │                                              │
 │──── POST /api/v1/progress/game-pack/complete>│
 │     body: { game_pack_id, class_id }         │
 │                                              │
 │<─ ─ { ok, rewards[ ], isFirstComplete } ─ ─ ─│
 │   奖励金币 / 卡片 / 积分                      │
 │                                              │
 │  ════════ 阶段四：检测所有树桩是否完成 ═══════│
 │                                              │
 │──── POST /api/v1/progress/course-unit/complete>
 │     body: { course_unit_id, class_id }       │
 │                                              │
 │<─ ─ { ok, status: "completed" } ─ ─ ─ ─ ─ ─ │
 │                                              │
 │  ════════ 阶段五：庆祝动画 + Toast 通知 ══════│
 │                                              │
```

---

## 三、API 接口汇总

| Method | Path | 参数 | 业务阶段 | 说明 |
|--------|------|------|----------|------|
| GET | `/api/v1/runtime/game-packs` | `course_unit_id, class_id` | 获取树桩列表 | 返回当前单元所有游戏包，含完成态 |
| GET | `/api/v1/runtime/game-pack/detail` | `pack_id, version, device_id` | 加载游戏内容 | 返回 pack.json 内容与资源基地址 |
| POST | `/api/v1/progress/game-pack/complete` | `{ game_pack_id, class_id }` | 游戏上报 | 记录单局完成，返回奖励信息 |
| POST | `/api/v1/progress/course-unit/complete` | `{ course_unit_id, class_id }` | 单元上报 | 所有树桩完成后上报当天单元 |
| GET | `/api/v1/progress/course-unit/complete-status` | `course_unit_id, class_id` | 查询完成态 | 查询单元满星完成状态（单元列表用） |

---

## 四、EventBus 跨页通信

| 事件名 | 发送方 | 接收方 | 作用 |
|--------|--------|--------|------|
| `GamePackCompleteEvent` | `GamePackCompleteReporter` | `KetLoadingPage` · `KetKingsleyPage` | 刷新树桩完成态 + 地图积分 |
| `CourseUnitCompleteEvent` | `CourseUnitCompleteReporter` | `KetUnitCoursesPage` | 刷新单元满星显示 |

---

## 五、关键调用链（标准路径）

```
1. 进入
   KetUnitCoursesPage._onCourseTap()
     → context.push('/ket/resource-loader?courseUnitId=...&class_id=...')
     → app.dart redirect → '/ket/loading?...'

2. 树桩数据
   KetLoadingPage.initState()
     → GamePackRuntimeManager.refreshGameIndex(courseUnitId, classId)
         → ApiService.getGameIndex()
     → setState(_stumpPacksFromIndex)

3. 进入游戏
   KetLoadingPage._onStumpTap(index)
     → GamePackRuntimeManager.setCurrentModulePacketID(pack.packId)
     → context.push('/ket/xxx?pack_id=...&courseUnitId=...&class_id=...')

4. 加载游戏数据
   KetBaseState.initState()
     → GamePackEntryUtil.fetchPackJsonDirect(packId, version)
         → ApiService.getGamePackContent(packId, version, deviceId)
     → onPackLoaded(packJson)    // 子类实现
     → _enterPlaying() / guiding

5. 游戏完成
   子类末题逻辑 → runFinishFlow()
     → GamePackCompleteReporter.reportDetailed(packId, classId)
         → ApiService.reportGamePackComplete({ game_pack_id, class_id })
     → EventBusUtil.emit(GamePackCompleteEvent)

6. 单元完成
   KetLoadingPage._onGamePackComplete()
     → _refreshStumpPacksFromCachedIndex()
     → _checkAndReportUnitCompleteIfAllDone()
         → all pack.isCompleted == true
         → CourseUnitCompleteReporter.report(courseUnitId)
             → ApiService.reportCourseUnitComplete({ course_unit_id, class_id })
         → EventBusUtil.emit(CourseUnitCompleteEvent)

7. UI 反馈
   - 游戏内：GameFinishCelebrationOverlay（星星/金币/彩带）
   - 回树桩：didPopNext → "Complete Today's Tasks!"
   - 单元列表：CourseUnitCompleteEvent → 满星刷新
   - 地图：GamePackCompleteEvent → 积分刷新
```

---

## 六、特殊游戏上报说明

### Collect It 双包链路

```
collect_it_main（主场景）
  → push /ket/collect-it?pack_id=子包&source_pack_id=主包

collect_it 完成
  → reportDetailed(子包, emitEvent: !mainAllComplete)
  → 若 main 全完成 → reportDetailed(主包, emitEvent: true)
  → 按合并 rewards 播翻卡 / 庆祝
  → 最后一关 popUntilPath("/ket/loading")
```

### 不上报的中间关

以下页面不调用 `runFinishFlow`，属于流程中间页：
- `role_play_one_choose`（选角色）
- `level_up_two`（中间关）
- `listening_word_matching`（跳转到句配，非终点）
- `role_play_one_speaking_tip` / `role_play_one_second`

---

## 七、相关文档

- [游戏完成上报对接说明.md](./游戏完成上报对接说明.md)
- [单元完成上报对接说明.md](./单元完成上报对接说明.md)
- [六阶游戏数据流说明.md](./六阶游戏数据流说明.md)
- [开场动画和音频使用文档.md](./开场动画和音频使用文档.md)

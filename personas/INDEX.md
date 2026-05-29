# ASP Persona Registry

ASP 项目的 persona 路由层。默认加载 Marvin（CTO/后端架构），其他成员通过 Observer 积累后逐步构建。

## Design Contract

每个 persona 目录遵循统一契约：

```text
personas/<name>/
├── PROFILE.md          # 认知画像、决策哲学、沟通偏好
└── axioms/
    └── INDEX.md        # 与 ASP 决策相关的公理子集
```

## Available Personas

### `marvin`

- **默认加载**: 是
- **角色**: CTO，后端/架构决策，产品技术负责人
- **负责 Surface**: backend, wecom, websites, canonical
- **入口**: `personas/marvin/PROFILE.md`
- **公理**: 15 条核心子集（从 rootgrove `rules/axioms/` 导入与 ASP 决策相关的部分）

### `hujianfei` (待构建)

- **默认加载**: 否
- **角色**: 前端 Lead，App/Admin 技术决策
- **负责 Surface**: app, admin
- **状态**: Observer 积累中，交互模式数据尚不足以形成完整画像
- **计划**: 累积 30+ 次有效交互后，从 OBSERVATIONS.md 蒸馏初始 PROFILE

## Switch Protocol

与 rootgrove persona 切换协议一致：

1. 识别 persona 触发词（如"胡剑飞会怎么处理"）
2. 读取目标 `PROFILE.md` + `axioms/INDEX.md`
3. 在该回答内采用目标 persona 的视角
4. 回答结束后回到 Marvin 默认视角

## 演化路径

1. **初始阶段**（当前）：仅 Marvin persona，公理从 rootgrove 导入核心子集
2. **积累阶段**：Observer 每日记录团队交互模式（PR 风格、issue 处理偏好、沟通习惯）
3. **蒸馏阶段**：Reflector 周频从 OBSERVATIONS 中提取 persona 相关信号
4. **形成阶段**：信号充足后（30+ 有效交互），创建新成员的 PROFILE + axioms

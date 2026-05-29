# ASP 领域词汇表

## 产品

| 术语 | 含义 |
|------|------|
| ASP | A Smart Pet，儿童英语教育 App |
| NativeSense | ASP 底层英语教育引擎品牌 |
| 初阶/触界 | ASP 课程体系层级名称 |
| COS | 腾讯云对象存储，用于媒体资源（音频、视频、图片） |
| 投屏 | App 端投屏到电视端的功能 |
| 口语评测 | AI 驱动的英语口语打分功能 |

## 架构

| 术语 | 含义 |
|------|------|
| Surface | ASP 产品的一个技术面（backend/app/admin/wecom/websites/canonical） |
| 中央 Issue | 本 repo 的需求级 issue，1 个需求对应 1 个中央 issue |
| 执行 Issue | Surface repo 的执行级 issue，1 个中央 issue 可拆分为 N 个执行 issue |
| Pipeline A | 飞书 Bitable 自动化 → 本 repo 创建中央 Issue |
| Pipeline B | 综合 Agent 读取中央 Issue → 分诊 → 各 surface repo 创建执行 Issue |
| Pipeline C | 执行完成 → 飞书通知需求方 |
| Smart PR | rootgrove `tools/smart_pr.py`，基于 `team_registry.yaml` 自动路由分支和 reviewer |

## 团队

| 角色 | 人员 | 负责 Surface |
|------|------|-------------|
| CTO / Backend Lead | Marvin (369795172) | backend, wecom, websites, canonical |
| Frontend Lead | 胡剑飞 (1401554949) | app, admin |

## 工具链

| 工具 | 用途 |
|------|------|
| OpenCode Server | 本地 Agent 执行环境（localhost:4096） |
| Observer | 日频扫描 GitHub 活动 → OBSERVATIONS.md |
| Reflector | 周频蒸馏观察 → MEMORY.md |
| Feishu Bitable | 需求池（外部入口） |

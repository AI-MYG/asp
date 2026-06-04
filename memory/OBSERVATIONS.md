# ASP Project Observations (L1)

Observer 日频写入的项目信号。按时间倒序排列，最新在前。

## 保留策略

- **Hot**（7 天内）：保留原文
- **Medium**（8-30 天）：Reflector 周频蒸馏后压缩为摘要
- **Archive**（30 天+）：移入 `archive/YYYY-MM.md`

## 信号类型

- `[ISSUE]` 新 issue 创建、分诊、关闭
- `[PR]` PR 创建、审查、合并
- `[DEPLOY]` 部署事件
- `[PATTERN]` 团队交互模式（persona 演化素材）
- `[RISK]` 风险信号（阻塞、延期、跨 surface 冲突）

---

<!-- Observer entries below this line -->

## 2026-06-03


### AI-MYG/asp-backend

Issues: [{"createdAt":"2026-06-03T12:25:00Z","labels":[],"number":76,"state":"OPEN","title":"[impl] 互动绘本按 A 重建模：并入 course_media 一层（取代平行表方案）"},{"createdAt":"2026-06-03T12:24:58Z","labels":[],"number":75,"state":"OPEN","title":"[follow-up] phonics-picture 端点补全 Swagger 文档（response_model + summary）"},{"createdAt":"2026-06-03T08:36:04Z","labels":[{"id":"LA_kwDOSpGKIM8AAAACk4d1Kg","name":"bug","description":"Something isn't working","color":"d73a4a"},{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"}],"number":72,"state":"OPEN","title":"班级课程同步：课程内媒体未级联同步到新班级"},{"createdAt":"2026-06-03T01:45:02Z","labels":[{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"}],"number":69,"state":"OPEN","title":"[debug-report] 生产环境 phonics-picture 接口 404 导致绘本编辑不可用"},{"createdAt":"2026-06-02T10:30:06Z","labels":[{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"}],"number":65,"state":"OPEN","title":"[排查协助] realtime status 返回的 wss://inputer-api.aimyg.com/realtime/ws 连接大概率 404"},{"createdAt":"2026-06-02T09:03:43Z","labels":[{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"}],"number":62,"state":"OPEN","title":"[Bug] 批量课程分配报\"已分配给其他班级\"，但找不到实际归属班级"},{"createdAt":"2026-06-02T06:19:31Z","labels":[{"id":"LA_kwDOSpGKIM8AAAACk4d1Qg","name":"enhancement","description":"New feature or request","color":"a2eeef"},{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"},{"id":"LA_kwDOSpGKIM8AAAAClimqPw","name":"approved-to-execute","description":"","color":"EDEDED"},{"id":"LA_kwDOSpGKIM8AAAAClimqhA","name":"executed","description":"","color":"EDEDED"}],"number":60,"state":"CLOSED","title":"引入 swag 自动生成 API 文档，替代手动维护的独立文档"},{"createdAt":"2026-06-02T02:53:52Z","labels":[{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"},{"id":"LA_kwDOSpGKIM8AAAAClimqPw","name":"approved-to-execute","description":"","color":"EDEDED"},{"id":"LA_kwDOSpGKIM8AAAAClimqhA","name":"executed","description":"","color":"EDEDED"}],"number":56,"state":"CLOSED","title":"[Bug] 更新课程单元接口返回成功但数据库未实际更新"},{"createdAt":"2026-06-02T02:11:28Z","labels":[{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"},{"id":"LA_kwDOSpGKIM8AAAAClimqPw","name":"approved-to-execute","description":"","color":"EDEDED"},{"id":"LA_kwDOSpGKIM8AAAAClimqhA","name":"executed","description":"","color":"EDEDED"}],"number":55,"state":"CLOSED","title":"course-unit/complete-status 同单元不同设备 completed 状态不一致"},{"createdAt":"2026-06-01T06:34:58Z","labels":[{"id":"LA_kwDOSpGKIM8AAAAClSdwkA","name":"analyzed","description":"Deep analysis completed","color":"0E8A16"},{"id":"LA_kwDOSpGKIM8AAAAClimqPw","name":"approved-to-execute","description":"","color":"EDEDED"},{"id":"LA_kwDOSpGKIM8AAAAClimqhA","name":"executed","description":"","color":"EDEDED"}],"number":42,"state":"CLOSED","title":"批量添加媒体到独立课程返回成功(200)但媒体未实际添加（全部失败仍返回201）"}]
PRs: [{"createdAt":"2026-06-03T13:44:32Z","mergedAt":null,"number":81,"state":"OPEN","title":"[ci] docs/db 经 CVM SSH 隧道生成（私网库不可直连修复）"},{"createdAt":"2026-06-03T13:34:06Z","mergedAt":null,"number":80,"state":"OPEN","title":"[Cursor] fix(asp/backend): issue #62 batch-assign and independent course list"},{"createdAt":"2026-06-03T13:19:30Z","mergedAt":"2026-06-03T13:39:44Z","number":79,"state":"MERGED","title":"[docs] 统一 ER + API 文档进 Git（tbls + 类型化 OpenAPI）"},{"createdAt":"2026-06-03T13:18:38Z","mergedAt":"2026-06-03T13:23:06Z","number":78,"state":"MERGED","title":"[Promote] [Cursor] fix(backend): sync re-anchors media schedule; selective syncs media (#7"},{"createdAt":"2026-06-03T12:37:01Z","mergedAt":"2026-06-03T13:15:26Z","number":77,"state":"MERGED","title":"[Cursor] fix(backend): sync re-anchors media schedule; selective syncs media (#72)"},{"createdAt":"2026-06-03T10:00:18Z","mergedAt":"2026-06-03T10:11:45Z","number":74,"state":"MERGED","title":"[Promote] Merge pull request #71 from AI-MYG/issue-60/backend"},{"createdAt":"2026-06-03T08:50:29Z","mergedAt":null,"number":73,"state":"CLOSED","title":"[Cursor] fix(asp/backend): issues #55 and #62 data-query and assign diagnostics"},{"createdAt":"2026-06-03T06:56:09Z","mergedAt":"2026-06-03T09:13:46Z","number":71,"state":"MERGED","title":"[ASP-60] 引入 swag 自动生成 API 文档，替代手动维护的独立文档"},{"createdAt":"2026-06-03T06:16:17Z","mergedAt":null,"number":70,"state":"OPEN","title":"[ASP-69] 互动绘本重建模：模板+班级交付，修复 phonics-picture 404"},{"createdAt":"2026-06-02T12:13:05Z","mergedAt":"2026-06-02T12:13:17Z","number":68,"state":"MERGED","title":"[Cursor] fix: add missing ApiResponse import in admin_course_management.py"}]

### AI-MYG/asp-app

Issues: [{"createdAt":"2026-05-28T23:59:55Z","labels":[],"number":10,"state":"OPEN","title":"[APP] feat: Implement centralized error presentation layer"},{"createdAt":"2026-05-28T23:59:49Z","labels":[],"number":9,"state":"OPEN","title":"[child_audio_page] 儿童端隐藏理论课音频（展示与播放）"},{"createdAt":"2026-05-28T23:59:42Z","labels":[],"number":8,"state":"OPEN","title":"[feishu] 竖版视频太小了，需要考虑看是否可以有其他的显示格式，或者内部调整视频尺寸"},{"createdAt":"2026-05-28T23:59:35Z","labels":[],"number":7,"state":"OPEN","title":"[feishu] 竖版视频太小了，需要考虑看是否可以有其他的显示格式，或者视频组调整视频比例"},{"createdAt":"2026-05-28T23:59:28Z","labels":[],"number":6,"state":"OPEN","title":"[feishu] app端：音频播放可否设置定时功能"},{"createdAt":"2026-05-28T23:59:21Z","labels":[],"number":5,"state":"OPEN","title":"[feishu] 亲子营儿童端每天的封面显示是公用的封面，不是课程配对的，亲子营是有上传对应封面的"},{"createdAt":"2026-05-28T23:59:15Z","labels":[],"number":4,"state":"OPEN","title":"[feishu] 希望熏听模式增加单曲循环和列表循环"},{"createdAt":"2026-05-28T23:59:08Z","labels":[],"number":3,"state":"OPEN","title":"[feishu] 投屏功能下手机播放的视频和电视播放的不同步，投屏后手机也一直在播放，点击停止电视会停止手机还是正常播放"},{"createdAt":"2026-05-28T23:59:01Z","labels":[],"number":2,"state":"OPEN","title":"[feishu] 儿童端音频只有随机和列表播放,没有单曲循环和列表循环,需要添加这两个功能"},{"createdAt":"2026-05-28T23:58:51Z","labels":[],"number":1,"state":"OPEN","title":"[feishu] 亲子营课程儿童端音频把理论课的音频也放进去了,理论课音频不用在儿童端上面显示"}]
PRs: []

### AI-MYG/asp-admin

Issues: [{"createdAt":"2026-06-03T08:52:34Z","labels":[],"number":11,"state":"CLOSED","title":"[Deploy] Manual Deploy 完成后飞书群通知"},{"createdAt":"2026-06-03T06:33:45Z","labels":[],"number":10,"state":"OPEN","title":"[Feature] 管理端数据库增删改查运维页面（数据问题自助修复）"},{"createdAt":"2026-06-03T06:17:23Z","labels":[],"number":8,"state":"CLOSED","title":"[Deploy] 管理端改用 GitHub Actions 双 CVM 部署"},{"createdAt":"2026-06-03T06:01:35Z","labels":[],"number":6,"state":"CLOSED","title":"[Deploy] 管理端双 CVM 一键部署脚本迁移至 asp-admin"},{"createdAt":"2026-06-02T08:49:52Z","labels":[],"number":4,"state":"OPEN","title":"[CI] Code Quality workflow 误用 Flutter 工具链，阻塞 admin PR（含 PR #3）"},{"createdAt":"2026-05-29T00:00:32Z","labels":[],"number":1,"state":"CLOSED","title":"管理端：创建课程单元时优化 unit_order 录入与插入/排序体验"}]
PRs: [{"createdAt":"2026-06-03T08:54:50Z","mergedAt":"2026-06-03T08:57:53Z","number":12,"state":"MERGED","title":"[Cursor] chore(asp/admin): issue #11"},{"createdAt":"2026-06-03T06:20:50Z","mergedAt":"2026-06-03T08:11:57Z","number":9,"state":"MERGED","title":"[Cursor] feat(deploy): GitHub Actions 双 CVM 部署流水线"},{"createdAt":"2026-06-03T06:03:42Z","mergedAt":"2026-06-03T06:13:22Z","number":7,"state":"MERGED","title":"[Deploy] 管理端双 CVM 一键部署脚本迁移至 asp-admin"},{"createdAt":"2026-06-03T03:24:49Z","mergedAt":"2026-06-03T03:54:19Z","number":5,"state":"MERGED","title":"fix(ci): replace Flutter toolchain with Node/Vue for admin repo"},{"createdAt":"2026-06-02T03:45:30Z","mergedAt":"2026-06-03T05:51:57Z","number":3,"state":"MERGED","title":"合并 dev_admin_hjf：课程管理媒体加载重构及多模块更新"},{"createdAt":"2026-06-01T10:23:08Z","mergedAt":null,"number":2,"state":"OPEN","title":"[ASP-9] [班级管理] 课程打卡总览接口（列表 + 导出）"}]

### AI-MYG/asp-websites

Issues: [{"createdAt":"2026-05-29T00:00:38Z","labels":[],"number":1,"state":"OPEN","title":"官网 muyugan.com 二维码非最新版，请更新到 1.0.23"}]
PRs: []

### AI-MYG/asp-canonical

Issues: []
PRs: [{"createdAt":"2026-06-03T13:34:09Z","mergedAt":null,"number":2,"state":"OPEN","title":"[Cursor] feat(asp/canonical): issue #62 data repair script (backup/rollback/verify)"},{"createdAt":"2026-06-03T08:56:57Z","mergedAt":null,"number":1,"state":"OPEN","title":"[Cursor] fix(asp/canonical): upgrade #55/#62 SQL scripts with STEP 0 backup + rollback + verify"}]

### AI-MYG/asp

Issues: [{"createdAt":"2026-06-03T08:28:53Z","labels":[],"number":5,"state":"OPEN","title":"[feishu] 管理端班级课程同步：课程内媒体未同步到新班级"}]
PRs: [{"createdAt":"2026-06-01T09:02:29Z","mergedAt":"2026-06-01T09:42:09Z","number":4,"state":"MERGED","title":"fix: Pipeline D parser robustness + Smart PR traceability"},{"createdAt":"2026-06-01T08:11:34Z","mergedAt":"2026-06-01T08:30:29Z","number":3,"state":"MERGED","title":"feat: Pipeline D worktree isolation + P2 review fixes"},{"createdAt":"2026-06-01T07:34:52Z","mergedAt":"2026-06-01T08:06:27Z","number":2,"state":"MERGED","title":"fix: Pipeline C reliability + D scheduling + issue type classification"},{"createdAt":"2026-06-01T04:39:58Z","mergedAt":"2026-06-01T06:16:36Z","number":1,"state":"MERGED","title":"feat: Pipeline D issue_executor.py"}]


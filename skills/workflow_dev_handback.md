# Dev Handback（Pipeline F）

给人读的 F 段说明。**完整契约 SSOT**：rootgrove `rules/skills/workflow_feishu_inbound_dev_handback.md`（2026-06-20 更新：四角色、负责人代理验收、F 验收评论模板）。

## 这一步做什么？

在 **E（AI）已通过 + PR 已 merge + dev CI/CD success** 之后：

1. sole assignee → **GitHub 负责人**（ASP：开发负责人，代飞书提需人操作 issue；personal 常与提需人同一人）
2. 发 **F 验收评论**（`## Pipeline F Dev Handback`，含飞书提需人 / GitHub 负责人）

**不再**打 `ready-for-acceptance` label。业务验收结论由负责人在 **E 人测 gate** 代录（见 `workflow_gate_review.md`）。

## 扫描与 Gate

- 扫描：`review-dev-pass`；跳过：已有 F 验收评论
- PR merged + `pipeline_f.dev_cicd` workflow success

## 脚本

`tools/feishu_inbound/issue_dev_handback.py` — Lead tick（`:20/:50`）

配置：`config.yaml` → `pipeline_f`

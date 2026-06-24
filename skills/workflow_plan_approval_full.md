# Feishu Inbound Plan Approval Workflow

## 元数据

- **类型**: Workflow（人工操作）
- **适用场景**: **Pipeline C → D 人工 Gate**——审核 `## Feishu Inbound Analysis` 后授权自动执行
- **边界**: 不改代码；只加 label 或请求重分析
- **触发**: 审核分析、approved-to-execute、授权执行、plan approval、分析审核
- **工具**: `gh issue edit`；重分析用 label `request-reanalysis`
- **创建日期**: 2026-06-24

---

## 何时需要

| difficulty | 需要本步骤？ |
|------------|-------------|
| `difficulty-trivial` | 否（D 自动执行） |
| `difficulty-standard` / `complex` | **是** — 加 `approved-to-execute` |

---

## 操作步骤

1. 读 issue 上 `## Feishu Inbound Analysis`（唯一推荐方案，无 A/B）
2. 确认 Evidence、改动文件、API/App 版本说明齐全
3. 有 `待确认（产品）` 非「无」→ **不要**批准，先在 issue 澄清
4. 通过 → 加 label；不通过 → 评论说明 + `request-reanalysis` 或手动改 Analysis

```bash
gh issue edit <N> --repo <owner/repo> --add-label "approved-to-execute"
```

重分析（自动被 Pipeline C 拾取）：

```bash
gh issue edit <N> --repo <owner/repo> --add-label "request-reanalysis"
```

---

## 角色

| 角色 | 职责 |
|------|------|
| Assignee / Tech lead | 通常由 assignee 或 surface owner 审核 |
| 飞书提需人 | 产品歧义在 issue 回复，不替代技术 Gate |

ASP：`config/surfaces.yaml` → `default_reviewers` 可参考谁审哪条 surface。

---

## 相关

- [Pipeline C Agent](./workflow_feishu_inbound_agent.md)
- [Pipeline D Executor](./workflow_feishu_inbound_executor.md)
- [Inbound Pipeline](./workflow_feishu_inbound_pipeline.md)

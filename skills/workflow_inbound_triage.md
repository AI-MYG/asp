# Feishu Inbound Triage Workflow (Pipeline B)

## 元数据

- **类型**: Workflow
- **适用场景**: 飞书入站 Issue 的**中心化分诊**（surface / scope / difficulty / assignee），无深度代码分析
- **边界**: 不调用 Feishu API；不运行 AgentClient。深度分析由 Pipeline C（`issue_scanner.py`）在各开发者本机完成
- **触发**: feishu triage、triage agent、`tools/feishu_inbound/triage_agent.py`
- **工具**: `tools/feishu_inbound/triage_agent.py`、`tools/feishu_inbound/routing.py`
- **创建日期**: 2026-05-26

---

## 输入 / 输出契约

| 方向 | 内容 |
|------|------|
| **扫描条件** | `open` + label `feishu-inbound`（宽进：只看来源标记） |
| **跳过条件** | 已有 `triaged` → 内部跳过（幂等；`--force` 覆盖） |
| **输出** | labels（surface、`scope-*`、`difficulty-*`）、`triaged`、assignee（`config.yaml` → `assignee_routing`）、comment `## Feishu Inbound Triage` |
| **不写** | `## Feishu Inbound Analysis`（属 Pipeline C） |

### 难度分级

`routing.py::classify_difficulty(scope, surfaces)` → `difficulty-trivial` / `difficulty-standard` / `difficulty-complex`

| Scope | Surface 数量 | Difficulty | 下游 routing_profile |
|-------|-------------|------------|---------------------|
| S | 1 | trivial | quick_triage |
| S | ≥2 | standard | analysis |
| M | 1 | standard | analysis |
| M | ≥2 | complex | architecture_decision |
| L | any | complex | architecture_decision |

与 Pipeline A（`feishu-inbound.yml`）仅通过 GitHub Issue 交接。

---

## 运行

```bash
./venv/bin/python tools/feishu_inbound/triage_agent.py --scan-only
./venv/bin/python tools/feishu_inbound/triage_agent.py --issue 432
./venv/bin/python tools/feishu_inbound/triage_agent.py

# 总监机（Marvin MacBook）：B + 本机 C
./periodic_jobs/ai_heartbeat/install_launchd_jobs.sh --with-feishu-inbound

# 其它 lead 本机仅 Pipeline C
# ./periodic_jobs/ai_heartbeat/install_launchd_jobs.sh --with-feishu-inbound-agent
```

日志：`logs/feishu_inbound_triage.log`

---

## 相关

- [**Feishu Inbound Pipeline（顶层编排）**](./workflow_feishu_inbound_pipeline.md) — 全流程总览 A–E
- [Feishu Inbound Pipeline 任务文档](../../docs/tasks/asp/20260519_feishu_inbound_requirement_pipeline.md)
- [Issue Scanner 深度分析](./workflow_feishu_inbound_agent.md)（Pipeline C）

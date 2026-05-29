# Triage Comment Contract

## 元数据

- **类型**: Contract
- **适用场景**: 综合 Agent 在中央 issue 上的分诊 comment 输出格式

## Comment 结构

```markdown
## Triage Result

**Surface**: {surface} (or `cross-surface: [surface1, surface2]`)
**Difficulty**: {small|medium|large}
**Assignee**: @{github_login}

### Routing Rationale

{why_this_surface_and_difficulty}

### Execution Issues Created

- {surface_repo}#{exec_issue_N}: {brief_description}

### Notes

{any_ambiguity_or_special_handling}

---
_Auto-triaged by ASP comprehensive agent._
```

## 原则

- Routing Rationale 写清匹配的关键词和上下文判断依据
- 如有歧义（多 surface 命中），在 Notes 说明拆分逻辑
- 无法判定时标注 `needs-manual-triage`，Rationale 写明缺失信息

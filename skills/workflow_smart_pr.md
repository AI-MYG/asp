# Smart PR (ASP)

## 元数据

- **类型**: Workflow
- **适用场景**: ASP 各 surface repo 的 PR 创建
- **触发**: smart pr、提交 PR、推代码提 PR

## 约定

ASP 项目的 Smart PR 使用 rootgrove 的 `tools/smart_pr.py`，该工具读取 `contexts/team_registry.yaml` 自动处理：

1. **分支命名**: `issue-{N}/{surface}`
2. **Base branch**: 从 `team_registry.yaml` 查询（backend=dev, 其他=main）
3. **Reviewer 指派**: 从 `team_registry.yaml` 的 `default_reviewers` 读取

## 使用方式

在 rootgrove 根目录执行：

```bash
./venv/bin/python tools/smart_pr.py --issue <N> --surface <surface>
```

或在对应 surface 的 worktree 目录中，Smart PR 自动检测当前 repo 并匹配 registry。

## 注意事项

- `team_registry.yaml` 是分支/reviewer 路由的 SSOT，不在本 repo 重复维护
- 跨 surface PR（涉及多个 repo）需分别提交，每个 surface 单独 PR
- PR title 格式：`[ASP-<central_issue_N>] <description>`，方便关联追踪

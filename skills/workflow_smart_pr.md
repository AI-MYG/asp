# Smart PR (ASP)

## 元数据

- **类型**: Workflow
- **适用场景**: ASP 各 surface repo 的 PR 创建
- **触发**: smart pr、提交 PR、推代码提 PR

## 约定

ASP 项目的 Smart PR 使用本 repo 的 `tools/smart_pr.py`，该工具读取 `config/surfaces.yaml` 自动处理：

1. **分支命名**: `issue-{N}/{surface}`
2. **Base branch**: 从 `config/surfaces.yaml` 查询（backend=dev, 其他=main）
3. **Reviewer 指派**: 从 `config/surfaces.yaml` 的 `default_reviewers` 读取

## 使用方式

在本 repo 根目录执行：

```bash
python tools/smart_pr.py --issue <N> --surface <surface>
```

或 dry-run 预览：

```bash
python tools/smart_pr.py --issue <N> --surface <surface> --dry-run
```

## 注意事项

- `config/surfaces.yaml` 是分支/reviewer 路由的 SSOT
- **backend surface OpenAPI gate**：`surface=backend` 且 diff 含 `backend/app/**` 时，PR 创建前用与 Pipeline D executor 相同的 `resolve_python` 链（worktree venv → surface venv → env）调用 `export_openapi.py`，并以 `git diff --exit-code docs/api/openapi.json` 校验（必要时追加 commit 并 push）；**不**依赖 PATH 裸 `python` / `make openapi`
- 跨 surface PR（涉及多个 repo）需分别提交，每个 surface 单独 PR
- PR title 格式：`[ASP-<central_issue_N>] <description>`，方便关联追踪
- **Pipeline D** 调用本脚本时**不**传 `--handback-requester`；提需人验收指派在 **Pipeline F**（见 `workflow_dev_handback.md`）

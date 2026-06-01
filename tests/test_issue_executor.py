"""Regression tests for issue_executor — branch↔PR number contract."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make tools importable — asp-infra project root
_ASP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ASP_ROOT))

from tools.feishu_inbound.issue_executor import parse_analysis_comment


# ---------------------------------------------------------------------------
# Fixtures: minimal Analysis comment bodies
# ---------------------------------------------------------------------------

def _wrap_analysis(body: str) -> list[dict[str, str]]:
    """Wrap markdown body in a comment that looks like an Analysis comment."""
    return [{"body": f"## Feishu Inbound Analysis\n\n{body}"}]


ANALYSIS_WITH_EXEC_PATH = _wrap_analysis("""\
### 1. 影响模块

- `server/service/cos_sync.go`

### 2. 推荐方案

修复 sublevel 字段缺失问题。

### 3. 执行路径

- **Surface**: backend
- **Branch**: issue-36/backend
- **Worktree**: projects/asp/backend

### 4. Scope 评估

S — 单文件修改
""")


# ---------------------------------------------------------------------------
# P2.6: branch always uses issue_number, never central_number
# ---------------------------------------------------------------------------

class TestBranchNumberContract:
    """Branch name must use the issue_number passed to parse_analysis_comment,
    not any number that might appear elsewhere (e.g. a central repo number)."""

    def test_branch_uses_issue_number(self):
        spec = parse_analysis_comment(ANALYSIS_WITH_EXEC_PATH, issue_number=36)
        assert spec is not None
        assert spec.branch == "issue-36/backend"

    def test_branch_ignores_comment_branch_hint(self):
        """Even if the Analysis comment mentions a different branch number,
        the spec must use issue_number."""
        comments = _wrap_analysis("""\
### 推荐方案

按照 issue-999/backend 的方案修复。

### 执行路径

- **Surface**: backend
- **Branch**: issue-999/backend
""")
        spec = parse_analysis_comment(comments, issue_number=42)
        assert spec is not None
        # Must use issue_number=42, not the 999 from the comment
        assert spec.branch == "issue-42/backend"

    def test_branch_format(self):
        spec = parse_analysis_comment(ANALYSIS_WITH_EXEC_PATH, issue_number=7)
        assert spec is not None
        assert spec.branch == "issue-7/backend"
        assert spec.surface == "backend"


class TestScopeParser:
    """P2.3: scope uses re.search for S/M/L, not re.match."""

    def test_scope_s(self):
        spec = parse_analysis_comment(ANALYSIS_WITH_EXEC_PATH, issue_number=1)
        assert spec is not None
        assert spec.scope == "S"

    def test_scope_default_when_missing(self):
        comments = _wrap_analysis("""\
### 推荐方案

修复问题。

### 执行路径

- **Surface**: backend
""")
        spec = parse_analysis_comment(comments, issue_number=1)
        assert spec is not None
        assert spec.scope == "S"  # default

    def test_scope_m(self):
        comments = _wrap_analysis("""\
### 1. 推荐方案

多文件修改。

### 2. 执行路径

- **Surface**: backend

### 3. Scope 评估

M — 涉及 3 个文件
""")
        spec = parse_analysis_comment(comments, issue_number=1)
        assert spec is not None
        assert spec.scope == "M"

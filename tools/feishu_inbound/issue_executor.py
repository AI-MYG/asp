#!/usr/bin/env python3
"""Pipeline D — auto-execute analyzed issues via worktree agents + Smart PR.

Scans open issues with 'analyzed' label, checks difficulty-based gate
(trivial=auto, standard/complex=need 'approved-to-execute' label),
spawns AgentClient in the target surface worktree to implement the
recommended plan from the Analysis comment, then runs Smart PR.

Scan contract:
  open + assignee=GITHUB_ASSIGNEE + 'analyzed' label + gate passed + no 'executed'/'execution-in-progress'

Gate:
  difficulty-trivial  → auto-execute (no human approval needed)
  difficulty-standard → requires 'approved-to-execute' label
  difficulty-complex  → requires 'approved-to-execute' label

Usage:
    export GITHUB_ASSIGNEE=369795172
    python tools/feishu_inbound/issue_executor.py --scan-only
    python tools/feishu_inbound/issue_executor.py --issue 441 --dry-run
    python tools/feishu_inbound/issue_executor.py --issue 441
    python tools/feishu_inbound/issue_executor.py --batch 3 --parallel
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess as sp
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_ASP_ROOT = _SCRIPT_DIR.parent.parent
_STATE_FILE = _ASP_ROOT / "state" / "issue_executor_state.json"
_STATE_LOCK = _ASP_ROOT / "state" / "issue_executor_state.lock"


# ---------------------------------------------------------------------------
# Cross-platform advisory file lock — POSIX uses fcntl.flock, Windows uses
# msvcrt.locking. The branch keeps the macOS/Linux path identical to before
# while letting the executor import and run on Windows.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    import msvcrt

    def _lock_file(lf) -> None:
        # msvcrt locks a byte range from the current position; ensure 1 byte exists.
        lf.write("lock")
        lf.flush()
        lf.seek(0)
        msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock_file(lf) -> None:
        lf.seek(0)
        msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(lf) -> None:
        fcntl.flock(lf, fcntl.LOCK_EX)

    def _unlock_file(lf) -> None:
        fcntl.flock(lf, fcntl.LOCK_UN)


def _merge_state_entry(issue_key: str, entry: dict[str, Any]) -> None:
    """Atomic read-merge-write of a single issue key under exclusive lock.

    Safe for parallel subprocesses: each only touches its own key.
    """
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_LOCK, "w") as lf:
        _lock_file(lf)
        try:
            state: dict[str, Any] = {}
            if _STATE_FILE.exists():
                with open(_STATE_FILE, encoding="utf-8") as f:
                    state = json.load(f)
            state[issue_key] = entry
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        finally:
            _unlock_file(lf)


_WORKTREE_ROOT = Path(
    os.getenv("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
).resolve()

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from routing import (  # noqa: E402
    DIFFICULTY_ROUTING_PROFILES,
    run_gh,
    surface_repos_for_operator,
)

# Surface repo selected via ASP_SURFACE_REPO so Pipeline D can execute issues on
# any surface (app/admin/...) instead of a hardcoded backend. The top-level run
# resolves the operator's repos from config/surfaces.yaml and dispatches one
# child per repo (each child sees ASP_SURFACE_REPO in its env).
REPO = os.getenv("ASP_SURFACE_REPO", "AI-MYG/asp-backend")

from inbound_agent import (  # noqa: E402
    ISSUE_TYPE_DATA,
    ISSUE_TYPE_FEATURE,
    ISSUE_TYPE_OPERATIONAL,
    _load_env,
    extract_issue_type,
    fetch_issue_comments,
    has_analysis_comment,
)
from sync_worktrees import sync_asp_worktrees, surfaces_to_sync  # noqa: E402

try:
    from tools.agent_client import AgentClient
except ImportError:
    AgentClient = None  # type: ignore[misc, assignment]

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
_ANALYZED_LABEL = "analyzed"
_APPROVED_LABEL = "approved-to-execute"
_LOCK_LABEL = "execution-in-progress"
_EXECUTED_LABEL = "executed"
_FAILED_LABEL = "execution-failed"
_REVIEW_FAILED_LABEL = "review-failed"
_MAX_PARALLEL = int(os.getenv("MAX_PARALLEL_EXECUTORS", "3"))

# AI code-review loop config (Pipeline D): a second agent checks the diff
# against the analysis before push/PR. Default on; tunable via .env.
_REVIEW_ENABLED = os.getenv("ASP_REVIEW_ENABLED", "true").strip().lower() in ("1", "true", "yes")
_REVIEW_MAX_ROUNDS = int(os.getenv("ASP_REVIEW_MAX_ROUNDS", "2"))
_REVIEW_MODEL = os.getenv("ASP_REVIEW_MODEL", "").strip()

# 跳过原因 → 中文说明（让 logs/executor_*.log 能直接看出每个 issue 为何没执行）
_SKIP_REASON_CN: dict[str, str] = {
    "skip": "已执行过（带 executed 标签），跳过",
    "skip_locked": "正在被其他进程执行（execution-in-progress 锁），跳过",
    "skip_no_analysis": "缺少分析报告（没有 analyzed 标签或 Analysis 评论），跳过",
    "skip_pending_approval": "非 trivial 难度，等待人工加 approved-to-execute 标签，跳过",
    "skip_product_ambiguity": "存在未解决的产品歧义，跳过",
    "skip_operational": "运维类 issue，无需写代码，跳过",
    "skip_data_pending_approval": "数据类 issue，等待 approved-to-execute 标签，跳过",
    "skip_has_pr": "已存在关联 PR，跳过",
    "skip_failed": "上次执行失败/审查未过（execution-failed 或 review-failed），留给人工，不自动重试",
}

# ---------------------------------------------------------------------------
# Surface worktree mapping (mirrors team_registry / config)
# ---------------------------------------------------------------------------
_SURFACE_WORKTREE: dict[str, str] = {
    "backend": "projects/asp/backend",
    "app": "projects/asp/app",
    "admin": "projects/asp/admin",
    "wecom": "projects/asp/wecom",
    "websites": "projects/asp/websites",
    "canonical": "projects/asp/canonical",
}


def _surface_local_paths() -> dict[str, str]:
    """Read surface → local_path from config/surfaces.yaml (SSOT).

    Falls back to the hardcoded _SURFACE_WORKTREE when surfaces.yaml is
    unreadable, so behavior degrades gracefully without PyYAML.
    """
    try:
        import yaml

        cfg_path = _ASP_ROOT / "config" / "surfaces.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        out: dict[str, str] = {}
        for name, cfg in (data.get("surfaces") or {}).items():
            lp = (cfg or {}).get("local_path")
            if lp:
                out[name] = str(lp)
        return out or dict(_SURFACE_WORKTREE)
    except (ImportError, OSError):
        return dict(_SURFACE_WORKTREE)


def _resolve_surface_repo(worktree_dir: str) -> Path:
    """Resolve a worktree dir to an absolute repo path.

    Absolute local_path values (e.g. a Windows path in surfaces.yaml) are used
    as-is; relative ones are joined under ASP_WORKTREE_ROOT (legacy behavior).
    """
    p = Path(worktree_dir)
    return p.resolve() if p.is_absolute() else (_WORKTREE_ROOT / p).resolve()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class ExecutionSpec:
    """Parsed execution plan from Analysis comment."""
    surface: str
    branch: str
    worktree_dir: str
    plan_text: str
    affected_files: list[str] = field(default_factory=list)
    scope: str = "S"
    has_product_ambiguity: bool = False
    analysis_full_text: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _operator() -> str:
    return (os.getenv("GITHUB_ASSIGNEE") or "369795172").strip()


def _dispatch_per_repo(repos: list[str], operator: str) -> bool:
    """Re-exec this script once per surface repo, with ASP_SURFACE_REPO pinned.

    The top-level invocation has no repo pinned (module ``REPO`` defaulted at
    import), so we re-exec one child per resolved repo with the repo in env.
    Children see ASP_SURFACE_REPO and run the real work. Returns True so the
    caller returns immediately.
    """
    passthrough: list[str] = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a == "--repo":
            skip_next = True
            continue
        if a.startswith("--repo="):
            continue
        passthrough.append(a)

    rc = 0
    for repo in repos:
        print(f"\n{'#'*60}\n# 仓库：{repo}  （操作人={operator}）\n{'#'*60}")
        env = {**os.environ, "ASP_SURFACE_REPO": repo, "GITHUB_ASSIGNEE": operator}
        proc = sp.run(
            [sys.executable, str(Path(__file__).resolve()), *passthrough],
            env=env,
        )
        rc = rc or proc.returncode
    if rc:
        sys.exit(rc)
    return True


def _issue_labels(issue: dict[str, Any]) -> list[str]:
    return [lb["name"] for lb in issue.get("labels", [])]


def _extract_central_number(issue: dict[str, Any]) -> int | None:
    """Extract central AI-MYG/asp issue number from [ASP-{N}] in title or body."""
    title = issue.get("title", "")
    m = re.search(r"\[ASP-(\d+)\]", title)
    if m:
        return int(m.group(1))
    body = issue.get("body", "")
    m = re.search(r"AI-MYG/asp#(\d+)", body)
    if m:
        return int(m.group(1))
    return None


def _get_difficulty_from_central(central_number: int) -> str | None:
    """Fetch difficulty label from central AI-MYG/asp issue."""
    try:
        raw = run_gh("issue", "view", str(central_number), "-R", "AI-MYG/asp", "--json", "labels")
        labels = [lb["name"] for lb in json.loads(raw).get("labels", [])]
        for lb in labels:
            if lb.startswith("difficulty-"):
                return lb.replace("difficulty-", "")
    except (RuntimeError, json.JSONDecodeError):
        pass
    return None


def _get_difficulty(issue: dict[str, Any], central_number: int | None = None) -> str:
    for lb in _issue_labels(issue):
        if lb.startswith("difficulty-"):
            return lb.replace("difficulty-", "")
    if central_number is not None:
        central_diff = _get_difficulty_from_central(central_number)
        if central_diff:
            return central_diff
    return "standard"


def _extract_analysis_text(comments: list[dict[str, str]]) -> str | None:
    """Return the full body of the Feishu Inbound Analysis comment, or None."""
    marker = "## Feishu Inbound Analysis"
    for c in reversed(comments):
        body = c.get("body", "")
        if marker in body:
            idx = body.index(marker)
            return body[idx:]
    return None


# ---------------------------------------------------------------------------
# Parse Analysis comment → ExecutionSpec
# ---------------------------------------------------------------------------
_SECTION_RE = re.compile(r"^###\s+(\d+)\.\s+(.+)$", re.MULTILINE)


def _extract_section_by_title(text: str, keywords: str | list[str]) -> str:
    """Extract section content by matching any keyword in the section title.

    More robust than number-based lookup: survives chapter renumbering.
    If multiple sections match, their contents are concatenated.
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    matches = list(_SECTION_RE.finditer(text))
    parts: list[str] = []
    for i, m in enumerate(matches):
        title = m.group(2)
        if any(kw in title for kw in keywords):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            parts.append(text[start:end].strip())
    return "\n\n".join(parts)


def _parse_surface_from_execution(section: str) -> str:
    """Extract surface from '执行路径' section."""
    # Look for branch pattern: issue-{N}/{surface}
    m = re.search(r"issue-\d+/(\w+)", section)
    if m:
        return m.group(1)
    # Fallback: look for worktree dir
    for surface, wdir in _SURFACE_WORKTREE.items():
        if wdir in section or surface in section.lower():
            return surface
    return "backend"


def _parse_affected_files(text: str) -> list[str]:
    """Extract file paths from Evidence and Plan sections."""
    files: list[str] = []
    # Match patterns like `path/to/file.py:123` or `path/to/file.py`
    for m in re.finditer(r"`([a-zA-Z0-9_/]+\.\w+(?::\d+)?)`", text):
        path = m.group(1).split(":")[0]
        if "/" in path:
            files.append(path)
    return list(dict.fromkeys(files))  # dedupe preserving order


def parse_analysis_comment(
    comments: list[dict[str, str]],
    issue_number: int,
) -> ExecutionSpec | None:
    """Parse the Analysis comment into an ExecutionSpec."""
    analysis = _extract_analysis_text(comments)
    if not analysis:
        return None

    plan_section = _extract_section_by_title(
        analysis, ["推荐方案", "修复方案", "建议行动", "实现方案", "解决方案"]
    )
    exec_section = _extract_section_by_title(analysis, ["执行路径"])
    scope_section = _extract_section_by_title(
        analysis, ["Scope", "scope", "范围评估"]
    )
    evidence_section = _extract_section_by_title(
        analysis, ["影响模块", "涉及文件", "关键代码", "影响范围", "Evidence"]
    )

    surface = _parse_surface_from_execution(exec_section or analysis)
    # Always use backend issue number for branch — matches Smart PR --issue
    branch = f"issue-{issue_number}/{surface}"
    # Prefer surfaces.yaml local_path (SSOT, may be absolute); fall back to the
    # hardcoded mapping when not present.
    _local_paths = _surface_local_paths()
    worktree_dir = _local_paths.get(surface) or _SURFACE_WORKTREE.get(
        surface, f"projects/asp/{surface}"
    )

    # Check product ambiguity
    ambiguity_section = ""
    m = re.search(r"###\s*待确认[（(]产品[）)](.+?)(?=###|$)", analysis, re.DOTALL)
    if m:
        ambiguity_section = m.group(1).strip()
    has_ambiguity = bool(ambiguity_section) and ambiguity_section != "无"

    # Parse scope
    scope = "S"
    scope_match = re.search(r"\b(S|M|L)\b", scope_section)
    if scope_match:
        scope = scope_match.group(1)

    affected = _parse_affected_files(
        evidence_section + "\n" + plan_section
    )

    return ExecutionSpec(
        surface=surface,
        branch=branch,
        worktree_dir=worktree_dir,
        plan_text=plan_section,
        affected_files=affected,
        scope=scope,
        has_product_ambiguity=has_ambiguity,
        analysis_full_text=analysis,
    )


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------
def needs_execution(
    issue: dict[str, Any],
    comments: list[dict[str, str]],
    force: bool,
) -> str:
    """Determine execution eligibility.

    Returns:
      'execute'               — ready to execute
      'skip'                  — already executed
      'skip_locked'           — another process is executing
      'skip_no_analysis'      — no Analysis comment found
      'skip_pending_approval' — non-trivial, awaiting approved-to-execute label
      'skip_product_ambiguity'— product ambiguity unresolved
      'skip_failed'           — previously failed/review-failed, left for a human
    """
    if force:
        return "execute"

    labels = _issue_labels(issue)

    if _EXECUTED_LABEL in labels:
        return "skip"
    # 失败后不自动重试：execution-failed / review-failed 的 issue 交给人工处理，
    # 定时任务不再反复重跑（避免浪费 AI 额度、反复刷屏）。人工修复后可手动
    # 去掉失败标签、或用 --force 重跑。
    if _FAILED_LABEL in labels or _REVIEW_FAILED_LABEL in labels:
        return "skip_failed"
    if _LOCK_LABEL in labels:
        return "skip_locked"
    if _ANALYZED_LABEL not in labels:
        return "skip_no_analysis"
    if not has_analysis_comment(comments):
        return "skip_no_analysis"

    # Read issue type directly from Pipeline C's analysis comment (SSOT)
    analysis_text = _extract_analysis_text(comments) or ""
    issue_type = extract_issue_type(analysis_text)

    if issue_type == ISSUE_TYPE_OPERATIONAL:
        return "skip_operational"
    if issue_type == ISSUE_TYPE_DATA and _APPROVED_LABEL not in labels:
        return "skip_data_pending_approval"

    number = issue.get("number")
    central_number = _extract_central_number(issue)
    if number and _has_linked_pr(number, central_number):
        return "skip_has_pr"

    difficulty = _get_difficulty(issue, central_number)
    if difficulty != "trivial" and _APPROVED_LABEL not in labels:
        return "skip_pending_approval"

    return "execute"


# ---------------------------------------------------------------------------
# Execution prompt
# ---------------------------------------------------------------------------
_EXECUTION_PROMPT = """你是 ASP {surface} 开发者 Agent。下面是一个**已审核通过**的 GitHub Issue 分析报告。你需要严格按照推荐方案实现。

## 硬性规则

1. **严格按「推荐方案」的步骤和文件列表实现**，不得自行扩展或修改范围
2. 每个改动必须有对应的代码变更
3. 实现完成后用 `git add` 添加改动的文件，然后 `git commit -m "fix: #{number} — <简述>"` 提交（commit message 必须引用 issue number）
4. 不要运行 deploy / migration / 生产操作
5. 不要修改与推荐方案无关的文件
6. 如果推荐方案中某个步骤无法实现（文件不存在、接口已变等），在 commit message 中注明差异，但尽量完成其余步骤

## Issue #{number}: {title}

{body}

## 审核通过的分析报告

{analysis}

## 工作环境

- 工作目录: `{workdir}`
- 分支: `{branch}`（已为你创建并 checkout）

直接开始实现。完成后 git add + git commit。不要输出分析过程，直接写代码。
"""


def _build_execution_prompt(
    issue: dict[str, Any],
    spec: ExecutionSpec,
    workdir: str,
) -> str:
    return _EXECUTION_PROMPT.format(
        surface=spec.surface,
        number=issue["number"],
        title=issue.get("title", ""),
        body=issue.get("body", "")[:3000],
        analysis=spec.analysis_full_text,
        workdir=workdir,
        branch=spec.branch,
    )


# ---------------------------------------------------------------------------
# AI code-review loop: a second agent checks the diff against the analysis
# before the change is pushed / a PR is opened.
# ---------------------------------------------------------------------------
_REVIEW_PROMPT = """判断下面的代码改动是否正确实现了下面的需求。只输出一个 JSON 对象，第一个字符必须是 {{，不要 markdown、不要解释。

需求（推荐方案）：
{analysis}

代码改动（git diff）：
{diff}

输出格式：{{"verdict": "符合" 或 "不符合", "summary": "一两句结论", "issues": [{{"file": "路径", "problem": "问题", "suggestion": "建议"}}]}}
符合时 issues 用 []。直接输出 JSON。
"""

_REWORK_PROMPT = """你之前对 Issue #{number} 的代码实现**未通过审查**。请根据审查意见修正代码。

## 硬性规则
1. 只修正审查指出的问题，不要扩大改动范围。
2. 修正后用 `git add` 添加改动并 `git commit -m "fix: #{number} — 按审查意见修正"` 提交。
3. 不要运行 deploy / migration / 生产操作。

## 原需求分析报告（推荐方案）
{analysis}

## 上一轮审查发现的问题
{review_issues}

## 工作环境
- 工作目录: `{workdir}`
- 分支: `{branch}`（已 checkout）

直接开始修正。完成后 git add + git commit。不要输出分析过程。
"""


def _get_diff(worktree_path: Path, base_branch: str) -> str:
    """Return the diff of the issue branch against its base (read-only)."""
    result = sp.run(
        ["git", "diff", f"origin/{base_branch}...HEAD"],
        cwd=worktree_path, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    diff = result.stdout or ""
    # Cap to keep the review prompt within a sane size.
    max_chars = int(os.getenv("ASP_REVIEW_DIFF_MAX_CHARS", "60000"))
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n...(diff truncated)"
    return diff


def _post_comment(number: int, body: str) -> None:
    """Post a comment to the issue (best-effort, never fatal)."""
    try:
        run_gh("issue", "comment", str(number), "-R", REPO, "--body", body)
    except RuntimeError as e:
        print(f"  Warning: could not post comment to #{number}: {e}")


def _parse_review_verdict(text: str) -> dict[str, Any]:
    """Parse the review agent's JSON verdict, tolerating extra prose / fences."""
    if not text:
        return {"verdict": "不符合", "summary": "审查无输出", "issues": []}
    # Strip ```json fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", cleaned).strip()
    # Try whole-string, then the first {...} block
    candidates = [cleaned]
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and "verdict" in obj:
                obj.setdefault("summary", "")
                obj.setdefault("issues", [])
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    # No parseable JSON — fall back to keyword sniffing so a model that ignored
    # the format but clearly said pass/fail still yields the right verdict.
    low = cleaned.lower()
    fail_kw = ("不符合", "fail", "rejected", "not pass", "does not", "未通过", "✗", "❌")
    pass_kw = ("符合", "pass", "approved", "lgtm", "通过", "✓", "✅")
    if any(k in cleaned or k in low for k in fail_kw):
        return {"verdict": "不符合", "summary": cleaned[:300], "issues": []}
    if any(k in cleaned or k in low for k in pass_kw):
        return {"verdict": "符合", "summary": cleaned[:300], "issues": []}
    # Truly unparseable → treat as fail so a human looks at it
    return {"verdict": "不符合", "summary": f"审查输出无法解析：{text[:200]}", "issues": []}


def _format_review_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "（无具体条目）"
    lines = []
    for i, it in enumerate(issues, 1):
        f = it.get("file", "?")
        p = it.get("problem", "")
        s = it.get("suggestion", "")
        lines.append(f"{i}. `{f}` — {p}" + (f"\n   建议：{s}" if s else ""))
    return "\n".join(lines)


def _run_review_loop(
    issue: dict[str, Any],
    spec: ExecutionSpec,
    worktree_path: Path,
    base_branch: str,
) -> bool:
    """Review the diff vs the analysis; rework on failure up to N rounds.

    Returns True if the change passes review (ready to push/PR), False if it
    fails after _REVIEW_MAX_ROUNDS rounds (issue is marked review-failed and
    left for a human). Each round's verdict is posted to the issue for an
    auditable human-visible trail.
    """
    number = issue["number"]

    for round_no in range(1, _REVIEW_MAX_ROUNDS + 1):
        diff = _get_diff(worktree_path, base_branch)
        if not diff.strip():
            print(f"  审查第 {round_no} 轮：diff 为空，无需审查")
            return True

        print(f"  审查第 {round_no}/{_REVIEW_MAX_ROUNDS} 轮（模型={_REVIEW_MODEL or 'default'}）...")
        review_prompt = _REVIEW_PROMPT.format(
            analysis=spec.analysis_full_text, diff=diff,
        )
        review = AgentClient(model=_REVIEW_MODEL or "default").run(
            review_prompt,
            intent="review",
            workdir=str(worktree_path),
            timeout_sec=min(int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600")), 900),
            model=_REVIEW_MODEL or None,
        )

        if review.status != "success":
            print(f"  审查 Agent 执行失败：{review.error} —— 视为未通过")
            verdict = {"verdict": "不符合", "summary": f"审查 Agent 执行失败：{review.error}", "issues": []}
        else:
            verdict = _parse_review_verdict(review.text)

        passed = str(verdict.get("verdict", "")).strip() == "符合"
        issues_md = _format_review_issues(verdict.get("issues", []))

        # Audit trail on the issue
        _post_comment(
            number,
            f"## 🔍 AI 代码审查（第 {round_no}/{_REVIEW_MAX_ROUNDS} 轮）\n\n"
            f"**结论**：{'✅ 符合需求' if passed else '❌ 不符合需求'}\n\n"
            f"**总体**：{verdict.get('summary', '')}\n\n"
            f"**问题清单**：\n{issues_md}\n",
        )

        if passed:
            print(f"  第 {round_no} 轮审查通过")
            return True

        if round_no < _REVIEW_MAX_ROUNDS:
            print(f"  审查未通过 —— 要求返工（第 {round_no} 轮）...")
            rework_prompt = _REWORK_PROMPT.format(
                number=number,
                analysis=spec.analysis_full_text,
                review_issues=issues_md,
                workdir=str(worktree_path),
                branch=spec.branch,
            )
            rework = AgentClient().run(
                rework_prompt,
                intent="execution",
                workdir=str(worktree_path),
                timeout_sec=min(int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600")), 1200),
            )
            if rework.status != "success":
                print(f"  返工 Agent 执行失败：{rework.error}")
                _add_label(number, _REVIEW_FAILED_LABEL, dry_run=False)
                return False
        else:
            print(f"  审查 {_REVIEW_MAX_ROUNDS} 轮后仍未通过 —— 转交人工")
            _add_label(number, _REVIEW_FAILED_LABEL, dry_run=False)
            return False

    return False


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------
def _add_label(number: int, label: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY RUN] would add label '{label}' to #{number}")
        return
    try:
        run_gh("issue", "edit", str(number), "-R", REPO, "--add-label", label)
    except RuntimeError as e:
        print(f"  Warning: could not add label '{label}' to #{number}: {e}")


def _remove_label(number: int, label: str) -> None:
    try:
        run_gh("issue", "edit", str(number), "-R", REPO, "--remove-label", label)
    except RuntimeError:
        pass


def _acquire_lock(number: int, dry_run: bool) -> bool:
    if dry_run:
        return True
    try:
        raw = run_gh("issue", "view", str(number), "-R", REPO, "--json", "labels")
        labels = [lb["name"] for lb in json.loads(raw).get("labels", [])]
        if _LOCK_LABEL in labels:
            return False
        run_gh("issue", "edit", str(number), "-R", REPO, "--add-label", _LOCK_LABEL)
        return True
    except RuntimeError:
        return False


def _release_lock(number: int) -> None:
    _remove_label(number, _LOCK_LABEL)


def _has_linked_pr(number: int, central_number: int | None = None) -> bool:
    """Check if there's an open or merged PR for this issue.

    Searches branch pattern ``issue-{N}/`` for both the backend issue number
    and the central AI-MYG/asp number (if available) to catch PRs created
    with either numbering scheme.
    """
    numbers_to_check = [number]
    if central_number and central_number != number:
        numbers_to_check.append(central_number)

    for n in numbers_to_check:
        try:
            raw = run_gh(
                "pr", "list", "-R", REPO,
                "--search", f"issue-{n}/",
                "--state", "all",
                "--json", "number,state,headRefName",
            )
            prs = json.loads(raw)
            for pr in prs:
                branch = pr.get("headRefName", "")
                if branch.startswith(f"issue-{n}/"):
                    return True
        except (RuntimeError, json.JSONDecodeError):
            pass
    return False


# ---------------------------------------------------------------------------
# Git worktree helpers — each issue gets an isolated worktree so multiple
# issues on the same surface can execute in parallel without conflicts.
# ---------------------------------------------------------------------------
_WORKTREE_DIR = _ASP_ROOT / "worktrees"


def _prefetch_surface(surface_repo: Path) -> None:
    """Fetch + prune once per surface before parallel spawning.

    Call this from the main process so subprocesses skip the fetch.
    Failures are logged but not fatal — subprocesses will build from
    whatever local state exists.
    """
    try:
        sp.run(
            ["git", "fetch", "--prune", "origin"],
            cwd=surface_repo, capture_output=True, timeout=60,
        )
    except sp.TimeoutExpired:
        print(f"  WARNING: git fetch timed out for {surface_repo}", file=sys.stderr)
    except sp.SubprocessError as exc:
        print(f"  WARNING: git fetch failed for {surface_repo}: {exc}", file=sys.stderr)


def _create_issue_worktree(
    surface_repo: Path, branch: str, base_branch: str, issue_number: int,
    *, skip_fetch: bool = False,
) -> Path | None:
    """Create a git worktree for the issue branch. Returns worktree path or None."""
    worktree_path = _WORKTREE_DIR / f"issue-{issue_number}"
    try:
        if not skip_fetch:
            sp.run(["git", "fetch", "--prune", "origin"],
                   cwd=surface_repo, check=True, capture_output=True)

        if worktree_path.exists():
            sp.run(["git", "worktree", "remove", "--force", str(worktree_path)],
                   cwd=surface_repo, capture_output=True)

        result = sp.run(
            ["git", "branch", "-r", "--list", f"origin/{branch}"],
            cwd=surface_repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if result.stdout.strip():
            sp.run(
                ["git", "worktree", "add", "-B", branch, str(worktree_path), f"origin/{branch}"],
                cwd=surface_repo, check=True, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        else:
            sp.run(
                ["git", "worktree", "add", "-b", branch, str(worktree_path), f"origin/{base_branch}"],
                cwd=surface_repo, check=True, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        return worktree_path
    except sp.CalledProcessError as e:
        print(f"  Error creating worktree for {branch}: {e.stderr if hasattr(e, 'stderr') else e}")
        return None


def _remove_issue_worktree(surface_repo: Path, worktree_path: Path) -> None:
    """Remove the temporary issue worktree."""
    try:
        sp.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=surface_repo, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
    except (sp.CalledProcessError, sp.TimeoutExpired):
        pass


def _push_branch(worktree_path: Path, branch: str) -> bool:
    """Push branch to remote. Returns True on success."""
    try:
        sp.run(
            ["git", "push", "-u", "origin", branch],
            cwd=worktree_path, check=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=120,
        )
        return True
    except (sp.CalledProcessError, sp.TimeoutExpired) as e:
        print(f"  Error pushing branch {branch}: {e}")
        return False



def _has_changes(worktree_path: Path) -> bool:
    """Check if worktree has uncommitted or staged changes."""
    result = sp.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_path, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return bool(result.stdout.strip())


def _has_commits_ahead(worktree_path: Path, base_branch: str) -> bool:
    """Check if current branch has commits ahead of base."""
    result = sp.run(
        ["git", "log", f"origin/{base_branch}..HEAD", "--oneline"],
        cwd=worktree_path, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return bool(result.stdout.strip())


# ---------------------------------------------------------------------------
# Surface base branch lookup
# ---------------------------------------------------------------------------
_SURFACE_BASE_BRANCH: dict[str, str] = {
    "backend": "dev",
    "app": "main",
    "admin": "main",
    "wecom": "main",
    "websites": "main",
    "canonical": "main",
}


# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------
def execute_issue(
    issue: dict[str, Any],
    spec: ExecutionSpec,
    *,
    token: str,
    dry_run: bool,
    skip_pr: bool,
    skip_fetch: bool = False,
) -> dict[str, Any] | None:
    """Execute the recommended plan for one issue. Returns state entry or None."""
    number = issue["number"]
    title = issue.get("title", "")

    print(f"\n{'='*60}")
    print(f"开始执行 #{number}：{title}")
    print(f"  surface={spec.surface}，分支={spec.branch}")
    print(f"  scope={spec.scope}，涉及文件 {len(spec.affected_files)} 个")
    print(f"{'='*60}")

    surface_repo = _resolve_surface_repo(spec.worktree_dir)
    if not surface_repo.exists():
        print(f"  错误：surface 仓库不存在：{surface_repo}")
        return None

    base_branch = _SURFACE_BASE_BRANCH.get(spec.surface, "main")

    if dry_run:
        wt_path = _WORKTREE_DIR / f"issue-{number}"
        print(f"  [试运行] surface 仓库：{surface_repo}")
        print(f"  [试运行] worktree：{wt_path}")
        print(f"  [试运行] 分支：{spec.branch}（基于 {base_branch}）")
        print(f"  [试运行] 涉及文件：{spec.affected_files}")
        print(f"  [试运行] 方案：\n{spec.plan_text[:500]}")
        return {"status": "dry_run"}

    # 1. 加锁，防止同一 issue 被并发执行
    print(f"  [步骤 1/8] 加执行锁（execution-in-progress）...")
    if not _acquire_lock(number, dry_run=False):
        print(f"  #{number}：已被锁定（execution-in-progress），跳过")
        return None

    issue_worktree: Path | None = None
    try:
        # 2. 为该 issue 创建独立 worktree
        print(f"  [步骤 2/8] 创建独立 worktree（分支 {spec.branch}，基于 {base_branch}）...")
        issue_worktree = _create_issue_worktree(
            surface_repo, spec.branch, base_branch, number, skip_fetch=skip_fetch,
        )
        if not issue_worktree:
            print(f"  创建 worktree 失败：{spec.branch}")
            _add_label(number, _FAILED_LABEL, dry_run=False)
            return None
        print(f"  worktree 已创建：{issue_worktree}")

        # 3. 调用 Agent 按方案写代码
        if AgentClient is None:
            print("  错误：AgentClient 无法导入")
            _add_label(number, _FAILED_LABEL, dry_run=False)
            return None

        prompt = _build_execution_prompt(issue, spec, str(issue_worktree))
        timeout = int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600"))
        if spec.scope == "S":
            timeout = min(timeout, 1200)

        print(f"  [步骤 3/8] 调用 Agent 写代码（工作目录={issue_worktree}，超时={timeout}秒）...")
        result = AgentClient().run(
            prompt,
            intent="execution",
            workdir=str(issue_worktree),
            timeout_sec=timeout,
        )

        if result.status != "success":
            print(f"  Agent 执行失败：{result.error}")
            _add_label(number, _FAILED_LABEL, dry_run=False)
            return None

        print(f"  Agent 完成：{result.executor}/{result.model or 'default'}（耗时 {result.elapsed_sec}秒）")

        # 4. 校验确实产生了代码改动
        print(f"  [步骤 4/8] 校验是否有代码改动...")
        if not _has_commits_ahead(issue_worktree, base_branch) and not _has_changes(issue_worktree):
            print(f"  警告：Agent 执行后未检测到任何代码改动")
            _add_label(number, _FAILED_LABEL, dry_run=False)
            return None

        # 4.2. AI code review loop — a second agent checks the diff against the
        # analysis before we push/PR. On failure it reworks up to N rounds; if
        # it still doesn't pass, the issue is left (review-failed) for a human.
        if _REVIEW_ENABLED:
            print(f"  [步骤 5/8] AI 代码审查（最多 {_REVIEW_MAX_ROUNDS} 轮）...")
            if not _run_review_loop(issue, spec, issue_worktree, base_branch):
                print(f"  #{number}：未通过 AI 审查 → 不推送，转交人工")
                return None
        else:
            print(f"  [步骤 5/8] AI 审查已关闭（ASP_REVIEW_ENABLED=false），跳过")

        # 4.5. 推送分支到远端（创建 PR 前必须）
        if not skip_pr:
            print(f"  [步骤 6/8] 推送分支 {spec.branch} 到远端...")
            if not _push_branch(issue_worktree, spec.branch):
                print(f"  推送失败，不标记为已执行")
                _add_label(number, _FAILED_LABEL, dry_run=False)
                return None

        # 5. Smart PR
        pr_result: dict[str, Any] = {}
        if not skip_pr:
            print(f"  [步骤 7/8] 创建 Smart PR（--issue {number} --surface {spec.surface}）...")
            smart_pr_path = _ASP_ROOT / "tools" / "smart_pr.py"
            model_tag = f"{result.executor}/{result.model}" if result.model else result.executor
            cmd = [
                sys.executable, str(smart_pr_path),
                "--issue", str(number),
                "--surface", spec.surface,
                "--issue-repo", REPO,
                "--model", model_tag,
            ]
            try:
                proc = sp.run(
                    cmd,
                    cwd=str(issue_worktree),
                    capture_output=True, text=True, timeout=120,
                    encoding="utf-8", errors="replace",
                )
                if proc.returncode == 0:
                    try:
                        pr_result = json.loads(proc.stdout)
                    except json.JSONDecodeError:
                        pr_result = {"raw_output": proc.stdout[:500]}
                    print(f"  PR 已创建：{pr_result.get('pr_url', 'unknown')}")
                else:
                    print(f"  Smart PR 失败（退出码 {proc.returncode}）：{proc.stderr[:300]}")
                    _add_label(number, _FAILED_LABEL, dry_run=False)
                    return None
            except sp.TimeoutExpired:
                print(f"  Smart PR 超时")
                _add_label(number, _FAILED_LABEL, dry_run=False)
                return None
        else:
            print(f"  跳过 PR（--skip-pr）")

        # 6. 标记成功
        print(f"  [步骤 8/8] 标记 executed 标签...")
        _add_label(number, _EXECUTED_LABEL, dry_run=False)
        print(f"  ✅ #{number}：执行完成")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "last_executed_at": now_iso,
            "title": title,
            "surface": spec.surface,
            "branch": spec.branch,
            "scope": spec.scope,
            "pr": pr_result,
            "executor": result.executor,
            "elapsed_sec": result.elapsed_sec,
        }

    finally:
        _release_lock(number)
        if issue_worktree:
            _remove_issue_worktree(surface_repo, issue_worktree)


# ---------------------------------------------------------------------------
# Issue fetching (reuse from issue_scanner pattern)
# ---------------------------------------------------------------------------
def fetch_assigned_issues(
    issue_number: int | None = None,
    *,
    operator: str,
) -> list[dict[str, Any]]:
    """Fetch open issues assigned to operator."""
    if issue_number:
        raw = run_gh(
            "issue", "view", str(issue_number),
            "-R", REPO,
            "--json",
            "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        )
        issue = json.loads(raw)
        if issue.get("state", "").upper() != "OPEN":
            raise ValueError(f"Issue #{issue_number} is not open")
        return [issue]

    raw = run_gh(
        "issue", "list",
        "-R", REPO,
        "--assignee", operator,
        "--state", "open",
        "--label", _ANALYZED_LABEL,
        "--json",
        "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        "--limit", "50",
    )
    return json.loads(raw)


def _comments_count(issue: dict[str, Any]) -> int:
    comments = issue.get("comments", 0)
    if isinstance(comments, list):
        return len(comments)
    return int(comments or 0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline D — auto-execute analyzed issues via worktree agents + Smart PR"
    )
    parser.add_argument("--issue", type=int, help="Execute one issue")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-only", action="store_true", help="List eligible issues without executing")
    parser.add_argument("--skip-pr", action="store_true", help="Implement but skip Smart PR")
    parser.add_argument("--force", action="store_true", help="Skip gate checks")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip git fetch in worktree creation (used by parallel parent)")
    parser.add_argument("--batch", type=int, default=1, help="Max issues per run (default: 1)")
    parser.add_argument("--parallel", action="store_true", help="Process multiple issues in parallel")
    parser.add_argument("--repo", help="Target a single surface repo (e.g. AI-MYG/asp-app); "
                                       "default: auto-resolve all repos you own from surfaces.yaml")
    parser.add_argument("--approve", type=int, metavar="ISSUE",
                        help="Human approval shortcut: add the 'approved-to-execute' label to "
                             "ISSUE so Pipeline D will execute it. Requires --repo.")
    args = parser.parse_args()

    _load_env()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("错误：未设置 GITHUB_TOKEN 环境变量")
        sys.exit(1)

    operator = _operator()

    # --- Human approval shortcut ----------------------------------------
    # `--approve N --repo R` just stamps the approved-to-execute label so the
    # requester can confirm a requirement with one command after reading the
    # plain-language summary. No execution happens here.
    if args.approve is not None:
        repo = args.repo or os.getenv("ASP_SURFACE_REPO")
        if not repo:
            print("错误：--approve 需要配合 --repo（例如 --repo AI-MYG/asp-app）")
            sys.exit(1)
        try:
            run_gh("issue", "edit", str(args.approve), "-R", repo,
                   "--add-label", _APPROVED_LABEL)
            print(f"✅ 已批准 {repo} 的 #{args.approve}，添加了 '{_APPROVED_LABEL}' 标签。"
                  f"Pipeline D 下次运行时会自动执行。")
        except RuntimeError as e:
            print(f"批准 #{args.approve} 出错：{e}")
            sys.exit(1)
        return

    # --- Multi-repo dispatch ---------------------------------------------
    # Top-level invocation (no ASP_SURFACE_REPO pinned) resolves the repos this
    # operator owns and re-execs one child per repo with the repo in env.
    # Children (env already set) fall through and execute against that repo.
    if not os.getenv("ASP_SURFACE_REPO"):
        repos = [args.repo] if args.repo else surface_repos_for_operator(operator)
        if _dispatch_per_repo(repos, operator):
            return

    try:
        issues = fetch_assigned_issues(args.issue, operator=operator)
    except (RuntimeError, ValueError) as e:
        print(f"错误：{e}")
        sys.exit(1)

    issues.sort(key=lambda i: i.get("createdAt", ""), reverse=True)

    # Filter candidates
    candidates: list[tuple[dict[str, Any], ExecutionSpec]] = []
    for issue in issues:
        number = issue["number"]
        comments: list[dict[str, str]] = []
        if _comments_count(issue) > 0:
            try:
                comments = fetch_issue_comments(token, number)
            except Exception:
                pass

        action = needs_execution(issue, comments, args.force)
        if action != "execute":
            reason = _SKIP_REASON_CN.get(action, action)
            print(f"  跳过 #{number}：{reason}")
            continue

        spec = parse_analysis_comment(comments, number)
        if not spec:
            print(f"  跳过 #{number}：无法解析 Analysis 分析评论")
            continue

        # 产品歧义门禁：分析报告里若有「待确认（产品）」内容，默认不自动执行。
        # 但人工加了 approved-to-execute 标签 = 已读过计划（含歧义问题）并确认放行，
        # 此时按人工意愿覆盖歧义门禁继续执行（这也是你回复「解决产品歧义」后的预期行为）。
        approved = _APPROVED_LABEL in _issue_labels(issue)
        if spec.has_product_ambiguity and not args.force and not approved:
            print(f"  跳过 #{number}：存在未解决的产品歧义，且未加 approved-to-execute 标签")
            continue
        if spec.has_product_ambiguity and approved:
            print(f"  #{number}：检测到产品歧义，但已加 approved-to-execute 标签 → 按人工确认放行")

        print(f"  纳入执行队列 #{number}：surface={spec.surface} 分支={spec.branch} scope={spec.scope}")
        candidates.append((issue, spec))

    if not args.issue and not args.scan_only:
        candidates = candidates[: args.batch]

    print(f"\n执行队列（操作人 {operator}）：{len(issues)} 个已分析，{len(candidates)} 个可执行")

    if args.scan_only:
        for issue, spec in candidates:
            cn = _extract_central_number(issue)
            d = _get_difficulty(issue, cn)
            print(f"  #{issue['number']}：surface={spec.surface} 分支={spec.branch} "
                  f"scope={spec.scope} 难度={d} 中央issue={cn or '?'} 文件数={len(spec.affected_files)}")
        return

    if not candidates:
        print("没有可执行的 issue。")
        return

    if not args.dry_run and AgentClient is None:
        print("错误：AgentClient 无法导入（tools/agent_client.py）")
        sys.exit(1)

    # Worktree 同步
    if not args.dry_run and not args.skip_sync:
        all_surfaces = {spec.surface for _, spec in candidates}
        required = surfaces_to_sync(list(all_surfaces))
        print(f"同步 surface worktree {required}（操作人={operator}）...")
        report = sync_asp_worktrees(required, operator=operator)
        if report.stale_surfaces:
            print(f"  过期的 surface：{', '.join(report.stale_surfaces)}")

    # --- 并行多 issue（子进程） ---
    if args.parallel and len(candidates) > 1 and not args.dry_run:
        # 预先 fetch 所有 surface，避免并发 git fetch 冲突
        prefetched: set[str] = set()
        for _, spec in candidates:
            surface_repo = _resolve_surface_repo(spec.worktree_dir)
            if spec.surface not in prefetched and surface_repo.exists():
                print(f"  预拉取 {spec.surface}（{surface_repo}）...")
                _prefetch_surface(surface_repo)
                prefetched.add(spec.surface)

        max_workers = min(_MAX_PARALLEL, len(candidates))
        print(f"\n--- 并行执行：{len(candidates)} 个 issue，最多 {max_workers} 个并发 ---")

        active: dict[int, sp.Popen] = {}
        pending = list(candidates)
        processed = 0

        log_dir = _ASP_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        while pending or active:
            while pending and len(active) < max_workers:
                issue, spec = pending.pop(0)
                number = issue["number"]
                cmd = [
                    sys.executable, str(Path(__file__).resolve()),
                    "--issue", str(number),
                    "--skip-sync",
                    "--skip-fetch",
                ]
                if args.force:
                    cmd.append("--force")
                if args.skip_pr:
                    cmd.append("--skip-pr")
                log_path = log_dir / f"issue_executor_{number}.log"
                log_file = open(log_path, "w", encoding="utf-8")
                print(f"  启动 #{number} 的执行子进程（日志：{log_path.name}）")
                proc = sp.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=sp.STDOUT,
                    cwd=str(_ASP_ROOT),
                    # PYTHONUTF8/PYTHONIOENCODING：强制子进程以 UTF-8 输出，
                    # 否则 Windows 默认 cp936 编码写入 utf-8 日志文件会乱码。
                    env={
                        **os.environ,
                        "GITHUB_TOKEN": token,
                        "GITHUB_ASSIGNEE": operator,
                        "PYTHONUTF8": "1",
                        "PYTHONIOENCODING": "utf-8",
                    },
                )
                active[number] = proc
                proc._log_file = log_file  # type: ignore[attr-defined]

            done_numbers: list[int] = []
            for number, proc in active.items():
                ret = proc.poll()
                if ret is not None:
                    proc._log_file.close()  # type: ignore[attr-defined]
                    if ret == 0:
                        print(f"  #{number}：执行成功（退出码 0）")
                        processed += 1
                    else:
                        print(f"  #{number}：执行失败（退出码 {ret}）")
                    done_numbers.append(number)

            for n in done_numbers:
                del active[n]

            if active:
                time.sleep(5)

        print(f"\n完成。共为 {operator} 执行了 {processed} 个 issue。")

    else:
        # --- 串行执行 ---
        processed = 0
        for issue, spec in candidates:
            entry = execute_issue(
                issue, spec,
                token=token,
                dry_run=args.dry_run,
                skip_pr=args.skip_pr,
                skip_fetch=args.skip_fetch,
            )
            if entry and entry.get("status") != "dry_run":
                # 按 key 原子合并：作为并行子进程调用时也安全
                _merge_state_entry(str(issue["number"]), entry)
                processed += 1

        print(f"\n完成。共为 {operator} 执行了 {processed} 个 issue。")


if __name__ == "__main__":
    main()

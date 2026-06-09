#!/usr/bin/env python3
"""Pipeline D — auto-execute analyzed issues via worktree agents + Smart PR.

Scans open issues with 'analyzed' label, checks difficulty-based gate
(trivial=auto, standard/complex=need 'approved-to-execute' label),
spawns AgentClient in the target surface worktree to implement the
recommended plan from the Analysis comment, then runs Smart PR.

Scan contract:
  范围见 ``config.yaml`` → ``pipeline_cd_scan``（与 Pipeline C 相同）；
  在此基础上要求 analyzed + gate + 非 executed。

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
import fcntl
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


def _merge_state_entry(issue_key: str, entry: dict[str, Any]) -> None:
    """Atomic read-merge-write of a single issue key under exclusive lock.

    Safe for parallel subprocesses: each only touches its own key.
    """
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            state: dict[str, Any] = {}
            if _STATE_FILE.exists():
                with open(_STATE_FILE, encoding="utf-8") as f:
                    state = json.load(f)
            state[issue_key] = entry
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

_WORKTREE_ROOT = Path(
    os.getenv("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
).resolve()

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from routing import (  # noqa: E402
    DIFFICULTY_ROUTING_PROFILES,
    load_config,
    run_gh,
)

from inbound_agent import (  # noqa: E402
    ISSUE_TYPE_DATA,
    ISSUE_TYPE_FEATURE,
    ISSUE_TYPE_OPERATIONAL,
    _load_env,
    extract_issue_type,
    fetch_issue_comments,
    has_analysis_comment,
)
from scan_scope import (  # noqa: E402
    describe_scan_scope,
    fetch_assigned_issues,
    issue_repo,
    issue_state_key,
    load_pipeline_cd_scan,
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
_REVIEW_CHANGES_LABEL = "review-changes-requested"
_GATE_REVIEW_MARKER = "## Pipeline E Gate Review"
_MAX_PARALLEL = int(os.getenv("MAX_PARALLEL_EXECUTORS", "3"))

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


def _extract_gate_review_feedback(comments: list[dict[str, str]]) -> str | None:
    """Latest Pipeline E gate review feedback for executor revision rounds."""
    for c in reversed(comments):
        body = c.get("body", "")
        if _GATE_REVIEW_MARKER in body:
            idx = body.index(_GATE_REVIEW_MARKER)
            return body[idx:].strip()
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
    worktree_dir = _SURFACE_WORKTREE.get(surface, f"projects/asp/{surface}")

    # Check product ambiguity
    ambiguity_section = ""
    m = re.search(r"###\s*待确认[（(]产品[）)](.+?)(?=###|$)", analysis, re.DOTALL)
    if m:
        ambiguity_section = m.group(1).strip()
    ambiguity_body = re.sub(r"\n?---.*$", "", ambiguity_section, flags=re.DOTALL).strip()
    # "无", "无。", "无。..." (with explanation after) are all "no ambiguity"
    has_ambiguity = bool(ambiguity_body) and not ambiguity_body.startswith("无")

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
      'skip'                  — already executed (handed off to Pipeline E)
      'skip_locked'           — another process is executing
      'skip_no_analysis'      — no Analysis comment found
      'skip_pending_approval' — non-trivial, awaiting approved-to-execute label
      'skip_product_ambiguity'— product ambiguity unresolved
    """
    if force:
        return "execute"

    labels = _issue_labels(issue)

    if _EXECUTED_LABEL in labels:
        return "skip"
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

    # Awaiting-review gate: the ``executed`` short-circuit above already skips
    # issues handed off to Pipeline E. When E removes ``executed`` (revision
    # round) D re-enters here and re-executes on the same branch/PR, reading the
    # ``## Pipeline E Gate Review`` feedback via _build_execution_prompt.
    central_number = _extract_central_number(issue)
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

{gate_review_section}

## 工作环境

- 工作目录: `{workdir}`
- 分支: `{branch}`（已为你创建并 checkout）

直接开始实现。完成后 git add + git commit。不要输出分析过程，直接写代码。
"""


def _build_execution_prompt(
    issue: dict[str, Any],
    spec: ExecutionSpec,
    workdir: str,
    *,
    gate_review_feedback: str | None = None,
) -> str:
    gate_section = ""
    if gate_review_feedback:
        gate_section = (
            "## Pipeline E 审查反馈（必须处理）\n\n"
            "上一轮 PR 未通过 gate review。请**优先**按下列反馈修改，"
            "不要扩大范围。\n\n"
            f"{gate_review_feedback}\n"
        )
    return _EXECUTION_PROMPT.format(
        surface=spec.surface,
        number=issue["number"],
        title=issue.get("title", ""),
        body=issue.get("body", "")[:3000],
        analysis=spec.analysis_full_text,
        gate_review_section=gate_section,
        workdir=workdir,
        branch=spec.branch,
    )


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------
def _add_label(number: int, repo: str, label: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY RUN] would add label '{label}' to {repo}#{number}")
        return
    try:
        run_gh("issue", "edit", str(number), "-R", repo, "--add-label", label)
    except RuntimeError as e:
        print(f"  Warning: could not add label '{label}' to {repo}#{number}: {e}")


def _remove_label(number: int, repo: str, label: str) -> None:
    try:
        run_gh("issue", "edit", str(number), "-R", repo, "--remove-label", label)
    except RuntimeError:
        pass


def _acquire_lock(number: int, repo: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    for attempt in range(3):
        try:
            raw = run_gh("issue", "view", str(number), "-R", repo, "--json", "labels")
            labels = [lb["name"] for lb in json.loads(raw).get("labels", [])]
            if _LOCK_LABEL in labels:
                return False
            run_gh("issue", "edit", str(number), "-R", repo, "--add-label", _LOCK_LABEL)
            return True
        except RuntimeError as e:
            if attempt < 2:
                print(f"  Lock attempt {attempt + 1} failed ({e}), retrying...")
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  Failed to acquire lock after 3 attempts: {e}")
                return False


def _release_lock(number: int, repo: str) -> None:
    _remove_label(number, repo, _LOCK_LABEL)


def _find_linked_pr(
    repo: str,
    number: int,
    central_number: int | None = None,
    *,
    state: str = "open",
) -> dict[str, Any] | None:
    """Find PR for issue branch ``issue-{N}/…`` (open by default).

    Lists PRs and filters by head ref prefix. ``gh pr list --search`` does NOT
    match branch names reliably (slashes aren't indexed as search terms), so we
    must enumerate and prefix-match ``headRefName`` ourselves.
    """
    numbers_to_check = [number]
    if central_number and central_number != number:
        numbers_to_check.append(central_number)

    try:
        raw = run_gh(
            "pr", "list", "-R", repo,
            "--state", state,
            "--limit", "100",
            "--json", "number,state,headRefName,url,baseRefName",
        )
        prs = json.loads(raw)
    except (RuntimeError, json.JSONDecodeError):
        return None

    for n in numbers_to_check:
        prefix = f"issue-{n}/"
        for pr in prs:
            if pr.get("headRefName", "").startswith(prefix):
                return pr
    return None


def _has_linked_pr(repo: str, number: int, central_number: int | None = None) -> bool:
    return _find_linked_pr(repo, number, central_number) is not None


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

        # If the surface repo's own HEAD is on the target branch, switch it back
        # to base_branch first — git disallows two worktrees on the same branch.
        head_ref = sp.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=surface_repo, capture_output=True, text=True,
        )
        if head_ref.returncode == 0 and head_ref.stdout.strip() == branch:
            sp.run(["git", "checkout", base_branch],
                   cwd=surface_repo, capture_output=True, text=True)

        result = sp.run(
            ["git", "branch", "-r", "--list", f"origin/{branch}"],
            cwd=surface_repo, capture_output=True, text=True,
        )

        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if result.stdout.strip():
            # Remote branch exists: reset local branch to remote state
            sp.run(
                ["git", "worktree", "add", "-B", branch, str(worktree_path), f"origin/{branch}"],
                cwd=surface_repo, check=True, capture_output=True, text=True,
            )
        else:
            # No remote branch: create (or force-reset) local branch from base
            sp.run(
                ["git", "worktree", "add", "-B", branch, str(worktree_path), f"origin/{base_branch}"],
                cwd=surface_repo, check=True, capture_output=True, text=True,
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
        )
    except (sp.CalledProcessError, sp.TimeoutExpired):
        pass


def _push_branch(worktree_path: Path, branch: str) -> bool:
    """Push branch to remote. Returns True on success."""
    try:
        sp.run(
            ["git", "push", "-u", "origin", branch],
            cwd=worktree_path, check=True, capture_output=True, text=True,
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
    )
    return bool(result.stdout.strip())


def _has_commits_ahead(worktree_path: Path, base_branch: str) -> bool:
    """Check if current branch has commits ahead of base."""
    result = sp.run(
        ["git", "log", f"origin/{base_branch}..HEAD", "--oneline"],
        cwd=worktree_path, capture_output=True, text=True,
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
def _surface_github_repo(surface: str) -> str:
    try:
        import yaml

        cfg = yaml.safe_load((_ASP_ROOT / "config" / "surfaces.yaml").read_text(encoding="utf-8"))
        return (cfg.get("surfaces") or {}).get(surface, {}).get("repo", "")
    except Exception:
        return ""


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
    gh_repo = issue_repo(issue)
    title = issue.get("title", "")

    print(f"\n{'='*60}")
    print(f"Executing {gh_repo}#{number}: {title}")
    print(f"  Surface: {spec.surface}, Branch: {spec.branch}")
    print(f"  Scope: {spec.scope}, Files: {len(spec.affected_files)}")
    print(f"{'='*60}")

    surface_repo = _WORKTREE_ROOT / spec.worktree_dir
    if not surface_repo.exists():
        print(f"  Error: surface repo does not exist: {surface_repo}")
        return None

    base_branch = _SURFACE_BASE_BRANCH.get(spec.surface, "main")

    if dry_run:
        wt_path = _WORKTREE_DIR / f"issue-{number}"
        print(f"  [DRY RUN] Surface repo: {surface_repo}")
        print(f"  [DRY RUN] Worktree: {wt_path}")
        print(f"  [DRY RUN] Branch: {spec.branch} from {base_branch}")
        print(f"  [DRY RUN] Affected files: {spec.affected_files}")
        print(f"  [DRY RUN] Plan:\n{spec.plan_text[:500]}")
        return {"status": "dry_run"}

    # 1. Acquire lock
    if not _acquire_lock(number, gh_repo, dry_run=False):
        print(f"  {gh_repo}#{number}: locked (execution-in-progress), skipping")
        return None

    issue_worktree: Path | None = None
    try:
        # 2. Create isolated worktree for this issue
        issue_worktree = _create_issue_worktree(
            surface_repo, spec.branch, base_branch, number, skip_fetch=skip_fetch,
        )
        if not issue_worktree:
            print(f"  Failed to create worktree for {spec.branch}")
            _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
            return None
        print(f"  Worktree created: {issue_worktree}")

        # 3. Run agent
        if AgentClient is None:
            print("  Error: AgentClient not importable")
            _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
            return None

        comments: list[dict[str, str]] = []
        try:
            comments = fetch_issue_comments(token, number, repo=gh_repo)
        except Exception:
            pass
        gate_feedback = _extract_gate_review_feedback(comments)
        prompt = _build_execution_prompt(
            issue, spec, str(issue_worktree), gate_review_feedback=gate_feedback,
        )
        timeout = int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600"))
        if spec.scope == "S":
            timeout = min(timeout, 1200)

        print(f"  Running AgentClient (workdir={issue_worktree}, timeout={timeout}s)...")
        result = AgentClient().run(
            prompt,
            intent="execution",
            workdir=str(issue_worktree),
            timeout_sec=timeout,
        )

        if result.status != "success":
            print(f"  Agent execution failed: {result.error}")
            _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
            return None

        print(f"  Agent completed: {result.executor}/{result.model or 'default'} ({result.elapsed_sec}s)")

        # 4. Verify changes exist
        if not _has_commits_ahead(issue_worktree, base_branch) and not _has_changes(issue_worktree):
            print(f"  Warning: no changes detected after agent execution")
            _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
            return None

        # 4.5. Push branch to remote (required before PR creation)
        if not skip_pr:
            print(f"  Pushing branch {spec.branch} to remote...")
            if not _push_branch(issue_worktree, spec.branch):
                print(f"  Push failed, not marking as executed")
                _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
                return None

        # 5. Smart PR (skip create if open PR already exists — revision round)
        pr_result: dict[str, Any] = {}
        central_number = _extract_central_number(issue)
        pr_repo = _surface_github_repo(spec.surface)
        existing_pr = _find_linked_pr(pr_repo, number, central_number) if pr_repo else None
        if not skip_pr:
            if existing_pr:
                pr_result = {
                    "pr_url": existing_pr.get("url", ""),
                    "number": existing_pr.get("number"),
                    "reused": True,
                }
                print(f"  Open PR exists: {pr_result.get('pr_url')} (skip Smart PR create)")
            else:
                print(f"  Running Smart PR (--issue {number} --surface {spec.surface})...")
                smart_pr_path = _ASP_ROOT / "tools" / "smart_pr.py"
                model_tag = f"{result.executor}/{result.model}" if result.model else result.executor
                cmd = [
                    sys.executable, str(smart_pr_path),
                    "--issue", str(number),
                    "--surface", spec.surface,
                    "--issue-repo", gh_repo,
                    "--model", model_tag,
                    "--handback-requester",
                ]
                try:
                    proc = sp.run(
                        cmd,
                        cwd=str(issue_worktree),
                        capture_output=True, text=True, timeout=120,
                    )
                    if proc.returncode == 0:
                        try:
                            pr_result = json.loads(proc.stdout)
                        except json.JSONDecodeError:
                            pr_result = {"raw_output": proc.stdout[:500]}
                        print(f"  PR created: {pr_result.get('pr_url', 'unknown')}")
                    else:
                        print(f"  Smart PR failed (exit {proc.returncode}): {proc.stderr[:300]}")
                        _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
                        return None
                except sp.TimeoutExpired:
                    print(f"  Smart PR timed out")
                    _add_label(number, gh_repo, _FAILED_LABEL, dry_run=False)
                    return None
            if _REVIEW_CHANGES_LABEL in _issue_labels(issue):
                _remove_label(number, gh_repo, _REVIEW_CHANGES_LABEL)
        else:
            print(f"  Skipping PR (--skip-pr)")

        # 6. Mark success
        _add_label(number, gh_repo, _EXECUTED_LABEL, dry_run=False)
        print(f"  {gh_repo}#{number}: execution complete")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "last_executed_at": now_iso,
            "title": title,
            "repo": gh_repo,
            "surface": spec.surface,
            "branch": spec.branch,
            "scope": spec.scope,
            "pr": pr_result,
            "executor": result.executor,
            "elapsed_sec": result.elapsed_sec,
        }

    finally:
        _release_lock(number, gh_repo)
        if issue_worktree:
            _remove_issue_worktree(surface_repo, issue_worktree)


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
    parser.add_argument(
        "--repo",
        help="owner/repo (required if issue number exists in multiple repos)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-only", action="store_true", help="List eligible issues without executing")
    parser.add_argument("--skip-pr", action="store_true", help="Implement but skip Smart PR")
    parser.add_argument("--force", action="store_true", help="Skip gate checks")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip git fetch in worktree creation (used by parallel parent)")
    parser.add_argument("--batch", type=int, default=1, help="Max issues per run (default: 1)")
    parser.add_argument("--parallel", action="store_true", help="Process multiple issues in parallel")
    args = parser.parse_args()

    _load_env()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    operator = _operator()
    config = load_config()
    scan_cfg = load_pipeline_cd_scan(config)

    try:
        issues = fetch_assigned_issues(
            operator,
            config=config,
            scan=scan_cfg,
            issue_number=args.issue,
            repo=args.repo,
        )
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    issues.sort(key=lambda i: i.get("createdAt", ""), reverse=True)

    # Filter candidates
    candidates: list[tuple[dict[str, Any], ExecutionSpec]] = []
    for issue in issues:
        number = issue["number"]
        repo = issue_repo(issue)
        comments: list[dict[str, str]] = []
        if _comments_count(issue) > 0:
            try:
                comments = fetch_issue_comments(token, number, repo=repo)
            except Exception:
                pass

        action = needs_execution(issue, comments, args.force)
        if action != "execute":
            reason = action.replace("skip_", "").replace("skip", "already executed")
            print(f"  {repo}#{number}: {reason}")
            continue

        spec = parse_analysis_comment(comments, number)
        if not spec:
            print(f"  {repo}#{number}: could not parse Analysis comment")
            continue

        if spec.has_product_ambiguity and not args.force:
            print(f"  {repo}#{number}: product ambiguity unresolved, skipping")
            continue

        candidates.append((issue, spec))

    if not args.issue and not args.scan_only:
        candidates = candidates[: args.batch]

    print(
        f"\nExecutor queue ({operator}, scope={describe_scan_scope(scan_cfg, operator)}): "
        f"{len(issues)} open assigned, {len(candidates)} ready to execute"
    )

    if args.scan_only:
        for issue, spec in candidates:
            cn = _extract_central_number(issue)
            d = _get_difficulty(issue, cn)
            repo = issue_repo(issue)
            print(
                f"  {repo}#{issue['number']}: surface={spec.surface} branch={spec.branch} "
                f"scope={spec.scope} difficulty={d} central={cn or '?'} files={len(spec.affected_files)}"
            )
        return

    if not candidates:
        print("Nothing to execute.")
        return

    if not args.dry_run and AgentClient is None:
        print("Error: AgentClient not importable (tools/agent_client.py)")
        sys.exit(1)

    # Worktree sync
    if not args.dry_run and not args.skip_sync:
        all_surfaces = {spec.surface for _, spec in candidates}
        required = surfaces_to_sync(list(all_surfaces))
        print(f"Syncing surfaces {required} (operator={operator})...")
        report = sync_asp_worktrees(required, operator=operator)
        if report.stale_surfaces:
            print(f"  Stale surfaces: {', '.join(report.stale_surfaces)}")

    # --- Parallel multi-issue via subprocess ---
    if args.parallel and len(candidates) > 1 and not args.dry_run:
        # Pre-fetch all surfaces once to avoid concurrent git fetch conflicts
        prefetched: set[str] = set()
        for _, spec in candidates:
            surface_repo = _WORKTREE_ROOT / spec.worktree_dir
            if spec.surface not in prefetched and surface_repo.exists():
                print(f"  Pre-fetching {spec.surface} ({surface_repo})...")
                _prefetch_surface(surface_repo)
                prefetched.add(spec.surface)

        max_workers = min(_MAX_PARALLEL, len(candidates))
        print(f"\n--- Parallel: {len(candidates)} issue(s), max {max_workers} concurrent ---")

        active: dict[str, sp.Popen] = {}
        pending = list(candidates)
        processed = 0

        log_dir = _ASP_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        while pending or active:
            while pending and len(active) < max_workers:
                issue, spec = pending.pop(0)
                number = issue["number"]
                repo = issue_repo(issue)
                job_key = issue_state_key(issue)
                cmd = [
                    sys.executable, str(Path(__file__).resolve()),
                    "--issue", str(number),
                    "--repo", repo,
                    "--skip-sync",
                    "--skip-fetch",
                ]
                if args.force:
                    cmd.append("--force")
                if args.skip_pr:
                    cmd.append("--skip-pr")
                log_slug = repo.replace("/", "_")
                log_path = log_dir / f"issue_executor_{log_slug}_{number}.log"
                log_file = open(log_path, "w")
                print(f"  Spawning executor for {repo}#{number} (log: {log_path.name})")
                proc = sp.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=sp.STDOUT,
                    cwd=str(_ASP_ROOT),
                    env={**os.environ, "GITHUB_TOKEN": token, "GITHUB_ASSIGNEE": operator},
                )
                active[job_key] = proc
                proc._log_file = log_file  # type: ignore[attr-defined]

            done_keys: list[str] = []
            for job_key, proc in active.items():
                ret = proc.poll()
                if ret is not None:
                    proc._log_file.close()  # type: ignore[attr-defined]
                    if ret == 0:
                        print(f"  {job_key}: executed (exit 0)")
                        processed += 1
                    else:
                        print(f"  {job_key}: failed (exit {ret})")
                    done_keys.append(job_key)

            for k in done_keys:
                del active[k]

            if active:
                time.sleep(5)

        print(f"\nDone. Executed {processed} issue(s) for {operator}.")

    else:
        # --- Sequential ---
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
                # Atomic per-key merge: safe even when called as parallel subprocess
                _merge_state_entry(issue_state_key(issue), entry)
                processed += 1

        print(f"\nDone. Executed {processed} issue(s) for {operator}.")


if __name__ == "__main__":
    main()

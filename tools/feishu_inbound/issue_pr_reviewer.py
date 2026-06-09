#!/usr/bin/env python3
"""Pipeline E — gate review of executed surface PRs (review only, never edits code).

Scans surface execution issues that have the ``executed`` label and an open
linked PR but no ``review-dev-pass`` yet, delegates gate review to an **agent
platform different from Pipeline D** (e.g. Cursor Composer 2.5 when D used
OpenCode), and applies a state machine:

  PASS    → add ``review-dev-pass`` (keep ``executed``); never merge; Feishu DM.
  CHANGES → remove ``executed`` + add ``review-changes-requested``; post a
            ``## Pipeline E Gate Review`` comment that Pipeline D reads on its
            next revision round; Feishu DM with the business-language reason.

Hard boundaries (see AI-MYG/asp#11):
  - Pipeline E NEVER edits code, commits, pushes, runs the executor, or merges.
  - Only surface execution issues are processed (never the central issue).
  - dev → prod deploy is always a human action.

Usage:
    export GITHUB_ASSIGNEE=369795172
    python tools/feishu_inbound/issue_pr_reviewer.py --scan-only
    python tools/feishu_inbound/issue_pr_reviewer.py --issue 41 --repo AI-MYG/asp-backend --dry-run
    python tools/feishu_inbound/issue_pr_reviewer.py --batch 3 --parallel
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess as sp
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_ASP_ROOT = _SCRIPT_DIR.parent.parent
_STATE_FILE = _ASP_ROOT / "state" / "issue_pr_reviewer_state.json"
_STATE_LOCK = _ASP_ROOT / "state" / "issue_pr_reviewer_state.lock"

_WORKTREE_ROOT = Path(
    os.getenv("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
).resolve()

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_ASP_ROOT / "scripts"))
sys.path.insert(0, str(_SCRIPT_DIR))

from routing import run_gh, load_config  # noqa: E402
from scan_scope import (  # noqa: E402
    describe_scan_scope,
    fetch_assigned_issues,
    issue_repo,
    issue_state_key,
    load_pipeline_cd_scan,
)
from inbound_agent import (  # noqa: E402
    _load_env,
    fetch_issue_comments,
)
from issue_executor import (  # noqa: E402
    _extract_central_number,
    _find_linked_pr,
)

try:
    import completion_notify as _notify
except ImportError:
    _notify = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Labels & markers
# ---------------------------------------------------------------------------
_EXECUTED_LABEL = "executed"
_REVIEW_PASS_LABEL = "review-dev-pass"
_REVIEW_CHANGES_LABEL = "review-changes-requested"
_REVIEW_LOCK_LABEL = "review-in-progress"
_LOCK_STALE_SECONDS = int(os.getenv("PIPELINE_E_LOCK_STALE_SECONDS", "3600"))
_GATE_REVIEW_MARKER = "## Pipeline E Gate Review"
_APPROVED_MARKER = "## Pipeline E Review — Approved (dev gate)"
_ANALYSIS_MARKER = "## Feishu Inbound Analysis"

_MAX_PARALLEL = int(os.getenv("MAX_PARALLEL_REVIEWERS", "3"))

# Review route config — SSOT: config.yaml → pipeline_e; env overrides.
# Mutual exclusion = different *executor platform* than Pipeline D (not OpenCode model swap).
_PIPELINE_E_CFG: dict[str, Any] = (load_config() or {}).get("pipeline_e") or {}

_GateReviewClient: type[Any] | None = None


@dataclass(frozen=True)
class ReviewRoute:
    executor: str
    model: str


_CURSOR_EXECUTORS = frozenset({"cursor_sdk", "cursor_agent"})


def _same_agent_platform(a: str, b: str) -> bool:
    """Treat cursor_sdk and cursor_agent as one platform for mutual exclusion."""
    al, bl = a.lower(), b.lower()
    if al in _CURSOR_EXECUTORS and bl in _CURSOR_EXECUTORS:
        return True
    return al == bl


def _load_gate_review_client() -> type[Any] | None:
    """Rootgrove multi-executor AgentClient (Cursor / Claude / OpenCode).

    asp-infra has its own ``tools/`` package (OpenCode-only). Prefer rootgrove on
    ``sys.path`` and drop a cached asp-infra ``tools`` module before importing.
    """
    global _GateReviewClient
    if _GateReviewClient is not None:
        return _GateReviewClient

    root_str = str(_WORKTREE_ROOT)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)

    # issue_executor / inbound_agent import asp-infra ``tools.agent_client`` first,
    # which pins ``tools`` to asp-infra (no agent_clients). Drop before rootgrove import.
    for key in list(sys.modules):
        if key == "tools" or key.startswith("tools."):
            del sys.modules[key]

    try:
        from tools.agent_clients.client import AgentClient as cls

        _GateReviewClient = cls
        return cls
    except Exception as exc:
        if os.getenv("PIPELINE_E_DEBUG_IMPORT"):
            print(f"  DEBUG: gate review AgentClient import failed: {exc}", file=sys.stderr)
        return None


def _default_review_route() -> ReviewRoute:
    return ReviewRoute(
        os.getenv("PIPELINE_E_REVIEW_EXECUTOR")
        or _PIPELINE_E_CFG.get("review_executor")
        or "cursor_sdk",
        os.getenv("PIPELINE_E_REVIEW_MODEL")
        or _PIPELINE_E_CFG.get("review_model")
        or "composer-2.5",
    )


def _review_route_pool() -> list[ReviewRoute]:
    pool_cfg = _PIPELINE_E_CFG.get("review_route_pool")
    if pool_cfg:
        return [
            ReviewRoute(str(r["executor"]), str(r["model"]))
            for r in pool_cfg
            if r.get("executor") and r.get("model")
        ]
    preferred = _default_review_route()
    fallbacks = [
        ReviewRoute("cursor_agent", "composer-2.5"),
        ReviewRoute("claude_code", "claude-sonnet-4"),
        ReviewRoute("opencode", "glm-5.1"),
    ]
    out = [preferred]
    for route in fallbacks:
        if route not in out:
            out.append(route)
    return out

# Label specs created on demand (gh add-label fails for non-existent labels).
_REVIEW_LABEL_SPECS: dict[str, tuple[str, str]] = {
    _REVIEW_PASS_LABEL: ("0E8A16", "Pipeline E gate passed — ready for human dev merge"),
    _REVIEW_CHANGES_LABEL: ("D93F0B", "Pipeline E gate requested changes — back to Pipeline D"),
    _REVIEW_LOCK_LABEL: ("FBCA04", "Pipeline E is reviewing this issue (mutex lock)"),
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _operator() -> str:
    return (os.getenv("GITHUB_ASSIGNEE") or "369795172").strip()


def _issue_labels(issue: dict[str, Any]) -> list[str]:
    return [lb["name"] for lb in issue.get("labels", [])]


def _comments_count(issue: dict[str, Any]) -> int:
    comments = issue.get("comments", 0)
    if isinstance(comments, list):
        return len(comments)
    return int(comments or 0)


def _ensure_label(repo: str, name: str) -> None:
    """Idempotently create a label so add-label never fails."""
    color, desc = _REVIEW_LABEL_SPECS.get(name, ("EDEDED", ""))
    try:
        run_gh(
            "label", "create", name, "-R", repo,
            "--color", color, "--description", desc, "--force",
            check=False,
        )
    except RuntimeError:
        pass


def _add_label(number: int, repo: str, label: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY RUN] would add label '{label}' to {repo}#{number}")
        return
    _ensure_label(repo, label)
    try:
        run_gh("issue", "edit", str(number), "-R", repo, "--add-label", label)
    except RuntimeError as e:
        print(f"  Warning: could not add label '{label}' to {repo}#{number}: {e}")


def _remove_label(number: int, repo: str, label: str, dry_run: bool = False) -> None:
    if dry_run:
        print(f"  [DRY RUN] would remove label '{label}' from {repo}#{number}")
        return
    try:
        run_gh("issue", "edit", str(number), "-R", repo, "--remove-label", label)
    except RuntimeError:
        pass


def _lock_age_seconds(number: int, repo: str) -> float | None:
    """Seconds since ``review-in-progress`` was last added, via GitHub timeline API."""
    try:
        raw = run_gh(
            "api", f"repos/{repo}/issues/{number}/timeline",
            "--paginate", "--jq",
            '[.[] | select(.event=="labeled" and .label.name=="review-in-progress")] | last | .created_at',
        )
        ts = raw.strip().strip('"')
        if not ts or ts == "null":
            return None
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds()
    except (RuntimeError, ValueError):
        return None


def _auto_release_stale_lock(number: int, repo: str) -> bool:
    """If the lock label has been held longer than the threshold, force-release it.

    Returns True if the lock was stale and released (caller may proceed).
    """
    age = _lock_age_seconds(number, repo)
    if age is not None and age > _LOCK_STALE_SECONDS:
        print(
            f"  {repo}#{number}: stale lock detected ({age / 60:.0f}min > "
            f"{_LOCK_STALE_SECONDS // 60}min threshold), auto-releasing"
        )
        _release_lock(number, repo)
        return True
    return False


def _acquire_lock(number: int, repo: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    try:
        raw = run_gh("issue", "view", str(number), "-R", repo, "--json", "labels")
        labels = [lb["name"] for lb in json.loads(raw).get("labels", [])]
        if _REVIEW_LOCK_LABEL in labels:
            if not _auto_release_stale_lock(number, repo):
                return False
        _ensure_label(repo, _REVIEW_LOCK_LABEL)
        run_gh("issue", "edit", str(number), "-R", repo, "--add-label", _REVIEW_LOCK_LABEL)
        return True
    except RuntimeError:
        return False


def _release_lock(number: int, repo: str) -> None:
    _remove_label(number, repo, _REVIEW_LOCK_LABEL)


def _post_comment(number: int, repo: str, body: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY RUN] comment on {repo}#{number}:\n{body[:600]}")
        return
    try:
        run_gh("issue", "comment", str(number), "-R", repo, "--body", body)
    except RuntimeError as e:
        print(f"  Warning: could not comment on {repo}#{number}: {e}")


# ---------------------------------------------------------------------------
# Surface resolution
# ---------------------------------------------------------------------------
def _load_surfaces() -> dict[str, Any]:
    try:
        import yaml

        cfg = yaml.safe_load((_ASP_ROOT / "config" / "surfaces.yaml").read_text(encoding="utf-8"))
        return cfg.get("surfaces") or {}
    except Exception:
        return {}


def _surface_for(repo: str, pr_branch: str) -> str:
    """Resolve surface from PR branch (issue-N/<surface>) or repo→surface map."""
    m = re.search(r"issue-\d+/(\w+)", pr_branch or "")
    if m:
        return m.group(1)
    for name, spec in _load_surfaces().items():
        if (spec or {}).get("repo") == repo:
            return name
    return "backend"


def _surface_worktree(surface: str) -> Path:
    spec = _load_surfaces().get(surface) or {}
    local_path = spec.get("local_path", f"projects/asp/{surface}")
    return _WORKTREE_ROOT / local_path


# ---------------------------------------------------------------------------
# PR / analysis context
# ---------------------------------------------------------------------------
def _extract_analysis_text(comments: list[dict[str, str]]) -> str | None:
    for c in reversed(comments):
        body = c.get("body", "")
        if _ANALYSIS_MARKER in body:
            return body[body.index(_ANALYSIS_MARKER):]
    return None


def _implemented_by_from_pr(pr_body: str) -> tuple[str | None, str | None]:
    """Parse '**Implemented by**: `opencode/glm-5.1`' → ('opencode', 'glm-5.1')."""
    m = re.search(r"\*\*Implemented by\*\*:\s*`([^`]+)`", pr_body or "")
    if not m:
        return None, None
    tag = m.group(1).strip()
    if "/" in tag:
        exe, model = tag.split("/", 1)
        return exe.strip().lower(), model.strip()
    return None, tag.strip()


def _executor_model_from_pr(pr_body: str) -> str | None:
    """Parse PR body Implemented-by tag → executor model only."""
    _, model = _implemented_by_from_pr(pr_body)
    return model


def pick_review_route(
    executor_name: str | None,
    executor_model: str | None,
) -> ReviewRoute:
    """Pick review agent route on a different *platform* than Pipeline D."""
    routes = pick_review_routes(executor_name, executor_model)
    return routes[0] if routes else _default_review_route()


def pick_review_routes(
    executor_name: str | None,
    executor_model: str | None,
) -> list[ReviewRoute]:
    """Return ranked list of candidate review routes excluding Pipeline D's platform."""
    exe = (executor_name or "").lower()
    candidates = [
        route for route in _review_route_pool()
        if not (exe and _same_agent_platform(route.executor.lower(), exe))
    ]
    return candidates if candidates else [_default_review_route()]


def pick_review_model(executor_model: str | None) -> str:
    """Legacy helper — returns model leg of :func:`pick_review_route`."""
    return pick_review_route(None, executor_model).model


def _fetch_pr_diff(repo: str, pr_number: int, max_chars: int = 60000) -> str:
    try:
        diff = run_gh("pr", "diff", str(pr_number), "-R", repo)
    except RuntimeError as e:
        return f"(could not fetch diff: {e})"
    if len(diff) > max_chars:
        return diff[:max_chars] + "\n...(diff truncated)"
    return diff


# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------
def needs_review(issue: dict[str, Any], pr: dict[str, Any] | None, force: bool) -> str:
    """Classify review eligibility.

    Returns:
      'review'            — executed + open PR, not yet passed
      'skip_no_executed'  — no ``executed`` label (not handed off by D)
      'skip_passed'       — already ``review-dev-pass``
      'skip_locked'       — another reviewer is processing
      'skip_no_pr'        — executed but no open linked PR
    """
    labels = _issue_labels(issue)
    if _REVIEW_LOCK_LABEL in labels:
        return "skip_locked"
    if not force:
        if _EXECUTED_LABEL not in labels:
            return "skip_no_executed"
        if _REVIEW_PASS_LABEL in labels:
            return "skip_passed"
    if pr is None:
        return "skip_no_pr"
    return "review"


_VERDICT_PASS = "pass"
_VERDICT_CHANGES = "changes"
_VERDICT_UNKNOWN = "unknown"


def parse_verdict(text: str) -> str:
    """Parse the gate verdict from the review agent output.

    Looks for a '结论' / 'verdict' line; accepts 通过/pass/approve and
    打回/changes/reject. Returns 'pass' | 'changes' | 'unknown'.
    """
    if not text:
        return _VERDICT_UNKNOWN
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("*->#").strip()
        if not line:
            continue
        if line.lower().startswith(("结论", "verdict", "判定", "决策")):
            payload = re.sub(
                r"(?i)^(结论|verdict|判定|决策)\s*[:：]?\s*", "", line
            ).lower()
            if any(k in payload for k in ("通过", "pass", "approve")):
                return _VERDICT_PASS
            if any(k in payload for k in ("打回", "changes", "reject", "request")):
                return _VERDICT_CHANGES
    # Fallback: scan whole text for an explicit marker token.
    low = text.lower()
    if "verdict: pass" in low or "结论: 通过" in text or "结论：通过" in text:
        return _VERDICT_PASS
    if "verdict: changes" in low or "结论: 打回" in text or "结论：打回" in text:
        return _VERDICT_CHANGES
    return _VERDICT_UNKNOWN


# ---------------------------------------------------------------------------
# Review prompt
# ---------------------------------------------------------------------------
_REVIEW_PROMPT = """你是 ASP Pipeline E 的 **Gate Reviewer**。你只做 code review，**绝对禁止**修改任何文件、运行 git commit/push、运行 executor 或 merge。你的唯一产出是下方规定格式的 Markdown 文本。

## 审查目标

判断该 PR 是否可以进入 **dev 分支合并门**（dev gate）。dev → prod 永远由人决定，不在你的判断范围。

## 审查维度（逐项给结论）

1. **正确性**：逻辑是否正确，边界条件，是否引入 regression
2. **方案符合度**：是否严格实现了下方「推荐方案」，无擅自扩大/缩小范围
3. **设计**：抽象层次、是否遵循既有模式
4. **安全**：注入/XSS/硬编码凭证等常见问题
5. **可维护性**：dead code、命名、过度工程
6. **测试/验证**：变更是否有测试覆盖或 PR 说明了验证方式

## 判定标准

- **通过**：无 blocking 问题（non-blocking 可后续 PR 处理）
- **打回**：存在 blocking 问题（正确性缺陷、安全漏洞、会导致 regression、明显偏离推荐方案）

## 待审 PR

- **Repo**: {repo}
- **PR**: #{pr_number} {pr_url}
- **分支**: {pr_branch} → {base_branch}
- **执行 Agent（你必须委托给不同 Agent 平台审查）**: {executor_agent}

### 关联 Issue #{number}: {title}

{body}

### 已审核通过的分析报告（推荐方案 = 实现契约）

{analysis}

### PR Diff

```diff
{diff}
```

## 输出格式（严格遵守，第一行必须是结论）

结论: 通过
（或）结论: 打回

**摘要**: 一句话业务语言说明这条需求的实现是否达标（给非技术读者看）。

**审查维度**:
- 正确性: …
- 方案符合度: …
- 设计: …
- 安全: …
- 可维护性: …
- 测试/验证: …

**Blocking 问题**（仅打回时填写，必须具体到文件:行号）:
1. `path/to/file.ext:line` — 问题描述 + 期望修法

直接输出上述 Markdown，不要前言后语，不要输出思考过程。
"""


def build_review_prompt(
    issue: dict[str, Any],
    pr: dict[str, Any],
    analysis_text: str,
    diff: str,
    executor_name: str | None,
    executor_model: str | None,
) -> str:
    if executor_name and executor_model:
        executor_agent = f"{executor_name}/{executor_model}"
    elif executor_model:
        executor_agent = executor_model
    else:
        executor_agent = "unknown"
    return _REVIEW_PROMPT.format(
        repo=issue_repo(issue),
        pr_number=pr.get("number", "?"),
        pr_url=pr.get("url", ""),
        pr_branch=pr.get("headRefName", ""),
        base_branch=pr.get("baseRefName", ""),
        executor_agent=executor_agent,
        number=issue.get("number"),
        title=issue.get("title", ""),
        body=(issue.get("body", "") or "")[:2500],
        analysis=analysis_text or "(无分析报告)",
        diff=diff,
    )


# ---------------------------------------------------------------------------
# Feishu notification (business language; DM with webhook fallback)
# ---------------------------------------------------------------------------
def _feishu_open_id() -> str:
    open_id = (
        os.getenv("PIPELINE_E_FEISHU_OPEN_ID")
        or os.getenv("FEISHU_DM_OPEN_ID")
        or ""
    ).strip()
    if open_id:
        return open_id
    # Optional fallback: rootgrove team_registry (marvin)
    try:
        import yaml

        registry = _WORKTREE_ROOT / "contexts" / "team_registry.yaml"
        if registry.exists():
            data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
            member = (data.get("team_members") or {}).get("marvin") or {}
            return (member.get("feishu_open_id") or "").strip()
    except Exception:
        pass
    return ""


def notify_feishu(text: str, *, dry_run: bool) -> str:
    """Send a Feishu DM to the pipeline owner; fall back to webhook group.

    Returns a short status string. Never raises — notification failure must
    not break the gate state machine.
    """
    if dry_run:
        print(f"  [DRY RUN] Feishu notify:\n{text}\n")
        return "dry_run"
    if _notify is None:
        print("  Feishu: completion_notify not importable, skipped")
        return "skipped_no_module"

    open_id = _feishu_open_id()
    app_id = os.getenv("FEISHU_APP_ID") or os.getenv("IC_FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET") or os.getenv("IC_FEISHU_APP_SECRET", "")
    try:
        if open_id and app_id and app_secret:
            _notify.send_feishu_dm(app_id, app_secret, open_id, text, dry_run=False)
            return "dm"
        webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
        if webhook:
            _notify.send_webhook_message(webhook, text, dry_run=False)
            return "webhook"
    except Exception as e:  # noqa: BLE001 — notification must never break gate
        print(f"  Feishu notify failed: {e}")
        return "error"
    print("  Feishu: no open_id and no webhook configured, skipped")
    return "skipped_no_target"


def _business_message(
    issue: dict[str, Any],
    pr: dict[str, Any],
    verdict: str,
    summary: str,
) -> str:
    repo = issue_repo(issue)
    title = issue.get("title", "")
    central = _extract_central_number(issue)
    central_line = f"\n中央需求：AI-MYG/asp#{central}" if central else ""
    pr_url = pr.get("url", "")
    if verdict == _VERDICT_PASS:
        head = "【ASP Pipeline E】✅ 通过 dev 门"
        nxt = "下一步：等你人工合入 dev（E 不自动合并）。"
    elif verdict == _VERDICT_CHANGES:
        head = "【ASP Pipeline E】⛔ 打回"
        nxt = "下一步：已退回 Pipeline D 按 Gate Review 反馈自动修订。"
    else:
        head = "【ASP Pipeline E】⚠️ 审查异常"
        nxt = "下一步：需要人工查看（标签未变更）。"
    return (
        f"{head}\n"
        f"需求：{title}\n"
        f"Repo：{repo}#{issue.get('number')}{central_line}\n"
        f"PR：{pr_url}\n"
        f"结论：{summary or verdict}\n"
        f"{nxt}"
    )


# ---------------------------------------------------------------------------
# Core: review one issue
# ---------------------------------------------------------------------------
def _summary_from_review(text: str) -> str:
    m = re.search(r"\*\*摘要\*\*[:：]\s*(.+)", text or "")
    if m:
        return m.group(1).strip()[:200]
    return ""


def review_issue(
    issue: dict[str, Any],
    *,
    token: str,
    dry_run: bool,
    skip_notify: bool,
    pr: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    number = issue["number"]
    repo = issue_repo(issue)
    title = issue.get("title", "")
    central = _extract_central_number(issue)

    print(f"\n{'='*60}")
    print(f"Gate review {repo}#{number}: {title}")

    if pr is None:
        pr = _find_linked_pr(repo, number, central)
    if pr is None:
        print(f"  {repo}#{number}: no open linked PR, skipping")
        return None
    print(f"  PR #{pr.get('number')} ({pr.get('headRefName')} → {pr.get('baseRefName')})")

    if dry_run:
        pr_body = pr.get("body", "")
        if not pr_body:
            try:
                raw = run_gh("pr", "view", str(pr["number"]), "-R", repo, "--json", "body")
                pr_body = json.loads(raw).get("body", "")
            except (RuntimeError, json.JSONDecodeError, KeyError):
                pr_body = ""
        exe_name, exe_model = _implemented_by_from_pr(pr_body)
        route = pick_review_route(exe_name, exe_model)
        client_ok = _load_gate_review_client() is not None
        print(
            f"  [DRY RUN] would gate-review PR {pr.get('url')}\n"
            f"  [DRY RUN] Pipeline D: {exe_name or '?'}/{exe_model or '?'} "
            f"→ delegate: {route.executor}/{route.model} "
            f"(AgentClient={'ok' if client_ok else 'MISSING'})"
        )
        return {
            "status": "dry_run",
            "pr": pr.get("number"),
            "review_route": {"executor": route.executor, "model": route.model},
        }

    if not _acquire_lock(number, repo, dry_run=False):
        print(f"  {repo}#{number}: locked (review-in-progress), skipping")
        return None

    try:
        comments = fetch_issue_comments(token, number, repo=repo)
        analysis_text = _extract_analysis_text(comments) or ""

        pr_body = pr.get("body", "")
        if not pr_body:
            try:
                raw = run_gh("pr", "view", str(pr["number"]), "-R", repo, "--json", "body")
                pr_body = json.loads(raw).get("body", "")
            except (RuntimeError, json.JSONDecodeError, KeyError):
                pr_body = ""
        executor_name, executor_model = _implemented_by_from_pr(pr_body)
        review_routes = pick_review_routes(executor_name, executor_model)
        review_route = review_routes[0]
        if executor_name and _same_agent_platform(
            review_route.executor.lower(), executor_name.lower()
        ):
            print(
                f"  WARNING: review platform == Pipeline D platform ({review_route.executor}); proceeding"
            )
        print(
            f"  Pipeline D: {executor_name or '?'}/{executor_model or '?'} "
            f"→ gate review delegate: {review_route.executor}/{review_route.model}"
            f" ({len(review_routes)} route(s) in pool)"
        )

        diff = _fetch_pr_diff(repo, pr["number"])
        surface = _surface_for(repo, pr.get("headRefName", ""))
        workdir = _surface_worktree(surface)
        workdir_str = str(workdir) if workdir.exists() else str(_ASP_ROOT)

        GateReviewClient = _load_gate_review_client()
        if GateReviewClient is None:
            print("  Error: rootgrove tools.agent_clients not importable (ASP_WORKTREE_ROOT?)")
            return None

        prompt = build_review_prompt(
            issue, pr, analysis_text, diff, executor_name, executor_model,
        )
        timeout = int(os.getenv("AGENT_CLIENT_TIMEOUT", "1800"))

        # Try each route in the pool until one succeeds
        result = None
        for i, route in enumerate(review_routes):
            review_route = route
            print(
                f"  Running gate review (delegate {route.executor}/{route.model}, "
                f"workdir={workdir_str})..."
            )
            result = GateReviewClient().run(
                prompt,
                intent="review",
                workdir=workdir_str,
                timeout_sec=timeout,
                executor=route.executor,
                model=route.model,
            )
            if result.status == "success" and result.text:
                break
            print(f"  Route failed: {result.error}")
            if i < len(review_routes) - 1:
                print(f"  Falling back to next route: {review_routes[i + 1].executor}/{review_routes[i + 1].model}")

        if result is None or (result.status != "success" or not result.text):
            verdict = _VERDICT_UNKNOWN
            review_text = (result.text or "") if result else ""
            if result:
                print(f"  All review routes exhausted. Last error: {result.error}")
        else:
            review_text = result.text
            verdict = parse_verdict(review_text)
        summary = _summary_from_review(review_text)
        review_agent = f"{result.executor}/{result.model or review_route.model}"
        d_agent = (
            f"{executor_name}/{executor_model}"
            if executor_name and executor_model
            else (executor_model or "unknown")
        )
        print(f"  Verdict: {verdict} (review_agent={review_agent})")

        if verdict == _VERDICT_PASS:
            _add_label(number, repo, _REVIEW_PASS_LABEL, dry_run=False)
            _remove_label(number, repo, _REVIEW_CHANGES_LABEL)
            _post_comment(
                number, repo,
                f"{_APPROVED_MARKER}\n\n"
                f"_审查 Agent `{review_agent}` ≠ 执行 Agent `{d_agent}`。_\n\n"
                f"{review_text}\n\n---\n_Pipeline E gate passed. 不自动合并；等待人工合入 dev。_",
                dry_run=False,
            )
        elif verdict == _VERDICT_CHANGES:
            # Add `review-changes-requested` BEFORE removing `executed` so the
            # issue always carries at least one meaningful label. D's scan runs
            # only ~10 min after E's; removing `executed` first would open a
            # TOCTOU window where D sees neither label and could skip the issue.
            _add_label(number, repo, _REVIEW_CHANGES_LABEL, dry_run=False)
            _remove_label(number, repo, _EXECUTED_LABEL)
            _post_comment(
                number, repo,
                f"{_GATE_REVIEW_MARKER}\n\n"
                f"_审查 Agent `{review_agent}` ≠ 执行 Agent `{d_agent}`。_\n\n"
                f"{review_text}\n\n---\n_Pipeline E 打回：已移除 `executed`，Pipeline D 下一轮将按上述反馈修订。_",
                dry_run=False,
            )
        else:
            # Unknown / agent failure: do NOT change labels. Notify for human.
            _post_comment(
                number, repo,
                f"{_GATE_REVIEW_MARKER} — ⚠️ 审查未产出明确结论\n\n"
                f"审查 Agent `{review_agent}` 输出无法解析为通过/打回，标签未变更，需人工查看。\n\n"
                f"<details><summary>原始输出</summary>\n\n{review_text[:3000]}\n\n</details>",
                dry_run=False,
            )

        if not skip_notify:
            msg = _business_message(issue, pr, verdict, summary)
            ch = notify_feishu(msg, dry_run=False)
            print(f"  Feishu: {ch}")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "last_reviewed_at": now_iso,
            "title": title,
            "repo": repo,
            "pr": pr.get("number"),
            "pr_url": pr.get("url", ""),
            "verdict": verdict,
            "review_executor": review_route.executor,
            "review_model": review_route.model,
            "executor_name": executor_name,
            "executor_model": executor_model,
            "central": central,
        }
    finally:
        _release_lock(number, repo)


def _merge_state_entry(issue_key: str, entry: dict[str, Any]) -> None:
    import fcntl

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _collect_candidates(
    issues: list[dict[str, Any]],
    token: str,
    force: bool,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for issue in issues:
        number = issue["number"]
        repo = issue_repo(issue)
        labels = _issue_labels(issue)
        # Cheap pre-filter before hitting the PR API.
        if not force and (_EXECUTED_LABEL not in labels or _REVIEW_PASS_LABEL in labels):
            continue
        if _REVIEW_LOCK_LABEL in labels:
            if not _auto_release_stale_lock(number, repo):
                print(f"  {repo}#{number}: locked (review-in-progress)")
                continue
        central = _extract_central_number(issue)
        pr = _find_linked_pr(repo, number, central)
        action = needs_review(issue, pr, force)
        if action != "review":
            print(f"  {repo}#{number}: {action.replace('skip_', '')}")
            continue
        candidates.append((issue, pr))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline E — gate review of executed surface PRs (review only)"
    )
    parser.add_argument("--issue", type=int, help="Review one issue")
    parser.add_argument("--repo", help="owner/repo (with --issue when ambiguous)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-only", action="store_true", help="List eligible issues only")
    parser.add_argument("--force", action="store_true", help="Skip gate checks (re-review)")
    parser.add_argument("--skip-notify", action="store_true", help="Do not send Feishu notification")
    parser.add_argument("--batch", type=int, default=1, help="Max issues per run (default: 1)")
    parser.add_argument("--parallel", action="store_true", help="Review multiple issues in parallel")
    args = parser.parse_args()

    _load_env()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    operator = _operator()
    scan_cfg = load_pipeline_cd_scan()

    try:
        issues = fetch_assigned_issues(
            operator, scan=scan_cfg, issue_number=args.issue, repo=args.repo,
        )
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    issues.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    candidates = _collect_candidates(issues, token, args.force)

    if not args.issue and not args.scan_only:
        candidates = candidates[: args.batch]

    print(
        f"\nReviewer queue ({operator}, scope={describe_scan_scope(scan_cfg, operator)}): "
        f"{len(issues)} open assigned, {len(candidates)} ready to gate-review"
    )

    if args.scan_only:
        for issue, pr in candidates:
            print(
                f"  {issue_repo(issue)}#{issue['number']}: PR #{pr.get('number')} "
                f"({pr.get('headRefName')} → {pr.get('baseRefName')})"
            )
        return

    if not candidates:
        print("Nothing to review.")
        return

    if not args.dry_run and _load_gate_review_client() is None:
        print(
            "Error: rootgrove tools.agent_clients not importable "
            f"(ASP_WORKTREE_ROOT={_WORKTREE_ROOT})"
        )
        sys.exit(1)

    # --- Parallel via subprocess (per repo#issue; lock is per-issue label) ---
    if args.parallel and len(candidates) > 1 and not args.dry_run:
        max_workers = min(_MAX_PARALLEL, len(candidates))
        print(f"\n--- Parallel: {len(candidates)} issue(s), max {max_workers} concurrent ---")
        active: dict[str, sp.Popen] = {}
        pending = list(candidates)
        processed = 0
        log_dir = _ASP_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        while pending or active:
            while pending and len(active) < max_workers:
                issue, _pr = pending.pop(0)
                number = issue["number"]
                repo = issue_repo(issue)
                job_key = issue_state_key(issue)
                cmd = [
                    sys.executable, str(Path(__file__).resolve()),
                    "--issue", str(number), "--repo", repo,
                ]
                if args.force:
                    cmd.append("--force")
                if args.skip_notify:
                    cmd.append("--skip-notify")
                log_path = log_dir / f"issue_pr_reviewer_{repo.replace('/', '_')}_{number}.log"
                log_file = open(log_path, "w")
                print(f"  Spawning reviewer for {repo}#{number} (log: {log_path.name})")
                proc = sp.Popen(
                    cmd, stdout=log_file, stderr=sp.STDOUT, cwd=str(_ASP_ROOT),
                    env={**os.environ, "GITHUB_TOKEN": token, "GITHUB_ASSIGNEE": operator},
                )
                active[job_key] = proc
                proc._log_file = log_file  # type: ignore[attr-defined]

            done_keys: list[str] = []
            for job_key, proc in active.items():
                ret = proc.poll()
                if ret is not None:
                    proc._log_file.close()  # type: ignore[attr-defined]
                    print(f"  {job_key}: {'reviewed' if ret == 0 else f'failed (exit {ret})'}")
                    processed += 1 if ret == 0 else 0
                    done_keys.append(job_key)
            for k in done_keys:
                del active[k]
            if active:
                time.sleep(5)

        print(f"\nDone. Reviewed {processed} issue(s) for {operator}.")
    else:
        # --- Sequential ---
        processed = 0
        for issue, pr in candidates:
            entry = review_issue(
                issue, token=token, dry_run=args.dry_run, skip_notify=args.skip_notify, pr=pr,
            )
            if entry and entry.get("status") != "dry_run":
                _merge_state_entry(issue_state_key(issue), entry)
                processed += 1
        print(f"\nDone. Reviewed {processed} issue(s) for {operator}.")


if __name__ == "__main__":
    main()

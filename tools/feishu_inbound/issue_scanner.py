#!/usr/bin/env python3
"""Pipeline C — unified per-developer issue scanner with difficulty-aware routing.

Scan contract (宽进): open + assignee contains GITHUB_ASSIGNEE — that's it.
Skip logic (幂等): already has `## Feishu Inbound Analysis` comment → skip (--force overrides).
Labels are soft references: difficulty-* / triaged are used if present, degraded gracefully if absent.

Difficulty-aware routing (labels set by triage_agent.py):
  - difficulty-trivial  → routing_profile=quick_triage
  - difficulty-standard → routing_profile=analysis  (default when no label)
  - difficulty-complex  → routing_profile=architecture_decision, sequential only

Multi-issue parallel: --parallel spawns independent subprocess per issue.

Usage:
    export GITHUB_ASSIGNEE=369795172
    python tools/feishu_inbound/issue_scanner.py
    python tools/feishu_inbound/issue_scanner.py --issue 441
    python tools/feishu_inbound/issue_scanner.py --scan-only
    python tools/feishu_inbound/issue_scanner.py --batch 5 --parallel
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess as sp
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_ASP_ROOT = _SCRIPT_DIR.parent.parent
_STATE_FILE = _ASP_ROOT / "state" / "issue_scanner_state.json"
_ANALYSIS_MARKER = "## Feishu Inbound Analysis"

# Worktree root for code analysis (the workspace containing projects/asp/*)
_WORKTREE_ROOT = Path(
    os.getenv("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
).resolve()


def _surface_workdir(surface: str) -> Path:
    """Resolve the local code dir for a surface from surfaces.yaml.

    Lets the analysis agent read that surface's real code. Honors absolute
    local_path values; relative ones join under ASP_WORKTREE_ROOT. Falls back
    to a guaranteed-existing dir (the ASP repo root) when surfaces.yaml or the
    surface's local code dir is unavailable — the analysis agent only needs a
    valid cwd to start in, and an invalid cwd makes claude crash on Windows with
    WinError 267 (目录名称无效).
    """
    try:
        import yaml

        with open(_ASP_ROOT / "config" / "surfaces.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        lp = ((data.get("surfaces") or {}).get(surface) or {}).get("local_path")
        if lp:
            # expanduser so "~/..." in ASP_WORKTREE_ROOT / local_path resolves to
            # a real home path instead of a literal "~" dir that doesn't exist.
            p = Path(str(lp)).expanduser()
            resolved = p if p.is_absolute() else (_WORKTREE_ROOT.expanduser() / p)
            if resolved.exists():
                return resolved.resolve()
    except (ImportError, OSError):
        pass
    # 兜底：ASP 仓库根一定存在，保证 claude 有个有效的 cwd（避免 WinError 267）。
    return _ASP_ROOT

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from routing import (  # noqa: E402
    DIFFICULTY_ROUTING_PROFILES,
    REPO as _CENTRAL_REPO,
    format_routing_section,
    load_config,
    preflight_routing,
    run_gh,
    surface_repos_for_operator,
)

# issue_scanner operates on surface repos (execution issues), not the central repo.
# Repo is selected via ASP_SURFACE_REPO so a developer can scan all the surfaces
# they own (app/admin/...) instead of a hardcoded backend. The top-level run
# resolves the operator's repos from config/surfaces.yaml and dispatches one
# child process per repo (each child sees ASP_SURFACE_REPO in its env).
REPO = os.getenv("ASP_SURFACE_REPO", "AI-MYG/asp-backend")
from sync_worktrees import sync_asp_worktrees, surfaces_to_sync  # noqa: E402

try:
    from tools.agent_client import AgentClient
except ImportError:
    AgentClient = None  # type: ignore[misc, assignment]

from inbound_agent import (  # noqa: E402
    _build_inbound_prompt,
    _comments_count,
    _FINALIZE_PROMPT,
    _is_valid_analysis,
    _load_env,
    extract_issue_type,
    fetch_issue_comments,
    format_comments_for_prompt,
    has_analysis_comment,
    post_analysis_comment,
)


def _operator() -> str:
    return (os.getenv("GITHUB_ASSIGNEE") or "369795172").strip()


def _dispatch_per_repo(repos: list[str], operator: str) -> bool:
    """Re-exec this script once per surface repo, with ASP_SURFACE_REPO pinned.

    The top-level invocation has no repo pinned (module ``REPO`` defaulted at
    import), so we re-exec one child per resolved repo with the repo in env.
    Children see ASP_SURFACE_REPO and run the real work. Returns True so the
    caller returns immediately.
    """
    # Pass through original CLI args, dropping --repo / --repo=... (now pinned via env)
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
        print(f"\n{'#'*60}\n# Repo: {repo}  (operator={operator})\n{'#'*60}")
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


def _get_difficulty(issue: dict[str, Any]) -> str:
    """Read difficulty tier from issue labels (set by triage_agent)."""
    labels = _issue_labels(issue)
    for lb in labels:
        if lb.startswith("difficulty-"):
            return lb.replace("difficulty-", "")
    return "standard"


def fetch_assigned_issues(
    issue_number: int | None = None,
    *,
    operator: str,
) -> list[dict[str, Any]]:
    """Scan all open issues assigned to operator (宽进: no label requirement)."""
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
        "--json",
        "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        "--limit", "50",
    )
    issues = json.loads(raw)
    raw_all = run_gh(
        "issue", "list",
        "-R", REPO,
        "--state", "open",
        "--json",
        "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        "--limit", "100",
    )
    all_issues = json.loads(raw_all)
    seen = {i["number"] for i in issues}
    for i in all_issues:
        if i["number"] not in seen and operator in {a.get("login", "") for a in i.get("assignees", [])}:
            issues.append(i)
    return issues


def _should_process(issue: dict[str, Any], state: dict[str, Any], force: bool) -> bool:
    if force:
        return True
    key = str(issue["number"])
    entry = state.get(key)
    if not entry or not entry.get("last_analyzed_at"):
        return True
    issue_updated = issue.get("updatedAt") or issue.get("updated_at", "")
    last_known = entry.get("last_issue_updated_at", "")
    if issue_updated and last_known and issue_updated <= last_known:
        return False
    return True


def analyze_issue(
    issue: dict[str, Any],
    *,
    token: str,
    config: dict[str, Any],
    dry_run: bool,
    skip_email: bool,
    stale_surfaces: list[str] | None = None,
) -> dict[str, Any] | None:
    """Run analysis on a single issue. Returns state entry or None on failure."""
    number = issue["number"]
    title = issue.get("title", "")
    difficulty = _get_difficulty(issue)
    routing_profile = DIFFICULTY_ROUTING_PROFILES.get(difficulty, "analysis")

    print(f"\n{'='*60}")
    print(f"Issue #{number}: {title}")
    print(f"  Difficulty: {difficulty} → profile: {routing_profile}")
    print(f"{'='*60}")

    comments: list[dict[str, str]] = []
    if _comments_count(issue) > 0:
        comments = fetch_issue_comments(token, number)

    routing = preflight_routing(issue, config)
    routing_md = format_routing_section(routing)
    surfaces = routing["surfaces"]
    # Allow forcing the primary surface (keyword routing can mis-detect a pure
    # admin/app issue as cross-surface). ASP_FORCE_SURFACE pins which surface's
    # code the analysis agent reads and which worktree Pipeline D will target.
    forced = os.getenv("ASP_FORCE_SURFACE", "").strip()
    if forced:
        surfaces = [forced] + [s for s in surfaces if s != forced]
    # primary_surface 决定 analysis agent 在哪个 surface 的代码目录里启动。
    # 跨 surface issue（如 #16=[backend,admin,app]）若把 primary 选成本地不存在的
    # surface（你只有 app/admin，没有 backend），agent 的 cwd 会落到无效目录 →
    # claude 在 Windows 报 WinError 267。所以优先选 local_path 真实存在的 surface。
    if not forced and surfaces:
        present = [s for s in surfaces if _surface_workdir(s) != _ASP_ROOT]
        if present:
            surfaces = present + [s for s in surfaces if s not in present]
    primary_surface = surfaces[0] if surfaces else "backend"
    print(f"  Surfaces: {surfaces or 'NONE'}")
    print(f"  Scope: {routing['scope']}")

    comments_md = format_comments_for_prompt(comments)

    if dry_run:
        analysis_md = f"*(Dry-run — profile={routing_profile})*\n\n**Body preview**:\n\n{(issue.get('body') or '')[:500]}"
    else:
        if AgentClient is None:
            print("  Error: AgentClient not importable")
            return None

        intent = routing_profile
        timeout = int(os.getenv("AGENT_CLIENT_TIMEOUT", "3600"))
        if difficulty == "trivial":
            timeout = min(timeout, 600)

        prompt = _build_inbound_prompt(issue, routing_md, comments_md, primary_surface, stale_surfaces)
        print(f"  Analyzing via AgentClient (intent={intent})...")

        def _validate(text: str) -> bool:
            return _is_valid_analysis(text, issue_title=title)

        result = AgentClient().run(
            prompt,
            intent=intent,
            workdir=_surface_workdir(primary_surface),
            timeout_sec=timeout,
            validate=_validate,
            finalize_prompt=_FINALIZE_PROMPT,
        )

        if result.status != "success":
            print(f"  Analysis failed: {result.error}")
            return None

        analysis_md = result.text
        print(f"  Route: {result.executor}/{result.model or 'default'} ({result.elapsed_sec}s)")

        if not _is_valid_analysis(analysis_md, issue_title=title):
            print(f"  HARD STOP: final output still invalid after finalize — NOT posting comment")
            try:
                run_gh(
                    "issue", "edit", str(number), "-R", REPO,
                    "--add-label", "analysis-failed",
                )
            except RuntimeError:
                pass
            return None

    post_analysis_comment(number, routing_md, analysis_md, dry_run=dry_run)
    _add_analyzed_label(number, dry_run)

    issue_type = extract_issue_type(analysis_md)
    print(f"  Issue type: {issue_type} (from comment, Pipeline D reads this directly)")

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "last_seen_at": now_iso,
        "last_analyzed_at": now_iso,
        "last_issue_updated_at": issue.get("updatedAt") or issue.get("updated_at", ""),
        "last_state": issue.get("state", "OPEN").lower(),
        "title": title,
        "url": issue.get("url", ""),
        "surfaces": routing["surfaces"],
        "difficulty": difficulty,
        "routing_profile": routing_profile,
        "assignee": _operator(),
        "issue_type": issue_type,
    }


_MAX_PARALLEL_AGENTS = int(os.getenv("MAX_PARALLEL_AGENTS", "3"))
_LOCK_LABEL = "analysis-in-progress"
_ANALYZED_LABEL = "analyzed"


def _add_analyzed_label(number: int, dry_run: bool) -> None:
    """Idempotently add the 'analyzed' label (Pipeline C completion marker)."""
    if dry_run:
        print(f"  [DRY RUN] would add label '{_ANALYZED_LABEL}' to #{number}")
        return
    try:
        raw = run_gh("issue", "view", str(number), "-R", REPO, "--json", "labels")
        labels = [lb["name"] for lb in json.loads(raw).get("labels", [])]
        if _ANALYZED_LABEL not in labels:
            run_gh("issue", "edit", str(number), "-R", REPO, "--add-label", _ANALYZED_LABEL)
            print(f"  Added label '{_ANALYZED_LABEL}' to #{number}")
    except RuntimeError as e:
        print(f"  Warning: could not add label '{_ANALYZED_LABEL}' to #{number}: {e}")


def needs_analysis(
    issue: dict[str, Any],
    comments: list[dict[str, str]],
    force: bool,
) -> str:
    """Classify whether analysis should run.

    Returns:
      'skip'         — both analysis comment AND 'analyzed' label present
      'repair_label' — analysis comment present, 'analyzed' label missing
      'analyze'      — needs full analysis
    """
    if force:
        return "analyze"
    has_marker = has_analysis_comment(comments)
    has_label = _ANALYZED_LABEL in _issue_labels(issue)
    if has_marker and has_label:
        return "skip"
    if has_marker and not has_label:
        return "repair_label"
    return "analyze"


def _acquire_lock(number: int, dry_run: bool) -> bool:
    """Add analysis-in-progress label as distributed lock. Returns False if already held."""
    if dry_run:
        return True
    try:
        raw = run_gh(
            "issue", "view", str(number), "-R", REPO,
            "--json", "labels",
        )
        labels = [lb["name"] for lb in json.loads(raw).get("labels", [])]
        if _LOCK_LABEL in labels:
            return False
        run_gh("issue", "edit", str(number), "-R", REPO, "--add-label", _LOCK_LABEL)
        return True
    except RuntimeError:
        return False


def _release_lock(number: int) -> None:
    try:
        run_gh("issue", "edit", str(number), "-R", REPO, "--remove-label", _LOCK_LABEL)
    except RuntimeError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified issue scanner (Pipeline C) — difficulty-aware agent routing"
    )
    parser.add_argument("--issue", type=int, help="Analyze one issue")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--skip-email", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--batch", type=int, default=1, help="Max issues per run (default: 1)")
    parser.add_argument("--parallel", action="store_true", help="Process multiple issues in parallel")
    parser.add_argument("--repo", help="Target a single surface repo (e.g. AI-MYG/asp-app); "
                                       "default: auto-resolve all repos you own from surfaces.yaml")
    args = parser.parse_args()

    _load_env()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    operator = _operator()

    # --- Multi-repo dispatch ---------------------------------------------
    # Top-level invocation (no ASP_SURFACE_REPO in env yet) resolves the repos
    # this operator owns and re-execs one child per repo with the repo pinned in
    # the environment. Children (env already set) fall through and do real work.
    if not os.getenv("ASP_SURFACE_REPO"):
        repos = [args.repo] if args.repo else surface_repos_for_operator(operator)
        if _dispatch_per_repo(repos, operator):
            return

    config = load_config()

    try:
        issues = fetch_assigned_issues(args.issue, operator=operator)
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    issues.sort(key=lambda i: i.get("createdAt", ""), reverse=True)

    # Load state
    state: dict[str, Any] = {}
    if _STATE_FILE.exists():
        with open(_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)

    # Filter candidates
    candidates: list[dict[str, Any]] = []
    for issue in issues:
        number = issue["number"]
        comments: list[dict[str, str]] = []
        if _comments_count(issue) > 0:
            try:
                comments = fetch_issue_comments(token, number)
            except Exception:
                pass
        action = needs_analysis(issue, comments, args.force)
        if action == "skip":
            print(f"  #{number}: already analyzed (comment + label present)")
            continue
        if action == "repair_label":
            print(f"  #{number}: analysis comment present, repairing missing 'analyzed' label")
            _add_analyzed_label(number, args.dry_run)
            continue
        if _should_process(issue, state, args.force):
            candidates.append(issue)
        else:
            print(f"  #{number}: unchanged since last run")

    if not args.issue and not args.scan_only:
        candidates = candidates[: args.batch]

    print(f"Scanner queue ({operator}): {len(issues)} open assigned, {len(candidates)} need analysis")

    if args.scan_only:
        for issue in candidates:
            r = preflight_routing(issue, config)
            d = _get_difficulty(issue)
            print(f"  #{issue['number']}: surfaces={r['surfaces']} scope={r['scope']} "
                  f"difficulty={d} profile={DIFFICULTY_ROUTING_PROFILES.get(d, 'analysis')}")
        return

    if not candidates:
        print("Nothing to process.")
        return

    if not args.dry_run and AgentClient is None:
        print("Error: AgentClient not importable (tools/agent_client.py)")
        sys.exit(1)

    # Worktree sync (once, before any analysis)
    stale_surfaces: list[str] = []
    if not args.dry_run and not args.skip_sync:
        all_surfaces: set[str] = set()
        for c in candidates:
            r = preflight_routing(c, config)
            all_surfaces.update(r["surfaces"] or ["backend"])
        required = surfaces_to_sync(list(all_surfaces))
        print(f"Syncing surfaces {required} (operator={operator})...")
        report = sync_asp_worktrees(required, operator=operator)
        stale_surfaces = report.stale_surfaces
        if stale_surfaces:
            print(f"  Stale surfaces: {', '.join(stale_surfaces)}")

    # --- Parallel multi-issue via subprocess ---
    if args.parallel and len(candidates) > 1 and not args.dry_run:
        parallelizable = [c for c in candidates if _get_difficulty(c) != "complex"]
        sequential = [c for c in candidates if _get_difficulty(c) == "complex"]

        max_workers = min(_MAX_PARALLEL_AGENTS, len(parallelizable))
        print(f"\n--- Parallel: {len(parallelizable)} issue(s), max {max_workers} concurrent ---")

        active: dict[int, sp.Popen] = {}
        pending = list(parallelizable)
        processed = 0

        log_dir = _ASP_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        while pending or active:
            while pending and len(active) < max_workers:
                issue = pending.pop(0)
                number = issue["number"]
                if not _acquire_lock(number, dry_run=False):
                    print(f"  #{number}: locked (analysis-in-progress), skipping")
                    continue
                cmd = [
                    sys.executable, str(Path(__file__).resolve()),
                    "--issue", str(number),
                    "--skip-sync", "--skip-email",
                ]
                if args.force:
                    cmd.append("--force")
                log_path = log_dir / f"issue_scanner_{number}.log"
                log_file = open(log_path, "w")
                print(f"  Spawning agent for #{number} (log: {log_path.name})")
                proc = sp.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=sp.STDOUT,
                    cwd=str(_ASP_ROOT),
                    env={**os.environ, "GITHUB_TOKEN": token, "GITHUB_ASSIGNEE": operator},
                )
                active[number] = proc
                proc._log_file = log_file  # type: ignore[attr-defined]

            done_numbers: list[int] = []
            for number, proc in active.items():
                ret = proc.poll()
                if ret is not None:
                    proc._log_file.close()  # type: ignore[attr-defined]
                    _release_lock(number)
                    if ret == 0:
                        print(f"  #{number}: completed (exit 0)")
                        processed += 1
                    else:
                        print(f"  #{number}: failed (exit {ret})")
                    done_numbers.append(number)

            for n in done_numbers:
                del active[n]

            if active:
                time.sleep(5)

        for issue in sequential:
            entry = analyze_issue(
                issue,
                token=token,
                config=config,
                dry_run=False,
                skip_email=args.skip_email,
                stale_surfaces=stale_surfaces or None,
            )
            if entry:
                state[str(issue["number"])] = entry
                processed += 1

        if _STATE_FILE.exists():
            with open(_STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)

        print(f"\nDone. Parallel processed {processed} issue(s) for {operator}.")

    else:
        # --- Sequential ---
        processed = 0
        for issue in candidates:
            entry = analyze_issue(
                issue,
                token=token,
                config=config,
                dry_run=args.dry_run,
                skip_email=args.skip_email,
                stale_surfaces=stale_surfaces or None,
            )
            if entry:
                state[str(issue["number"])] = entry
                processed += 1

        if not args.dry_run:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

        print(f"\nDone. Analyzed {processed} issue(s) for {operator}.")


if __name__ == "__main__":
    main()

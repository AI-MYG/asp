#!/usr/bin/env python3
"""Pipeline B — centralized triage for feishu-inbound issues (no deep code analysis).

Scan contract (宽进): open + label ``feishu-inbound`` — that's it.
Skip logic (幂等): already has ``triaged`` label + triage comment → skip (``--force`` overrides).

Deep analysis is Pipeline C: ``issue_scanner.py`` on each developer machine.

Usage:
    python tools/feishu_inbound/triage_agent.py
    python tools/feishu_inbound/triage_agent.py --issue 432
    python tools/feishu_inbound/triage_agent.py --scan-only --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_ASP_ROOT = _SCRIPT_DIR.parent.parent
_STATE_FILE = _ASP_ROOT / "state" / "feishu_inbound_triage_state.json"
_TRIAGE_MARKER = "## Feishu Inbound Triage"
_PROCESSED_LABEL = "triaged"

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from routing import (  # noqa: E402
    REPO,
    ensure_difficulty_labels,
    format_routing_section,
    load_config,
    preflight_routing,
    run_gh,
)
from inbound_agent import (  # noqa: E402
    _comments_count,
    _load_env,
    apply_github_updates,
    fetch_issue_comments,
)


def _issue_labels(issue: dict[str, Any]) -> list[str]:
    return [lb["name"] for lb in issue.get("labels", [])]


def _has_triage_marker(comments: list[dict[str, str]]) -> bool:
    return any(_TRIAGE_MARKER in (c.get("body") or "") for c in comments)


def fetch_issues_needing_triage(issue_number: int | None = None) -> list[dict[str, Any]]:
    if issue_number:
        raw = run_gh(
            "issue", "view", str(issue_number),
            "-R", REPO,
            "--json", "number,title,body,labels,createdAt,updatedAt,state,url,comments",
        )
        issue = json.loads(raw)
        labels = _issue_labels(issue)
        if "feishu-inbound" not in labels:
            raise ValueError(f"Issue #{issue_number} does not have feishu-inbound label")
        if issue.get("state", "").upper() != "OPEN":
            raise ValueError(f"Issue #{issue_number} is not open")
        return [issue]

    raw = run_gh(
        "issue", "list",
        "-R", REPO,
        "--label", "feishu-inbound",
        "--state", "open",
        "--json", "number,title,body,labels,createdAt,updatedAt,state,url,comments",
        "--limit", "50",
    )
    return json.loads(raw)


def needs_triage(issue: dict[str, Any], comments: list[dict[str, str]], force: bool) -> bool:
    if force:
        return True
    if _PROCESSED_LABEL in _issue_labels(issue) and _has_triage_marker(comments):
        return False
    if _PROCESSED_LABEL in _issue_labels(issue) and not _has_triage_marker(comments):
        return True
    return True


def post_triage_comment(number: int, routing_md: str, dry_run: bool) -> None:
    body = (
        f"{_TRIAGE_MARKER}\n\n"
        f"{routing_md}\n\n"
        f"---\n"
        f"_Deterministic triage by `triage_agent.py`. "
        f"Assignee should run `issue_scanner.py` for deep analysis (Pipeline C)._"
    )
    if dry_run:
        print(f"\n{'='*60}\n[DRY RUN] Triage comment for #{number}:\n{'='*60}\n{body}")
        return
    run_gh("issue", "comment", str(number), "-R", REPO, "--body", body)


def load_state() -> dict[str, Any]:
    if _STATE_FILE.exists():
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict[str, Any]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def process_triage(
    issue: dict[str, Any],
    *,
    token: str,
    config: dict[str, Any],
    dry_run: bool,
    force: bool,
    state: dict[str, Any],
    now_iso: str,
) -> bool:
    number = issue["number"]
    labels = _issue_labels(issue)
    comments: list[dict[str, str]] = []
    if _comments_count(issue) > 0:
        comments = fetch_issue_comments(token, number, repo=REPO)

    if not needs_triage(issue, comments, force):
        print(f"  #{number}: already triaged")
        return False

    print(f"\n{'='*60}")
    print(f"Triage #{number}: {issue.get('title', '')}")
    print(f"{'='*60}")

    routing = preflight_routing(issue, config)
    routing_md = format_routing_section(routing)
    print(f"  Surfaces: {routing['surfaces'] or 'NONE'}")
    print(f"  Scope: {routing['scope']}")
    print(f"  Difficulty: {routing.get('difficulty', 'standard')} → profile: {routing.get('routing_profile', 'analysis')}")
    print(f"  Assignee: {routing['assignee_name'] or 'NONE'}")

    apply_github_updates(number, routing, dry_run=dry_run)
    post_triage_comment(number, routing_md, dry_run=dry_run)

    if dry_run:
        return True

    key = str(number)
    state[key] = {
        "last_triaged_at": now_iso,
        "last_issue_updated_at": issue.get("updatedAt") or issue.get("updated_at", ""),
        "surfaces": routing["surfaces"],
        "difficulty": routing.get("difficulty", "standard"),
        "routing_profile": routing.get("routing_profile", "analysis"),
        "assignee": routing.get("assignee"),
        "labels": labels + routing.get("labels", []) + [_PROCESSED_LABEL],
    }
    return True


def backfill_difficulty_labels(config: dict[str, Any], *, dry_run: bool) -> int:
    """Add difficulty-* labels to open triaged feishu-inbound issues (no new comments)."""
    raw = run_gh(
        "issue", "list",
        "-R", REPO,
        "--label", "feishu-inbound,triaged",
        "--state", "open",
        "--json", "number,title,body,labels",
        "--limit", "100",
    )
    issues = json.loads(raw)
    updated = 0
    for issue in issues:
        number = issue["number"]
        existing = _issue_labels(issue)
        routing = preflight_routing(issue, config)
        difficulty_label = f"difficulty-{routing['difficulty']}"
        if difficulty_label in existing:
            continue
        print(f"  #{number}: add {difficulty_label}")
        if not dry_run:
            try:
                run_gh("issue", "edit", str(number), "-R", REPO, "--add-label", difficulty_label)
                updated += 1
            except RuntimeError as e:
                print(f"    Warning: {e}")
        else:
            updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Feishu inbound triage (Pipeline B)")
    parser.add_argument("--issue", type=int, help="Triage one issue")
    parser.add_argument("--dry-run", action="store_true", help="No GitHub writes")
    parser.add_argument("--scan-only", action="store_true", help="List candidates only")
    parser.add_argument("--force", action="store_true", help="Re-triage even if triaged")
    parser.add_argument("--batch", type=int, default=5, help="Max issues per run (default: 5)")
    parser.add_argument("--json-output", action="store_true", help="Print routing JSON (with --scan-only)")
    parser.add_argument(
        "--backfill-difficulty",
        action="store_true",
        help="Add difficulty-* labels to already-triaged issues (no re-triage comment)",
    )
    args = parser.parse_args()

    _load_env()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    config = load_config()
    now_iso = datetime.now(timezone.utc).isoformat()
    ensure_difficulty_labels(dry_run=args.dry_run)

    if args.backfill_difficulty:
        n = backfill_difficulty_labels(config, dry_run=args.dry_run)
        print(f"\nBackfill done. Updated {n} issue(s).")
        return

    try:
        issues = fetch_issues_needing_triage(args.issue)
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    issues.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    candidates: list[dict[str, Any]] = []
    for issue in issues:
        number = issue["number"]
        comments: list[dict[str, str]] = []
        if _comments_count(issue) > 0:
            try:
                comments = fetch_issue_comments(token, number, repo=REPO)
            except Exception:
                pass
        if needs_triage(issue, comments, args.force):
            candidates.append(issue)
        else:
            print(f"  #{number}: already triaged")

    if not args.issue and not args.scan_only:
        candidates = candidates[: args.batch]

    print(f"Found {len(issues)} feishu-inbound issue(s), {len(candidates)} need triage")

    if args.scan_only:
        reports = []
        for issue in candidates:
            routing = preflight_routing(issue, config)
            print(format_routing_section(routing))
            print()
            reports.append({"number": issue["number"], **routing})
        if args.json_output:
            print(json.dumps(reports, ensure_ascii=False, indent=2))
        return

    if not candidates:
        print("Nothing to triage.")
        return

    state = load_state()
    processed = 0
    for issue in candidates:
        if process_triage(
            issue,
            token=token,
            config=config,
            dry_run=args.dry_run,
            force=args.force,
            state=state,
            now_iso=now_iso,
        ):
            processed += 1

    if not args.dry_run:
        save_state(state)
    print(f"\nDone. Triaged {processed} issue(s).")


if __name__ == "__main__":
    main()

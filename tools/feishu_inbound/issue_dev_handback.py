#!/usr/bin/env python3
"""Pipeline F — hand back issues after dev CI/CD succeeds.

Scans surface execution issues with ``review-dev-pass`` (Pipeline E passed) that
are not yet ``ready-for-acceptance``. When the linked PR is merged to the
surface base branch and the configured dev CI/CD workflow succeeded on the
merge commit, reassigns the issue to its author and posts an acceptance comment.

Pipeline E only adds ``review-dev-pass``; human merges the PR to dev; CI/CD
runs; this script completes the handback.

Usage:
    export GITHUB_TOKEN=...
    python tools/feishu_inbound/issue_dev_handback.py --scan-only
    python tools/feishu_inbound/issue_dev_handback.py --issue 125 --repo AI-MYG/asp-backend
    python tools/feishu_inbound/issue_dev_handback.py --dry-run
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

sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from routing import load_config, run_gh  # noqa: E402
from org_issues import fetch_org_labeled_issues, github_org, issue_repo  # noqa: E402
from inbound_agent import _load_env  # noqa: E402
from issue_executor import (  # noqa: E402
    _extract_central_number,
    _find_linked_pr,
)

_tools_dir = _ASP_ROOT / "tools"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))
from smart_pr import handback_to_requester  # noqa: E402

_CENTRAL_REPO = "AI-MYG/asp"
_REVIEW_PASS_LABEL = "review-dev-pass"
_READY_LABEL = "ready-for-acceptance"
_PIPELINE_F_CFG_KEY = "pipeline_f"


def _issue_labels(issue: dict[str, Any]) -> list[str]:
    return [lb["name"] for lb in issue.get("labels", [])]


def _load_surfaces() -> dict[str, Any]:
    try:
        import yaml

        cfg = yaml.safe_load((_ASP_ROOT / "config" / "surfaces.yaml").read_text(encoding="utf-8"))
        return cfg.get("surfaces") or {}
    except Exception:
        return {}


def _dev_cicd_workflow(repo: str) -> str | None:
    cfg = (load_config() or {}).get(_PIPELINE_F_CFG_KEY) or {}
    block = (cfg.get("dev_cicd") or {}).get(repo)
    if isinstance(block, dict):
        name = block.get("workflow")
        if name:
            return str(name)
    if isinstance(block, str):
        return block
    return None


def _handback_targets(issue: dict[str, Any], central: int | None) -> list[tuple[int, str]]:
    number = issue["number"]
    repo = issue_repo(issue)
    targets: list[tuple[int, str]] = []
    if central and (repo != _CENTRAL_REPO or number != central):
        targets.append((central, _CENTRAL_REPO))
    targets.append((number, repo))
    return targets


def _pr_merge_info(repo: str, pr_number: int) -> dict[str, Any] | None:
    try:
        raw = run_gh(
            "pr", "view", str(pr_number), "-R", repo,
            "--json", "mergedAt,mergeCommit,url,baseRefName",
        )
        data = json.loads(raw)
    except (RuntimeError, json.JSONDecodeError):
        return None
    if not data.get("mergedAt"):
        return None
    merge_commit = data.get("mergeCommit") or {}
    sha = merge_commit.get("oid") or merge_commit.get("sha")
    if not sha:
        return None
    return {
        "sha": sha,
        "url": data.get("url", ""),
        "merged_at": data["mergedAt"],
        "base": data.get("baseRefName", ""),
    }


def dev_cicd_conclusion(repo: str, head_sha: str, workflow_name: str) -> str | None:
    """Return workflow conclusion when completed; None if pending or no run yet."""
    safe_name = workflow_name.replace('"', '\\"')
    jq = (
        f'[.workflow_runs[] | select(.name == "{safe_name}") '
        '| {status, conclusion, created_at}] | sort_by(.created_at) | reverse | .[0]'
    )
    try:
        raw = run_gh(
            "api", f"repos/{repo}/actions/runs",
            "-f", f"head_sha={head_sha}",
            "--jq", jq,
        )
    except RuntimeError:
        return None
    if not raw or raw.strip() in ("", "null"):
        return None
    run = json.loads(raw)
    if run.get("status") != "completed":
        return None
    return run.get("conclusion")


def eligibility(
    issue: dict[str, Any],
    *,
    pr: dict[str, Any] | None = None,
    central: int | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Classify handback readiness.

    Returns (status, detail) where status is one of:
      ready | skip_no_pass | skip_ready | skip_no_pr | skip_not_merged |
      skip_no_workflow | skip_cicd_pending | skip_cicd_failed
    """
    labels = _issue_labels(issue)
    if _REVIEW_PASS_LABEL not in labels:
        return "skip_no_pass", None
    if _READY_LABEL in labels:
        return "skip_ready", None

    number = issue["number"]
    repo = issue_repo(issue)
    if central is None:
        central = _extract_central_number(issue)

    if pr is None:
        pr = _find_linked_pr(repo, number, central, state="merged")
        if pr is None:
            pr = _find_linked_pr(repo, number, central, state="closed")
    if pr is None:
        return "skip_no_pr", None

    merge = _pr_merge_info(repo, int(pr["number"]))
    if merge is None:
        return "skip_not_merged", {"pr": pr}

    workflow = _dev_cicd_workflow(repo)
    if not workflow:
        return "skip_no_workflow", {"pr": pr, "merge": merge}

    conclusion = dev_cicd_conclusion(repo, merge["sha"], workflow)
    if conclusion is None:
        return "skip_cicd_pending", {"pr": pr, "merge": merge, "workflow": workflow}
    if conclusion != "success":
        return "skip_cicd_failed", {
            "pr": pr, "merge": merge, "workflow": workflow, "conclusion": conclusion,
        }

    return "ready", {"pr": pr, "merge": merge, "workflow": workflow, "conclusion": conclusion}


def _add_label(number: int, repo: str, label: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY RUN] would add label '{label}' to {repo}#{number}")
        return
    try:
        run_gh("issue", "edit", str(number), "-R", repo, "--add-label", label)
    except RuntimeError as e:
        print(f"  Warning: could not add label '{label}' to {repo}#{number}: {e}")


def process_issue(
    issue: dict[str, Any],
    *,
    dry_run: bool,
    force: bool = False,
) -> dict[str, Any] | None:
    number = issue["number"]
    repo = issue_repo(issue)
    title = issue.get("title", "")
    central = _extract_central_number(issue)

    print(f"\n{'='*60}")
    print(f"Dev handback {repo}#{number}: {title}")

    status, detail = eligibility(issue, central=central)
    if status != "ready" and not (force and status.startswith("skip_")):
        print(f"  {status}")
        return None

    if not detail:
        print("  No detail for ready issue")
        return None

    pr = detail["pr"]
    pr_url = pr.get("url", "")
    workflow = detail.get("workflow", "?")
    print(
        f"  PR #{pr.get('number')} merged; dev CI/CD ({workflow}) "
        f"conclusion={detail.get('conclusion')}"
    )

    handback_results: list[dict[str, Any]] = []
    for issue_num, target_repo in _handback_targets(issue, central):
        hb = handback_to_requester(
            issue_num, target_repo, pr_url, dry_run=dry_run, stage="f",
        )
        handback_results.append({"issue": issue_num, "repo": target_repo, **hb})
        print(f"  Handback {target_repo}#{issue_num}: {hb.get('handback', 'skipped')}")

    _add_label(number, repo, _READY_LABEL, dry_run=dry_run)

    return {
        "repo": repo,
        "number": number,
        "pr": pr.get("number"),
        "pr_url": pr_url,
        "merge_sha": detail["merge"].get("sha"),
        "workflow": workflow,
        "handback": handback_results,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline F — hand back issues after dev CI/CD succeeds",
    )
    parser.add_argument("--issue", type=int, help="Process one issue number")
    parser.add_argument("--repo", help="owner/repo (with --issue when ambiguous)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="Hand back even if CI/CD not success")
    args = parser.parse_args()

    _load_env()
    if not os.getenv("GITHUB_TOKEN"):
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    cfg = (load_config() or {}).get(_PIPELINE_F_CFG_KEY) or {}
    scan = cfg.get("scan") or {}
    org = scan.get("org") or github_org()
    limit = int(scan.get("limit") or os.getenv("GITHUB_ORG_ISSUE_LIMIT") or 100)

    try:
        issues = fetch_org_labeled_issues(
            org=org,
            include_labels=[_REVIEW_PASS_LABEL],
            exclude_labels=[_READY_LABEL],
            issue_number=args.issue,
            repo=args.repo,
            limit=limit,
        )
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    candidates: list[tuple[dict[str, Any], str]] = []
    for issue in issues:
        central = _extract_central_number(issue)
        status, _ = eligibility(issue, central=central)
        candidates.append((issue, status))

    print(
        f"\nHandback queue (org:{org} label:{_REVIEW_PASS_LABEL} "
        f"-label:{_READY_LABEL}): {len(issues)} issue(s)"
    )

    if args.scan_only:
        for issue, status in candidates:
            repo = issue_repo(issue)
            print(f"  {repo}#{issue['number']}: {status}")
        return

    ready = [(i, s) for i, s in candidates if s == "ready" or args.force]
    if not ready:
        print("Nothing ready for handback.")
        for issue, status in candidates:
            if status != "ready":
                print(f"  {issue_repo(issue)}#{issue['number']}: {status}")
        return

    processed = 0
    for issue, _status in ready:
        entry = process_issue(issue, dry_run=args.dry_run, force=args.force)
        if entry:
            processed += 1

    print(f"\nDone. Handed back {processed} issue(s).")


if __name__ == "__main__":
    main()

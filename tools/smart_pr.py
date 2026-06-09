#!/usr/bin/env python3
"""ASP Smart PR: auto-create PR with correct branch, base, and reviewers.

Reads config/surfaces.yaml for surface → repo/branch/reviewer mapping.

Usage:
    python tools/smart_pr.py --issue 42 --surface backend
    python tools/smart_pr.py --issue 42 --surface backend --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Missing PyYAML. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACES_CONFIG = REPO_ROOT / "config" / "surfaces.yaml"


def load_surfaces() -> dict[str, Any]:
    with open(SURFACES_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True, dry_run: bool = False) -> str:
    display = " ".join(cmd)
    print(f"$ {display}", file=sys.stderr)
    if dry_run:
        print("  [DRY RUN] skipped", file=sys.stderr)
        return ""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=60)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr.strip()}")
    return result.stdout.strip()


def resolve_surface(surface_name: str, config: dict) -> dict[str, Any]:
    surfaces = config.get("surfaces", {})
    if surface_name not in surfaces:
        available = ", ".join(surfaces.keys())
        raise RuntimeError(f"Unknown surface '{surface_name}'. Available: {available}")
    return surfaces[surface_name]


def handback_to_requester(
    issue: int, issue_repo: str, pr_url: str, *, dry_run: bool = False
) -> dict[str, Any]:
    """Hand the issue back to the person who raised it.

    After Pipeline D opens the PR, the issue's owner should be the original
    requester (issue author) — not the executor/lead — so they can verify and,
    once satisfied, close it. Sets the requester as the sole assignee. Bot
    authors (e.g. the Stage-A pipeline / github-actions) are skipped because
    there is no human to hand back to.
    """
    result: dict[str, Any] = {"handback": "skipped", "requester": None}
    try:
        raw = run(["gh", "issue", "view", str(issue), "-R", issue_repo,
                   "--json", "author,assignees"])
    except RuntimeError as e:
        print(f"  Warning: handback skipped, could not read issue: {e}", file=sys.stderr)
        result["handback"] = "error"
        return result
    if not raw:
        return result

    data = json.loads(raw)
    author = data.get("author") or {}
    requester = author.get("login")
    if not requester or author.get("is_bot") or requester.startswith("app/"):
        print(f"  Handback skipped: issue author is a bot/unknown ({requester!r})",
              file=sys.stderr)
        return result

    current = [a.get("login") for a in data.get("assignees", []) if a.get("login")]
    to_remove = [a for a in current if a != requester]
    result["requester"] = requester

    edit_cmd = ["gh", "issue", "edit", str(issue), "-R", issue_repo,
                "--add-assignee", requester]
    if to_remove:
        edit_cmd += ["--remove-assignee", ",".join(to_remove)]
    try:
        run(edit_cmd, dry_run=dry_run)
    except RuntimeError as e:
        print(f"  Warning: could not reassign issue to '{requester}': {e}", file=sys.stderr)
        result["handback"] = "error"
        return result

    comment = (
        f"@{requester} Pipeline D 已实现并提交 PR：{pr_url or '(见上)'}\n\n"
        f"已将该 issue 交回给你验收。确认满足需求后请手动关闭；"
        f"如需修订，移除 `executed` 标签即可让 Pipeline D 下一轮重新处理。"
    )
    try:
        run(["gh", "issue", "comment", str(issue), "-R", issue_repo, "--body", comment],
            dry_run=dry_run)
    except RuntimeError as e:
        print(f"  Warning: could not post handback comment: {e}", file=sys.stderr)

    result["handback"] = "reassigned"
    result["removed_assignees"] = to_remove
    print(f"  Handback: issue {issue_repo}#{issue} reassigned to @{requester}"
          + (f" (removed {to_remove})" if to_remove else ""), file=sys.stderr)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="ASP Smart PR")
    parser.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    parser.add_argument("--surface", required=True, help="Surface name (backend, app, admin, etc.)")
    parser.add_argument("--title", help="PR title (default: auto from issue)")
    parser.add_argument("--issue-repo", default="AI-MYG/asp",
                        help="Repo to look up issue title (default: AI-MYG/asp)")
    parser.add_argument("--model", help="Model that implemented the change (shown in PR body)")
    parser.add_argument("--handback-requester", action="store_true",
                        help="After PR creation, reassign the issue to its requester "
                             "(issue author) as sole assignee and notify them")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_surfaces()
    surface = resolve_surface(args.surface, config)
    branch_pattern = config.get("branch_pattern", "issue-{issue_number}/{surface}")

    repo = surface["repo"]
    base_branch = surface["base_branch"]
    reviewers = surface.get("default_reviewers", [])
    branch_name = branch_pattern.format(issue_number=args.issue, surface=args.surface)

    print(f"Surface: {args.surface}")
    print(f"Repo: {repo}")
    print(f"Base branch: {base_branch}")
    print(f"PR branch: {branch_name}")
    print(f"Reviewers: {reviewers}")

    # Get issue title for PR title
    pr_title = args.title
    if not pr_title:
        raw = run(["gh", "issue", "view", str(args.issue), "-R", args.issue_repo, "--json", "title"])
        if raw:
            issue_data = json.loads(raw)
            pr_title = f"[ASP-{args.issue}] {issue_data.get('title', '').replace('[feishu] ', '')}"
        else:
            pr_title = f"[ASP-{args.issue}] {args.surface}"

    # Create PR
    model_line = f"\n\n**Implemented by**: `{args.model}`" if args.model else ""
    # Use "Closes" to establish GitHub sidebar link between PR and issue.
    # Auto-close on merge is disabled at repo level (Settings → General → Issues),
    # so closing remains a human decision after acceptance.
    pr_body = f"Closes {args.issue_repo}#{args.issue}{model_line}\n\n🤖 Generated by Pipeline D (Smart PR)"
    pr_cmd = [
        "gh", "pr", "create",
        "-R", repo,
        "--base", base_branch,
        "--head", branch_name,
        "--title", pr_title,
        "--body", pr_body,
    ]
    for reviewer in reviewers:
        pr_cmd.extend(["--reviewer", reviewer])

    result = run(pr_cmd, dry_run=args.dry_run)

    output = {
        "surface": args.surface,
        "repo": repo,
        "base_branch": base_branch,
        "branch": branch_name,
        "reviewers": reviewers,
        "pr_url": result if result else "(dry-run)",
    }

    if args.handback_requester:
        output["handback"] = handback_to_requester(
            args.issue, args.issue_repo, result, dry_run=args.dry_run
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ASP Triage Dispatch: scan central repo for untriaged issues, create execution issues in surface repos.

Usage:
    python scripts/triage_dispatch.py
    python scripts/triage_dispatch.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Missing PyYAML. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
CENTRAL_REPO = "AI-MYG/asp"


def load_config(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def gh(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=60
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh failed: {' '.join(args)}")
    return result.stdout.strip()


def fetch_untriaged_issues() -> list[dict[str, Any]]:
    raw = gh(
        "issue", "list",
        "-R", CENTRAL_REPO,
        "--label", "feishu-inbound",
        "--search", "-label:triaged",
        "--state", "open",
        "--json", "number,title,body,labels",
        "--limit", "20",
    )
    return json.loads(raw)


def detect_surfaces(title: str, body: str, triage_config: dict) -> list[str]:
    text = f"{title} {body}".lower()
    surfaces: list[str] = []
    for _name, cfg in triage_config.get("surface_routing", {}).items():
        for kw in cfg.get("keywords", []):
            if kw.lower() in text:
                label = cfg.get("label", _name)
                if label not in surfaces:
                    surfaces.append(label)
                break
    return surfaces


def estimate_difficulty(surfaces: list[str], title: str, body: str, triage_config: dict) -> str:
    text = f"{title} {body}".lower()
    heuristics = triage_config.get("scope_heuristics", {})
    if len(surfaces) >= 3 or any(kw in text for kw in heuristics.get("large", {}).get("keywords", [])):
        return "large"
    if len(surfaces) >= 2 or any(kw in text for kw in heuristics.get("medium", {}).get("keywords", [])):
        return "medium"
    return "small"


def resolve_assignee(surfaces: list[str], triage_config: dict) -> str:
    routing = triage_config.get("assignee_routing", {})
    if not surfaces:
        return routing.get("cross_surface_default", "")
    assignees = {routing[s] for s in surfaces if s in routing}
    if len(assignees) == 1:
        return assignees.pop()
    return routing.get("cross_surface_default", "")


def create_execution_issue(
    surface: str,
    central_number: int,
    title: str,
    body: str,
    difficulty: str,
    assignee: str,
    surfaces_config: dict,
    *,
    dry_run: bool,
) -> str | None:
    surface_cfg = surfaces_config.get("surfaces", {}).get(surface)
    if not surface_cfg:
        print(f"  WARNING: No config for surface '{surface}', skipping")
        return None

    repo = surface_cfg["repo"]
    exec_title = f"[ASP-{central_number}] {title.replace('[feishu] ', '')}"
    exec_body = (
        f"## Execution Issue\n\n"
        f"**Central Issue**: {CENTRAL_REPO}#{central_number}\n"
        f"**Surface**: {surface}\n"
        f"**Difficulty**: {difficulty}\n\n"
        f"---\n\n{body}\n\n---\n"
        f"_Auto-created by ASP triage agent from central issue._\n"
    )

    if dry_run:
        print(f"  [DRY RUN] Would create in {repo}: {exec_title}")
        print(f"             Assignee: {assignee}")
        return f"(dry-run) {repo}#?"

    raw = gh(
        "issue", "create",
        "-R", repo,
        "--title", exec_title,
        "--body", exec_body,
        "--assignee", assignee,
    )
    print(f"  Created: {raw}")
    return raw


def post_triage_comment(
    central_number: int,
    surfaces: list[str],
    difficulty: str,
    assignee: str,
    exec_issues: list[str],
    *,
    dry_run: bool,
) -> None:
    surface_str = ", ".join(surfaces) if surfaces else "unknown"
    exec_links = "\n".join(f"- {url}" for url in exec_issues if url)

    comment = (
        f"## Triage Result\n\n"
        f"**Surface**: {surface_str}\n"
        f"**Difficulty**: {difficulty}\n"
        f"**Assignee**: {assignee}\n\n"
        f"### Execution Issues Created\n\n{exec_links}\n\n"
        f"---\n_Auto-triaged by ASP comprehensive agent._\n"
    )

    if dry_run:
        print(f"  [DRY RUN] Would comment on {CENTRAL_REPO}#{central_number}")
        return

    gh(
        "issue", "comment", str(central_number),
        "-R", CENTRAL_REPO,
        "--body", comment,
    )
    # Add triaged label + surface labels
    labels = ["triaged"] + surfaces
    gh(
        "issue", "edit", str(central_number),
        "-R", CENTRAL_REPO,
        "--add-label", ",".join(labels),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ASP Triage Dispatch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    triage_config = load_config("triage.yaml")
    surfaces_config = load_config("surfaces.yaml")

    issues = fetch_untriaged_issues()
    print(f"Found {len(issues)} untriaged issue(s) in {CENTRAL_REPO}")

    if not issues:
        return

    for issue in issues:
        number = issue["number"]
        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        print(f"\n--- #{number}: {title[:60]} ---")

        surfaces = detect_surfaces(title, body, triage_config)
        difficulty = estimate_difficulty(surfaces, title, body, triage_config)
        assignee = resolve_assignee(surfaces, triage_config)

        print(f"  Surfaces: {surfaces or ['none detected']}")
        print(f"  Difficulty: {difficulty}")
        print(f"  Assignee: {assignee}")

        if not surfaces:
            print("  No surface detected, adding needs-manual-triage label")
            if not args.dry_run:
                gh("issue", "edit", str(number), "-R", CENTRAL_REPO,
                   "--add-label", "needs-manual-triage")
            continue

        exec_issues: list[str] = []
        for surface in surfaces:
            url = create_execution_issue(
                surface, number, title, body, difficulty, assignee,
                surfaces_config, dry_run=args.dry_run,
            )
            if url:
                exec_issues.append(url)

        post_triage_comment(
            number, surfaces, difficulty, assignee, exec_issues,
            dry_run=args.dry_run,
        )
        print(f"  Triage complete for #{number}")

    print(f"\nDone. Processed {len(issues)} issue(s).")


if __name__ == "__main__":
    main()

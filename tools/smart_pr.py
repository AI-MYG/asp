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

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACES_CONFIG = REPO_ROOT / "config" / "surfaces.yaml"


def _git_lines(cmd: list[str], *, cwd: Path) -> list[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return []
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def _resolve_surface_worktree(surface: dict[str, Any]) -> Path | None:
    local_path = surface.get("local_path")
    if not isinstance(local_path, str) or not local_path.strip():
        return None
    candidate = (REPO_ROOT.parent.parent / local_path).resolve()
    return candidate if candidate.is_dir() else None


def _backend_repo_root(cwd: Path, surface: dict[str, Any]) -> Path | None:
    if (cwd / "backend" / "Makefile").is_file():
        return cwd
    if (cwd / "Makefile").is_file() and (cwd / "scripts" / "export_openapi.py").is_file():
        return cwd.parent
    return _resolve_surface_worktree(surface)


def _commits_touch_backend_app(repo_root: Path, base_branch: str) -> bool:
    for ref in (f"origin/{base_branch}...HEAD", f"origin/{base_branch}..HEAD"):
        names = _git_lines(["git", "diff", "--name-only", ref], cwd=repo_root)
        if names and any(n.startswith("backend/app/") for n in names):
            return True
    return False


def _executable_python(path: Path) -> str | None:
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


def _resolve_openapi_python(repo_root: Path, surface: dict[str, Any]) -> str:
    """Match feishu_inbound ``resolve_python`` chain for OpenAPI export gates."""
    surface_repo = _resolve_surface_worktree(surface)
    try:
        from feishu_inbound.contracts.toolchain import ToolchainError, resolve_python

        return resolve_python(repo_root, surface_repo=surface_repo)
    except ImportError:
        pass
    except ToolchainError as exc:
        raise RuntimeError(str(exc)) from exc

    override = os.environ.get("FEISHU_INBOUND_PYTHON") or os.environ.get("PYTHON")
    if override:
        return override

    worktree_python = repo_root / "backend" / "venv" / "bin" / "python"
    found = _executable_python(worktree_python)
    if found:
        return found

    if surface_repo is not None:
        surface_python = surface_repo / "backend" / "venv" / "bin" / "python"
        found = _executable_python(surface_python)
        if found:
            return found

    raise RuntimeError(
        f"No usable Python venv for OpenAPI export under {repo_root}; "
        "bootstrap backend venv or set FEISHU_INBOUND_PYTHON"
    )


def ensure_openapi_synced(
    repo_root: Path,
    base_branch: str,
    *,
    surface: dict[str, Any],
    dry_run: bool = False,
) -> None:
    """Export OpenAPI spec and verify before PR creation (backend surface)."""
    backend_dir = repo_root / "backend"
    export_script = backend_dir / "scripts" / "export_openapi.py"
    openapi_doc = repo_root / "docs" / "api" / "openapi.json"
    if not export_script.is_file():
        raise RuntimeError(f"missing {export_script}")

    python_bin = _resolve_openapi_python(repo_root, surface)
    print(f"  OpenAPI gate: using {python_bin}", file=sys.stderr)

    if dry_run:
        print(f"  [DRY RUN] skipped export via {python_bin}", file=sys.stderr)
        return

    export = subprocess.run(
        [python_bin, str(export_script)],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if export.returncode != 0:
        err = (export.stderr or export.stdout or "export_openapi.py failed").strip()
        raise RuntimeError(f"OpenAPI export failed: {err}")

    status = subprocess.run(
        ["git", "status", "--porcelain", "docs/api/openapi.json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if status.stdout.strip():
        run(["git", "add", "docs/api/openapi.json"], cwd=repo_root, dry_run=False)
        run(
            ["git", "commit", "-m", "chore: regenerate openapi.json"],
            cwd=repo_root,
            dry_run=False,
        )
        branch = _git_lines(["git", "branch", "--show-current"], cwd=repo_root)
        branch_name = branch[0] if branch else "HEAD"
        run(["git", "push", "origin", branch_name], cwd=repo_root, dry_run=False)

    check = subprocess.run(
        ["git", "diff", "--exit-code", str(openapi_doc.relative_to(repo_root))],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check.returncode != 0:
        err = (check.stdout or check.stderr or "openapi.json out of date").strip()
        raise RuntimeError(f"OpenAPI check failed: {err}")


def maybe_enforce_backend_openapi_gate(
    surface_name: str,
    surface: dict[str, Any],
    base_branch: str,
    branch_name: str,
    *,
    dry_run: bool = False,
) -> None:
    if surface_name != "backend":
        return
    repo_root = _backend_repo_root(Path.cwd(), surface)
    if repo_root is None:
        print("  Warning: backend worktree not found; skipping OpenAPI gate", file=sys.stderr)
        return
    run(["git", "fetch", "origin", base_branch, branch_name], cwd=repo_root, dry_run=dry_run)
    if not _commits_touch_backend_app(repo_root, base_branch):
        print("  OpenAPI gate: no backend/app changes; skipped", file=sys.stderr)
        return
    print(f"  OpenAPI gate: syncing spec in {repo_root}", file=sys.stderr)
    ensure_openapi_synced(repo_root, base_branch, surface=surface, dry_run=dry_run)


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
    issue: int,
    issue_repo: str,
    pr_url: str,
    *,
    dry_run: bool = False,
    stage: str = "f",
) -> dict[str, Any]:
    """Hand the issue back to the person who raised it.

    Intended after **Pipeline F** — PR merged to dev/base and dev CI/CD succeeded.
    Sets the requester (issue author) as the sole assignee so they can verify
    and close. Bot authors (e.g. Stage-A github-actions) are skipped.
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

    if stage.lower() == "d":
        comment = (
            f"@{requester} Pipeline D 已实现并提交 PR：{pr_url or '(见上)'}\n\n"
            f"已将该 issue 交回给你验收。确认满足需求后请手动关闭；"
            f"如需修订，移除 `executed` 标签即可让 Pipeline D 下一轮重新处理。"
        )
    elif stage.lower() == "prod":
        # Prod marker comment is posted by feishu-inbound engine (Pipeline F Prod Handback).
        result["handback"] = "reassigned"
        result["removed_assignees"] = to_remove
        print(
            f"  Handback: issue {issue_repo}#{issue} reassigned to @{requester}"
            + (f" (removed {to_remove})" if to_remove else ""),
            file=sys.stderr,
        )
        return result
    elif stage.lower() == "f":
        comment = (
            f"@{requester} PR 已合入 dev 且 dev 环境 CI/CD 已成功：{pr_url or '(见上)'}\n\n"
            f"请在此 issue 上验收。确认满足需求后请手动关闭；"
            f"如需修订，移除 `executed` 标签即可让 Pipeline D 下一轮重新处理。"
        )
    else:
        comment = (
            f"@{requester} Pipeline E 已通过 dev 门审查：{pr_url or '(见上)'}\n\n"
            f"等待合入 dev 并部署成功后才会指派验收；本 comment 为 legacy stage={stage!r}。"
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
    parser.add_argument(
        "--handback-requester",
        action="store_true",
        help="(Legacy) Reassign issue to author after PR creation. Use Pipeline F "
        "(issue_dev_handback.py) after dev CI/CD instead.",
    )
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

    maybe_enforce_backend_openapi_gate(
        args.surface,
        surface,
        base_branch,
        branch_name,
        dry_run=args.dry_run,
    )

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
            args.issue, args.issue_repo, result, dry_run=args.dry_run, stage="d"
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sync ASP git worktrees to latest origin before feishu inbound analysis.

Operator-aware: surfaces the operator owns (via surfaces.yaml default_reviewers)
are skipped — local WIP is allowed. Non-owned surfaces use graceful degradation:
  SYNCED  — clean + ff-only succeeded (best case)
  FETCHED — dirty working tree, but git fetch updated remote refs (stale warning)
  SKIPPED — directory missing / network error / fetch failed (stale warning)

Usage:
    python tools/feishu_inbound/sync_worktrees.py --all
    python tools/feishu_inbound/sync_worktrees.py --all --operator 369795172
    python tools/feishu_inbound/sync_worktrees.py --surface app --dry-run
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ASP_ROOT = Path(__file__).resolve().parent.parent.parent
_SURFACES_YAML = _ASP_ROOT / "config" / "surfaces.yaml"
# Worktree paths in surfaces.yaml are relative to the workspace root that
# contains the actual git worktrees (rootgrove or equivalent).
_WORKTREE_ROOT = Path(
    os.getenv("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
).resolve()
_ALL_SURFACES = ("backend", "app", "admin", "wecom", "websites")
_DEFAULT_OPERATOR = "369795172"


@dataclass
class SyncResult:
    surface: str
    status: str  # "synced", "fetched", "skipped", "owned"
    message: str
    stale: bool = False


@dataclass
class SyncReport:
    results: list[SyncResult] = field(default_factory=list)

    @property
    def stale_surfaces(self) -> list[str]:
        return [r.surface for r in self.results if r.stale]

    @property
    def has_stale(self) -> bool:
        return any(r.stale for r in self.results)

    @property
    def all_ok(self) -> bool:
        return all(r.status in ("synced", "owned") for r in self.results)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
    )


def _load_surfaces() -> dict[str, Any]:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML required: pip install pyyaml") from e

    with open(_SURFACES_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("surfaces", {})


def operator_owned_surfaces(operator: str) -> set[str]:
    """Surfaces where operator is default_reviewer — skip sync, allow local WIP."""
    surfaces = _load_surfaces()
    owned: set[str] = set()
    for key, cfg in surfaces.items():
        reviewers = cfg.get("default_reviewers") or []
        if operator in [str(r) for r in reviewers]:
            owned.add(key)
    return owned


def resolve_worktree(local_path: str) -> Path:
    """Resolve a local_path from surfaces.yaml against the worktree root."""
    p = Path(local_path)
    return p.resolve() if p.is_absolute() else (_WORKTREE_ROOT / p).resolve()


def surfaces_to_sync(primary_surfaces: list[str]) -> list[str]:
    """Include backend when app/admin/wecom/websites need API code context."""
    keys: list[str] = []
    for s in primary_surfaces:
        if s in _ALL_SURFACES and s not in keys:
            keys.append(s)
    if any(s in ("app", "admin", "wecom", "websites") for s in keys) and "backend" not in keys:
        keys.insert(0, "backend")
    return keys or list(_ALL_SURFACES)


def sync_one(path: Path, base_branch: str, *, dry_run: bool = False) -> SyncResult:
    """Sync a single worktree with graceful degradation on dirty state."""
    surface = path.name

    if not path.is_dir():
        return SyncResult(surface, "skipped", f"missing directory: {path}", stale=True)

    git_marker = path / ".git"
    if not git_marker.exists():
        return SyncResult(surface, "skipped", f"not a git worktree: {path}", stale=True)

    status = _run(["git", "status", "--porcelain"], path)
    if status.returncode != 0:
        return SyncResult(surface, "skipped", status.stderr.strip() or "git status failed", stale=True)

    is_dirty = bool(status.stdout.strip())

    if dry_run:
        if is_dirty:
            return SyncResult(surface, "fetched", f"would fetch only (dirty working tree)", stale=True)
        return SyncResult(surface, "synced", f"would fetch + checkout {base_branch} + pull --ff-only")

    # Always fetch remote refs (safe: only updates .git/refs/remotes)
    fetch = _run(["git", "fetch", "origin"], path)
    if fetch.returncode != 0:
        msg = fetch.stderr.strip() or fetch.stdout.strip() or "git fetch failed"
        return SyncResult(surface, "skipped", f"fetch failed: {msg}", stale=True)

    if is_dirty:
        return SyncResult(
            surface, "fetched",
            "dirty working tree: fetched remote refs only",
            stale=True,
        )

    # Clean working tree: checkout + ff-only pull
    branch = _run(["git", "branch", "--show-current"], path)
    if branch.returncode != 0:
        return SyncResult(surface, "fetched", "git branch failed after fetch", stale=True)

    current = branch.stdout.strip()
    if current != base_branch:
        checkout = _run(["git", "checkout", base_branch], path)
        if checkout.returncode != 0:
            return SyncResult(
                surface, "fetched",
                f"cannot checkout {base_branch}: {checkout.stderr.strip()}",
                stale=True,
            )

    pull = _run(["git", "pull", "--ff-only", "origin", base_branch], path)
    if pull.returncode != 0:
        return SyncResult(
            surface, "fetched",
            f"pull --ff-only failed: {pull.stderr.strip()}",
            stale=True,
        )

    summary = (pull.stdout or pull.stderr or "").strip()
    return SyncResult(surface, "synced", summary or f"synced {base_branch}")


def sync_asp_worktrees(
    surfaces: list[str] | None = None,
    *,
    operator: str | None = None,
    dry_run: bool = False,
) -> SyncReport:
    """Sync ASP worktrees with graceful degradation. Never raises on dirty trees."""
    operator = (operator or os.getenv("GITHUB_ASSIGNEE") or _DEFAULT_OPERATOR).strip()
    owned = operator_owned_surfaces(operator)
    surfaces_cfg = _load_surfaces()
    targets = list(_ALL_SURFACES) if surfaces is None else surfaces_to_sync(surfaces)

    to_sync = [s for s in targets if s not in owned]
    skipped_owned = [s for s in targets if s in owned]

    report = SyncReport()

    for s in skipped_owned:
        report.results.append(SyncResult(s, "owned", "operator-owned, skip sync"))

    if skipped_owned:
        print(f"Operator {operator} — skip owned surfaces (local WIP OK): {', '.join(skipped_owned)}")

    if not to_sync:
        print("No remote worktrees to sync.")
        return report

    for key in to_sync:
        cfg = surfaces_cfg.get(key)
        if not cfg:
            report.results.append(SyncResult(key, "skipped", f"unknown surface: {key}", stale=True))
            continue
        path = resolve_worktree(str(cfg["local_path"]))
        base = str(cfg["base_branch"])
        result = sync_one(path, base, dry_run=dry_run)
        result.surface = key
        tag = result.status.upper()
        print(f"[{tag}] {key}: {path} → origin/{base} — {result.message}")
        report.results.append(result)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ASP worktrees before inbound analysis")
    parser.add_argument("--all", action="store_true", help="Consider all ASP surfaces")
    parser.add_argument("--surface", action="append", dest="surfaces", metavar="SURFACE")
    parser.add_argument(
        "--operator",
        default=None,
        help=f"GitHub login of analyst (default: GITHUB_ASSIGNEE or {_DEFAULT_OPERATOR})",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all or not args.surfaces:
        targets: list[str] | None = None
    else:
        targets = args.surfaces

    report = sync_asp_worktrees(targets, operator=args.operator, dry_run=args.dry_run)
    if report.has_stale:
        stale = ", ".join(report.stale_surfaces)
        print(f"\nWarning: stale surfaces (fetched remote refs only): {stale}")
        print("Analysis will proceed with stale code warning injected into prompt.")
    if not report.all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

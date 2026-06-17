"""Pipeline C/D scan scope — loaded from tools/feishu_inbound/config.yaml (SSOT)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from org_issues import (
    fetch_org_assigned_issues,
    fetch_repo_assigned_issues,
    issue_repo,
    issue_state_key,
    state_entry,
)
from routing import load_config

# Re-export helpers used by scanners
__all__ = [
    "PipelineCDScanConfig",
    "load_pipeline_cd_scan",
    "fetch_assigned_issues",
    "issue_repo",
    "issue_state_key",
    "state_entry",
    "describe_scan_scope",
]


@dataclass
class PipelineCDScanConfig:
    """Resolved scan scope for issue_scanner (C) and issue_executor (D)."""

    mode: str  # org | repo | repos
    org: str = "AI-MYG"
    repo: str | None = None
    repos: list[str] = field(default_factory=list)
    exclude_repos: list[str] = field(default_factory=list)
    limit: int = 100
    state: str = "open"
    assignee_default: str | None = None

    def summary(self) -> str:
        if self.mode == "org":
            base = f"org:{self.org} assignee:{{assignee}} is:{self.state}"
        elif self.mode == "repo":
            base = f"repo:{self.repo} assignee:{{assignee}} is:{self.state}"
        else:
            base = f"repos:{','.join(self.repos)} assignee:{{assignee}} is:{self.state}"
        if self.exclude_repos:
            base += f" exclude:{','.join(self.exclude_repos)}"
        return base


def load_pipeline_cd_scan(config: dict[str, Any] | None = None) -> PipelineCDScanConfig:
    """Load ``pipeline_cd_scan`` from config.yaml. Env may override org/limit only."""
    cfg = config if config is not None else load_config()
    block = cfg.get("pipeline_cd_scan") or {}
    gh = block.get("github") or {}

    mode = str(block.get("mode", "org")).strip().lower()
    if mode not in ("org", "repo", "repos"):
        raise ValueError(f"pipeline_cd_scan.mode must be org|repo|repos, got {mode!r}")

    org = (
        os.getenv("GITHUB_ORG")
        or gh.get("org")
        or cfg.get("github", {}).get("repo", "AI-MYG/asp").split("/")[0]
        or "AI-MYG"
    ).strip()

    limit = int(os.getenv("GITHUB_ORG_ISSUE_LIMIT") or gh.get("limit") or 100)
    state = str(gh.get("state", "open")).strip().lower()

    scan = PipelineCDScanConfig(
        mode=mode,
        org=org,
        repo=block.get("repo"),
        repos=list(block.get("repos") or []),
        exclude_repos=list(block.get("exclude_repos") or []),
        limit=limit,
        state=state,
        assignee_default=block.get("assignee") or cfg.get("assignee_routing", {}).get("cross_surface_default"),
    )

    if mode == "repo" and not scan.repo:
        scan.repo = "AI-MYG/asp-backend"
    if mode == "repos" and not scan.repos:
        raise ValueError("pipeline_cd_scan.mode=repos requires pipeline_cd_scan.repos list")

    return scan


def describe_scan_scope(scan: PipelineCDScanConfig, operator: str) -> str:
    return scan.summary().format(assignee=operator)


def _apply_excludes(issues: list[dict[str, Any]], scan: PipelineCDScanConfig) -> list[dict[str, Any]]:
    if not scan.exclude_repos:
        return issues
    excluded = set(scan.exclude_repos)
    return [i for i in issues if issue_repo(i) not in excluded]


def fetch_assigned_issues(
    operator: str,
    *,
    config: dict[str, Any] | None = None,
    scan: PipelineCDScanConfig | None = None,
    issue_number: int | None = None,
    repo: str | None = None,
    label: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch issues per ``pipeline_cd_scan`` in config.yaml."""
    scan = scan or load_pipeline_cd_scan(config)

    if scan.mode == "org":
        issues = fetch_org_assigned_issues(
            operator,
            issue_number=issue_number,
            repo=repo,
            label=label,
            org=scan.org,
            limit=scan.limit,
            state=scan.state,
        )
    elif scan.mode == "repo":
        target = repo or scan.repo
        if not target:
            raise ValueError("pipeline_cd_scan.repo is not set")
        issues = fetch_repo_assigned_issues(
            operator,
            target,
            issue_number=issue_number,
            label=label,
            limit=scan.limit,
            state=scan.state,
        )
    else:
        if issue_number is not None:
            if not repo:
                raise ValueError("--repo owner/name required with --issue when mode=repos")
            issues = fetch_repo_assigned_issues(
                operator,
                repo,
                issue_number=issue_number,
                label=label,
                limit=scan.limit,
                state=scan.state,
            )
        else:
            seen: set[str] = set()
            issues = []
            for r in scan.repos:
                batch = fetch_repo_assigned_issues(
                    operator,
                    r,
                    label=label,
                    limit=scan.limit,
                    state=scan.state,
                )
                for item in batch:
                    key = issue_state_key(item)
                    if key not in seen:
                        seen.add(key)
                        issues.append(item)

    return _apply_excludes(issues, scan)

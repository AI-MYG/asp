"""Fetch GitHub issues assigned to an operator across an entire org."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

from routing import run_gh

_API_REPO_RE = re.compile(r"/repos/([^/]+/[^/]+?)/?$")
_GITHUB_REPO_RE = re.compile(r"github\.com/([^/]+/[^/]+?)(?:\.git)?/?$")


def github_org(*, org: str | None = None) -> str:
    if org:
        return org.strip()
    return (
        os.getenv("GITHUB_ORG")
        or os.getenv("OBSERVER_GITHUB_ORG")
        or "AI-MYG"
    ).strip()


def repo_from_repository_url(repository_url: str) -> str:
    url = repository_url or ""
    m = _API_REPO_RE.search(url)
    if m:
        return m.group(1)
    m = _GITHUB_REPO_RE.search(url)
    if m:
        return m.group(1)
    path = urlparse(url).path.strip("/")
    if path.startswith("repos/") and path.count("/") >= 2:
        parts = path.split("/")
        return f"{parts[1]}/{parts[2]}"
    if path.count("/") >= 1:
        parts = path.split("/")
        return f"{parts[0]}/{parts[1]}"
    raise ValueError(f"Cannot parse repository URL: {repository_url!r}")


def issue_repo(issue: dict[str, Any]) -> str:
    """Return owner/repo for an issue dict."""
    if repo := issue.get("repo"):
        return str(repo)
    if repository := issue.get("repository"):
        if isinstance(repository, str):
            return repository
        if name := repository.get("nameWithOwner"):
            return str(name)
    if url := issue.get("repository_url"):
        return repo_from_repository_url(str(url))
    raise ValueError(f"Issue #{issue.get('number')} missing repository metadata")


def issue_state_key(issue: dict[str, Any]) -> str:
    return f"{issue_repo(issue)}#{issue['number']}"


def state_entry(state: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any] | None:
    key = issue_state_key(issue)
    if key in state:
        return state[key]
    legacy = str(issue["number"])
    return state.get(legacy)


def normalize_search_item(item: dict[str, Any]) -> dict[str, Any]:
    """Map GitHub search API item → issue_scanner/executor shape."""
    labels = item.get("labels", [])
    if labels and isinstance(labels[0], dict):
        label_objs = labels
    else:
        label_objs = [{"name": lb} if isinstance(lb, str) else lb for lb in labels]

    assignees = item.get("assignees") or []
    if item.get("assignee") and not assignees:
        assignees = [item["assignee"]]

    user = item.get("user") or {}
    return {
        "number": item["number"],
        "title": item.get("title", ""),
        "body": item.get("body") or "",
        "labels": label_objs,
        "createdAt": item.get("created_at", ""),
        "updatedAt": item.get("updated_at", ""),
        "state": (item.get("state") or "open").upper(),
        "url": item.get("html_url", ""),
        "comments": item.get("comments", 0),
        "assignees": assignees,
        "author": {"login": user.get("login", "unknown")},
        "repo": repo_from_repository_url(item.get("repository_url", "")),
        "repository": {"nameWithOwner": repo_from_repository_url(item.get("repository_url", ""))},
    }


def _search_issues(query: str, *, limit: int = 100) -> list[dict[str, Any]]:
    per_page = min(100, max(1, limit))
    items: list[dict[str, Any]] = []
    page = 1
    while len(items) < limit:
        raw = run_gh(
            "api",
            f"search/issues?q={query}&per_page={per_page}&page={page}",
            check=True,
        )
        data = json.loads(raw)
        batch = data.get("items", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return [normalize_search_item(i) for i in items[:limit]]


def _issue_list_json_fields() -> str:
    return "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author"


def fetch_repo_assigned_issues(
    operator: str,
    repo: str,
    *,
    issue_number: int | None = None,
    label: str | None = None,
    limit: int = 100,
    state: str = "open",
) -> list[dict[str, Any]]:
    """Open issues in one repo assigned to operator."""
    fields = _issue_list_json_fields()
    if issue_number is not None:
        raw = run_gh(
            "issue",
            "view",
            str(issue_number),
            "-R",
            repo,
            "--json",
            fields,
        )
        issue = json.loads(raw)
        if issue.get("state", "").upper() != "OPEN":
            raise ValueError(f"Issue #{issue_number} in {repo} is not open")
        issue["repo"] = repo
        issue["repository"] = {"nameWithOwner": repo}
        return [issue]

    args = [
        "issue",
        "list",
        "-R",
        repo,
        "--assignee",
        operator,
        "--state",
        state,
        "--json",
        fields,
        "--limit",
        str(min(100, limit)),
    ]
    if label:
        args.extend(["--label", label])
    raw = run_gh(*args)
    issues = json.loads(raw)
    for issue in issues:
        issue["repo"] = repo
        issue["repository"] = {"nameWithOwner": repo}
    return issues


def fetch_org_assigned_issues(
    operator: str,
    *,
    issue_number: int | None = None,
    repo: str | None = None,
    label: str | None = None,
    limit: int | None = None,
    org: str | None = None,
    state: str = "open",
) -> list[dict[str, Any]]:
    """Open issues in org assigned to ``operator`` (user id or login)."""
    org_name = github_org(org=org)
    max_items = int(os.getenv("GITHUB_ORG_ISSUE_LIMIT", "100"))
    if limit is not None:
        max_items = limit
    state_q = "open" if state.lower() == "open" else state

    if issue_number is not None:
        target_repo = repo
        if not target_repo:
            q = f"org:{org_name}+assignee:{operator}+is:{state_q}"
            if label:
                q += f"+label:{label}"
            matches = [
                i for i in _search_issues(q, limit=max_items)
                if i["number"] == issue_number
            ]
            if not matches:
                raise ValueError(
                    f"Issue #{issue_number} not found among {state_q} issues assigned to "
                    f"{operator} in {org_name}"
                )
            if len(matches) > 1 and not repo:
                repos = ", ".join(issue_repo(m) for m in matches)
                raise ValueError(
                    f"Issue #{issue_number} is ambiguous across repos: {repos}. Pass --repo owner/name"
                )
            return matches[:1]

        raw = run_gh(
            "issue",
            "view",
            str(issue_number),
            "-R",
            target_repo,
            "--json",
            "number,title,body,labels,createdAt,updatedAt,state,url,comments,assignees,author",
        )
        issue = json.loads(raw)
        if issue.get("state", "").upper() != "OPEN":
            raise ValueError(f"Issue #{issue_number} in {target_repo} is not open")
        issue["repo"] = target_repo
        issue["repository"] = {"nameWithOwner": target_repo}
        return [issue]

    q = f"org:{org_name}+assignee:{operator}+is:{state_q}"
    if label:
        q += f"+label:{label}"
    return _search_issues(q, limit=max_items)


def fetch_org_labeled_issues(
    *,
    org: str | None = None,
    include_labels: list[str] | None = None,
    exclude_labels: list[str] | None = None,
    issue_number: int | None = None,
    repo: str | None = None,
    limit: int | None = None,
    state: str = "open",
) -> list[dict[str, Any]]:
    """Open issues in org matching label filters (no assignee requirement)."""
    org_name = github_org(org=org)
    max_items = int(os.getenv("GITHUB_ORG_ISSUE_LIMIT", "100"))
    if limit is not None:
        max_items = limit
    state_q = "open" if state.lower() == "open" else state

    q = f"org:{org_name}+is:{state_q}"
    for lb in include_labels or []:
        q += f"+label:{lb}"
    for lb in exclude_labels or []:
        q += f"+-label:{lb}"

    if issue_number is not None:
        matches = [i for i in _search_issues(q, limit=max_items) if i["number"] == issue_number]
        if not matches:
            raise ValueError(
                f"Issue #{issue_number} not found for query {q!r} in {org_name}"
            )
        if repo:
            matches = [m for m in matches if issue_repo(m) == repo]
            if not matches:
                raise ValueError(f"Issue #{issue_number} not found in {repo}")
        elif len(matches) > 1:
            repos = ", ".join(issue_repo(m) for m in matches)
            raise ValueError(
                f"Issue #{issue_number} is ambiguous across repos: {repos}. Pass --repo"
            )
        return matches[:1]

    return _search_issues(q, limit=max_items)


def fetch_org_labeled_issues(
    *,
    org: str | None = None,
    include_labels: list[str] | None = None,
    exclude_labels: list[str] | None = None,
    issue_number: int | None = None,
    repo: str | None = None,
    limit: int | None = None,
    state: str = "open",
) -> list[dict[str, Any]]:
    """Open issues in org matching label filters (no assignee requirement)."""
    org_name = github_org(org=org)
    max_items = int(os.getenv("GITHUB_ORG_ISSUE_LIMIT", "100"))
    if limit is not None:
        max_items = limit
    state_q = "open" if state.lower() == "open" else state

    q = f"org:{org_name}+is:{state_q}"
    for lb in include_labels or []:
        q += f"+label:{lb}"
    for lb in exclude_labels or []:
        q += f"+-label:{lb}"

    if issue_number is not None:
        matches = [i for i in _search_issues(q, limit=max_items) if i["number"] == issue_number]
        if not matches:
            raise ValueError(
                f"Issue #{issue_number} not found for query {q!r} in {org_name}"
            )
        if repo:
            matches = [m for m in matches if issue_repo(m) == repo]
            if not matches:
                raise ValueError(f"Issue #{issue_number} not found in {repo}")
        elif len(matches) > 1:
            repos = ", ".join(issue_repo(m) for m in matches)
            raise ValueError(
                f"Issue #{issue_number} is ambiguous across repos: {repos}. Pass --repo"
            )
        return matches[:1]

    return _search_issues(q, limit=max_items)

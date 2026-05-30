"""Deterministic routing helpers for feishu-inbound issues (surface, scope, assignee, duplicates)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "config.yaml"
REPO = "AI-MYG/asp"

ASSIGNEE_NAMES = {
    "369795172": "袁牧",
    "1401554949": "胡剑飞",
}

# Reverse lookup: Chinese name / common alias → GitHub user ID
_NAME_TO_ID: dict[str, str] = {
    "袁牧": "369795172",
    "胡剑飞": "1401554949",
}


def _extract_executor_from_body(body: str) -> str | None:
    """Parse '执行人员: XXX' from Feishu inbound issue body. Returns GitHub user ID or None."""
    m = re.search(r"执行人员[:：]\s*(.+)", body)
    if not m:
        return None
    name = m.group(1).strip()
    return _NAME_TO_ID.get(name)


def run_gh(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh failed: {' '.join(args)}")
    return result.stdout.strip()


def load_config() -> dict[str, Any]:
    try:
        import yaml

        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        return {
            "surface_routing": {
                "backend": {
                    "keywords": ["后端", "API", "接口", "数据库", "服务端", "backend", "endpoint", "migration"],
                    "label": "backend",
                },
                "admin": {
                    "keywords": ["管理端", "管理后台", "admin", "后台管理", "运营端"],
                    "label": "admin",
                },
                "app": {
                    "keywords": ["APP", "Flutter", "移动端", "客户端", "app端", "安卓", "iOS", "儿童端"],
                    "label": "app",
                },
                "websites": {
                    "keywords": ["官网", "landing", "website", "落地页", "静态页"],
                    "label": "websites",
                },
                "wecom": {
                    "keywords": ["企微", "企业微信", "wecom", "侧边栏"],
                    "label": "wecom",
                },
            },
            "assignee_routing": {
                "backend": "369795172",
                "wecom": "369795172",
                "websites": "369795172",
                "app": "1401554949",
                "admin": "1401554949",
                "cross_surface_default": "369795172",
            },
        }


def detect_surface(title: str, body: str, config: dict[str, Any]) -> list[str]:
    text = f"{title} {body}".lower()
    surfaces: list[str] = []
    for _surface_name, surface_cfg in config.get("surface_routing", {}).items():
        for kw in surface_cfg.get("keywords", []):
            if kw.lower() in text:
                label = surface_cfg.get("label", _surface_name)
                if label not in surfaces:
                    surfaces.append(label)
                break
    return surfaces


def estimate_scope(surfaces: list[str], title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    if len(surfaces) >= 3 or any(kw in text for kw in ["重构", "架构", "迁移", "全量"]):
        return "L"
    if len(surfaces) >= 2 or any(kw in text for kw in ["新增", "优化", "feature"]):
        return "M"
    return "S"


def resolve_assignee(surfaces: list[str], config: dict[str, Any], body: str = "") -> str | None:
    """Resolve assignee. Priority: explicit 执行人员 in body > surface routing."""
    explicit = _extract_executor_from_body(body)
    if explicit:
        return explicit

    routing = config.get("assignee_routing", {})
    if not surfaces:
        return None

    assignees = {routing[s] for s in surfaces if routing.get(s)}
    if len(assignees) == 1:
        return assignees.pop()
    if len(assignees) > 1:
        return routing.get("cross_surface_default")
    return None


def search_duplicates(title: str) -> list[dict[str, Any]]:
    clean_title = title.replace("[feishu]", "").strip()
    words = [w for w in re.split(r"\s+", clean_title) if len(w) > 1][:3]
    if not words:
        return []

    raw = run_gh(
        "issue", "list",
        "-R", REPO,
        "--search", " ".join(words),
        "--state", "open",
        "--json", "number,title,labels,state",
        "--limit", "5",
    )
    candidates = json.loads(raw)
    return [
        c for c in candidates
        if "feishu-inbound" not in [lb["name"] for lb in c.get("labels", [])]
    ]


DIFFICULTY_TIERS = ("trivial", "standard", "complex")

DIFFICULTY_ROUTING_PROFILES = {
    "trivial": "quick_triage",
    "standard": "analysis",
    "complex": "architecture_decision",
}

DIFFICULTY_LABEL_SPECS: dict[str, tuple[str, str]] = {
    "difficulty-trivial": ("5B9F3B", "Scope S, single surface — quick_triage profile"),
    "difficulty-standard": ("FBCA04", "Typical single-surface work — analysis profile"),
    "difficulty-complex": ("D93F0B", "Cross-surface / L scope — architecture_decision profile"),
    "analysis-in-progress": ("1D76DB", "Issue is being analyzed by an agent (mutex lock)"),
    "analysis-failed": ("B60205", "Agent analysis failed validation — needs manual review"),
}


def ensure_difficulty_labels(dry_run: bool = False) -> None:
    """Create difficulty-* labels in GitHub repo if missing (idempotent)."""
    if dry_run:
        return
    for name, (color, description) in DIFFICULTY_LABEL_SPECS.items():
        try:
            run_gh(
                "label", "create", name,
                "-R", REPO,
                "--color", color,
                "--description", description,
                check=False,
            )
        except RuntimeError:
            pass


def classify_difficulty(scope: str, surfaces: list[str]) -> str:
    n = len(surfaces)
    if scope == "L" or n >= 3:
        return "complex"
    if scope == "M" and n >= 2:
        return "complex"
    if scope == "M" and n <= 1:
        return "standard"
    if scope == "S" and n >= 2:
        return "standard"
    return "trivial"


def preflight_routing(issue: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run deterministic routing for one issue."""
    config = config or load_config()
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    surfaces = detect_surface(title, body, config)
    scope = estimate_scope(surfaces, title, body)
    assignee = resolve_assignee(surfaces, config, body)
    duplicates = search_duplicates(title)
    difficulty = classify_difficulty(scope, surfaces)
    labels = list(surfaces) + [f"scope-{scope.lower()}", f"difficulty-{difficulty}"]

    return {
        "surfaces": surfaces,
        "scope": scope,
        "difficulty": difficulty,
        "routing_profile": DIFFICULTY_ROUTING_PROFILES[difficulty],
        "assignee": assignee,
        "assignee_name": ASSIGNEE_NAMES.get(assignee, assignee) if assignee else None,
        "duplicates": duplicates,
        "labels": labels,
    }


def format_routing_section(routing: dict[str, Any]) -> str:
    lines = ["## Routing", ""]
    if routing["surfaces"]:
        lines.append(f"- **Surface**: {', '.join(routing['surfaces'])}")
    else:
        lines.append("- **Surface**: ⚠️ 未检测到，需手动分配")
    lines.append(f"- **Scope**: {routing['scope']}")
    lines.append(f"- **Difficulty**: {routing.get('difficulty', 'standard')} → profile `{routing.get('routing_profile', 'analysis')}`")
    if routing["assignee"]:
        name = routing["assignee_name"] or routing["assignee"]
        lines.append(f"- **Assignee**: @{routing['assignee']} ({name})")
    else:
        lines.append("- **Assignee**: ⚠️ 需手动分配")
    if routing["duplicates"]:
        lines.append("\n**Potential duplicates**:")
        for dup in routing["duplicates"]:
            lines.append(f"- #{dup['number']}: {dup['title']}")
    return "\n".join(lines)

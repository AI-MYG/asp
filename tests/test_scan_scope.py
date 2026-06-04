"""Tests for pipeline_cd_scan config loading."""

from __future__ import annotations

import sys
from pathlib import Path

_ASP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_ASP_ROOT / "tools" / "feishu_inbound"))

from scan_scope import load_pipeline_cd_scan  # noqa: E402


def test_default_org_mode_from_config_file():
    scan = load_pipeline_cd_scan()
    assert scan.mode == "org"
    assert scan.org == "AI-MYG"
    assert scan.limit == 100


def test_repo_mode_override():
    scan = load_pipeline_cd_scan({
        "pipeline_cd_scan": {
            "mode": "repo",
            "repo": "AI-MYG/asp-app",
        },
    })
    assert scan.mode == "repo"
    assert scan.repo == "AI-MYG/asp-app"


def test_repos_mode_requires_list():
    import pytest

    with pytest.raises(ValueError, match="repos list"):
        load_pipeline_cd_scan({"pipeline_cd_scan": {"mode": "repos", "repos": []}})

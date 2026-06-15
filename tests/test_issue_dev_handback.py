"""Tests for Pipeline F dev handback eligibility (no gh/network)."""

from __future__ import annotations

import sys
from pathlib import Path

_ASP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_ASP_ROOT / "tools" / "feishu_inbound"))

from tools.feishu_inbound import issue_dev_handback as f  # noqa: E402


def _issue(labels: list[str], number: int = 125) -> dict:
    return {
        "number": number,
        "labels": [{"name": n} for n in labels],
        "title": "test",
        "repo": "AI-MYG/asp-backend",
    }


class TestEligibility:
    def test_skip_without_review_pass(self):
        status, _ = f.eligibility(_issue(["executed"]))
        assert status == "skip_no_pass"

    def test_skip_when_already_ready(self):
        status, _ = f.eligibility(_issue(["review-dev-pass", "ready-for-acceptance"]))
        assert status == "skip_ready"

    def test_skip_when_no_merged_pr(self, monkeypatch):
        monkeypatch.setattr(f, "_find_linked_pr", lambda *a, **k: None)
        status, _ = f.eligibility(_issue(["review-dev-pass"]))
        assert status == "skip_no_pr"

    def test_skip_cicd_pending(self, monkeypatch):
        monkeypatch.setattr(
            f,
            "_find_linked_pr",
            lambda *a, **k: {"number": 9, "url": "http://pr/9"},
        )
        monkeypatch.setattr(
            f,
            "_pr_merge_info",
            lambda repo, n: {"sha": "abc123", "url": "http://pr/9"},
        )
        monkeypatch.setattr(f, "_dev_cicd_workflow", lambda repo: "Backend Dev Test Container")
        monkeypatch.setattr(f, "dev_cicd_conclusion", lambda *a, **k: None)

        status, detail = f.eligibility(_issue(["review-dev-pass"]))
        assert status == "skip_cicd_pending"
        assert detail is not None
        assert detail["workflow"] == "Backend Dev Test Container"

    def test_ready_when_cicd_success(self, monkeypatch):
        monkeypatch.setattr(
            f,
            "_find_linked_pr",
            lambda *a, **k: {"number": 9, "url": "http://pr/9"},
        )
        monkeypatch.setattr(
            f,
            "_pr_merge_info",
            lambda repo, n: {"sha": "abc123", "url": "http://pr/9"},
        )
        monkeypatch.setattr(f, "_dev_cicd_workflow", lambda repo: "Backend Dev Test Container")
        monkeypatch.setattr(f, "dev_cicd_conclusion", lambda *a, **k: "success")

        status, detail = f.eligibility(_issue(["review-dev-pass"]))
        assert status == "ready"
        assert detail["conclusion"] == "success"

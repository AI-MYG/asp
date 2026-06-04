"""Tests for Smart PR handback-to-requester logic (no network / gh calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ASP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ASP_ROOT))

from tools import smart_pr  # noqa: E402


class _Recorder:
    """Stub for smart_pr.run that records commands and returns canned issue JSON."""

    def __init__(self, issue_json: str = "") -> None:
        self.issue_json = issue_json
        self.calls: list[tuple[list[str], bool]] = []

    def __call__(self, cmd, *, cwd=None, check=True, dry_run=False):
        self.calls.append((cmd, dry_run))
        if cmd[:3] == ["gh", "issue", "view"]:
            return self.issue_json
        return ""

    def first(self, *prefix: str) -> list[str] | None:
        for cmd, _ in self.calls:
            if cmd[: len(prefix)] == list(prefix):
                return cmd
        return None


class TestHandback:
    def test_human_author_reassigned_and_removes_lead(self, monkeypatch):
        issue_json = json.dumps({
            "author": {"login": "Aldeigia-GJ", "is_bot": False},
            "assignees": [{"login": "369795172"}],
        })
        rec = _Recorder(issue_json)
        monkeypatch.setattr(smart_pr, "run", rec)

        out = smart_pr.handback_to_requester(14, "AI-MYG/asp", "http://pr/1")

        assert out["handback"] == "reassigned"
        assert out["requester"] == "Aldeigia-GJ"
        assert out["removed_assignees"] == ["369795172"]

        edit = rec.first("gh", "issue", "edit")
        assert edit is not None
        assert "--add-assignee" in edit and "Aldeigia-GJ" in edit
        assert "--remove-assignee" in edit and "369795172" in edit
        assert rec.first("gh", "issue", "comment") is not None

    def test_bot_author_is_skipped(self, monkeypatch):
        issue_json = json.dumps({
            "author": {"login": "app/github-actions", "is_bot": True},
            "assignees": [],
        })
        rec = _Recorder(issue_json)
        monkeypatch.setattr(smart_pr, "run", rec)

        out = smart_pr.handback_to_requester(12, "AI-MYG/asp", "")

        assert out["handback"] == "skipped"
        assert rec.first("gh", "issue", "edit") is None
        assert rec.first("gh", "issue", "comment") is None

    def test_author_already_sole_assignee_no_removal(self, monkeypatch):
        issue_json = json.dumps({
            "author": {"login": "Aldeigia-GJ", "is_bot": False},
            "assignees": [{"login": "Aldeigia-GJ"}],
        })
        rec = _Recorder(issue_json)
        monkeypatch.setattr(smart_pr, "run", rec)

        out = smart_pr.handback_to_requester(14, "AI-MYG/asp", "http://pr/1")

        assert out["handback"] == "reassigned"
        assert out["removed_assignees"] == []
        edit = rec.first("gh", "issue", "edit")
        assert edit is not None and "--remove-assignee" not in edit

    def test_dry_run_does_not_mutate(self, monkeypatch):
        issue_json = json.dumps({
            "author": {"login": "Aldeigia-GJ", "is_bot": False},
            "assignees": [{"login": "369795172"}],
        })
        rec = _Recorder(issue_json)
        monkeypatch.setattr(smart_pr, "run", rec)

        out = smart_pr.handback_to_requester(14, "AI-MYG/asp", "http://pr/1", dry_run=True)

        assert out["handback"] == "reassigned"
        edit = rec.first("gh", "issue", "edit")
        comment = rec.first("gh", "issue", "comment")
        # mutating commands are issued with dry_run=True (run() no-ops them)
        assert (edit, True) in rec.calls
        assert (comment, True) in rec.calls

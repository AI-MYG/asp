"""Regression tests for Pipeline E gate reviewer — pure decision logic.

These tests avoid any network / gh / agent calls: they exercise the verdict
parser, the gate state machine, and the review-model mutual-exclusion rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make tools importable — asp-infra project root + feishu_inbound dir
_ASP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ASP_ROOT))
sys.path.insert(0, str(_ASP_ROOT / "scripts"))
sys.path.insert(0, str(_ASP_ROOT / "tools" / "feishu_inbound"))

from tools.feishu_inbound import issue_pr_reviewer as e  # noqa: E402


def _issue(labels: list[str], number: int = 41) -> dict:
    return {"number": number, "labels": [{"name": n} for n in labels],
            "title": "t", "repo": "AI-MYG/asp-backend"}


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------
class TestParseVerdict:
    def test_pass_cn(self):
        assert e.parse_verdict("结论: 通过\n**摘要**: ok") == "pass"

    def test_pass_cn_fullwidth_colon(self):
        assert e.parse_verdict("结论：通过") == "pass"

    def test_changes_cn(self):
        assert e.parse_verdict("结论: 打回\nblocking issue") == "changes"

    def test_pass_en(self):
        assert e.parse_verdict("Verdict: PASS") == "pass"

    def test_changes_en(self):
        assert e.parse_verdict("VERDICT: changes") == "changes"

    def test_unknown_when_no_verdict(self):
        assert e.parse_verdict("some free text without a verdict") == "unknown"

    def test_unknown_empty(self):
        assert e.parse_verdict("") == "unknown"

    def test_first_verdict_line_wins(self):
        text = "结论: 通过\n后面提到 打回 这个词不应影响"
        assert e.parse_verdict(text) == "pass"


# ---------------------------------------------------------------------------
# Review model mutual exclusion (review model != executor model)
# ---------------------------------------------------------------------------
class TestReviewModelSelection:
    def test_default_differs_from_glm_executor(self):
        m = e.pick_review_model("glm-5.1")
        assert m != "glm-5.1"

    def test_falls_back_when_executor_is_default(self):
        # When executor used the default review model, pick a different one.
        m = e.pick_review_model(e._DEFAULT_REVIEW_MODEL)
        assert m != e._DEFAULT_REVIEW_MODEL

    def test_unknown_executor_uses_default(self):
        assert e.pick_review_model(None) == e._DEFAULT_REVIEW_MODEL

    def test_result_in_pool_or_default(self):
        for exe in ("glm-5.1", "claude-sonnet-4-20250514", None, "other"):
            m = e.pick_review_model(exe)
            assert m and m != exe or exe is None


class TestExecutorModelParse:
    def test_parse_from_pr_body(self):
        body = "Closes AI-MYG/asp#41\n\n**Implemented by**: `opencode/glm-5.1`\n\n🤖"
        assert e._executor_model_from_pr(body) == "glm-5.1"

    def test_parse_without_executor_prefix(self):
        body = "**Implemented by**: `glm-5.1`"
        assert e._executor_model_from_pr(body) == "glm-5.1"

    def test_none_when_missing(self):
        assert e._executor_model_from_pr("no model line here") is None


# ---------------------------------------------------------------------------
# Gate state machine (needs_review)
# ---------------------------------------------------------------------------
class TestNeedsReview:
    def test_review_when_executed_and_pr(self):
        assert e.needs_review(_issue(["executed"]), {"number": 1}, force=False) == "review"

    def test_skip_no_executed(self):
        assert e.needs_review(_issue(["analyzed"]), {"number": 1}, force=False) == "skip_no_executed"

    def test_skip_already_passed(self):
        assert e.needs_review(
            _issue(["executed", "review-dev-pass"]), {"number": 1}, force=False
        ) == "skip_passed"

    def test_skip_locked(self):
        assert e.needs_review(
            _issue(["executed", "review-in-progress"]), {"number": 1}, force=False
        ) == "skip_locked"

    def test_skip_no_pr(self):
        assert e.needs_review(_issue(["executed"]), None, force=False) == "skip_no_pr"

    def test_force_reviews_even_without_executed(self):
        # force bypasses executed/passed gates but still needs a PR
        assert e.needs_review(_issue(["review-dev-pass"]), {"number": 1}, force=True) == "review"

    def test_force_still_blocked_by_lock(self):
        assert e.needs_review(
            _issue(["review-in-progress"]), {"number": 1}, force=True
        ) == "skip_locked"


# ---------------------------------------------------------------------------
# Business message + summary extraction
# ---------------------------------------------------------------------------
class TestMessaging:
    def test_summary_extraction(self):
        text = "结论: 通过\n**摘要**: 课程解锁修复达标，可合并\n**审查维度**:"
        assert e._summary_from_review(text) == "课程解锁修复达标，可合并"

    def test_summary_empty_when_missing(self):
        assert e._summary_from_review("结论: 通过") == ""

    def test_business_message_pass_has_no_merge(self):
        issue = _issue(["executed"])
        pr = {"url": "https://github.com/AI-MYG/asp-backend/pull/9", "number": 9}
        msg = e._business_message(issue, pr, "pass", "达标")
        assert "通过" in msg and "不自动合并" in msg

    def test_business_message_changes_routes_to_d(self):
        issue = _issue(["executed"])
        pr = {"url": "u", "number": 9}
        msg = e._business_message(issue, pr, "changes", "有 blocking")
        assert "打回" in msg and "Pipeline D" in msg

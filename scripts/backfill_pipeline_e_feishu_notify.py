#!/usr/bin/env python3
"""Backfill Pipeline E Feishu notifications for issues that already have review-dev-pass.

Use when E applied labels/comments but notify_feishu crashed (e.g. _notify NameError).

Usage:
    source scripts/load_asp_env.sh
    python scripts/backfill_pipeline_e_feishu_notify.py --dry-run
    python scripts/backfill_pipeline_e_feishu_notify.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
from asp_env import load_keychain_env  # noqa: E402

import completion_notify as notify  # noqa: E402

REVIEW_PASS = "review-dev-pass"


def _tts_open_id() -> str:
    return (
        os.getenv("TTS_BROADCAST_FEISHU_OPEN_ID")
        or os.getenv("FI_PERSONAL_FEISHU_OPEN_ID")
        or os.getenv("PIPELINE_E_FEISHU_OPEN_ID")
        or ""
    ).strip()


def _ic_open_id() -> str:
    return (os.getenv("IC_FEISHU_OPEN_ID") or "").strip()


def gh_json(*args: str):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout)
    return json.loads(r.stdout)


def linked_pr(repo: str, issue_num: int, central: int | None = None) -> dict | None:
    numbers = [issue_num]
    if central and central != issue_num:
        numbers.append(central)

    for state in ("open", "merged"):
        raw = subprocess.run(
            ["gh", "pr", "list", "-R", repo, "--state", state, "--limit", "100",
             "--json", "number,state,headRefName,url,baseRefName"],
            capture_output=True, text=True, timeout=60,
        )
        if raw.returncode != 0:
            continue
        prs = json.loads(raw.stdout)
        for n in numbers:
            prefix = f"issue-{n}/"
            for pr in prs:
                if pr.get("headRefName", "").startswith(prefix):
                    return pr
    return None


def central_from_body(body: str) -> int | None:
    import re

    m = re.search(r"AI-MYG/asp#(\d+)", body or "")
    return int(m.group(1)) if m else None


def build_message(repo: str, issue: dict, pr: dict) -> str:
    num = issue["number"]
    title = issue.get("title", "")
    central = central_from_body(issue.get("body", "") or "")
    central_line = f"\n中央需求：AI-MYG/asp#{central}" if central else ""
    return (
        "【ASP Pipeline E】✅ 通过 dev 门（补发通知）\n"
        f"需求：{title}\n"
        f"Repo：{repo}#{num}{central_line}\n"
        f"PR：{pr.get('url', '')}\n"
        "结论：Pipeline E 已通过，此前飞书通知因引擎回归未送达。\n"
        "下一步：等你人工合入 dev（E 不自动合并）。"
    )


def send_notify(msg: str, *, dry_run: bool) -> str:
    """Personal bot: TTS_BROADCAST webhook (signed) preferred; DM needs app-scoped open_id."""
    app_id = (
        os.getenv("PIPELINE_E_FEISHU_APP_ID")
        or os.getenv("TTS_BROADCAST_FEISHU_APP_ID")
        or os.getenv("FEISHU_DM_APP_ID")
        or ""
    )
    app_secret = (
        os.getenv("PIPELINE_E_FEISHU_APP_SECRET")
        or os.getenv("TTS_BROADCAST_FEISHU_APP_SECRET")
        or os.getenv("FEISHU_DM_APP_SECRET")
        or ""
    )
    ic_app = os.getenv("IC_FEISHU_APP_ID", "")
    if app_id and app_id == ic_app:
        open_id = _ic_open_id()
    else:
        open_id = _tts_open_id()
    webhook = os.getenv("PIPELINE_E_FEISHU_WEBHOOK") or os.getenv("TTS_BROADCAST_FEISHU_WEBHOOK") or ""
    sign_secret = os.getenv("TTS_BROADCAST_FEISHU_SIGN_SECRET") or ""

    if dry_run:
        if app_id and open_id:
            notify.send_feishu_dm(app_id, app_secret, open_id, msg, dry_run=True)
        if webhook:
            print(f"[DRY RUN] Feishu webhook:\n{msg}\n")
        return "dry_run"

    if app_id and app_secret and open_id:
        try:
            notify.send_feishu_dm(app_id, app_secret, open_id, msg, dry_run=False)
            return "dm"
        except Exception as e:
            print(f"  DM failed ({e}); trying webhook fallback")

    if webhook:
        root = REPO_ROOT.parent.parent
        sys.path.insert(0, str(root / "periodic_jobs"))
        from feishu_interactive_push import push_feishu  # noqa: WPS433

        push_feishu(webhook, sign_secret or None, text=msg)
        return "webhook"

    raise RuntimeError("No working Feishu channel (DM or webhook)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Pipeline E Feishu notifications")
    parser.add_argument("--repo", default="AI-MYG/asp-backend")
    parser.add_argument("--assignee", default=os.getenv("GITHUB_ASSIGNEE", "369795172"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_keychain_env()

    issues = gh_json(
        "issue", "list", "-R", args.repo,
        "--label", REVIEW_PASS, "--state", "open",
        "--assignee", args.assignee,
        "--json", "number,title,body,labels",
    )
    if not issues:
        print(f"No open {REVIEW_PASS} issues for {args.assignee} in {args.repo}")
        return

    sent = 0
    for issue in issues:
        num = issue["number"]
        central = central_from_body(issue.get("body", "") or "")
        pr = linked_pr(args.repo, num, central)
        if not pr:
            print(f"  #{num}: no linked PR, skip")
            continue
        msg = build_message(args.repo, issue, pr)
        print(f"  #{num}: notify ({'dry-run' if args.dry_run else 'send'})")
        ch = send_notify(msg, dry_run=args.dry_run)
        print(f"    channel: {ch}")
        sent += 1

    print(f"Done: {sent}/{len(issues)} notifications")


if __name__ == "__main__":
    main()

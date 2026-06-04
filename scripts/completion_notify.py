#!/usr/bin/env python3
"""ASP Completion Notify: send Feishu notification when a requirement is completed.

Usage:
    python scripts/completion_notify.py --central-issue 42 --surface backend --pr-url https://github.com/AI-MYG/asp-backend/pull/10
    python scripts/completion_notify.py --central-issue 42 --surface backend --pr-url ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import requests
    import yaml
except ImportError as e:
    print(f"Missing dependency: {e}. Install: pip install requests pyyaml", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
CENTRAL_REPO = "AI-MYG/asp"
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

sys.path.insert(0, str(REPO_ROOT / "tools"))
from asp_env import load_keychain_env  # noqa: E402


def load_env() -> None:
    load_keychain_env()


def load_notifications_config() -> dict[str, Any]:
    with open(CONFIG_DIR / "notifications.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def get_feishu_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {data}")
    return data["tenant_access_token"]


def send_webhook_message(webhook_url: str, text: str, *, dry_run: bool) -> dict:
    if dry_run:
        print(f"[DRY RUN] Feishu webhook:\n{text}\n")
        return {"code": 0, "dry_run": True}

    resp = requests.post(
        webhook_url,
        json={"msg_type": "text", "content": {"text": text}},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def send_feishu_dm(
    app_id: str, app_secret: str, open_id: str, text: str, *, dry_run: bool
) -> dict:
    if dry_run:
        print(f"[DRY RUN] Feishu DM -> {open_id}:\n{text}\n")
        return {"code": 0, "dry_run": True}

    token = get_feishu_token(app_id, app_secret)
    resp = requests.post(
        f"{FEISHU_BASE_URL}/im/v1/messages",
        params={"receive_id_type": "open_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_issue_author(central_issue: int) -> str:
    """Get the author field from the central issue body."""
    raw = gh(
        "issue", "view", str(central_issue),
        "-R", CENTRAL_REPO,
        "--json", "body",
    )
    data = json.loads(raw)
    body = data.get("body", "")
    for line in body.splitlines():
        if line.strip().startswith("**Author**:"):
            return line.split(":", 1)[1].strip()
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="ASP Completion Notify")
    parser.add_argument("--central-issue", type=int, required=True, help="Central issue number in AI-MYG/asp")
    parser.add_argument("--surface", required=True, help="Surface name (backend, app, admin, etc.)")
    parser.add_argument("--pr-url", required=True, help="Merged PR URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env()
    config = load_notifications_config()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    central_url = f"https://github.com/{CENTRAL_REPO}/issues/{args.central_issue}"

    # Get issue title
    raw = gh(
        "issue", "view", str(args.central_issue),
        "-R", CENTRAL_REPO,
        "--json", "title",
    )
    title = json.loads(raw).get("title", "")

    # Build notification from template
    template = config.get("events", {}).get("requirement_completed", {}).get("template", "")
    message = template.format(
        title=title,
        surface=args.surface,
        pr_url=args.pr_url,
        central_issue_url=central_url,
        completed_at=now,
    ) if template else (
        f"[ASP] 需求已完成\n"
        f"需求：{title}\n"
        f"Surface：{args.surface}\n"
        f"PR：{args.pr_url}\n"
        f"中央 Issue：{central_url}\n"
        f"完成时间：{now}"
    )

    print(f"Notifying completion of {CENTRAL_REPO}#{args.central_issue}")
    print(f"  Surface: {args.surface}")
    print(f"  PR: {args.pr_url}")

    # Method 1: Webhook (group notification)
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if webhook_url:
        result = send_webhook_message(webhook_url, message, dry_run=args.dry_run)
        print(f"  Webhook: {result.get('code', 'unknown')}")
    else:
        print("  Webhook: skipped (FEISHU_WEBHOOK_URL not set)")

    # Method 2: DM to requirement author (if Feishu app credentials available)
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if app_id and app_secret:
        author = get_issue_author(args.central_issue)
        if author:
            print(f"  Author: {author} (DM via Feishu App requires open_id mapping)")
            # TODO: resolve author name → Feishu open_id via team_registry
            # For now, webhook covers the notification
    else:
        print("  DM: skipped (FEISHU_APP_ID/SECRET not set)")

    # Update central issue with completion comment
    comment = (
        f"## Completed\n\n"
        f"**Surface**: {args.surface}\n"
        f"**PR**: {args.pr_url}\n"
        f"**Completed at**: {now}\n\n"
        f"Feishu notification sent.\n"
    )
    if not args.dry_run:
        gh(
            "issue", "comment", str(args.central_issue),
            "-R", CENTRAL_REPO,
            "--body", comment,
        )
        print(f"  Central issue commented")
    else:
        print(f"  [DRY RUN] Would comment on {CENTRAL_REPO}#{args.central_issue}")

    print("Done.")


if __name__ == "__main__":
    main()

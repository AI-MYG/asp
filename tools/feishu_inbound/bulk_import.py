#!/usr/bin/env python3
"""Bulk import existing Feishu Bitable demand pool records into GitHub Issues.

Reads all records from the demand pool table, skips those already linked to
a GitHub Issue, and creates new Issues for the rest.

Usage:
    # Load env from canonical .env, then run:
    cd /Users/marvi/CursorWorks/rootgrove
    env $(grep ^CANONICAL_FEISHU projects/asp/canonical_frontend/.env | xargs) \
        ./venv/bin/python tools/feishu_inbound/bulk_import.py --dry-run

    # Actually create issues:
    env $(grep ^CANONICAL_FEISHU projects/asp/canonical_frontend/.env | xargs) \
        ./venv/bin/python tools/feishu_inbound/bulk_import.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any, Optional

import requests

BASE_URL = "https://open.feishu.cn/open-apis"
REPO = "AI-MYG/asp"


class FeishuBitableClient:
    def __init__(self, app_id: str, app_secret: str):
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: Optional[str] = None
        self._token_expires: float = 0

    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires:
            return self._token
        resp = requests.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Token error: {data}")
        self._token = data["tenant_access_token"]
        self._token_expires = now + data.get("expire", 7200) - 300
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._ensure_token()}"}

    def list_records(
        self, base_token: str, table_id: str, page_size: int = 100
    ) -> list[dict[str, Any]]:
        """List all records with pagination."""
        all_records = []
        page_token = None
        while True:
            url = f"{BASE_URL}/bitable/v1/apps/{base_token}/tables/{table_id}/records"
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"List error: {data}")
            items = data.get("data", {}).get("items") or []
            all_records.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")
        return all_records

    def update_record(
        self, base_token: str, table_id: str, record_id: str, fields: dict
    ) -> dict:
        url = f"{BASE_URL}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}"
        resp = requests.put(
            url, headers=self._headers(), json={"fields": fields}, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Update error: {data}")
        return data["data"]["record"]


def extract_text(field_value: Any) -> str:
    """Extract plain text from various Bitable field types."""
    if field_value is None:
        return ""
    if isinstance(field_value, str):
        return field_value.strip()
    if isinstance(field_value, list):
        # Person field: [{"id": "...", "name": "..."}]
        names = []
        for item in field_value:
            if isinstance(item, dict):
                names.append(item.get("name", item.get("id", "")))
            else:
                names.append(str(item))
        return ", ".join(names)
    if isinstance(field_value, dict):
        # URL field or rich text
        return field_value.get("text", field_value.get("link", str(field_value)))
    return str(field_value)


def has_github_issue(fields: dict[str, Any]) -> bool:
    """Check if this record already has a linked GitHub Issue."""
    issue_field = fields.get("GitHub Issue")
    if not issue_field:
        return False
    text = extract_text(issue_field)
    return bool(text and text.strip())


AUTHOR_ASSIGNEE_MAP = {
    "胡剑飞": "1401554949",
}


def create_github_issue(title: str, body: str, assignee: str = "") -> dict[str, Any]:
    """Create a GitHub issue via gh CLI."""
    cmd = [
        "gh", "issue", "create",
        "-R", REPO,
        "--title", title,
        "--body", body,
        "--label", "feishu-inbound",
    ]
    if assignee:
        cmd.extend(["--assignee", assignee])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh issue create failed: {result.stderr}")
    # Parse issue URL from output
    issue_url = result.stdout.strip()
    return {"url": issue_url}


ACTIVE_STATUSES = {"待评审", "开发中"}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Bulk import Feishu demand pool to GitHub Issues")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating issues")
    parser.add_argument(
        "--all-statuses", action="store_true",
        help="Import all statuses (default: only active statuses: 待评审, 开发中)",
    )
    args = parser.parse_args()

    app_id = os.environ.get("CANONICAL_FEISHU_APP_ID", "")
    app_secret = os.environ.get("CANONICAL_FEISHU_APP_SECRET", "")
    base_token = os.environ.get("CANONICAL_FEISHU_BASE_TOKEN", "")
    table_id = os.environ.get("CANONICAL_FEISHU_TABLE_ID", "")

    if not all([app_id, app_secret, base_token, table_id]):
        print("Missing CANONICAL_FEISHU_* env vars. See usage in docstring.", file=sys.stderr)
        sys.exit(1)

    client = FeishuBitableClient(app_id, app_secret)
    print("Fetching records from Feishu Bitable...")
    records = client.list_records(base_token, table_id)
    print(f"Total records: {len(records)}")

    to_import = []
    for rec in records:
        fields = rec.get("fields", {})
        record_id = rec.get("record_id", "")

        if has_github_issue(fields):
            title = extract_text(fields.get("反馈问题", ""))
            print(f"  SKIP (has issue): {title[:50]}")
            continue

        title = extract_text(fields.get("反馈问题", ""))
        if not title:
            print(f"  SKIP (no title): record {record_id}")
            continue

        status = extract_text(fields.get("需求状态", ""))
        if not args.all_statuses and status not in ACTIVE_STATUSES:
            print(f"  SKIP (status={status}): {title[:50]}")
            continue

        to_import.append({
            "record_id": record_id,
            "title": title,
            "description": extract_text(fields.get("用户故事", "")),
            "author": extract_text(fields.get("需求负责人", "")),
            "priority": extract_text(fields.get("优先级", "")),
            "requirement_type": extract_text(fields.get("需求类型", "")),
            "status": extract_text(fields.get("需求状态", "")),
        })

    print(f"\nRecords to import: {len(to_import)}")

    if not to_import:
        print("Nothing to import.")
        return

    for i, item in enumerate(to_import, 1):
        print(f"\n[{i}/{len(to_import)}] {item['title'][:60]}")
        print(f"  Author: {item['author']}, Priority: {item['priority']}, Status: {item['status']}")

        issue_title = f"[feishu] {item['title']}"
        issue_body = f"""## Feishu Inbound Requirement

**Source**: Feishu Bitable (record: `{item['record_id']}`)
**Author**: {item['author']}
**Priority**: {item['priority']}
**Type**: {item['requirement_type']}
**Original Status**: {item['status']}

---

{item['description']}

---
_Bulk imported from Feishu demand pool._
"""

        assignee = AUTHOR_ASSIGNEE_MAP.get(item["author"], "")
        if args.dry_run:
            assign_info = f" (assignee: {assignee})" if assignee else ""
            print(f"  [DRY RUN] Would create: {issue_title}{assign_info}")
            continue

        assignee = AUTHOR_ASSIGNEE_MAP.get(item["author"], "")
        try:
            result = create_github_issue(issue_title, issue_body, assignee=assignee)
            print(f"  Created: {result['url']}")

            # Write back issue link to Bitable
            try:
                client.update_record(
                    base_token, table_id, item["record_id"],
                    {
                        "GitHub Issue": {"text": result["url"], "link": result["url"]},
                    },
                )
                print(f"  Bitable updated with issue link")
            except Exception as e:
                print(f"  Warning: Bitable writeback failed: {e}")

            # Rate limit: avoid hammering GitHub API
            time.sleep(1)

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    print(f"\nDone. Imported {len(to_import)} records.")


if __name__ == "__main__":
    main()

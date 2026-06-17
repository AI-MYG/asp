#!/usr/bin/env python3
"""Read launchd_schedules from config.yaml — used by launchd/install.sh and run wrappers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

_CONFIG = Path(__file__).resolve().parent.parent / "tools" / "feishu_inbound" / "config.yaml"

_JOB_ALIASES = {
    "triage": "feishu_inbound_triage",
    "agent": "feishu_inbound_agent",
    "lead_tick": "lead_tick",
    "executor": "issue_executor",
    "reviewer": "issue_pr_reviewer",
    "handback": "issue_dev_handback",
    "feishu_inbound_triage": "feishu_inbound_triage",
    "feishu_inbound_agent": "feishu_inbound_agent",
    "lead_tick": "lead_tick",
    "issue_executor": "issue_executor",
    "issue_pr_reviewer": "issue_pr_reviewer",
    "issue_dev_handback": "issue_dev_handback",
}


def load_config() -> dict[str, Any]:
    with open(_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def job_schedule(job: str) -> dict[str, Any]:
    key = _JOB_ALIASES.get(job, job)
    schedules = load_config().get("launchd_schedules") or {}
    if key not in schedules:
        raise KeyError(f"launchd_schedules.{key} not found in {_CONFIG}")
    return schedules[key]


def _hour_range(spec: dict[str, Any]) -> range:
    hours = spec.get("hours", "all")
    if hours == "all":
        return range(0, 24)
    if isinstance(hours, list):
        return range(min(hours), max(hours) + 1)
    if isinstance(hours, str) and "-" in hours:
        start_s, end_s = hours.split("-", 1)
        return range(int(start_s), int(end_s) + 1)
    raise ValueError(f"Unsupported hours spec: {hours!r}")


def calendar_interval_xml(job: str) -> str:
    spec = job_schedule(job)
    minutes = [int(m) for m in spec.get("minutes", [])]
    if not minutes:
        raise ValueError(f"launchd_schedules.{job}.minutes is empty")

    lines = ["  <array>"]
    for hour in _hour_range(spec):
        for minute in minutes:
            lines.append("    <dict>")
            lines.append(f"      <key>Hour</key><integer>{hour}</integer>")
            lines.append(f"      <key>Minute</key><integer>{minute}</integer>")
            lines.append("    </dict>")
    lines.append("  </array>")
    return "\n".join(lines)


def weekday_only(job: str) -> bool:
    return bool(job_schedule(job).get("weekday_only", False))


def summary(job: str) -> str:
    spec = job_schedule(job)
    hours = spec.get("hours", "all")
    mins = ",".join(str(m) for m in spec.get("minutes", []))
    wd = "weekdays" if spec.get("weekday_only") else "24/7"
    return f"hours={hours} :{mins} ({wd})"


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: schedule_config.py calendar-xml <triage|agent|lead_tick|executor|reviewer|handback>\n"
            "       schedule_config.py weekday-only <triage|agent|lead_tick|executor|reviewer|handback>\n"
            "       schedule_config.py summary <triage|agent|lead_tick|executor|reviewer|handback>",
            file=sys.stderr,
        )
        sys.exit(2)
    cmd, job = sys.argv[1], sys.argv[2]
    if cmd == "calendar-xml":
        print(calendar_interval_xml(job))
    elif cmd == "weekday-only":
        print("true" if weekday_only(job) else "false")
    elif cmd == "summary":
        print(summary(job))
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()

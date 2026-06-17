#!/usr/bin/env python3
"""Pipeline B — thin wrapper → feishu-inbound engine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _wrapper import run_main  # noqa: E402
from feishu_inbound.triage.triage_agent import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_main(main))

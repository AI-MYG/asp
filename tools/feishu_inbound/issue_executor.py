#!/usr/bin/env python3
"""Pipeline D — thin wrapper → feishu-inbound engine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _wrapper import run_main  # noqa: E402
from feishu_inbound.executor.issue_executor import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_main(main))

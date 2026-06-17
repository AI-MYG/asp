"""Thin bridge: ASP instance scripts → feishu-inbound engine."""

from __future__ import annotations

import sys
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent / "config.yaml"


def engine_argv(extra: list[str] | None = None) -> list[str]:
    return ["--config", str(_CONFIG), *(extra or [])]


def run_main(main_fn, extra: list[str] | None = None) -> int:
    from feishu_inbound import __version__

    print(f"feishu-inbound engine {__version__} config={_CONFIG}")
    prefix = ""
    try:
        import yaml

        cfg = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
        prefix = cfg.get("secrets_prefix") or ""
    except Exception:
        pass
    if prefix:
        print(f"secrets_prefix={prefix!r}")
    rc = main_fn(engine_argv(sys.argv[1:] + (extra or [])))
    return int(rc) if rc is not None else 0

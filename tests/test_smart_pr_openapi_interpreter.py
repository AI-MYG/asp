"""Tests for smart_pr OpenAPI gate interpreter resolution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

_ASP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ASP_ROOT))

from tools import smart_pr  # noqa: E402


def test_resolve_openapi_python_prefers_worktree_venv(tmp_path: Path) -> None:
    repo_root = tmp_path / "wt"
    backend = repo_root / "backend"
    venv_bin = backend / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    python_path = venv_bin / "python"
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")
    python_path.chmod(0o755)

    surface = {"local_path": "projects/asp/backend"}
    resolved = smart_pr._resolve_openapi_python(repo_root, surface)
    assert resolved == str(python_path)


def test_ensure_openapi_synced_uses_resolved_python(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "wt"
    backend = repo_root / "backend"
    scripts = backend / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "export_openapi.py").write_text("print('ok')\n", encoding="utf-8")
    docs = repo_root / "docs" / "api"
    docs.mkdir(parents=True)
    (docs / "openapi.json").write_text("{}", encoding="utf-8")

    fake_python = "/tmp/fake-venv-python"
    monkeypatch.setattr(smart_pr, "_resolve_openapi_python", lambda *_a, **_k: fake_python)

    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd=None, capture_output=True, text=True, timeout=60):
        calls.append(cmd)
        if cmd[:2] == [fake_python, str(scripts / "export_openapi.py")]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["git", "diff", "--exit-code"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(smart_pr.subprocess, "run", fake_run)

    smart_pr.ensure_openapi_synced(
        repo_root,
        "dev",
        surface={"local_path": "projects/asp/backend"},
        dry_run=False,
    )

    assert calls[0] == [fake_python, str(scripts / "export_openapi.py")]

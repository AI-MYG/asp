"""ASP automation environment — macOS Keychain (rootgrove/* namespace).

Local runs do not require asp-infra/.env. Shell wrappers should source
scripts/load_asp_env.sh; Python entrypoints call load_keychain_env().
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

KEYCHAIN_PREFIX = "rootgrove"
_loaded = False


def workspace_root() -> Path:
    return Path(
        os.environ.get("ASP_WORKTREE_ROOT", str(Path.home() / "CursorWorks" / "rootgrove"))
    ).expanduser().resolve()


def load_secrets_sh_path() -> Path:
    return workspace_root() / "tools" / "secrets" / "load_secrets.sh"


def load_keychain_env(*, force: bool = False) -> None:
    """Export all rootgrove/* Keychain entries into os.environ (no .env)."""
    global _loaded
    if _loaded and not force:
        return

    sh_path = load_secrets_sh_path()
    if sh_path.is_file():
        _load_via_shell(sh_path)
    else:
        _load_via_security_cli()

    _apply_opencode_aliases()
    _loaded = True


def _load_via_shell(sh_path: Path) -> None:
    """Source load_secrets.sh and merge exported vars (Keychain-only path)."""
    cmd = f'source "{sh_path}" && env -0'
    proc = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        _load_via_security_cli()
        return
    for entry in proc.stdout.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, _, value = entry.partition(b"=")
        k = key.decode(errors="replace")
        if k and k not in os.environ:
            os.environ[k] = value.decode(errors="replace")


def _load_via_security_cli() -> None:
    dump = subprocess.run(
        ["security", "dump-keychain"],
        capture_output=True,
        text=True,
        check=False,
    )
    services: set[str] = set()
    for match in re.finditer(rf'"{KEYCHAIN_PREFIX}/([^"]+)"', dump.stdout or ""):
        services.add(match.group(1))
    for key in sorted(services):
        full = f"{KEYCHAIN_PREFIX}/{key}"
        found = subprocess.run(
            ["security", "find-generic-password", "-s", full, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
        if found.returncode == 0 and found.stdout.strip():
            os.environ.setdefault(key, found.stdout.rstrip("\n"))


def _apply_opencode_aliases() -> None:
    """Map Keychain OPENCODE_* names to legacy observer/reflector vars."""
    base = os.environ.get("OPENCODE_BASE_URL", "").strip()
    if base and not os.environ.get("OPENCODE_HOST"):
        parsed = urlparse(base)
        if parsed.hostname:
            os.environ.setdefault("OPENCODE_HOST", parsed.hostname)
        port = parsed.port
        if port:
            os.environ.setdefault("OPENCODE_PORT", str(port))
        elif parsed.scheme == "https":
            os.environ.setdefault("OPENCODE_PORT", "443")
        else:
            os.environ.setdefault("OPENCODE_PORT", "4096")

    user = os.environ.get("OPENCODE_USERNAME") or os.environ.get("OPENCODE_USER")
    if user:
        os.environ.setdefault("OPENCODE_USERNAME", user)
        os.environ.setdefault("OPENCODE_USER", user)

    password = os.environ.get("OPENCODE_PASSWORD") or os.environ.get("OPENCODE_PASS")
    if password:
        os.environ.setdefault("OPENCODE_PASSWORD", password)
        os.environ.setdefault("OPENCODE_PASS", password)

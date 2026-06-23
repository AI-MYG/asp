#!/usr/bin/env bash
# Install feishu-inbound into asp-infra venv from GitHub Packages (version pin in requirements).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PIP="${VENV_PIP:-$REPO_ROOT/venv/bin/pip}"
REQ_FILE="${REQ_FILE:-$REPO_ROOT/requirements-feishu-inbound.txt}"
ENGINE_LOCAL="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/projects/feishu-inbound-skill"
GITHUB_PACKAGES_OWNER="${GITHUB_PACKAGES_OWNER:-369795172}"

if [[ ! -x "$VENV_PIP" ]]; then
  echo "Creating asp-infra venv..."
  python3 -m venv "$REPO_ROOT/venv"
fi

if [[ -f "$ENGINE_LOCAL/pyproject.toml" && "${FEISHU_INBOUND_INSTALL:-}" != "package" ]]; then
  echo "Installing feishu-inbound editable from $ENGINE_LOCAL"
  "$VENV_PIP" install -q -e "$ENGINE_LOCAL"
  exit 0
fi

_resolve_token() {
  if [[ -n "${GITHUB_PACKAGES_TOKEN:-}" ]]; then
    printf '%s' "$GITHUB_PACKAGES_TOKEN"
    return
  fi
  if [[ -n "${FEISHU_INBOUND_GH_PACKAGES_TOKEN:-}" ]]; then
    printf '%s' "$FEISHU_INBOUND_GH_PACKAGES_TOKEN"
    return
  fi
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    printf '%s' "$GITHUB_TOKEN"
    return
  fi
  if command -v gh >/dev/null 2>&1; then
    gh auth token 2>/dev/null || true
    return
  fi
  printf ''
}

TOKEN="$(_resolve_token)"
if [[ -z "$TOKEN" ]]; then
  echo "Error: need GITHUB_PACKAGES_TOKEN, GITHUB_TOKEN, or 'gh auth login' (read:packages)." >&2
  exit 1
fi

PKG_INDEX="https://__token__:${TOKEN}@pypi.pkg.github.com/${GITHUB_PACKAGES_OWNER}/simple/"
echo "Installing feishu-inbound from GitHub Packages (${GITHUB_PACKAGES_OWNER})..."
"$VENV_PIP" install -q -r "$REQ_FILE" \
  --index-url https://pypi.org/simple \
  --extra-index-url "$PKG_INDEX"

"$REPO_ROOT/venv/bin/python" -c "import feishu_inbound; print('feishu-inbound', feishu_inbound.__version__)"

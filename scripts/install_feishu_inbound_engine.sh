#!/usr/bin/env bash
# Install feishu-inbound into asp-infra venv from GitHub Release wheel (version pin in requirements).
# Prefers public dist Release; falls back to private engine Release.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PIP="${VENV_PIP:-$REPO_ROOT/venv/bin/pip}"
REQ_FILE="${REQ_FILE:-$REPO_ROOT/requirements-feishu-inbound.txt}"
ENGINE_LOCAL="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/projects/feishu-inbound-skill"
DIST_REPO="${FEISHU_INBOUND_DIST_REPO:-369795172/feishu-inbound-dist}"
ENGINE_REPO="${FEISHU_INBOUND_REPO:-369795172/feishu-inbound-skill}"

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
  if [[ -n "${FEISHU_INBOUND_GH_TOKEN:-}" ]]; then
    printf '%s' "$FEISHU_INBOUND_GH_TOKEN"
    return
  fi
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

_version_from_req() {
  grep -E '^feishu-inbound==' "$REQ_FILE" | head -1 | cut -d= -f3 | tr -d '[:space:]'
}

_download_public() {
  local url="https://github.com/${DIST_REPO}/releases/download/${TAG}/${WHEEL}"
  echo "Trying public dist: ${url}"
  if curl -fsSL "$url" -o "${TMPDIR}/${WHEEL}"; then
    echo "Downloaded from public dist ${DIST_REPO}"
    return 0
  fi
  return 1
}

_download_private() {
  local token="$1"
  if [[ -z "$token" ]]; then
    return 1
  fi
  echo "Falling back to private engine Release ${ENGINE_REPO} ${TAG}..."
  if command -v gh >/dev/null 2>&1; then
    GH_TOKEN="$token" gh release download "$TAG" --repo "$ENGINE_REPO" --pattern "*.whl" -D "$TMPDIR"
    return 0
  fi
  local asset_id
  asset_id="$(curl -fsSL -H "Authorization: Bearer ${token}" \
    "https://api.github.com/repos/${ENGINE_REPO}/releases/tags/${TAG}" \
    | python3 -c "import json,sys; assets=json.load(sys.stdin)['assets']; print(next(a['id'] for a in assets if a['name']=='${WHEEL}'))")"
  curl -fsSL -H "Authorization: Bearer ${token}" -H "Accept: application/octet-stream" \
    "https://api.github.com/repos/${ENGINE_REPO}/releases/assets/${asset_id}" \
    -o "${TMPDIR}/${WHEEL}"
}

VERSION="$(_version_from_req)"
if [[ -z "$VERSION" ]]; then
  echo "Error: $REQ_FILE must pin feishu-inbound==X.Y.Z" >&2
  exit 1
fi

TAG="v${VERSION}"
WHEEL="feishu_inbound-${VERSION}-py3-none-any.whl"

echo "Installing feishu-inbound==${VERSION} (public dist first, private fallback)..."
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

if ! _download_public; then
  TOKEN="$(_resolve_token)"
  if [[ -z "$TOKEN" ]]; then
    echo "Error: public dist miss and no token for private fallback." >&2
    echo "Need FEISHU_INBOUND_GH_TOKEN, GITHUB_TOKEN, or 'gh auth login' (repo read on ${ENGINE_REPO})." >&2
    exit 1
  fi
  _download_private "$TOKEN"
fi

"$VENV_PIP" install -q "${TMPDIR}"/*.whl

"$REPO_ROOT/venv/bin/python" -c "import feishu_inbound; print('feishu-inbound', feishu_inbound.__version__)"

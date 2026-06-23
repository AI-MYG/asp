#!/usr/bin/env bash
# Install feishu-inbound into asp-infra venv from GitHub Release wheel (version pin in requirements).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PIP="${VENV_PIP:-$REPO_ROOT/venv/bin/pip}"
REQ_FILE="${REQ_FILE:-$REPO_ROOT/requirements-feishu-inbound.txt}"
ENGINE_LOCAL="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/projects/feishu-inbound-skill"
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

VERSION="$(_version_from_req)"
if [[ -z "$VERSION" ]]; then
  echo "Error: $REQ_FILE must pin feishu-inbound==X.Y.Z" >&2
  exit 1
fi

TOKEN="$(_resolve_token)"
if [[ -z "$TOKEN" ]]; then
  echo "Error: need FEISHU_INBOUND_GH_TOKEN, GITHUB_TOKEN, or 'gh auth login' (repo read on ${ENGINE_REPO})." >&2
  exit 1
fi

TAG="v${VERSION}"
WHEEL="feishu_inbound-${VERSION}-py3-none-any.whl"

echo "Installing feishu-inbound==${VERSION} from GitHub Release ${TAG}..."
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

if command -v gh >/dev/null 2>&1; then
  GH_TOKEN="$TOKEN" gh release download "$TAG" --repo "$ENGINE_REPO" --pattern "*.whl" -D "$TMPDIR"
else
  ASSET_ID="$(curl -fsSL -H "Authorization: Bearer ${TOKEN}" \
    "https://api.github.com/repos/${ENGINE_REPO}/releases/tags/${TAG}" \
    | python3 -c "import json,sys; assets=json.load(sys.stdin)['assets']; print(next(a['id'] for a in assets if a['name']=='${WHEEL}'))")"
  curl -fsSL -H "Authorization: Bearer ${TOKEN}" -H "Accept: application/octet-stream" \
    "https://api.github.com/repos/${ENGINE_REPO}/releases/assets/${ASSET_ID}" \
    -o "${TMPDIR}/${WHEEL}"
fi

"$VENV_PIP" install -q "${TMPDIR}"/*.whl

"$REPO_ROOT/venv/bin/python" -c "import feishu_inbound; print('feishu-inbound', feishu_inbound.__version__)"

#!/usr/bin/env bash
# Minimal feishu-inbound CLI bootstrap for ASP team members (no rootgrove monorepo required).
#
# Usage (from asp repo root):
#   bash scripts/bootstrap_inbound_cli.sh
#
# See docs/onboarding_inbound_skills.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 required" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI required — install: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "error: run 'gh auth login' first (use your GitHub account, e.g. issue requester)" >&2
  exit 1
fi

if [[ ! -d "$REPO_ROOT/venv" ]]; then
  echo "Creating venv at $REPO_ROOT/venv ..."
  python3 -m venv "$REPO_ROOT/venv"
fi

"$REPO_ROOT/venv/bin/pip" install -q --upgrade pip
"$REPO_ROOT/venv/bin/pip" install -q python-dotenv requests 2>/dev/null || true

echo "Installing feishu-inbound engine (pinned in requirements-feishu-inbound.txt) ..."
# Prefer package wheel; skip editable from Marvin's rootgrove unless explicitly requested.
FEISHU_INBOUND_INSTALL=package bash "$SCRIPT_DIR/install_feishu_inbound_engine.sh"

"$REPO_ROOT/venv/bin/feishu-inbound" --help >/dev/null 2>&1 || {
  echo "error: feishu-inbound CLI not on PATH in venv" >&2
  exit 1
}

VER="$("$REPO_ROOT/venv/bin/python" -c "import feishu_inbound; print(feishu_inbound.__version__)")"
echo ""
echo "OK: feishu-inbound ${VER} at $REPO_ROOT/venv/bin/feishu-inbound"
echo ""
echo "Next — see docs/inbound_pipeline_team_guide.md for your pipeline role."
echo "  Acceptance: bash scripts/run_accept.sh pass --issue <N> --repo AI-MYG/asp-backend"
echo "  Pipeline C: ./venv/bin/python tools/feishu_inbound/issue_scanner.py --issue <N> --repo <R>"

#!/usr/bin/env bash
# ASP Observer — 日频扫描 GitHub 活动信号，写入 memory/OBSERVATIONS.md
#
# 调用方式:
#   bash scripts/observer.sh
#
# 环境变量 (从 .env 加载):
#   GITHUB_TOKEN          GitHub API token
#   OBSERVER_GITHUB_ORG   GitHub org (default: AI-MYG)
#   OBSERVER_REPOS        Comma-separated repo names (default: asp-backend,asp-app,asp-admin,asp-wecom,asp-websites,asp-canonical,asp)
#   OPENCODE_HOST/PORT/USER/PASS  OpenCode Server credentials

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env if present
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

ORG="${OBSERVER_GITHUB_ORG:-AI-MYG}"
REPOS="${OBSERVER_REPOS:-asp-backend,asp-app,asp-admin,asp-wecom,asp-websites,asp-canonical,asp}"
OUTPUT="${REPO_ROOT}/${OBSERVER_OUTPUT:-memory/OBSERVATIONS.md}"
DATE=$(date +%Y-%m-%d)

echo "=== ASP Observer — $DATE ==="
echo "Org: $ORG"
echo "Repos: $REPOS"
echo "Output: $OUTPUT"

# Collect signals from each repo
SIGNALS=""
IFS=',' read -ra REPO_LIST <<< "$REPOS"
for repo in "${REPO_LIST[@]}"; do
  echo "Scanning $ORG/$repo ..."

  # Recent issues (last 24h)
  ISSUES=$(gh issue list --repo "$ORG/$repo" --state all --limit 10 --json number,title,state,createdAt,labels 2>/dev/null || echo "[]")

  # Recent PRs (last 24h)
  PRS=$(gh pr list --repo "$ORG/$repo" --state all --limit 10 --json number,title,state,createdAt,mergedAt 2>/dev/null || echo "[]")

  if [[ "$ISSUES" != "[]" || "$PRS" != "[]" ]]; then
    SIGNALS="$SIGNALS\n### $ORG/$repo\n\nIssues: $ISSUES\nPRs: $PRS\n"
  fi
done

if [[ -z "$SIGNALS" ]]; then
  echo "No new signals detected."
  exit 0
fi

# Use OpenCode to analyze and format
OC_HOST="${OPENCODE_HOST:-localhost}"
OC_PORT="${OPENCODE_PORT:-4096}"
OC_USER="${OPENCODE_USER:-user}"
OC_PASS="${OPENCODE_PASS:-changeme}"

PROMPT="You are the ASP project Observer. Analyze these GitHub signals from today ($DATE) and write structured observation entries for memory/OBSERVATIONS.md.

Format each entry as:
- [$DATE] [TYPE] Brief description

Where TYPE is one of: ISSUE, PR, DEPLOY, PATTERN, RISK

Be concise. Only include actionable or notable signals. Skip routine/noise.

Signals:
$SIGNALS"

echo "Sending to OpenCode for analysis..."
ANALYSIS=$(curl -sf -u "$OC_USER:$OC_PASS" \
  -X POST "http://$OC_HOST:$OC_PORT/chat" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg msg "$PROMPT" '{message: $msg}')" \
  | jq -r '.response // .message // "No response"' 2>/dev/null || echo "OpenCode unavailable — raw signals appended")

# Append to OBSERVATIONS.md
{
  echo ""
  echo "## $DATE"
  echo ""
  if [[ "$ANALYSIS" == *"unavailable"* ]]; then
    echo -e "$SIGNALS"
  else
    echo "$ANALYSIS"
  fi
} >> "$OUTPUT"

echo "=== Observer complete — entries appended to $OUTPUT ==="

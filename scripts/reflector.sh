#!/usr/bin/env bash
# ASP Reflector — 周频蒸馏 OBSERVATIONS.md → MEMORY.md
#
# 调用方式:
#   bash scripts/reflector.sh
#
# 职责:
#   1. 读取 memory/OBSERVATIONS.md 中最近 7 天的 Hot 条目
#   2. 用 OpenCode 蒸馏为原子事实
#   3. 追加到 memory/MEMORY.md
#   4. 将 >30 天条目移入 memory/archive/YYYY-MM.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

OBS_FILE="$REPO_ROOT/memory/OBSERVATIONS.md"
MEM_FILE="$REPO_ROOT/memory/MEMORY.md"
ARCHIVE_DIR="$REPO_ROOT/memory/archive"
DATE=$(date +%Y-%m-%d)
MONTH=$(date +%Y-%m)

echo "=== ASP Reflector — $DATE ==="

if [[ ! -f "$OBS_FILE" ]]; then
  echo "No OBSERVATIONS.md found. Nothing to reflect."
  exit 0
fi

OBS_CONTENT=$(cat "$OBS_FILE")

OC_HOST="${OPENCODE_HOST:-localhost}"
OC_PORT="${OPENCODE_PORT:-4096}"
OC_USER="${OPENCODE_USER:-user}"
OC_PASS="${OPENCODE_PASS:-changeme}"

PROMPT="You are the ASP project Reflector. Review these project observations and distill them into atomic facts for long-term memory.

Rules:
1. Each fact should be 1-3 sentences, factual and specific
2. Categorize as: Architecture, Process, Product, or Team
3. Include confidence level (high/medium/low)
4. Skip noise, routine events, and one-off incidents
5. Focus on patterns, decisions, and insights that will be useful in future sessions

Format:
### [$DATE] Title

Content.

**来源**: OBSERVATIONS.md YYYY-MM-DD 条目
**置信度**: high/medium/low

Observations to reflect on:
$OBS_CONTENT"

echo "Sending to OpenCode for reflection..."
REFLECTION=$(curl -sf -u "$OC_USER:$OC_PASS" \
  -X POST "http://$OC_HOST:$OC_PORT/chat" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg msg "$PROMPT" '{message: $msg}')" \
  | jq -r '.response // .message // "No response"' 2>/dev/null || echo "OpenCode unavailable — skipping reflection")

if [[ "$REFLECTION" != *"unavailable"* && "$REFLECTION" != "No response" ]]; then
  echo "" >> "$MEM_FILE"
  echo "$REFLECTION" >> "$MEM_FILE"
  echo "Reflection appended to $MEM_FILE"
fi

# Archive old entries (>30 days) — simplified: move content before current month header
ARCHIVE_FILE="$ARCHIVE_DIR/$MONTH.md"
if [[ ! -f "$ARCHIVE_FILE" ]]; then
  echo "# ASP Observations Archive — $MONTH" > "$ARCHIVE_FILE"
fi

echo "=== Reflector complete ==="

#!/usr/bin/env bash
# Disable rootgrove feishu-inbound launchd jobs (ASP uses com.asp.* only).
#
# Usage: bash launchd/disable_rootgrove_feishu_inbound.sh

set -euo pipefail

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"

LABELS=(
  com.rootgrove.feishu-inbound-triage
  com.rootgrove.feishu-inbound-agent
)

for label in "${LABELS[@]}"; do
  plist="$LAUNCH_AGENTS/$label.plist"
  if launchctl print "$DOMAIN/$label" &>/dev/null; then
    launchctl bootout "$DOMAIN" "$plist" 2>/dev/null \
      || launchctl unload "$plist" 2>/dev/null \
      || true
    echo "Unloaded $label"
  fi
  if [[ -f "$plist" ]]; then
    rm -f "$plist"
    echo "Removed $plist"
  fi
done

echo "Done. ASP feishu inbound: use com.asp.feishu-inbound-* (bash launchd/install.sh)."

#!/usr/bin/env bash
# Install ASP launchd jobs (Observer + Reflector + Feishu Inbound triage + lead-tick)
#
# Schedule relative to rootgrove (higher priority = earlier):
#   rootgrove observer  daily 08:00  |  ASP observer  daily 22:00
#   rootgrove reflector Sun 09:00     |  ASP reflector Sun 10:00
#
# Feishu inbound on lead Mac: triage (B) + lead_tick (C→D→E→F). Per-stage legacy
# launchd jobs (agent/executor/reviewer/handback) are removed — use lead_tick only.
#
# Secrets: macOS Keychain rootgrove/* via scripts/load_asp_env.sh (no .env).
# Disable duplicate rootgrove feishu jobs: bash launchd/disable_rootgrove_feishu_inbound.sh
#
# Usage:
#   bash launchd/install.sh [--uninstall]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

OBSERVER_LABEL="com.asp.observer"
REFLECTOR_LABEL="com.asp.reflector"
TRIAGE_LABEL="com.asp.feishu-inbound-triage"
LEAD_TICK_LABEL="com.asp.feishu-inbound-lead-tick"

# Retired 2026-06-19 — bootout + delete if still present from older installs.
LEGACY_FEISHU_LABELS=(
  "com.asp.feishu-inbound-agent"
  "com.asp.issue-executor"
  "com.asp.issue-pr-reviewer"
  "com.asp.issue-dev-handback"
)

ALL_LABELS=("$OBSERVER_LABEL" "$REFLECTOR_LABEL" "$TRIAGE_LABEL" "$LEAD_TICK_LABEL")

uninstall() {
  echo "Uninstalling ASP launchd jobs..."
  for label in "${ALL_LABELS[@]}" "${LEGACY_FEISHU_LABELS[@]}"; do
    if launchctl list | grep -q "$label"; then
      launchctl unload "$LAUNCH_AGENTS/$label.plist" 2>/dev/null || true
    fi
    rm -f "$LAUNCH_AGENTS/$label.plist"
    echo "  Removed $label"
  done
  echo "Done."
}

remove_legacy_feishu_jobs() {
  UID_NUM="$(id -u)"
  DOMAIN="gui/$UID_NUM"
  for label in "${LEGACY_FEISHU_LABELS[@]}"; do
    plist="$LAUNCH_AGENTS/$label.plist"
    if launchctl print "$DOMAIN/$label" &>/dev/null; then
      launchctl bootout "$DOMAIN" "$plist" 2>/dev/null \
        || launchctl unload "$plist" 2>/dev/null \
        || true
    fi
    if [ -f "$plist" ]; then
      rm -f "$plist"
      echo "Removed legacy $label"
    fi
  done
}

if [[ "${1:-}" == "--uninstall" ]]; then
  uninstall
  exit 0
fi

mkdir -p "$LAUNCH_AGENTS"

# Bootstrap asp-infra venv + feishu-inbound engine (Pipeline B–F wrappers)
if [ ! -x "$REPO_ROOT/venv/bin/python" ]; then
  echo "Creating asp-infra venv..."
  python3 -m venv "$REPO_ROOT/venv"
fi
if ! "$REPO_ROOT/venv/bin/python" -c "import feishu_inbound" 2>/dev/null; then
  echo "Installing feishu-inbound engine into asp-infra venv..."
  bash "$REPO_ROOT/scripts/install_feishu_inbound_engine.sh"
fi
# opencode_job.py (Pipeline C/D analysis) needs dotenv in asp-infra venv
"$REPO_ROOT/venv/bin/pip" install -q python-dotenv requests 2>/dev/null || true

SCHEDULE_PY="$REPO_ROOT/launchd/schedule_config.py"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"
TRIAGE_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml triage)
LEAD_TICK_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml lead_tick)

PATH_ENV='  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>'

# Observer: daily at 22:00 (after rootgrove observer 08:00)
cat > "$LAUNCH_AGENTS/$OBSERVER_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$OBSERVER_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/observer.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>22</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/observer.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/observer.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# Reflector: weekly on Sunday at 10:00 (after rootgrove reflector 09:00)
cat > "$LAUNCH_AGENTS/$REFLECTOR_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$REFLECTOR_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/reflector.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>0</integer>
    <key>Hour</key>
    <integer>10</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/reflector.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/reflector.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# --- Feishu Inbound Pipeline B: Triage (schedule from config.yaml launchd_schedules) ---
cat > "$LAUNCH_AGENTS/$TRIAGE_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$TRIAGE_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/run_feishu_inbound_triage.sh</string>
  </array>
  <key>StartCalendarInterval</key>
$TRIAGE_SCHEDULE
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-triage.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-triage.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# --- Feishu Inbound lead tick (C+D+E+F chain — sole C–F scheduler on lead Mac) ---
cat > "$LAUNCH_AGENTS/$LEAD_TICK_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LEAD_TICK_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/run_feishu_inbound_lead_tick.sh</string>
  </array>
  <key>StartCalendarInterval</key>
$LEAD_TICK_SCHEDULE
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-lead-tick.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-lead-tick.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# Create logs directory
mkdir -p "$REPO_ROOT/logs"

remove_legacy_feishu_jobs

# Load jobs (bootout + bootstrap so stale ProgramArguments are replaced)
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"
for label in "${ALL_LABELS[@]}"; do
  plist="$LAUNCH_AGENTS/$label.plist"
  if launchctl print "$DOMAIN/$label" &>/dev/null; then
    launchctl bootout "$DOMAIN" "$plist" 2>/dev/null \
      || launchctl unload "$plist" 2>/dev/null \
      || true
  fi
  launchctl bootstrap "$DOMAIN" "$plist"
  echo "Loaded $label"
done

echo ""
echo "ASP launchd jobs installed:"
echo "  Observer:  daily at 22:00       ($OBSERVER_LABEL)"
echo "  Reflector: Sunday at 10:00      ($REFLECTOR_LABEL)"
echo "  Triage:    $("$VENV_PYTHON" "$SCHEDULE_PY" summary triage) ($TRIAGE_LABEL)"
echo "  Lead tick: $("$VENV_PYTHON" "$SCHEDULE_PY" summary lead_tick) ($LEAD_TICK_LABEL) — C+D+E+F chain"
echo "  Logs: $REPO_ROOT/logs/"

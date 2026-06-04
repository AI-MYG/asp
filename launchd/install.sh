#!/usr/bin/env bash
# Install ASP launchd jobs (Observer + Reflector + Feishu Inbound Pipeline B/C/D)
#
# Schedule relative to rootgrove (higher priority = earlier):
#   rootgrove observer  daily 08:00  |  ASP observer  daily 22:00
#   rootgrove reflector Sun 09:00     |  ASP reflector Sun 10:00
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
AGENT_LABEL="com.asp.feishu-inbound-agent"
EXECUTOR_LABEL="com.asp.issue-executor"

ALL_LABELS=("$OBSERVER_LABEL" "$REFLECTOR_LABEL" "$TRIAGE_LABEL" "$AGENT_LABEL" "$EXECUTOR_LABEL")

uninstall() {
  echo "Uninstalling ASP launchd jobs..."
  for label in "${ALL_LABELS[@]}"; do
    if launchctl list | grep -q "$label"; then
      launchctl unload "$LAUNCH_AGENTS/$label.plist" 2>/dev/null || true
    fi
    rm -f "$LAUNCH_AGENTS/$label.plist"
    echo "  Removed $label"
  done
  echo "Done."
}

if [[ "${1:-}" == "--uninstall" ]]; then
  uninstall
  exit 0
fi

mkdir -p "$LAUNCH_AGENTS"

SCHEDULE_PY="$REPO_ROOT/launchd/schedule_config.py"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
  VENV_PYTHON="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/venv/bin/python"
fi
TRIAGE_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml triage)
AGENT_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml agent)
EXECUTOR_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml executor)

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

# --- Feishu Inbound Pipeline C: Agent analysis ---
cat > "$LAUNCH_AGENTS/$AGENT_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$AGENT_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/run_feishu_inbound_agent.sh</string>
  </array>
  <key>StartCalendarInterval</key>
$AGENT_SCHEDULE
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-agent.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-agent.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# --- Pipeline D: Issue executor ---
cat > "$LAUNCH_AGENTS/$EXECUTOR_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$EXECUTOR_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/run_issue_executor.sh</string>
  </array>
  <key>StartCalendarInterval</key>
$EXECUTOR_SCHEDULE
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/issue-executor.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/issue-executor.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# Create logs directory
mkdir -p "$REPO_ROOT/logs"

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
echo "  Agent:     $("$VENV_PYTHON" "$SCHEDULE_PY" summary agent) ($AGENT_LABEL)"
echo "  Executor:  $("$VENV_PYTHON" "$SCHEDULE_PY" summary executor) ($EXECUTOR_LABEL)"
echo "  Logs: $REPO_ROOT/logs/"

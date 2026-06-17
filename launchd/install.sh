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
REVIEWER_LABEL="com.asp.issue-pr-reviewer"
HANDBACK_LABEL="com.asp.issue-dev-handback"
LEAD_TICK_LABEL="com.asp.feishu-inbound-lead-tick"

ALL_LABELS=("$OBSERVER_LABEL" "$REFLECTOR_LABEL" "$TRIAGE_LABEL" "$LEAD_TICK_LABEL" "$AGENT_LABEL" "$EXECUTOR_LABEL" "$REVIEWER_LABEL" "$HANDBACK_LABEL")

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

# Bootstrap asp-infra venv + feishu-inbound engine (Pipeline B–F wrappers)
if [ ! -x "$REPO_ROOT/venv/bin/python" ]; then
  echo "Creating asp-infra venv..."
  python3 -m venv "$REPO_ROOT/venv"
fi
if ! "$REPO_ROOT/venv/bin/python" -c "import feishu_inbound" 2>/dev/null; then
  ENGINE_LOCAL="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/projects/feishu-inbound-skill"
  echo "Installing feishu-inbound engine into asp-infra venv..."
  if [ -f "$ENGINE_LOCAL/pyproject.toml" ]; then
    "$REPO_ROOT/venv/bin/pip" install -q -e "$ENGINE_LOCAL"
  elif [ -f "$REPO_ROOT/requirements-feishu-inbound.txt" ]; then
    "$REPO_ROOT/venv/bin/pip" install -q -r "$REPO_ROOT/requirements-feishu-inbound.txt" \
      || "$REPO_ROOT/venv/bin/pip" install -q -e "$ENGINE_LOCAL"
  fi
fi

SCHEDULE_PY="$REPO_ROOT/launchd/schedule_config.py"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"
TRIAGE_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml triage)
AGENT_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml agent)
EXECUTOR_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml executor)
REVIEWER_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml reviewer)
HANDBACK_SCHEDULE=$("$VENV_PYTHON" "$SCHEDULE_PY" calendar-xml handback)
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

# --- Feishu Inbound lead tick (C+D+E+F chain — preferred on lead Mac) ---
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

# --- Pipeline E: Issue PR reviewer (gate review) ---
cat > "$LAUNCH_AGENTS/$REVIEWER_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$REVIEWER_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/run_issue_pr_reviewer.sh</string>
  </array>
  <key>StartCalendarInterval</key>
$REVIEWER_SCHEDULE
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/issue-pr-reviewer.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/issue-pr-reviewer.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
$PATH_ENV
</dict>
</plist>
EOF

# --- Pipeline F: Dev handback after CI/CD ---
cat > "$LAUNCH_AGENTS/$HANDBACK_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$HANDBACK_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO_ROOT/scripts/run_issue_dev_handback.sh</string>
  </array>
  <key>StartCalendarInterval</key>
$HANDBACK_SCHEDULE
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/issue-dev-handback.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/issue-dev-handback.err</string>
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
echo "  Lead tick: $("$VENV_PYTHON" "$SCHEDULE_PY" summary lead_tick) ($LEAD_TICK_LABEL) — C+D+E+F chain"
echo "  Agent:     $("$VENV_PYTHON" "$SCHEDULE_PY" summary agent) ($AGENT_LABEL)"
echo "  Executor:  $("$VENV_PYTHON" "$SCHEDULE_PY" summary executor) ($EXECUTOR_LABEL)"
echo "  Reviewer:  $("$VENV_PYTHON" "$SCHEDULE_PY" summary reviewer) ($REVIEWER_LABEL)"
echo "  Logs: $REPO_ROOT/logs/"

#!/usr/bin/env bash
# Install ASP launchd jobs (Observer + Reflector + Feishu Inbound Pipeline B/C/D)
#
# Usage:
#   bash launchd/install.sh [--uninstall]
#   bash launchd/install.sh --with-feishu-inbound   # include Pipeline B+C+D agents

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

# Observer: daily at 22:00
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
</dict>
</plist>
EOF

# Reflector: weekly on Sunday at 10:00
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
</dict>
</plist>
EOF

# --- Feishu Inbound Pipeline B: Triage (weekdays, :10 and :40 past 9-18) ---
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
  <array>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>10</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-triage.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-triage.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
</dict>
</plist>
EOF

# --- Feishu Inbound Pipeline C: Agent analysis (weekdays, :20 and :50 past 9-18) ---
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
  <array>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>20</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-agent.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/feishu-inbound-agent.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
</dict>
</plist>
EOF

# --- Pipeline D: Issue executor (weekdays, :35 and :05 past 9-18, offset +15 from C) ---
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
  <array>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>35</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>$REPO_ROOT/logs/issue-executor.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO_ROOT/logs/issue-executor.err</string>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
</dict>
</plist>
EOF

# Create logs directory
mkdir -p "$REPO_ROOT/logs"

# Load jobs
for label in "${ALL_LABELS[@]}"; do
  if launchctl list | grep -q "$label"; then
    launchctl unload "$LAUNCH_AGENTS/$label.plist" 2>/dev/null || true
  fi
  launchctl load "$LAUNCH_AGENTS/$label.plist"
  echo "Loaded $label"
done

echo ""
echo "ASP launchd jobs installed:"
echo "  Observer:  daily at 22:00       ($OBSERVER_LABEL)"
echo "  Reflector: Sunday at 10:00      ($REFLECTOR_LABEL)"
echo "  Triage:    weekdays :10/:40     ($TRIAGE_LABEL)"
echo "  Agent:     weekdays :20/:50     ($AGENT_LABEL)"
echo "  Executor:  weekdays :35/:05     ($EXECUTOR_LABEL)"
echo "  Logs: $REPO_ROOT/logs/"

#!/usr/bin/env bash
# Install ASP launchd jobs (Observer + Reflector)
#
# Usage:
#   bash launchd/install.sh [--uninstall]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

OBSERVER_LABEL="com.asp.observer"
REFLECTOR_LABEL="com.asp.reflector"

uninstall() {
  echo "Uninstalling ASP launchd jobs..."
  for label in "$OBSERVER_LABEL" "$REFLECTOR_LABEL"; do
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

# Create logs directory
mkdir -p "$REPO_ROOT/logs"

# Load jobs
for label in "$OBSERVER_LABEL" "$REFLECTOR_LABEL"; do
  if launchctl list | grep -q "$label"; then
    launchctl unload "$LAUNCH_AGENTS/$label.plist" 2>/dev/null || true
  fi
  launchctl load "$LAUNCH_AGENTS/$label.plist"
  echo "Loaded $label"
done

echo ""
echo "ASP launchd jobs installed:"
echo "  Observer:  daily at 22:00  ($OBSERVER_LABEL)"
echo "  Reflector: Sunday at 10:00 ($REFLECTOR_LABEL)"
echo "  Logs: $REPO_ROOT/logs/"

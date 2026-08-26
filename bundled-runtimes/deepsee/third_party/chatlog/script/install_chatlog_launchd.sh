#!/bin/zsh
set -euo pipefail

LABEL="com.chatlog.autostart"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="${CHATLOG_AUTOSTART_SCRIPT:-$SCRIPT_DIR/chatlog_autostart.sh}"
UID_VALUE="$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents"
chmod +x "$SCRIPT_PATH"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>${SCRIPT_PATH}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/chatlog_launchd.out</string>
  <key>StandardErrorPath</key>
  <string>/tmp/chatlog_launchd.err</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_VALUE}" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"
launchctl enable "gui/${UID_VALUE}/${LABEL}" || true
launchctl kickstart -k "gui/${UID_VALUE}/${LABEL}"

echo "installed_plist=$PLIST"
echo "label=$LABEL"

#!/usr/bin/env bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/com.ai-usage-hub.http.plist"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ai-usage-hub.http</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/mini/.local/bin/uv</string>
    <string>run</string>
    <string>--directory</string>
    <string>/Users/mini/ai-usage-hub</string>
    <string>python</string>
    <string>-m</string>
    <string>server.http_api</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/ai-usage-hub.log</string>
  <key>StandardErrorPath</key><string>/tmp/ai-usage-hub.err</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "LaunchAgent installed. HTTP API will be available at http://localhost:6737/status"

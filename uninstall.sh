#!/bin/bash
# uninstall.sh - Uninstaller for Voice Type Release Candidate (RC1)

echo "=== Voice Type RC1 Uninstallation Started ==="

# 1. Stop and disable service
echo "[1/3] Stopping and disabling systemd service..."
if systemctl --user is-active --quiet voice_type.service; then
    systemctl --user stop voice_type.service
fi
systemctl --user disable voice_type.service 2>/dev/null

# 2. Remove files
echo "[2/3] Cleaning up system configurations..."
rm -f "$HOME/.config/systemd/user/voice_type.service"
rm -f "$HOME/.local/share/applications/voice_type_toggle.desktop"
systemctl --user daemon-reload

# Cleanup PID/Health state files
rm -f "/tmp/voice_type.pid"
rm -f "/tmp/voice_type.health"
rm -f "/tmp/voice_type.toggle.lock"

# 3. Finalize
echo "[3/3] Finalizing cleanup..."
echo "Voice Type configuration and script files in '/home/rai/Scripts' and '/home/rai/config.json' have been kept."
echo "You can manually delete them if you want to perform a complete wipe."
echo "=== Voice Type RC1 Uninstallation Completed ==="
exit 0

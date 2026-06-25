#!/bin/bash
# update.sh - Update and configuration backup utility for Voice Type Daemon (RC1)

echo "=== Voice Type Update Started ==="

# 1. Back up config
CONFIG_FILE="/home/rai/config.json"
BACKUP_FILE="/home/rai/config.json.bak"
if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "$BACKUP_FILE"
    echo "Current configuration backed up to: $BACKUP_FILE"
fi

# 2. Restart and Reload
echo "Reloading systemd configuration..."
systemctl --user daemon-reload

echo "Restarting voice_type service..."
systemctl --user restart voice_type.service

# 3. Output status
sleep 2
systemctl --user status voice_type.service --no-pager

echo "=== Voice Type Update Completed ==="
exit 0

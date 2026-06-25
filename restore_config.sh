#!/bin/bash
# restore_config.sh - Restores configuration backup and restarts the daemon

CONFIG_FILE="/home/rai/config.json"
BACKUP_FILE="/home/rai/config.json.bak"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup configuration file '$BACKUP_FILE' does not exist."
    exit 1
fi

echo "Restoring configuration from backup..."
cp "$BACKUP_FILE" "$CONFIG_FILE"
echo "Restored configuration to $CONFIG_FILE successfully."

echo "Restarting service to apply restored settings..."
systemctl --user restart voice_type.service

sleep 1
if "/home/rai/Scripts/voice_type_health.sh" &>/dev/null; then
    echo "SUCCESS: Voice Type Daemon is active and healthy!"
else
    echo "WARNING: Health check failed or still loading. Run '/home/rai/Scripts/voice_type_health.sh' in a moment to verify status."
fi

exit 0

#!/bin/bash
# Dead-man's switch for voice_type daemon configuration.
# This script waits 3 minutes (180 seconds). If it is not disarmed,
# it restores the safe backup voice_type.py.bak and restarts the service.

DISARM_FILE="/tmp/deadman_disarm"
BACKUP_FILE="/home/rai/Scripts/voice_type.py.bak"
TARGET_FILE="/home/rai/Scripts/voice_type.py"

echo "[Deadman] Starting 3-minute safety countdown..."
sleep 180

if [ -f "$DISARM_FILE" ]; then
    echo "[Deadman] Disarm file found. Safely exiting without restoring backup."
    rm -f "$DISARM_FILE"
else
    echo "[Deadman] WARNING: Disarm file not found within 3 minutes!"
    echo "[Deadman] Restoring stable backup script..."
    if [ -f "$BACKUP_FILE" ]; then
        cp "$BACKUP_FILE" "$TARGET_FILE"
        echo "[Deadman] Restarting voice_type service..."
        systemctl --user restart voice_type
        echo "[Deadman] Backup restored and service restarted successfully."
    else
        echo "[Deadman] Error: Backup file $BACKUP_FILE not found!"
    fi
fi

#!/bin/bash
# voice_type_toggle.sh - Lightweight client toggle for Voice Type Daemon

echo "[$(date)] voice_type_toggle.sh called" >> /tmp/voice_type_toggle.log

PID_FILE="/tmp/voice_type.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    # Check if PID is running and matches voice_type
    if [ -d "/proc/$PID" ] && grep -q "voice_type.py" "/proc/$PID/cmdline" 2>/dev/null; then
        # Debounce logic (500ms client debounce)
        LOCK_FILE="/tmp/voice_type.toggle.lock"
        NOW=$(date +%s.%N)
        if [ -f "$LOCK_FILE" ]; then
            LAST=$(cat "$LOCK_FILE")
            DIFF=$(echo "$NOW - $LAST" | bc 2>/dev/null)
            if (( $(echo "$DIFF < 0.5" | bc -l 2>/dev/null) )); then
                echo "[toggle] Debounced quick press."
                exit 0
            fi
        fi
        echo "$NOW" > "$LOCK_FILE"

        # Send USR1 signal to daemon
        kill -USR1 "$PID"
        exit 0
    fi
fi

echo "voice_type.py daemon is not running." >&2
exit 1

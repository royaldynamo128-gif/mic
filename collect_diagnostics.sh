#!/bin/bash
# collect_diagnostics.sh - Collect system diagnostics for Voice Type Dictation Service

DIAG_FILE="/home/rai/voice_type_diagnostics.log"
echo "=== VOICE TYPE SYSTEM DIAGNOSTICS ===" > "$DIAG_FILE"
echo "Generated at: $(date)" >> "$DIAG_FILE"
echo "-------------------------------------" >> "$DIAG_FILE"

# 1. Daemon PID and Status
echo "=== 1. DAEMON PID AND HEALTH STATUS ===" >> "$DIAG_FILE"
PID_FILE="/tmp/voice_type.pid"
HEALTH_FILE="/tmp/voice_type.health"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "PID File: $PID_FILE (PID: $PID)" >> "$DIAG_FILE"
    if ps -p "$PID" >/dev/null 2>&1; then
        echo "Process state: RUNNING" >> "$DIAG_FILE"
        cat "/proc/$PID/cmdline" | tr '\0' ' ' >> "$DIAG_FILE"
        echo "" >> "$DIAG_FILE"
    else
        echo "Process state: DEAD (PID file exists but process is not running)" >> "$DIAG_FILE"
    fi
else
    echo "PID File: MISSING (Daemon not running or PID file deleted)" >> "$DIAG_FILE"
fi

if [ -f "$HEALTH_FILE" ]; then
    echo "Health File contents:" >> "$DIAG_FILE"
    cat "$HEALTH_FILE" >> "$DIAG_FILE"
    echo "" >> "$DIAG_FILE"
else
    echo "Health File: MISSING" >> "$DIAG_FILE"
fi
echo "" >> "$DIAG_FILE"

# 2. Systemd User Service Status
echo "=== 2. SYSTEMD USER SERVICE STATUS ===" >> "$DIAG_FILE"
systemctl --user status voice_type.service --no-pager >> "$DIAG_FILE" 2>&1
echo "" >> "$DIAG_FILE"

# 3. Last 50 lines of Systemd Journal Logs
echo "=== 3. JOURNALCTL SERVICE LOGS ===" >> "$DIAG_FILE"
journalctl --user -u voice_type.service -n 50 --no-pager >> "$DIAG_FILE" 2>&1
echo "" >> "$DIAG_FILE"

# 4. Last 50 lines of Structured Logs
echo "=== 4. DAEMON LOG FILE ===" >> "$DIAG_FILE"
LOG_FILE="$HOME/.local/share/voice_type/voice_type.log"
if [ -f "$LOG_FILE" ]; then
    tail -n 50 "$LOG_FILE" >> "$DIAG_FILE"
else
    echo "Log file: MISSING ($LOG_FILE)" >> "$DIAG_FILE"
fi
echo "" >> "$DIAG_FILE"

# 5. Microphone Input Source
echo "=== 5. PIPEWIRE/PULSEAUDIO STATUS ===" >> "$DIAG_FILE"
pactl get-default-source >> "$DIAG_FILE" 2>&1
echo "Input devices list:" >> "$DIAG_FILE"
pactl list short sources >> "$DIAG_FILE" 2>&1
echo "" >> "$DIAG_FILE"

# 6. GPU Status
echo "=== 6. NVIDIA GPU STATUS ===" >> "$DIAG_FILE"
nvidia-smi >> "$DIAG_FILE" 2>&1
echo "" >> "$DIAG_FILE"

# 7. ydotool Availability
echo "=== 7. YDOTOOL CONNECTIVITY ===" >> "$DIAG_FILE"
YDOTOOL_SOCKET="/run/user/$(id -u)/.ydotool_socket"
echo "Socket path: $YDOTOOL_SOCKET" >> "$DIAG_FILE"
if [ -S "$YDOTOOL_SOCKET" ]; then
    echo "Socket state: ACTIVE" >> "$DIAG_FILE"
else
    echo "Socket state: INACTIVE/MISSING" >> "$DIAG_FILE"
fi
/home/rai/.local/bin/ydotool help >> "$DIAG_FILE" 2>&1
echo "" >> "$DIAG_FILE"

# Print summary
echo "-------------------------------------" >> "$DIAG_FILE"
echo "Diagnostics collection finished." >> "$DIAG_FILE"

echo "Diagnostics successfully collected and written to: $DIAG_FILE"
echo "You can read the diagnostics by running: cat $DIAG_FILE"
exit 0

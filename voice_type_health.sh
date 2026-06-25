#!/bin/bash
# voice_type_health.sh - Lightweight health check for Voice Type Daemon

# 1. Daemon alive check
PID_FILE="/tmp/voice_type.pid"
if [ ! -f "$PID_FILE" ]; then
    echo "ERROR: Daemon PID file does not exist."
    exit 1
fi

PID=$(cat "$PID_FILE")
if ! ps -p "$PID" > /dev/null; then
    echo "ERROR: Daemon process (PID: $PID) is not running."
    exit 1
fi

if ! grep -q "voice_type.py" "/proc/$PID/cmdline" 2>/dev/null; then
    echo "ERROR: Process (PID: $PID) is not voice_type.py."
    exit 1
fi

# 2. Health metadata file check (Whisper loaded & GPU status)
HEALTH_FILE="/tmp/voice_type.health"
if [ ! -f "$HEALTH_FILE" ]; then
    echo "ERROR: Health metadata file has not been created yet."
    exit 1
fi

# Parse JSON variables using simple grep/sed/tr to avoid jq dependency
WHISPER_READY=$(grep -o '"whisper_loaded":[^,]*' "$HEALTH_FILE" | cut -d':' -f2 | tr -d ' "\n\r}')
GPU_TYPE=$(grep -o '"gpu_status":[^,]*' "$HEALTH_FILE" | cut -d':' -f2 | tr -d ' "\n\r}')
STATUS=$(grep -o '"status":[^,]*' "$HEALTH_FILE" | cut -d':' -f2 | tr -d ' "\n\r}')

if [ "$WHISPER_READY" != "true" ]; then
    echo "ERROR: Whisper model is still loading or failed to load (Status: $STATUS)."
    exit 1
fi

if [ "$GPU_TYPE" != "cuda" ]; then
    echo "WARNING: Whisper is running on CPU instead of GPU."
fi

# 3. Microphone availability
DEFAULT_SOURCE=$(pactl get-default-source 2>/dev/null)
if [ -z "$DEFAULT_SOURCE" ]; then
    echo "ERROR: No default audio source found in PulseAudio/PipeWire."
    exit 1
fi

# 4. GPU status check
if ! nvidia-smi > /dev/null 2>&1; then
    echo "ERROR: NVIDIA GPU or driver is not responding."
    exit 1
fi

# 5. ydotool availability
YDOTOOL_SOCKET="/run/user/$(id -u)/.ydotool_socket"
if [ ! -S "$YDOTOOL_SOCKET" ]; then
    echo "ERROR: ydotool socket file not found or not a socket: $YDOTOOL_SOCKET"
    exit 1
fi

if ! YDOTOOL_SOCKET="$YDOTOOL_SOCKET" /home/rai/.local/bin/ydotool help > /dev/null 2>&1; then
    echo "ERROR: ydotool executable failed to run or cannot connect to daemon socket."
    exit 1
fi

echo "OK: Voice Type Daemon is healthy (PID: $PID, Whisper: loaded, GPU: $GPU_TYPE, Mic: $DEFAULT_SOURCE)."
exit 0

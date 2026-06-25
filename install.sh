#!/bin/bash
# install.sh - Installer for Voice Type Release Candidate (RC1)

echo "=== Voice Type RC1 Installation Started ==="

# 1. Dependency checks
echo "[1/5] Verifying dependencies..."
dependencies=(xdotool xclip wl-copy pactl nvidia-smi)
for dep in "${dependencies[@]}"; do
    if ! command -v "$dep" &>/dev/null; then
        echo "WARNING: '$dep' is not installed or not in PATH. Some fallback features may be restricted."
    fi
done

# 2. Config Backup
echo "[2/5] Backing up configuration..."
CONFIG_FILE="/home/rai/config.json"
BACKUP_FILE="/home/rai/config.json.bak"
if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "$BACKUP_FILE"
    echo "Backup of existing configuration created at: $BACKUP_FILE"
else
    # Create default configuration
    cat <<EOF > "$CONFIG_FILE"
{
    "model_size": "large-v3",
    "device": "cuda",
    "compute_type": "int8_float16",
    "language": "en",
    "beam_size": 5,
    "patience": 2.0,
    "repetition_penalty": 1.0,
    "hotkey": "<Super>x",
    "play_sounds": false,
    "show_notifications": true,
    "typing_mode": "xdotool",
    "vad_threshold": 0.35,
    "min_speech_duration_ms": 150,
    "speech_pad_ms": 400,
    "vad_filter": false,
    "open_mic": false,
    "pause_threshold": 1.5,
    "logging_level": "INFO",
    "input_device_name": "default",
    "system_tray": true
}
EOF
    echo "Default configuration created at: $CONFIG_FILE"
fi

# 3. Setup Systemd and Desktop entries
echo "[3/5] Setting up system integration..."
mkdir -p "$HOME/.config/systemd/user"
mkdir -p "$HOME/.local/share/applications"

# Copy service and desktop templates
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/voice_type.service" "$HOME/.config/systemd/user/voice_type.service"
cp "$SCRIPT_DIR/voice_type_toggle.desktop" "$HOME/.local/share/applications/voice_type_toggle.desktop"

# Set permissions
chmod +x "/home/rai/Scripts/voice_type_toggle.sh"
chmod +x "/home/rai/Scripts/voice_type_health.sh"
chmod +x "/home/rai/Scripts/tray_indicator.py"
chmod +x "/home/rai/Scripts/voice_type.py"

# 4. Enable Service
echo "[4/5] Launching Systemd User Service..."
systemctl --user daemon-reload
systemctl --user enable voice_type.service
systemctl --user restart voice_type.service

# 5. Verify Installation
echo "[5/5] Performing self-check..."
sleep 2
if "/home/rai/Scripts/voice_type_health.sh" &>/dev/null; then
    echo "SUCCESS: Voice Type Daemon is active and healthy!"
else
    echo "WARNING: Health check failed or still loading. Run '/home/rai/Scripts/voice_type_health.sh' in a moment to verify status."
fi

echo "=== Voice Type RC1 Installation Completed Successfully ==="
exit 0

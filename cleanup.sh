#!/bin/bash
echo "=== Starting Complete Storage Optimization Cleanup ==="

# 1. User-Space Cleanups (do not require sudo)
echo "Cleaning user-space directories..."
rm -rf /home/rai/.cache/Unity /home/rai/.cache/unity3d
rm -rf /home/rai/.gemini/antigravity/browser_recordings/*
rm -rf /home/rai/.gemini/antigravity-ide/browser_recordings/*
rm -rf /home/rai/.steam /home/rai/.local/share/Steam /home/rai/Games/SteamLibrary
rm -rf /home/rai/.var/app/com.usebottles.bottles
rm -rf /home/rai/.whisper-env
rm -rf /home/rai/.config/unityhub
rm -rf /home/rai/.ollama
flatpak uninstall --delete-data -y com.usebottles.bottles 2>/dev/null
flatpak uninstall --unused -y 2>/dev/null

# Clean individual duplicate files
rm -f /home/rai/Downloads/Antigravity/Antigravity-x64/icudtl.dat
rm -f /home/rai/.npm/_npx/d07ada7b4a99c96e/node_modules/node-pty/prebuilds/win32-arm64/conpty/OpenConsole.exe
rm -f /home/rai/.npm/_npx/38c708f8d73fe4c9/node_modules/node-pty/third_party/conpty/1.23.251008001/win10-arm64/OpenConsole.exe
rm -f /home/rai/.npm/_npx/38c708f8d73fe4c9/node_modules/node-pty/prebuilds/win32-arm64/conpty/OpenConsole.exe
rm -f /home/rai/.hermes/hermes-agent/node_modules/node-pty/third_party/conpty/1.23.251008001/win10-arm64/OpenConsole.exe
rm -f /home/rai/.hermes/hermes-agent/node_modules/node-pty/prebuilds/win32-arm64/conpty/OpenConsole.exe
rm -f /home/rai/.npm/_npx/d07ada7b4a99c96e/node_modules/node-pty/prebuilds/win32-x64/conpty/OpenConsole.exe
rm -f /home/rai/.npm/_npx/38c708f8d73fe4c9/node_modules/node-pty/third_party/conpty/1.23.251008001/win10-x64/OpenConsole.exe
rm -f /home/rai/.npm/_npx/38c708f8d73fe4c9/node_modules/node-pty/prebuilds/win32-x64/conpty/OpenConsole.exe
rm -f /home/rai/.hermes/hermes-agent/node_modules/node-pty/third_party/conpty/1.23.251008001/win10-x64/OpenConsole.exe
rm -f /home/rai/.hermes/hermes-agent/node_modules/node-pty/prebuilds/win32-x64/conpty/OpenConsole.exe

# Recreate whisper-env with --system-site-packages
python3 -m venv --system-site-packages /home/rai/.whisper-env

# 2. System-Space Cleanups (require sudo)
echo "Cleaning system-space directories (will prompt for sudo)..."
sudo truncate -s 0 /var/log/syslog
sudo journalctl --vacuum-size=100M

# Stop & Remove Ollama
if systemctl is-active --quiet ollama; then
    sudo systemctl stop ollama
fi
sudo systemctl disable ollama 2>/dev/null
sudo rm -f /etc/systemd/system/ollama.service
sudo systemctl daemon-reload
sudo rm -f /usr/local/bin/ollama
sudo userdel ollama 2>/dev/null
sudo rm -rf /usr/share/ollama

# Purge Steam packages
sudo apt-get purge -y steam-installer steam-devices steam-libs steam-libs-i386 steam-libs-amd64
sudo apt-get autoremove -y

# Purge Unity Hub package
sudo apt-get purge -y unityhub
sudo apt-get autoremove -y

# Clear Flatpak leftovers
sudo rm -rf /var/lib/flatpak/.removed/*

echo "=== Cleanup Completed ==="

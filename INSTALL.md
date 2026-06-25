# Installation Guide

This guide details how to install, configure, and integrate the Voice Type Dictation Service on your Linux system.

## Prerequisites

Voice Type runs locally and requires:
* **Python 3.8+** with the following system dependencies:
  * `python-gobject` (PyGObject) for native system tray support.
  * Python virtual environment (`venv`).
* **Audio Server**: PipeWire or PulseAudio with `pactl`.
* **Subprocess Helpers**: `xdotool`, `xclip`, `wl-copy` (for Wayland), and `ydotool` (optional, for virtual keyboard input).
* **GPU (Recommended)**: NVIDIA GPU with CUDA & cuDNN drivers configured.

---

## Installation Steps

### Step 1: Run the Installer Script
Execute the packaging installation script:
```bash
/home/rai/Scripts/install.sh
```
This script:
1. Validates underlying system dependencies.
2. Backs up any existing `/home/rai/config.json` configuration file.
3. Automatically sets executable permissions on the main modules.
4. Registers and launches the systemd user service `voice_type.service`.
5. Spawns the companion native system tray item.

### Step 2: Register the Desktop Shortcut (KDE Plasma)
Under KDE Plasma, the global keyboard shortcut is handled by the window manager to trigger the client script:
1. Open **System Settings** -> **Shortcuts** -> **Custom Shortcuts**.
2. Create a new global shortcut application entry:
   * **Name**: Toggle Voice Dictation
   * **Trigger**: Set to your desired hotkey (e.g. `Meta+X` / `Super+X`).
   * **Action (Command/URL)**: `/home/rai/Scripts/voice_type_toggle.sh`
3. Click **Apply**.

---

## Service Administration

Manage the background service using systemd user session manager:

* **Start Service**: `systemctl --user start voice_type.service`
* **Stop Service**: `systemctl --user stop voice_type.service`
* **Restart Service**: `systemctl --user restart voice_type.service`
* **Check Status**: `systemctl --user status voice_type.service`
* **View Service Logs**: `journalctl --user -u voice_type.service -n 50 --no-pager`

---

## Uninstallation
To cleanly stop services and remove desktop shortcuts:
```bash
/home/rai/Scripts/uninstall.sh
```
This leaves scripts and user configurations intact under `/home/rai/Scripts/` and `/home/rai/config.json`.

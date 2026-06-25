# Troubleshooting Guide

This guide describes how to identify, debug, and resolve common issues with the Voice Type Dictation Service.

## 1. Collecting Diagnostics

If the daemon is behaving unexpectedly, run the dynamic diagnostics script:
```bash
/home/rai/Scripts/collect_diagnostics.sh
```
This command gathers:
* Active daemon process states and PID files.
* Systemd service status and the last 50 lines of logs from `journalctl`.
* Structured logs from `~/.local/share/voice_type/voice_type.log`.
* Audio input sources (PulseAudio/PipeWire status).
* NVIDIA GPU driver status.
* `ydotool` socket availability.

All diagnostics are written to: `/home/rai/voice_type_diagnostics.log`.

---

## 2. Common Issues & Solutions

### Stale PID Files
* **Symptom**: Systemd fails to start the daemon, or logs report `Another instance is already running` even though no python process is visible.
* **Resolution**: The hardened daemon automatically validates the contents of `/tmp/voice_type.pid` and deletes it if the process is dead or invalid. If a manual cleanup is required, run:
  ```bash
  rm -f /tmp/voice_type.pid /tmp/voice_type.health
  systemctl --user restart voice_type.service
  ```

### Audio Stream Stalled
* **Symptom**: You trigger dictation, the recording indicator lights up, but when you stop, nothing is transcribed. In the logs, you see: `RuntimeError: Audio stream stalled during recording`.
* **Resolution**: This occurs if the system audio server (PipeWire/PulseAudio) halts callbacks. The daemon watchdog automatically catches this, cancels the recording, and resets.
  * Check audio server status: `systemctl --user status pipewire.service`
  * Restart audio server: `systemctl --user restart pipewire.service wireplumber.service`

### GPU Compute Type Incompatibilities
* **Symptom**: Logs report `ctranslate2` errors during model loading, or fall back to CPU.
* **Resolution**: Some NVIDIA driver and hardware combinations do not support certain quantized precision types.
  * Try changing `"compute_type"` in `/home/rai/config.json` to `"float16"` or `"int8"`.
  * Restart the service: `systemctl --user restart voice_type.service`

### Missing ydotool Socket
* **Symptom**: Wayland text injection fails, or ydotool errors are printed.
* **Resolution**: Ensure `ydotool.service` is active:
  ```bash
  systemctl --user status ydotool.service
  systemctl --user restart ydotool.service
  ```

---

## 3. Configuration Reset
To revert all settings to factory defaults:
1. Delete the configuration file: `rm -f /home/rai/config.json`
2. Restart the daemon: `systemctl --user restart voice_type.service`
This will automatically generate a clean default `/home/rai/config.json`.

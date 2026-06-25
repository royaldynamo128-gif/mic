# Changelog

All notable changes to the Voice Type Dictation Service will be documented in this file.

---

## [RC1] - 2026-06-25 (Release Candidate 1)

### Added
- **Diagnostic Collection Script**: Introduced `/home/rai/Scripts/collect_diagnostics.sh` to compile system state, service logs, NVIDIA GPU statuses, PipeWire audio source maps, and virtual keyboard socket details into `/home/rai/voice_type_diagnostics.log`.
- **Lightweight Health Checker**: Added `/home/rai/Scripts/voice_type_health.sh` to dynamically query daemon status, model state, default microphones, and underlying `ydotool` availability.
- **Backup & Recovery Routines**: Added configuration backups (`/home/rai/config.json.bak`) in installer (`install.sh`) and update scripts (`update.sh`), along with an automatic restore mechanism (`restore_config.sh`).
- **Complete Packaging Scripts**: Structured the installation, updating, and uninstallation workflows (`install.sh`, `update.sh`, `uninstall.sh`) with dependency verifications and systemd integration.
- **Formalized Product Documentation**: Created `README.md`, `INSTALL.md`, `CONFIGURATION.md`, and `TROUBLESHOOTING.md`.

---

## [Feature Extensions Update] - 2026-06-24

### Added
- **System Tray Integration**: Implemented a standalone StatusNotifierItem system tray indicator (`tray_indicator.py`) using `AppIndicator3` / PyGObject to report status states (Idle, Recording, Transcribing) and expose quick toggle/exit control actions.
- **Large-Text Paste Acceleration**: Implemented automatic fallback to clipboard injection for dictations exceeding 50 characters to prevent keyboard rendering lag under xdotool/ydotool.
- **Clipboard History Preservation**: Added clipboard state interception. The daemon backs up, injects, and restores the user's active copy-paste buffer via a background thread after a 0.5s delay.
- **Toggle Debounce Protection**: Integrated a 0.5s client-side and 1.5s daemon-side debounce window to block accidental double-trigger inputs.
- **Whisper Biases and Hotwords**: Extended the speech-to-text pipeline with localized English/Hinglish vocabulary prompts and technical term injection (e.g. `systemd`, `Wayland`, `Git`).

### Changed
- **Dynamic Audio Source Resolution**: Upgraded sound capture to dynamically bind the PulseAudio/PipeWire default source name on stream init, automatically ignoring null-sink loopbacks (`.monitor` interfaces).

---

## [Production Hardening Update] - 2026-06-24

### Added
- **Systemd User Service Integration**: Created `voice_type.service` with automated graphical session startup ordering (`WantedBy=graphical-session.target`), restart protection limits (`StartLimitBurst=5`, `StartLimitIntervalSec=60`), and standard error capture.
- **Structured JSON Logging**: Implemented `RotatingFileHandler` with rotating JSON Lines output written to `~/.local/share/voice_type/voice_type.log` tracking service startups, stops, recording phases, transcription latency, warnings, and error stacks.
- **PID Integrity Shield**: Implemented automated stale PID checking and validation, scanning `/proc` to clean up dead pid files and prevent crash-loops.
- **Audio Stream Watchdog**: Added a stream stall watchdog that cancels and resets the recording loop if PipeWire/PulseAudio halts callbacks for longer than 5.0 seconds.

---

## [Stable Baseline V1] - 2026-06-24

### Added
- **SIGUSR1 IPC Architecture**: Main client-daemon signal path.
- **Voice Dictation Core**: Core `voice_type.py` transcription script leveraging `faster-whisper`.
- **Client Toggle Utility**: Lightweight `voice_type_toggle.sh` wrapper script.
- **KDE Global Shortcut Bindings**: Hooked standard `Meta+X` custom shortcut to invoke the toggle script via KDE Plasma.

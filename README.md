# Voice Type Dictation Service (Release Candidate 1)

Voice Type is a production-hardened, high-performance local voice dictation daemon designed for Linux desktops (fully tested on KDE Plasma / Wayland / X11). It leverages the **faster-whisper** engine to perform fast, highly accurate, offline speech-to-text transcription and inputs it directly at the cursor of any focused application.

This release (`VOICE_TYPE_RC1`) converts the stable baseline toggle implementation into a production-grade background service.

## Key Features in RC1

* **Zero-Lag IPC Architecture**: Leverages POSIX SIGUSR1 signal interrupts to toggle recording instantly (capturing compositors exclusively for GNOME and KDE).
* **Dynamic System Tray Indicator**: Integrates a StatusNotifierItem in the native KDE system tray displaying status states (Idle, Recording, Transcribing) and exposing toggle/quit options.
* **Preserved Clipboard History**: Intercepts paste events to back up, inject, and restore the user's copy-paste buffer, meaning dictation never overwrites your clipboard.
* **Large Dictation Safety**: Automatically detects dictations longer than 50 characters and forces clipboard-based pasting instead of key-by-key typing to bypass keyboard rendering lag.
* **GPU & Sound Hardware Hotplugging**: Auto-resolves default input microphones and recovers gracefully from transient sound server or driver restarts.
* **Reliability Shield**: Features stale PID file cleanup, queue debouncers to reject duplicate toggles, and safe timeouts on all background compositor sub-processes.

## Documentation Directory

* **[INSTALL.md](file:///home/rai/Scripts/docs/INSTALL.md)**: Setup, compilation, systemd service installation, and global shortcut mapping.
* **[CONFIGURATION.md](file:///home/rai/Scripts/docs/CONFIGURATION.md)**: Details on all parameters in `config.json`.
* **[TROUBLESHOOTING.md](file:///home/rai/Scripts/docs/TROUBLESHOOTING.md)**: Stale PID handling, audio driver watchdog resets, diagnostics reporting, and common fixes.
* **[CHANGELOG.md](file:///home/rai/Scripts/docs/CHANGELOG.md)**: Evolution history from v1 stable baseline to RC1.

# Configuration Guide

Voice Type settings are stored in `/home/rai/config.json`. This JSON document configures transcription behavior, microphone locking, logging levels, and the system tray.

---

## Configuration Parameter Reference

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`model_size`** | String | `"large-v3"` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`). |
| **`device`** | String | `"cuda"` | Execution backend (`cuda` for GPU, `cpu` for CPU fallback). |
| **`compute_type`** | String | `"int8_float16"`| Inference precision (`float16`, `int8`, `int8_float16`). |
| **`language`** | String | `"en"` | Language code for Whisper transcription bias. |
| **`beam_size`** | Integer| `5` | Beam search size (higher means better accuracy, slower latency). |
| **`play_sounds`** | Boolean| `false` | Enables/disables audio feedback tones on toggle and success. |
| **`show_notifications`**| Boolean| `true` | Enables system notification alerts. |
| **`typing_mode`** | String | `"xdotool"` | Typing backend (`clipboard` or `xdotool` key-simulation). |
| **`vad_threshold`** | Float | `0.35` | Voice Activity Detection confidence (0.0 to 1.0). |
| **`min_speech_duration_ms`**| Integer| `150` | Rejects audio segments shorter than this (removes clicks). |
| **`speech_pad_ms`** | Integer| `400` | Pre/post audio padding added to speech segments. |
| **`pause_threshold`**| Float | `1.5` | Silence duration (seconds) that triggers auto-stop. |
| **`logging_level`** | String | `"INFO"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| **`input_device_name`**| String | `"default"` | PulseAudio/PipeWire source name to lock input, or `"default"`. |
| **`system_tray`** | Boolean| `true` | Spawns status notifier menu in KDE panel when true. |

---

## Key Scenarios

### Locking Microphone to a Specific Device
To prevent the daemon from dynamically selecting the default system capture device (which might change when plugging in headphones):
1. Run `pactl list short sources` to find the exact name of your hardware mic (e.g. `alsa_input.pci-0000_05_00.6.analog-stereo`).
2. Update `/home/rai/config.json`:
   ```json
   "input_device_name": "alsa_input.pci-0000_05_00.6.analog-stereo"
   ```
3. Restart the service: `systemctl --user restart voice_type.service`

### Changing Logger Verbosity
To diagnose connection issues or check timestamps:
1. Set `"logging_level": "DEBUG"` in `config.json`.
2. Restart the service.
3. Logs will output to `~/.local/share/voice_type/voice_type.log`.

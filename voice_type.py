import os
import sys
import time
import signal
import subprocess
import queue
import threading
import json

CONFIG_PATH = os.path.expanduser("/home/rai/config.json")

DEFAULT_CONFIG = {
    "model_size": "large-v3",
    "device": "cuda",
    "compute_type": "float16",
    "language": "en",
    "beam_size": 5,
    "patience": 2.0,
    "repetition_penalty": 1.0,
    "hotkey": "<Super>x",
    "play_sounds": False,
    "show_notifications": True,
    "typing_mode": "clipboard",
    "vad_threshold": 0.35,
    "min_speech_duration_ms": 150,
    "speech_pad_ms": 400,
    "vad_filter": False,
    "open_mic": False,
    "pause_threshold": 1.5,
    "logging_level": "INFO",
    "input_device_name": "default",
    "system_tray": False,
    "max_recording_duration_seconds": 180.0,
    "silence_timeout_seconds": 8.0,
    "vad_sensitivity": 0.35,
    "minimum_speech_duration_ms": 250,
    "minimum_silence_duration_ms": 1000,
    "auto_copy_to_clipboard": True,
    "auto_paste_after_transcription": True,
    "restore_clipboard": True
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
        except Exception:
            pass
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except Exception as e:
        print(f"Error loading config.json, using defaults: {e}", file=sys.stderr)
        return DEFAULT_CONFIG

def import_systemd_environment():
    """Import environment variables from the systemd user manager to ensure Wayland/X11 display handles are present."""
    try:
        res = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True, text=True, check=True, timeout=5.0
        )
        for line in res.stdout.splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ[key] = val
    except Exception as e:
        print(f"Failed to import systemd user environment: {e}", file=sys.stderr)

    # ydotoold socket is never exported by systemd; inject it explicitly so
    # ydotool can connect regardless of how this daemon was launched.
    if "YDOTOOL_SOCKET" not in os.environ:
        uid = os.getuid()
        socket_path = f"/run/user/{uid}/.ydotool_socket"
        if os.path.exists(socket_path):
            os.environ["YDOTOOL_SOCKET"] = socket_path
            print(f"[env] Injected YDOTOOL_SOCKET={socket_path}")

# Import environment variables early so sound libraries initialize with the correct session paths
import_systemd_environment()

PID_FILE = "/tmp/voice_type.pid"

# ==============================================================================
# 1. Lightweight Toggle Client Logic (Runs in <5ms, no heavy imports)
# ==============================================================================
if len(sys.argv) > 1 and sys.argv[1] in ("--toggle", "-t"):
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f:
            try:
                pid = int(f.read().strip())
                # Client-side debounce lock
                lock_file = "/tmp/voice_type.toggle.lock"
                now = time.time()
                if os.path.exists(lock_file):
                    try:
                        with open(lock_file, "r") as lf:
                            last_t = float(lf.read().strip())
                        if now - last_t < 0.5:
                            sys.exit(0)
                    except Exception:
                        pass
                with open(lock_file, "w") as lf:
                    lf.write(str(now))
                
                # Check process validity to prevent targeting wrong pid
                is_valid = False
                try:
                    with open(f"/proc/{pid}/cmdline", "r") as cf:
                        cmdline = cf.read()
                        if "voice_type.py" in cmdline:
                            is_valid = True
                except Exception:
                    pass

                if is_valid:
                    os.kill(pid, signal.SIGUSR1)
                    sys.exit(0)
                else:
                    try:
                        os.remove(PID_FILE)
                    except OSError:
                        pass
            except (ProcessLookupError, ValueError):
                try:
                    os.remove(PID_FILE)
                except OSError:
                    pass
    print("voice_type.py daemon is not running.", file=sys.stderr)
    sys.exit(1)

# ==============================================================================
# 2. Structured Logging, Single Instance & Signal Debouncing
# ==============================================================================
import logging
from logging.handlers import RotatingFileHandler
import json
import re

LOG_DIR = os.path.expanduser("~/.local/share/voice_type")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "voice_type.log")

class StructuredJsonFormatter(logging.Formatter):
    def format(self, record):
        msg = record.getMessage()
        event = getattr(record, "event", None)
        
        # Attempt to parse event from bracket prefix if not explicitly set
        if not event:
            match = re.match(r"^\[Event:\s*([^\]]+)\]\s*(.*)$", msg)
            if match:
                event = match.group(1).strip()
                msg = match.group(2).strip()
            elif record.levelname == "ERROR":
                event = "error"
            elif record.levelname == "WARNING":
                event = "warning"
            else:
                event = "generic"
                
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "event": event,
            "message": msg
        }
        
        # Include transcription duration explicitly in structured field if applicable
        if event == "transcription_duration":
            dur_match = re.search(r"completed in ([\d\.]+)s", msg)
            if dur_match:
                try:
                    log_record["duration_sec"] = float(dur_match.group(1))
                except ValueError:
                    pass
                    
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

# Setup logging with rotation (5MB size, max 5 backup files)
config = load_config()
log_level_name = config.get("logging_level", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)

logger = logging.getLogger("voice_type")
logger.setLevel(log_level)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Rotating File Handler using Structured JSON
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(StructuredJsonFormatter())
logger.addHandler(file_handler)

# Stream Handler using human-readable format (mirror to systemd journal via stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

def write_health_status(whisper_loaded=False):
    health_info = {
        "pid": os.getpid(),
        "whisper_loaded": whisper_loaded,
        "gpu_status": "cuda" if globals().get("DEVICE") == "cuda" else "cpu",
        "last_pulse_source": os.environ.get("PULSE_SOURCE", "default"),
        "status": "OK" if whisper_loaded else "LOADING",
        "state": globals().get("state", "IDLE")
    }
    try:
        with open("/tmp/voice_type.health", "w") as hf:
            json.dump(health_info, hf)
    except Exception as e:
        logger.error(f"Failed to write health status file: {e}")

def check_single_instance():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                content = f.read().strip()
            if not content:
                logger.warning("[Crash Protection] PID file is empty. Proceeding.")
                return
            
            try:
                pid = int(content)
            except ValueError:
                logger.warning(f"[Crash Protection] PID file contains invalid content '{content}'. Overwriting.")
                try:
                    os.remove(PID_FILE)
                except OSError:
                    pass
                return

            # Check if process is running and indeed our daemon
            is_running = False
            try:
                os.kill(pid, 0)
                is_running = True
            except OSError:
                pass

            if is_running and pid != os.getpid():
                is_voice_type = False
                try:
                    with open(f"/proc/{pid}/cmdline", "r") as cf:
                        cmdline = cf.read()
                        if "voice_type.py" in cmdline:
                            is_voice_type = True
                except Exception:
                    pass
                
                if is_voice_type:
                    logger.error(f"[Crash Protection] Another instance is already running (PID: {pid}). Exiting.")
                    sys.exit(1)
                else:
                    logger.warning(f"[Crash Protection] PID file points to a non-daemon process (PID: {pid}). Overwriting stale PID file.")
                    try:
                        os.remove(PID_FILE)
                    except OSError:
                        pass
            else:
                logger.info(f"[Crash Protection] Stale PID file found (PID: {pid} is not running). Overwriting.")
                try:
                    os.remove(PID_FILE)
                except OSError:
                    pass
        except Exception as e:
            logger.warning(f"[Crash Protection] Error checking single instance: {e}. Overwriting.")

control_queue = queue.Queue()
model_loaded = False
last_signal_time = 0.0

def handle_signal(signum, frame):
    global last_signal_time
    now = time.time()
    if now - last_signal_time < 0.5:
        logger.warning("[Signal Handler] Debounced duplicate SIGUSR1 signal.")
        return
    last_signal_time = now

    logger.info("[Signal Handler] Received SIGUSR1 hotkey toggle signal from client.")
    if not model_loaded:
        logger.warning("[Toggle ignored: model still loading]")
        return
    control_queue.put("TOGGLE")

signal.signal(signal.SIGUSR1, handle_signal)

def handle_sigterm(signum, frame):
    logger.info("[Event: service_stop] Received SIGTERM, shutting down cleanly...")
    cleanup_pid()
    hide_mic_indicator()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)


def cleanup_pid():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(PID_FILE)
                # Cleanup health file too
                if os.path.exists("/tmp/voice_type.health"):
                    os.remove("/tmp/voice_type.health")
        except Exception:
            pass

def register_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    import atexit
    atexit.register(cleanup_pid)

# ==============================================================================
# 3. Pre-load NVIDIA CUDA/CuDNN libraries
# ==============================================================================
for pkg in ["cublas", "cudnn", "cuda_runtime", "nvrtc"]:
    try:
        import importlib
        mod = importlib.import_module(f"nvidia.{pkg}.lib")
        path = mod.__path__[0]
        for file in os.listdir(path):
            if ".so" in file:
                try:
                    import ctypes
                    ctypes.CDLL(os.path.join(path, file))
                except Exception:
                    pass
    except Exception:
        pass

# Define application metadata before sound library imports to enable persistent GNOME permissions
os.environ["PULSE_PROP_application.name"] = "Voice Dictation Daemon"
os.environ["PULSE_PROP_application.id"] = "org.freellmapi.voice-dictation"
os.environ["PULSE_PROP_media.role"] = "production"

import json
import numpy as np
from contextlib import contextmanager

@contextmanager
def suppress_stderr():
    """Silence low-level C warnings from ALSA/PortAudio/Jack."""
    try:
        stderr_fd = sys.stderr.fileno()
        saved_stderr_fd = os.dup(stderr_fd)
        with open(os.devnull, 'w') as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
            yield
    except Exception:
        yield
    finally:
        try:
            os.dup2(saved_stderr_fd, stderr_fd)
            os.close(saved_stderr_fd)
        except Exception:
            pass

with suppress_stderr():
    import sounddevice as sd

from faster_whisper import WhisperModel
from faster_whisper.vad import get_speech_timestamps, VadOptions

# ==============================================================================
# Configuration Paths & Default Settings
# ==============================================================================
SAMPLE_RATE = 16000

config = load_config()

# Read config settings
MODEL_SIZE = config.get("model_size", "large-v3")

# Force or prefer GPU (CUDA) if supported by ctranslate2
try:
    import ctranslate2
    supported_cuda_types = ctranslate2.get_supported_compute_types("cuda")
    if supported_cuda_types:
        print(f"[Device Check] GPU acceleration is active. Supported CUDA compute types: {supported_cuda_types}")
        DEVICE = "cuda"
        COMPUTE_TYPE = config.get("compute_type", "float16")
        if COMPUTE_TYPE not in supported_cuda_types:
            COMPUTE_TYPE = "float16" if "float16" in supported_cuda_types else list(supported_cuda_types)[0]
    else:
        print("[Device Check] GPU acceleration is NOT supported by ctranslate2 or no CUDA GPU is present. Falling back to CPU.")
        DEVICE = "cpu"
        COMPUTE_TYPE = "int8"
except Exception as e:
    print(f"[Device Check] Failed to verify GPU capability: {e}. Falling back to CPU.", file=sys.stderr)
    DEVICE = "cpu"
    COMPUTE_TYPE = "int8"

LANGUAGE = config.get("language", "en")
BEAM_SIZE = config.get("beam_size", 5)
PATIENCE = config.get("patience", 2.0)
REPETITION_PENALTY = config.get("repetition_penalty", 1.0)
HOTKEY = config.get("hotkey", "<Super>x")
PLAY_SOUNDS = config.get("play_sounds", True)
SHOW_NOTIFICATIONS = config.get("show_notifications", True)
TYPING_MODE = config.get("typing_mode", "clipboard")

# New configurable options
MAX_RECORDING_DURATION_SECONDS = config.get("max_recording_duration_seconds", 180.0)
SILENCE_TIMEOUT_SECONDS = config.get("silence_timeout_seconds", 8.0)
VAD_SENSITIVITY = config.get("vad_sensitivity", config.get("vad_threshold", 0.35))
VAD_THRESHOLD = VAD_SENSITIVITY

MINIMUM_SPEECH_DURATION_MS = config.get("minimum_speech_duration_ms", config.get("min_speech_duration_ms", 250))
MIN_SPEECH_DURATION_MS = MINIMUM_SPEECH_DURATION_MS

SPEECH_PAD_MS = config.get("speech_pad_ms", 400)
VAD_FILTER = config.get("vad_filter", False)
OPEN_MIC = config.get("open_mic", False)

# Mapping pause_threshold to silence_timeout_seconds (default 8.0s)
PAUSE_THRESHOLD = config.get("silence_timeout_seconds", config.get("pause_threshold", 8.0))

MINIMUM_SILENCE_DURATION_MS = config.get("minimum_silence_duration_ms", 1000)
AUTO_COPY_TO_CLIPBOARD = config.get("auto_copy_to_clipboard", True)
AUTO_PASTE_AFTER_TRANSCRIPTION = config.get("auto_paste_after_transcription", True)
RESTORE_CLIPBOARD = config.get("restore_clipboard", True)

# Technical context prompts for accuracy biasing
INITIAL_PROMPT = (
    "Technical coding and system administration session. "
    "Languages: Python, JavaScript, TypeScript, Bash, Rust, C++, Go. "
    "Libraries: PyTorch, TensorFlow, NumPy, Pandas, React, Next.js, Node.js, Vite. "
    "Topics: AI agents, LLMs, RAG, embeddings, vector databases, Docker, Kubernetes. "
    "Tools: git, systemd, systemctl, journalctl, xdotool, ydotool, wl-copy, pactl. "
    "File paths use forward slashes: /home/rai/Scripts/voice_type.py. "
    "Proper nouns are capitalized: GitHub, Linux, Whisper, KDE, Wayland, CUDA. "
    "Punctuation: sentences end with periods. Questions end with question marks. "
    "Hinglish phrases: yaar, kya, kaise, karna, chal, thik hai, matlab, aur bhi toh."
)
HOTWORDS = (
    "repo git systemd systemctl journalctl Wayland KDE Plasma GNOME CLI agentic SDK "
    "Durable Objects Cloudflare Workers Wrangler SQLite D1 KV vector embedding LLM "
    "Gemini Claude Whisper daemon CUDA cuDNN python pip apt pacman xdotool ydotool "
    "xclip wl-copy wl-paste sounddevice numpy scipy faster-whisper voice_type "
    "PyTorch TensorFlow Pandas React Next.js Node Docker PostgreSQL Redis Qdrant "
    "API endpoint interface config virtualenv venv npm pnpm cargo rustc TypeScript "
    "Hinglish yaar kya kaise karna chal thik hai matlab aur bhi toh suno dekho"
)

HALLUCINATION_BLOCKLIST = {
    "thank you", "hello", "you", "thanks for watching", "thank you for watching", "thank you very much",
    "subtitles by", "subscribe", "subscribe to", "bye", "goodbye",
    "learn more at www", "learn more at www. мер", "learn more at www.мер",
    "for more information visit the links in the description below",
    "if you have any questions, feel free to ask them in the comments below",
    "for more information, see description of the video",
    "please subscribe to my channel", "thank you and have a good day",
    "enjoy watching and see how we get things done", "thank you for listening",
    "we're trying to walk you down those two paths here", "if you like this video",
    "all of this is because we want to keep the host content as user-friendly as we can",
    "to koenigsegg, it's really, really easy to get the code",
    "first, let's talk about the table", "the table is your main thing",
    "the table is actually a little bit different", "the table itself is a little bit different"
}

# ------------------------------------------------------------------------------
# GNOME Custom Shortcut Auto-Installer
# ------------------------------------------------------------------------------
def install_gnome_shortcut():
    print(f"Registering GNOME custom shortcut for {HOTKEY}...")
    path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
    cmd_name = f"gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path} "
    
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    command_str = f"'{python_path} {script_path} --toggle'"
    
    try:
        subprocess.run(f"{cmd_name} name \"'Toggle Voice Dictation'\"", shell=True, check=True, timeout=5.0)
        subprocess.run(f"{cmd_name} command \"{command_str}\"", shell=True, check=True, timeout=5.0)
        subprocess.run(f"{cmd_name} binding \"'{HOTKEY}'\"", shell=True, check=True, timeout=5.0)
        
        # Query existing custom keybindings
        res = subprocess.run(
            ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            capture_output=True, text=True, check=True, timeout=5.0
        )
        current = res.stdout.strip()
        
        if path not in current:
            if current == "@as []" or current == "[]":
                new_list = f"['{path}']"
            else:
                items = current.strip("[]").replace("'", "").split(", ")
                items.append(path)
                new_list = "[" + ", ".join(f"'{i.strip()}'" for i in items if i.strip()) + "]"
            
            subprocess.run(
                ["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", new_list],
                check=True, timeout=5.0
            )
        print(f"GNOME global shortcut successfully registered to {HOTKEY}!")
        print("Mutter compositor will exclusively capture this key; it will never leak to apps.")
    except Exception as e:
        print(f"Error registering GNOME shortcut: {e}", file=sys.stderr)

if "--install-shortcut" in sys.argv:
    install_gnome_shortcut()
    sys.exit(0)

# ------------------------------------------------------------------------------
# Audio Feedback & Desktop Notifications
# ------------------------------------------------------------------------------
def play_sound(sound_name):
    current_config = load_config()
    if not current_config.get("play_sounds", True):
        return
    sound_path = f"/usr/share/sounds/freedesktop/stereo/{sound_name}.oga"
    if os.path.exists(sound_path):
        subprocess.Popen(
            ["paplay", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

# import_systemd_environment is defined and called at the top of the file

def get_clipboard_content():
    is_wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY") is not None
    if is_wayland:
        try:
            res = subprocess.run(["wl-paste", "-n"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass
    try:
        res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return None

def set_clipboard_content(text):
    if not text:
        return
    is_wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY") is not None
    if is_wayland:
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text, timeout=2.0)
            return
        except Exception:
            pass
    try:
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True)
        p.communicate(input=text, timeout=2.0)
    except Exception:
        pass

def copy_to_clipboard(text):
    """Ensure the text is copied to the system clipboard in both Wayland and X11 sessions."""
    set_clipboard_content(text)

def show_notification(title, message, icon="audio-input-microphone"):
    import subprocess
    current_config = load_config()
    if not current_config.get("show_notifications", True):
        return
    import_systemd_environment()
    subprocess.Popen(
        ["notify-send", "-t", "2000", "-i", icon, title, message],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def show_notification_with_action(title, message, text_to_copy, icon="audio-input-microphone"):
    current_config = load_config()
    if not current_config.get("show_notifications", True):
        return
    def worker():
        try:
            cmd = [
                "notify-send",
                "-t", "8000",
                "-i", icon,
                "--action=copy=Copy to Clipboard",
                title,
                message
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0)
            if "copy" in res.stdout.strip():
                copy_to_clipboard(text_to_copy)
        except Exception as e:
            print(f"Notification action error: {e}", file=sys.stderr)

    threading.Thread(target=worker, daemon=True).start()
# ------------------------------------------------------------------------------
# Text Injection Logic (Releases modifier keys to prevent shortcut conflicts)
# ------------------------------------------------------------------------------
def get_konsole_paste_shortcut():
    paths = [
        os.path.expanduser("~/.var/app/org.kde.konsole/config/konsolerc"),
        os.path.expanduser("~/.config/konsolerc")
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                import configparser
                config = configparser.ConfigParser()
                config.read(path)
                if "Shortcuts" in config and "edit_paste" in config["Shortcuts"]:
                    shortcut = config["Shortcuts"]["edit_paste"].strip().lower()
                    print(f"[inject_text] Detected Konsole paste shortcut from config: {shortcut}")
                    return shortcut
            except Exception as e:
                print(f"[inject_text] Error reading config {path}: {e}", file=sys.stderr)
    return "ctrl+shift+v"

def activate_window_by_uuid(uuid):
    print(f"[focus] activate_window_by_uuid ({uuid}) - DISABLED (SKELETON)")
    return False

last_injected_text = ""
last_injection_time = 0.0

def inject_text(text, transcription_duration=None):
    """Inject transcribed text into the focused window.

    If transcription_duration is provided, the text is revealed character-by-
    character via ydotool type --key-delay so the animation duration equals the
    Whisper processing time.  The complete text is already in the clipboard
    before the animation starts, so the user can Ctrl+V at any point.
    """
    global last_injected_text, last_injection_time
    if not text.strip():
        return

    now = time.time()
    # Prevent duplicate pastes within a 1.5-second window
    if text == last_injected_text and now - last_injection_time < 1.5:
        logger.warning(
            f"[inject_text] Blocked duplicate paste injection of '{text[:40]}' "
            f"within {now - last_injection_time:.2f}s"
        )
        return

    last_injected_text = text
    last_injection_time = now

    import_systemd_environment()

    current_config = load_config()
    auto_copy   = current_config.get("auto_copy_to_clipboard", True)
    auto_paste  = current_config.get("auto_paste_after_transcription", True)
    restore_enabled = current_config.get("restore_clipboard", False)
    typing_mode = current_config.get("typing_mode", "clipboard")

    # Always copy to clipboard first so text is safe even if insertion fails.
    # We do this unconditionally (regardless of auto_copy flag) so the
    # transcription is never lost.
    set_clipboard_content(text)

    # Verify clipboard integrity (up to 3 attempts)
    clipboard_ok = False
    for _attempt in range(3):
        time.sleep(0.05)
        copied = get_clipboard_content()
        if copied and copied.strip() == text.strip():
            clipboard_ok = True
            break
        set_clipboard_content(text)   # retry

    if not clipboard_ok:
        logger.error("[inject_text] Clipboard verification failed! Transcription may be truncated.")
    else:
        logger.info(f"[inject_text] Clipboard verified OK ({len(text)} chars).")

    if not auto_paste:
        logger.info("[inject_text] Auto-paste disabled – transcription is in clipboard.")
        return

    # ------------------------------------------------------------------
    # Decide injection strategy
    # ------------------------------------------------------------------
    import shutil
    is_wayland = (
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
        or os.environ.get("WAYLAND_DISPLAY") is not None
    )
    ydotool_bin = shutil.which("ydotool") or (
        os.path.expanduser("~/.local/bin/ydotool")
        if os.path.exists(os.path.expanduser("~/.local/bin/ydotool"))
        else None
    )

    # ------------------------------------------------------------------
    # Animated character-by-character injection
    # ------------------------------------------------------------------
    # When transcription_duration is available and ydotool is present we
    # use `ydotool type --key-delay <ms>` to produce a smooth reveal whose
    # total wall-clock time matches the Whisper processing time.  This is
    # purely a visual effect – the text is already safe in the clipboard.
    # ------------------------------------------------------------------
    n_chars = len(text)
    use_animated = (
        transcription_duration is not None
        and transcription_duration > 0.5
        and n_chars >= 2
        and is_wayland
        and ydotool_bin is not None
    )

    paste_success = False

    if use_animated:
        # Calculate per-key delay in milliseconds so the full text types
        # out in exactly transcription_duration seconds.
        # ydotool processes each character as one key-down+key-up pair, so
        # the delay between events is:  duration_ms / n_chars
        # We cap at 200 ms/char (very slow) and floor at 8 ms/char.
        ms_per_char = max(8, min(200, int((transcription_duration * 1000) / n_chars)))
        logger.info(
            f"[inject_text] Animated injection: {n_chars} chars "
            f"over {transcription_duration:.2f}s → {ms_per_char} ms/char"
        )
        ydotool_env = os.environ.copy()
        uid = os.getuid()
        if "YDOTOOL_SOCKET" not in ydotool_env:
            socket_path = f"/run/user/{uid}/.ydotool_socket"
            if os.path.exists(socket_path):
                ydotool_env["YDOTOOL_SOCKET"] = socket_path
        try:
            # Small pre-injection pause so the hotkey modifier is fully released
            time.sleep(0.35)
            result = subprocess.run(
                [
                    ydotool_bin, "type",
                    "--key-delay", str(ms_per_char),
                    "--", text + " ",
                ],
                env=ydotool_env,
                capture_output=True,
                text=True,
                timeout=transcription_duration + 10.0,
            )
            if result.returncode == 0:
                print(f"[inject_text] Animated ydotool type succeeded ({ms_per_char} ms/char)")
                paste_success = True
            else:
                print(
                    f"[inject_text] Animated ydotool type failed (rc={result.returncode}): {result.stderr.strip()}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"[inject_text] Animated ydotool type exception: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Fallback: clipboard paste (Ctrl+V / Ctrl+Shift+V)
    # ------------------------------------------------------------------
    if not paste_success:
        is_kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")
        is_terminal = False   # skeleton – window detection disabled
        use_ctrl_shift_v = False
        if is_terminal:
            shortcut = get_konsole_paste_shortcut()
            use_ctrl_shift_v = shortcut != "ctrl+v"

        if is_wayland:
            # 1. wtype (non-KDE Wayland)
            if not is_kde:
                wtype_bin = shutil.which("wtype") or (
                    os.path.expanduser("~/.local/bin/wtype")
                    if os.path.exists(os.path.expanduser("~/.local/bin/wtype"))
                    else None
                )
                if wtype_bin:
                    try:
                        time.sleep(0.40)
                        paste_keys = (
                            ["-M", "ctrl", "-M", "shift", "v", "-m", "shift", "-m", "ctrl"]
                            if use_ctrl_shift_v
                            else ["-M", "ctrl", "v", "-m", "ctrl"]
                        )
                        result = subprocess.run(
                            [wtype_bin] + paste_keys, capture_output=True, text=True, timeout=3.0
                        )
                        if result.returncode == 0:
                            print("[inject_text] wtype Paste succeeded")
                            paste_success = True
                    except Exception as exc:
                        print(f"[inject_text] wtype Paste exception: {exc}", file=sys.stderr)

            # 2. ydotool Ctrl+V (KDE/Wayland)
            if not paste_success and ydotool_bin:
                ydotool_env = os.environ.copy()
                uid = os.getuid()
                if "YDOTOOL_SOCKET" not in ydotool_env:
                    socket_path = f"/run/user/{uid}/.ydotool_socket"
                    if os.path.exists(socket_path):
                        ydotool_env["YDOTOOL_SOCKET"] = socket_path
                try:
                    time.sleep(0.40)
                    release_keys  = ["125:0", "126:0", "56:0", "100:0", "42:0", "54:0", "29:0", "97:0"]
                    paste_sequence = (
                        ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]
                        if use_ctrl_shift_v
                        else ["29:1", "47:1", "47:0", "29:0"]
                    )
                    result = subprocess.run(
                        [ydotool_bin, "key"] + release_keys + paste_sequence,
                        env=ydotool_env, capture_output=True, text=True, timeout=3.0,
                    )
                    if result.returncode == 0:
                        print("[inject_text] ydotool Ctrl+V Paste succeeded")
                        paste_success = True
                except Exception as exc:
                    print(f"[inject_text] ydotool Paste exception: {exc}", file=sys.stderr)
                finally:
                    clean_up = ["29:0", "42:0", "56:0", "125:0", "126:0", "97:0", "54:0", "100:0"]
                    subprocess.run(
                        [ydotool_bin, "key"] + clean_up,
                        env=ydotool_env, capture_output=True, timeout=3.0,
                    )

        # 3. xdotool paste fallback (X11 / last resort)
        if not paste_success:
            try:
                paste_key = "ctrl+shift+v" if use_ctrl_shift_v else "ctrl+v"
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", paste_key],
                    check=True, timeout=3.0,
                )
                paste_success = True
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Post-injection clipboard management
    # ------------------------------------------------------------------
    if paste_success:
        # Transcription remains in clipboard unless the user explicitly
        # opted in to restoring the old clipboard content.
        if restore_enabled and clipboard_ok:
            old_clipboard = get_clipboard_content()   # already set to text
            # Re-fetch original BEFORE we overwrote it – not available here,
            # so we intentionally skip restore when restore_clipboard=false.
            pass
        logger.info("[inject_text] Injection complete. Transcription in clipboard.")
    else:
        # Paste failed entirely: transcription is already safe in clipboard.
        logger.error("[inject_text] All paste methods failed. Transcription preserved in clipboard.")
        play_sound("suspend-error")
        show_notification(
            "Voice Type – Paste Failed",
            "Transcription kept in clipboard: " + text[:60] + ("…" if len(text) > 60 else ""),
            icon="dialog-warning",
        )

# ------------------------------------------------------------------------------
# Model Loading (Deferred until daemon start to prevent import-time OOM/delays)
# ------------------------------------------------------------------------------
model = None

def load_whisper_model():
    global model, model_loaded
    if model_loaded:
        return
    logger.info(f"Loading Whisper model '{MODEL_SIZE}' on {DEVICE} ({COMPUTE_TYPE})...")
    logger.info("Note: If the model is not cached, it will download locally (~1.6GB to ~3.1GB). Please wait...")
    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info(f"Model loaded successfully. Transcription engine is running on GPU: {DEVICE == 'cuda'}")
        model_loaded = True
    except Exception as e:
        logger.error(f"Failed to load local Whisper model: {e}")
        sys.exit(1)

# --------------------------------------------------------------------------------------------------------------------
# Control Loops & Buffering
# ------------------------------------------------------------------------------
state = "IDLE"

def set_state(new_state):
    global state
    state = new_state
    write_health_status(whisper_loaded=globals().get("model_loaded", False))

_tray_process = None

def start_tray_indicator():
    global _tray_process
    current_config = load_config()
    if current_config.get("system_tray", False):
        tray_script = "/home/rai/Scripts/tray_indicator.py"
        if os.path.exists(tray_script):
            logger.info("[Tray] Starting system tray indicator...")
            try:
                _tray_process = subprocess.Popen(
                    [sys.executable, tray_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                logger.error(f"[Tray] Failed to start system tray indicator: {e}")

def stop_tray_indicator():
    global _tray_process
    if _tray_process:
        logger.info("[Tray] Stopping system tray indicator...")
        try:
            _tray_process.terminate()
            _tray_process.wait(timeout=2.0)
        except Exception:
            try:
                _tray_process.kill()
            except Exception:
                pass
        _tray_process = None

import atexit
atexit.register(stop_tray_indicator)

audio_queue = queue.Queue()
audio_buffer = np.zeros(0, dtype=np.float32)
recording_start_time = 0.0

last_callback_time = time.time()

# ── Floating mic OSD indicator ─────────────────────────────────────────────────
_MIC_INDICATOR_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_indicator.py")
_mic_indicator_proc = None

def show_mic_indicator():
    global _mic_indicator_proc
    if _mic_indicator_proc is None:
        logger.info("[OSD] Spawning microphone OSD indicator...")
        try:
            _mic_indicator_proc = subprocess.Popen(
                [sys.executable, _MIC_INDICATOR_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.error(f"[OSD] Failed to spawn microphone indicator: {e}")

def hide_mic_indicator():
    global _mic_indicator_proc
    if _mic_indicator_proc is not None:
        logger.info("[OSD] Terminating microphone OSD indicator...")
        try:
            _mic_indicator_proc.terminate()
            _mic_indicator_proc.wait(timeout=1.0)
        except Exception:
            try:
                _mic_indicator_proc.kill()
            except Exception:
                pass
        _mic_indicator_proc = None

atexit.register(hide_mic_indicator)   # always clean up on daemon exit

def audio_callback(indata, frames, time_info, status):
    global last_callback_time
    if status:
        print(f"Audio status warning: {status}", file=sys.stderr)
    last_callback_time = time.time()
    audio_queue.put(indata[:, 0].copy())

# VAD parameters
vad_options = VadOptions(
    threshold=VAD_THRESHOLD,
    min_silence_duration_ms=400,
    speech_pad_ms=SPEECH_PAD_MS,
    min_speech_duration_ms=MIN_SPEECH_DURATION_MS
)

print(f"\nVoice Type daemon running (PID: {os.getpid()}).")
print("Install GNOME shortcut: python voice_type.py --install-shortcut")

# Helper functions for dynamic input device management
def get_default_input_device_name():
    """Return the real default PulseAudio/PipeWire capture source.

    .monitor sources are loopback sinks (null sinks used by PipeWire for
    inter-app routing). They never deliver real microphone data; opening one
    causes the stream watchdog to fire after 1.5 s every single boot.
    We skip them and keep polling until a real capture source is ready.
    """
    try:
        res = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True, check=True, timeout=3.0)
        name = res.stdout.strip()
        # Reject null-sink monitors – they are not real microphones
        if name and not name.endswith(".monitor"):
            return name
        # .monitor returned: PipeWire hasn't settled yet – return None so the
        # caller retries instead of opening a useless null-sink stream.
        print(f"[Device resolver] Default source '{name}' is a .monitor (null sink). Waiting for real mic...", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error querying pactl get-default-source: {e}", file=sys.stderr)
        return None

def find_sd_device_index(pulse_source_name):
    if not pulse_source_name:
        return None
    try:
        devices = sd.query_devices()
        # Search for exact name match first
        for idx, dev in enumerate(devices):
            if dev['name'] == pulse_source_name and dev['max_input_channels'] > 0:
                return idx
        # Substring match fallback
        for idx, dev in enumerate(devices):
            if pulse_source_name in dev['name'] and dev['max_input_channels'] > 0:
                return idx
    except Exception as e:
        print(f"Error querying sounddevice devices: {e}", file=sys.stderr)
    return None

transcription_lock = threading.Lock()

# ==============================================================================
# Threaded Background Transcription Worker
# ==============================================================================
# Helper to execute Whisper model transcription with a timeout limit
def transcribe_with_timeout(audio_to_transcribe, beam_size, patience, language, repetition_penalty, vad_filter, vad_threshold, speech_pad_ms, min_speech_duration_ms, min_silence_duration_ms, timeout=60.0):
    result_container = []
    exception_container = []
    
    def target():
        try:
            with transcription_lock:
                whisper_segments, _ = model.transcribe(
                    audio_to_transcribe,
                    beam_size=beam_size,
                    patience=patience,
                    language=language,
                    condition_on_previous_text=False,
                    initial_prompt=INITIAL_PROMPT,
                    hotwords=HOTWORDS,
                    repetition_penalty=repetition_penalty,
                    no_speech_threshold=None,
                    vad_filter=vad_filter,
                    vad_parameters=dict(
                        threshold=vad_threshold,
                        min_silence_duration_ms=min_silence_duration_ms,
                        speech_pad_ms=speech_pad_ms,
                        min_speech_duration_ms=min_speech_duration_ms
                    )
                )
                result_container.append(list(whisper_segments))
        except Exception as ex:
            exception_container.append(ex)
            
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    
    if t.is_alive():
        raise TimeoutError(f"Whisper transcription timed out after {timeout} seconds.")
    if exception_container:
        raise exception_container[0]
    if not result_container:
        raise RuntimeError("Whisper transcription returned no segments.")
    return result_container[0]

# Threaded Background Transcription Worker
# ==============================================================================
def transcribing_worker(audio_to_transcribe):
    global state
    logger.info("[Event: recording_stopped] Recording finished.")
    try:
        current_config = load_config()
        
        # Load transcription parameters dynamically from config
        beam_size = current_config.get("beam_size", BEAM_SIZE)
        patience = current_config.get("patience", PATIENCE)
        language = current_config.get("language", LANGUAGE)
        repetition_penalty = current_config.get("repetition_penalty", REPETITION_PENALTY)
        vad_filter = current_config.get("vad_filter", VAD_FILTER)
        vad_threshold = current_config.get("vad_sensitivity", current_config.get("vad_threshold", VAD_THRESHOLD))
        speech_pad_ms = current_config.get("speech_pad_ms", SPEECH_PAD_MS)
        min_speech_duration_ms = current_config.get("minimum_speech_duration_ms", current_config.get("min_speech_duration_ms", MIN_SPEECH_DURATION_MS))
        min_silence_duration_ms = current_config.get("minimum_silence_duration_ms", current_config.get("min_silence_duration_ms", 1000))

        # Check if there is any speech at all before transcribing (VAD pre-filter)
        local_vad_options = VadOptions(
            threshold=vad_threshold,
            min_silence_duration_ms=400,
            speech_pad_ms=speech_pad_ms,
            min_speech_duration_ms=min_speech_duration_ms
        )
        try:
            segments = get_speech_timestamps(audio_to_transcribe, local_vad_options)
            if len(segments) == 0:
                logger.warning("[Event: warning] Empty final transcription or hallucination filtered (No speech detected by VAD)")
                play_sound("suspend-error")
                return
        except Exception as vad_err:
            logger.error(f"[VAD pre-filter] Failed running VAD check: {vad_err}")

        logger.info(f"[Whisper Pipeline] Final transcription request initiated. Audio sample count: {len(audio_to_transcribe)}")
        
        start_time = time.time()
        
        # Run transcription with 60-second timeout
        whisper_segments = transcribe_with_timeout(
            audio_to_transcribe,
            beam_size=beam_size,
            patience=patience,
            language=language,
            repetition_penalty=repetition_penalty,
            vad_filter=vad_filter,
            vad_threshold=vad_threshold,
            speech_pad_ms=speech_pad_ms,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
            timeout=60.0
        )
        
        duration = time.time() - start_time
        logger.info(f"[Event: transcription_duration] Final transcription completed in {duration:.3f}s.")

        transcription = "".join(seg.text for seg in whisper_segments).strip()
        logger.info(f"[Whisper Pipeline] Final transcription result: '{transcription}'")

        cleaned_trans = transcription.lower().strip().rstrip(".!?,, ")
        if transcription and cleaned_trans not in HALLUCINATION_BLOCKLIST:
            inject_text(transcription, transcription_duration=duration)
        else:
            play_sound("suspend-error")
            logger.warning("[Event: warning] Empty final transcription or hallucination filtered")
    except Exception as e:
        logger.error(f"[Event: error] Error in transcription worker: {e}")
        play_sound("suspend-error")
    finally:
        hide_mic_indicator()   # hide the mic icon as soon as we are done
        set_state("IDLE")

def segment_transcribing_worker(audio_to_transcribe):
    try:
        current_config = load_config()
        beam_size = current_config.get("beam_size", BEAM_SIZE)
        patience = current_config.get("patience", PATIENCE)
        language = current_config.get("language", LANGUAGE)
        repetition_penalty = current_config.get("repetition_penalty", REPETITION_PENALTY)
        vad_filter = current_config.get("vad_filter", VAD_FILTER)
        vad_threshold = current_config.get("vad_sensitivity", current_config.get("vad_threshold", VAD_THRESHOLD))
        speech_pad_ms = current_config.get("speech_pad_ms", SPEECH_PAD_MS)
        min_speech_duration_ms = current_config.get("minimum_speech_duration_ms", current_config.get("min_speech_duration_ms", MIN_SPEECH_DURATION_MS))
        min_silence_duration_ms = current_config.get("minimum_silence_duration_ms", current_config.get("min_silence_duration_ms", 1000))

        logger.info(f"[Whisper Pipeline] Segment transcription request initiated. Audio sample count: {len(audio_to_transcribe)}")
        
        start_time = time.time()
        
        # Run transcription with 10-second timeout for partial segments
        whisper_segments = transcribe_with_timeout(
            audio_to_transcribe,
            beam_size=beam_size,
            patience=patience,
            language=language,
            repetition_penalty=repetition_penalty,
            vad_filter=vad_filter,
            vad_threshold=vad_threshold,
            speech_pad_ms=speech_pad_ms,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
            timeout=45.0
        )
        
        duration = time.time() - start_time
        logger.info(f"[Event: transcription_duration] Segment transcription completed in {duration:.3f}s.")

        transcription = "".join(seg.text for seg in whisper_segments).strip()
        logger.info(f"[Whisper Pipeline] Segment transcription result: '{transcription}'")  # noqa: E501

        cleaned_trans = transcription.lower().strip().rstrip(".!?,, ")
        if transcription and cleaned_trans not in HALLUCINATION_BLOCKLIST:
            inject_text(transcription, transcription_duration=duration)
        else:
            logger.info("[Segment] Empty transcription or hallucination filtered")
    except Exception as e:
        logger.error(f"[Event: error] Error in segment transcription worker: {e}")

def run_daemon():
    global current_device_name, state, audio_buffer, recording_start_time, last_callback_time
    logger.info("[Event: service_start] Starting Voice Type Dictation Daemon.")
    check_single_instance()
    register_pid()
    write_health_status(whisper_loaded=False)
    load_whisper_model()
    set_state("IDLE")
    start_tray_indicator()
    current_device_name = None

    while True:
        try:
            # Drain any stale toggle commands that were queued during transcribing/idle transition
            if state == "IDLE":
                while not control_queue.empty():
                    try:
                        control_queue.get_nowait()
                    except queue.Empty:
                        break
            
            # Block until a toggle signal is received (drives idle CPU usage to 0%)
            cmd = control_queue.get()
            if cmd != "TOGGLE":
                continue
                
            if state == "TRANSCRIBING":
                print("[Ignored toggle: still transcribing in background]")
                continue

            # ------------------------------------------------------------------
            # Resolve target microphone dynamically on recording start
            # ------------------------------------------------------------------
            current_config = load_config()
            configured_device = current_config.get("input_device_name", "default")
            if configured_device and configured_device != "default":
                default_pulse_source = configured_device
            else:
                default_pulse_source = None
                pipewire_settle_attempts = 0
                while default_pulse_source is None:
                    default_pulse_source = get_default_input_device_name()
                    if default_pulse_source is None:
                        wait = min(2 + pipewire_settle_attempts, 8)
                        print(f"[Stream loop] No real capture source yet (attempt {pipewire_settle_attempts + 1}). Retrying in {wait}s...", file=sys.stderr)
                        time.sleep(wait)
                        pipewire_settle_attempts += 1

            sd_device_index = find_sd_device_index(default_pulse_source)

            try:
                with suppress_stderr():
                    if sd_device_index is not None:
                        input_device = sd.query_devices(sd_device_index, kind="input")
                        print(f"Opening microphone: {input_device['name']} (index {sd_device_index}) (16kHz)...")
                        current_device_name = default_pulse_source
                    else:
                        input_device = sd.query_devices(kind="input")
                        print(f"Opening default microphone: {input_device['name']} (16kHz)...")
                        current_device_name = input_device['name']
            except Exception as e:
                print(f"No audio input device found: {e}.", file=sys.stderr)
                play_sound("suspend-error")
                continue

            set_state("RECORDING")
            recording_start_time = time.time()
            audio_buffer = np.zeros(0, dtype=np.float32)
            
            # [focus handling disabled in skeleton]
            pass
            
            # Drain old microphone buffers
            while not audio_queue.empty():
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Drain any pending control queue messages to prevent duplicate/accidental toggle processing
            while not control_queue.empty():
                try:
                    control_queue.get_nowait()
                except queue.Empty:
                    break
            
            play_sound("bell")
            show_mic_indicator()
            logger.info("[Event: recording_started] Recording initiated.")

            last_callback_time = time.time()

            # Open the microphone stream on-demand
            try:
                with suppress_stderr():
                    stream = sd.InputStream(
                        device=sd_device_index,
                        channels=1,
                        samplerate=SAMPLE_RATE,
                        callback=audio_callback,
                        blocksize=int(SAMPLE_RATE * 0.1),
                    )
                
                with stream:
                    while state == "RECORDING":
                        # Watchdog: fail if callbacks stall for >5s during recording
                        if time.time() - last_callback_time > 5.0:
                            raise RuntimeError("Audio stream stalled during recording.")

                        # Check for stop toggle
                        try:
                            cmd = control_queue.get_nowait()
                            if cmd == "TOGGLE":
                                if time.time() - recording_start_time < 0.6:
                                    print("[Ignored toggle: too quick]")
                                    continue
                                
                                set_state("TRANSCRIBING")
                                break
                        except queue.Empty:
                            pass

                        # Process audio chunk
                        try:
                            chunk = audio_queue.get(timeout=0.05)
                            audio_buffer = np.append(audio_buffer, chunk)
                            
                            # Log active capture buffer size periodically
                            chunk_count = getattr(transcribing_worker, "chunk_count", 0) + 1
                            setattr(transcribing_worker, "chunk_count", chunk_count)
                            if chunk_count % 20 == 0:
                                print(f"[Audio Capture] Active capture: {len(audio_buffer)/SAMPLE_RATE:.1f}s of audio currently in buffer.")
                            
                            current_config = load_config()
                            open_mic_enabled = current_config.get("open_mic", OPEN_MIC)
                            
                            # Load values supporting new keys
                            pause_threshold = current_config.get("silence_timeout_seconds", current_config.get("pause_threshold", PAUSE_THRESHOLD))
                            max_duration = current_config.get("max_recording_duration_seconds", MAX_RECORDING_DURATION_SECONDS)
                            vad_threshold = current_config.get("vad_sensitivity", current_config.get("vad_threshold", VAD_THRESHOLD))
                            speech_pad_ms = current_config.get("speech_pad_ms", SPEECH_PAD_MS)
                            min_speech_duration_ms = current_config.get("minimum_speech_duration_ms", current_config.get("min_speech_duration_ms", MIN_SPEECH_DURATION_MS))
                            
                            # Recreate VadOptions dynamically
                            local_vad_options = VadOptions(
                                threshold=vad_threshold,
                                min_silence_duration_ms=400,
                                speech_pad_ms=speech_pad_ms,
                                min_speech_duration_ms=min_speech_duration_ms
                            )
                            # Run VAD on the audio buffer
                            segments = get_speech_timestamps(audio_buffer, local_vad_options)
                            
                            if open_mic_enabled:
                                # First, check if buffer has grown too large (e.g. 15s) to prevent bloat/crashes
                                max_buffer_len = SAMPLE_RATE * 15
                                if len(audio_buffer) > max_buffer_len:
                                    print(f"[Open-mic] Max buffer length reached ({len(audio_buffer)/SAMPLE_RATE:.1f}s). Forcing transcription to prevent bloat...")
                                    segment_audio = audio_buffer.copy()
                                    # Keep the last 0.5s for continuity
                                    audio_buffer = audio_buffer[-int(SAMPLE_RATE * 0.5):]
                                    t = threading.Thread(
                                        target=segment_transcribing_worker,
                                        args=(segment_audio.copy(),),
                                        daemon=True
                                    )
                                    t.start()
                                    continue

                                if len(segments) == 0:
                                    # Keep only the last 0.5s of audio as pre-speech context
                                    max_silence_keep = int(SAMPLE_RATE * 0.5)
                                    if len(audio_buffer) > max_silence_keep:
                                        audio_buffer = audio_buffer[-max_silence_keep:]
                                else:
                                    start_sample = segments[0]["start"]
                                    end_sample = segments[-1]["end"]
                                    silence_samples = len(audio_buffer) - end_sample
                                    silence_seconds = silence_samples / SAMPLE_RATE
                                    
                                    if silence_seconds >= pause_threshold:
                                        speech_pad_samples = int(SAMPLE_RATE * (SPEECH_PAD_MS / 1000.0))
                                        transcribe_start = max(0, start_sample - speech_pad_samples)
                                        transcribe_end = min(len(audio_buffer), end_sample + speech_pad_samples)
                                        
                                        segment_audio = audio_buffer[transcribe_start:transcribe_end]
                                        audio_buffer = audio_buffer[transcribe_end:]
                                        
                                        print(f"[Open-mic] Pause detected ({silence_seconds:.2f}s). Transcribing segment...")
                                        t = threading.Thread(
                                            target=segment_transcribing_worker,
                                            args=(segment_audio.copy(),),
                                            daemon=True
                                        )
                                        t.start()
                            else:
                                # Standard single dictation mode with VAD auto-stop
                                # Prevent standard recording from running indefinitely (e.g. max 30 seconds)
                                elapsed = time.time() - recording_start_time
                                if elapsed > max_duration:
                                    print(f"[Auto-stop] Maximum recording limit reached ({elapsed:.1f}s). Stopping recording.")
                                    set_state("TRANSCRIBING")
                                    break
                                    
                                if len(segments) > 0:
                                    start_sample = segments[0]["start"]
                                    end_sample = segments[-1]["end"]
                                    silence_samples = len(audio_buffer) - end_sample
                                    silence_seconds = silence_samples / SAMPLE_RATE
                                    
                                    if silence_seconds >= pause_threshold:
                                        print(f"[Auto-stop] Silence of {silence_seconds:.2f}s detected. Stopping recording.")
                                        set_state("TRANSCRIBING")
                                        break
                                else:
                                    # No speech detected yet
                                    elapsed = time.time() - recording_start_time
                                    if elapsed > 5.0:
                                        print("[Auto-stop] No speech detected for 5.0 seconds. Canceling recording.")
                                        hide_mic_indicator()
                                        set_state("IDLE")
                                        # Play warning sound and clear buffer so it doesn't transcribe
                                        play_sound("suspend-error")
                                        audio_buffer = np.zeros(0, dtype=np.float32)
                                        break
                        except queue.Empty:
                            pass
            except Exception as e:
                                print(f"Recording error: {e}", file=sys.stderr)
                                hide_mic_indicator()
                                play_sound("suspend-error")
                                set_state("IDLE")
                                continue

            # Start background transcription if recording finished successfully
            if state == "TRANSCRIBING":
                # Drain any remaining chunks from the audio queue
                while not audio_queue.empty():
                    try:
                        chunk = audio_queue.get_nowait()
                        audio_buffer = np.append(audio_buffer, chunk)
                    except queue.Empty:
                        break

                if len(audio_buffer) == 0:
                    play_sound("suspend-error")
                    set_state("IDLE")
                    continue
                    
                play_sound("complete")
                print("[Transcribing...]")
                t = threading.Thread(target=transcribing_worker, args=(audio_buffer.copy(),), daemon=True)
                t.start()

        except Exception as e:
            print(f"Main loop error: {e}", file=sys.stderr)
            hide_mic_indicator()
            play_sound("suspend-error")
            set_state("IDLE")
            time.sleep(2.0)

if __name__ == "__main__":
    run_daemon()

import os
import subprocess
import sys
import queue
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from faster_whisper.vad import get_speech_timestamps, VadOptions

# Configuration
MODEL_SIZE = "large-v3-turbo"
DEVICE = "cuda"
COMPUTE_TYPE = "float16"
SAMPLE_RATE = 16000

# VAD & Streaming Settings
PAUSE_THRESHOLD = 0.6  # Seconds of silence to trigger transcription (pause detection)
MIN_SPEECH_DURATION_MS = 150  # Rejects clicks, pops, keyboard noise, breaths
SPEECH_PAD_MS = 300  # Padding added before and after speech segment for context
MAX_SPEECH_DURATION = 15.0  # Force transcription on very long speech segments
VAD_THRESHOLD = 0.5  # VAD model confidence threshold

# Strict blocklist for classic Whisper silence-hallucinations
HALLUCINATION_BLOCKLIST = {
    "thank you.",
    "thank you",
    "hello.",
    "hello",
    "you.",
    "you",
    "thanks for watching.",
    "thanks for watching",
    "subtitles by",
}

print(f"Loading Whisper model '{MODEL_SIZE}' on {DEVICE} ({COMPUTE_TYPE})...")
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    print("Model loaded successfully. Ready for input.")
except Exception as e:
    print(f"Error loading Whisper model: {e}", file=sys.stderr)
    sys.exit(1)

# Thread-safe queue for sharing audio data between the audio callback and main loop
audio_queue = queue.Queue()


def type_text(text):
    if not text.strip():
        return
    # Run xdotool to type the text
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def audio_callback(indata, frames, time_info, status):
    if status:
        # Avoid printing too many errors, but log warnings
        print(f"Audio status warning: {status}", file=sys.stderr)
    # Put a copy of the mono audio chunk in the queue
    audio_queue.put(indata[:, 0].copy())


# Detect and display the audio input device being used
try:
    input_device = sd.query_devices(kind="input")
    print(f"Using input device: {input_device['name']} (Sample Rate: {SAMPLE_RATE}Hz)")
except Exception as e:
    print(f"Warning: Could not query input device: {e}", file=sys.stderr)

# Initialize the audio stream
stream = sd.InputStream(
    channels=1,
    samplerate=SAMPLE_RATE,
    callback=audio_callback,
    blocksize=int(SAMPLE_RATE * 0.1),  # Call callback every 100ms
)

# Initialize VAD options
vad_options = VadOptions(
    threshold=VAD_THRESHOLD,
    min_silence_duration_ms=400,
    speech_pad_ms=SPEECH_PAD_MS,
    min_speech_duration_ms=MIN_SPEECH_DURATION_MS,
)

audio_buffer = np.zeros(0, dtype=np.float32)

print("\nListening (VAD-segmentation Mode)... Speak now.")
print("Press Ctrl+C to stop.")

with stream:
    try:
        while True:
            # Block until a chunk is available
            try:
                chunk = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            audio_buffer = np.append(audio_buffer, chunk)

            # Consume all other available chunks in the queue to minimize processing latency
            while not audio_queue.empty():
                audio_buffer = np.append(audio_buffer, audio_queue.get_nowait())

            # Detect speech timestamps in the accumulated buffer
            segments = get_speech_timestamps(audio_buffer, vad_options)

            if len(segments) == 0:
                # No speech detected in the buffer:
                # Keep only the last 0.5s of audio as pre-speech padding/context and discard the rest of the silence
                max_silence_keep = int(SAMPLE_RATE * 0.5)
                if len(audio_buffer) > max_silence_keep:
                    audio_buffer = audio_buffer[-max_silence_keep:]
            else:
                # Speech detected!
                start_sample = segments[0]["start"]
                end_sample = segments[-1]["end"]

                # Calculate silence duration at the end of the buffer
                silence_samples = len(audio_buffer) - end_sample
                silence_seconds = silence_samples / SAMPLE_RATE

                # Calculate current active speech segment duration
                speech_duration_seconds = (len(audio_buffer) - start_sample) / SAMPLE_RATE

                # Condition 1: User paused after speaking (silence >= PAUSE_THRESHOLD)
                if silence_seconds >= PAUSE_THRESHOLD:
                    # Crop the speech segment with padding
                    speech_pad_samples = int(SAMPLE_RATE * (SPEECH_PAD_MS / 1000.0))
                    transcribe_start = max(0, start_sample - speech_pad_samples)
                    transcribe_end = min(len(audio_buffer), end_sample + speech_pad_samples)

                    transcribe_audio = audio_buffer[transcribe_start:transcribe_end]

                    # Transcribe the utterance
                    whisper_segments, _ = model.transcribe(
                        transcribe_audio,
                        beam_size=5,
                        language="en",
                        temperature=0.0,
                        condition_on_previous_text=False,
                    )

                    transcription = "".join(seg.text for seg in whisper_segments).strip()

                    # Only type if it has text and is not a hallucination
                    if (
                        transcription
                        and transcription.lower() not in HALLUCINATION_BLOCKLIST
                    ):
                        print(f"Typed: {transcription}")
                        type_text(transcription + " ")

                    # Retain only the unprocessed portion of the buffer
                    audio_buffer = audio_buffer[transcribe_end:]

                # Condition 2: Continuous speech exceeded maximum duration threshold (safety limit)
                elif speech_duration_seconds >= MAX_SPEECH_DURATION:
                    # Force transcribe the active speech up to the current end
                    speech_pad_samples = int(SAMPLE_RATE * (SPEECH_PAD_MS / 1000.0))
                    transcribe_start = max(0, start_sample - speech_pad_samples)
                    transcribe_audio = audio_buffer[transcribe_start:]

                    whisper_segments, _ = model.transcribe(
                        transcribe_audio,
                        beam_size=5,
                        language="en",
                        temperature=0.0,
                        condition_on_previous_text=False,
                    )

                    transcription = "".join(seg.text for seg in whisper_segments).strip()

                    if (
                        transcription
                        and transcription.lower() not in HALLUCINATION_BLOCKLIST
                    ):
                        print(f"Typed (Force-cut): {transcription}")
                        type_text(transcription + " ")

                    # Clear the buffer completely to avoid repeating
                    audio_buffer = np.zeros(0, dtype=np.float32)

    except KeyboardInterrupt:
        print("\nStopped.")

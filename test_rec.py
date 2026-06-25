import sys
from faster_whisper import WhisperModel

print("Loading model...")
model = WhisperModel("large-v3-turbo", device="cuda")

print("Transcribing /tmp/test_mic.wav...")
segments, info = model.transcribe("/tmp/test_mic.wav", language="en")

print(f"Detected language '{info.language}' with probability {info.language_probability:.2f}")

for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")

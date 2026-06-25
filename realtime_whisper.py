import queue
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

print("Loading model...")
model = WhisperModel("large-v3-turbo", device="cuda")

q = queue.Queue()

def callback(indata, frames, time, status):
    q.put(indata.copy())

print("Listening... Press Ctrl+C to stop.")

with sd.InputStream(
    samplerate=16000,
    channels=1,
    dtype="float32",
    callback=callback,
):
    audio_buffer = np.empty((0, 1), dtype=np.float32)

    while True:
        chunk = q.get()
        audio_buffer = np.concatenate([audio_buffer, chunk])

        if len(audio_buffer) >= 16000 * 3:
            audio = audio_buffer.flatten()
            audio_buffer = np.empty((0, 1), dtype=np.float32)

            segments, _ = model.transcribe(
                audio,
                language="en",
                vad_filter=True
            )

            for segment in segments:
                print(segment.text, flush=True)

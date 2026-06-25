from faster_whisper import WhisperModel

print("Loading model...")

model = WhisperModel("large-v3")

segments, info = model.transcribe("sample.mp3")

for segment in segments:
    print(segment.text)

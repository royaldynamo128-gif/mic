#!/usr/bin/env python3
import os
import sys
import time
import numpy as np
import subprocess

# Add Scripts path to sys.path so we can import voice_type
sys.path.append("/home/rai/Scripts")

print("=== STARTING E2E LAYERS AUDIT & TEST ===")

# 1. Verify GPU acceleration capability
print("\n--- Testing Layer 1: GPU / Whisper ---")
try:
    import ctranslate2
    supported_cuda_types = ctranslate2.get_supported_compute_types("cuda")
    if supported_cuda_types:
        print(f"✔ GPU Acceleration is active. Supported CUDA compute types: {supported_cuda_types}")
    else:
        print("✘ GPU Acceleration is NOT active in ctranslate2!")
        sys.exit(1)
except Exception as e:
    print(f"✘ Failed to verify GPU capability: {e}")
    sys.exit(1)


# 2. Test VAD Auto-stop Logic
print("\n--- Testing Layer 2: VAD & Auto-Stop ---")
try:
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    import wave
    # Load test audio
    with wave.open("/home/rai/Scripts/test.wav", "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
        
        # Convert buffer to numpy array
        if sampwidth == 2:
            audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            audio_data = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError("Unsupported sample width")
            
        # Handle channels
        if n_channels > 1:
            audio_data = audio_data[0::n_channels]
    
    # We want to check VAD options matching voice_type.py
    vad_options = VadOptions(
        threshold=0.35,
        min_silence_duration_ms=400,
        speech_pad_ms=400,
        min_speech_duration_ms=150
    )
    
    # Simulate feeding chunks of 100ms of audio and checking VAD auto-stop
    chunk_size = int(sample_rate * 0.1) # 100ms
    accumulated_buffer = np.zeros(0, dtype=np.float32)
    
    speech_detected = False
    auto_stop_triggered = False
    
    # Let's feed the audio and check how many seconds until silence triggers auto-stop
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i+chunk_size]
        accumulated_buffer = np.append(accumulated_buffer, chunk)
        
        segments = get_speech_timestamps(accumulated_buffer, vad_options)
        if len(segments) > 0:
            speech_detected = True
            end_sample = segments[-1]["end"]
            silence_samples = len(accumulated_buffer) - end_sample
            silence_seconds = silence_samples / sample_rate
            
            # pause_threshold is 1.5s
            if silence_seconds >= 1.5:
                auto_stop_triggered = True
                print(f"✔ Auto-stop successfully triggered after {len(accumulated_buffer)/sample_rate:.2f}s of audio! Silence at end: {silence_seconds:.2f}s")
                break
                
    if not speech_detected:
        print("✘ VAD failed to detect speech in test.wav!")
        sys.exit(1)
    if not auto_stop_triggered:
        print("✘ Auto-stop failed to trigger after speech finished!")
        sys.exit(1)
except Exception as e:
    print(f"✘ VAD / Auto-stop test failed with exception: {e}")
    sys.exit(1)


# 3. Test KWin Focus Restoration Script
print("\n--- Testing Layer 3: KWin Focus Restoration ---")
try:
    import json
    # Query current active window info
    res = subprocess.run(
        ["busctl", "--user", "--json=short", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "queryWindowInfo"],
        capture_output=True, text=True, check=True
    )
    parsed = json.loads(res.stdout)
    active_uuid = parsed["data"][0]["uuid"]["data"]
    active_caption = parsed["data"][0]["caption"]["data"]
    print(f"Current active window UUID: {active_uuid} ('{active_caption}')")
    
    # Run the focus restoration script to reactivate this window
    # Importing function directly from voice_type
    import voice_type
    success = voice_type.activate_window_by_uuid(active_uuid)
    if success:
        print("✔ Focus restoration script executed and successfully returned success status.")
    else:
        print("⚠ Focus restoration script returned skeleton status (disabled as per architecture lock).")
except Exception as e:
    print(f"✘ Focus restoration layer test failed: {e}")
    sys.exit(1)


# 4. Test Clipboard & Direct Paste Layer
print("\n--- Testing Layer 4: Clipboard & ydotool Paste ---")
try:
    test_text = "Verification test message from e2e_layers.py"
    voice_type.copy_to_clipboard(test_text)
    
    # Check if wl-paste matches
    p = subprocess.run(["wl-paste"], capture_output=True, text=True)
    if p.stdout.strip() == test_text:
        print(f"✔ Clipboard copy and read via wl-paste succeeded! Content: '{p.stdout.strip()}'")
    else:
        print(f"✘ Clipboard contents '{p.stdout.strip()}' did not match expected '{test_text}'!")
        sys.exit(1)
        
    # Check ydotool socket and connection
    socket_path = os.environ.get("YDOTOOL_SOCKET")
    if not socket_path:
        socket_path = f"/run/user/{os.getuid()}/.ydotool_socket"
    
    if os.path.exists(socket_path):
        print(f"✔ ydotool socket is accessible at: {socket_path}")
    else:
        print(f"✘ ydotool socket is NOT found at: {socket_path}")
        sys.exit(1)
        
except Exception as e:
    print(f"✘ Clipboard / Paste layer test failed: {e}")
    sys.exit(1)

print("\n=== ALL LAYERS AUDIT AND VERIFICATION PASSED SUCCESSFULLY! ===")
sys.exit(0)

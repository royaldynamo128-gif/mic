#!/usr/bin/env python3
# analyze_logs.py - Log parser to gather reliability and performance statistics for Voice Type

import os
import json
import sys
from datetime import datetime

LOG_FILE = os.path.expanduser("~/.local/share/voice_type/voice_type.log")

def parse_time(ts_str):
    # Format: "2026-06-25 06:22:40,041"
    try:
        if "," in ts_str:
            base, ms = ts_str.split(",")
            dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
            return dt.timestamp() + float(ms) / 1000.0
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return 0.0

def main():
    if not os.path.exists(LOG_FILE):
        print(f"ERROR: Log file not found at {LOG_FILE}", file=sys.stderr)
        sys.exit(1)

    starts = []
    stops = []
    sessions_started = 0
    sessions_completed = 0
    durations = []
    errors = {}
    warnings = {}
    total_lines = 0
    corrupt_lines = 0

    with open(LOG_FILE, "r") as f:
        for line in f:
            total_lines += 1
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                corrupt_lines += 1
                continue

            event = record.get("event")
            level = record.get("level")
            msg = record.get("message", "")
            ts = record.get("timestamp", "")

            # Track service lifecycle
            if event == "service_start":
                starts.append(parse_time(ts))
            elif event == "service_stop":
                stops.append(parse_time(ts))

            # Track dictation sessions
            elif event == "recording_started":
                sessions_started += 1
            elif event == "recording_stopped":
                sessions_completed += 1

            # Track transcription performance
            elif event == "transcription_duration":
                dur = record.get("duration_sec")
                if dur is not None:
                    durations.append(dur)
                else:
                    # Fallback string parsing
                    import re
                    match = re.search(r"completed in ([\d\.]+)s", msg)
                    if match:
                        durations.append(float(match.group(1)))

            # Track errors
            if level == "ERROR" or event == "error":
                # Normalize message for grouping
                norm_msg = msg
                if "timed out after" in msg:
                    norm_msg = "Whisper transcription timed out"
                elif "stalled during recording" in msg:
                    norm_msg = "Audio stream stalled during recording"
                errors[norm_msg] = errors.get(norm_msg, 0) + 1

            # Track warnings
            if level == "WARNING" or event == "warning":
                warnings[msg] = warnings.get(msg, 0) + 1

    # Uptime and restart calculations
    restarts = max(0, len(starts) - 1)
    
    # Calculate approximate uptime based on log spans
    uptime_str = "Unknown (insufficient cycle data)"
    if starts:
        first_start = starts[0]
        last_event_time = parse_time(record.get("timestamp", "")) if total_lines > corrupt_lines else first_start
        total_span = last_event_time - first_start
        
        days = int(total_span // 86400)
        hours = int((total_span % 86400) // 3600)
        minutes = int((total_span % 3600) // 60)
        seconds = int(total_span % 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

    print("==================================================")
    print("        VOICE TYPE SYSTEM METRICS SUMMARY         ")
    print("==================================================")
    print(f"Log File Analyzed: {LOG_FILE}")
    print(f"Total Log Records: {total_lines} (Corrupt/Unparsed: {corrupt_lines})")
    print(f"Total Logged Span: {uptime_str}")
    print(f"Service Starts:    {len(starts)}")
    print(f"Service Restarts:  {restarts}")
    print("--------------------------------------------------")
    print(f"Dictation Sessions Initiated: {sessions_started}")
    print(f"Dictation Sessions Captured:  {sessions_completed}")
    print("--------------------------------------------------")
    
    if durations:
        avg_dur = sum(durations) / len(durations)
        min_dur = min(durations)
        max_dur = max(durations)
        print(f"Transcription Latency Statistics (from {len(durations)} samples):")
        print(f"  Average Latency: {avg_dur:.3f} seconds")
        print(f"  Minimum Latency: {min_dur:.3f} seconds")
        print(f"  Maximum Latency: {max_dur:.3f} seconds")
    else:
        print("Transcription Latency: No successful latencies recorded in log.")
        
    print("--------------------------------------------------")
    print(f"Logged Errors Count: {sum(errors.values())}")
    for err, count in sorted(errors.items(), key=lambda x: x[1], reverse=True):
        print(f"  - [{count}x] {err}")
        
    print("--------------------------------------------------")
    print(f"Logged Warnings Count: {sum(warnings.values())}")
    for warn, count in sorted(warnings.items(), key=lambda x: x[1], reverse=True):
        print(f"  - [{count}x] {warn}")
    print("==================================================")

if __name__ == "__main__":
    main()

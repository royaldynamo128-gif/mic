#!/home/rai/venv/bin/python
import os
import sys
import time
import subprocess
import json
import psutil

PID_FILE = "/tmp/voice_type.pid"

def get_daemon_pid():
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None

def run_toggle():
    # Call the voice_type_toggle.sh script
    res = subprocess.run(["/home/rai/Scripts/voice_type_toggle.sh"], capture_output=True, text=True)
    return res.returncode == 0

def get_journal_errors():
    try:
        # Check systemd user journal for errors or warnings for the service since start of test
        res = subprocess.run(
            ["journalctl", "--user", "-u", "voice_type.service", "-n", "100", "--no-pager"],
            capture_output=True, text=True
        )
        lines = res.stdout.splitlines()
        errors = [line for line in lines if "error" in line.lower() or "fail" in line.lower() or "crash" in line.lower()]
        return errors
    except Exception as e:
        return [f"Failed to query journalctl: {e}"]

def main():
    print("=== VOICE TYPE HARDENING STRESS TEST ===")
    initial_pid = get_daemon_pid()
    if not initial_pid:
        print("ERROR: Voice Type Daemon is not running.")
        sys.exit(1)
        
    print(f"Daemon PID detected: {initial_pid}")
    try:
        process = psutil.Process(initial_pid)
    except psutil.NoSuchProcess:
        print(f"ERROR: No process with PID {initial_pid} exists.")
        sys.exit(1)
        
    # Warm up CPU usage calculation
    process.cpu_percent(interval=None)
    time.sleep(0.5)
    
    initial_rss = process.memory_info().rss
    print(f"Initial Daemon RSS: {initial_rss / (1024 * 1024):.2f} MB")
    
    cpu_measurements = []
    ram_measurements = []
    
    total_toggles = 100
    if len(sys.argv) > 1:
        try:
            total_toggles = int(sys.argv[1])
        except ValueError:
            pass
    success_toggles = 0
    
    print(f"Starting {total_toggles} toggle operations...")
    start_time = time.time()
    
    for i in range(1, total_toggles + 1):
        if i % 50 == 0 or i == 1:
            print(f"Progress: Toggle {i}/{total_toggles}...")
            
        success = run_toggle()
        if success:
            success_toggles += 1
            
        # Collect metrics
        try:
            current_pid = get_daemon_pid()
            if current_pid != initial_pid:
                print(f"\nCRITICAL ERROR: Daemon PID changed from {initial_pid} to {current_pid}! (Crash/Restart detected)")
                break
                
            cpu = process.cpu_percent(interval=None)
            rss = process.memory_info().rss
            cpu_measurements.append(cpu)
            ram_measurements.append(rss)
        except psutil.NoSuchProcess:
            print("\nCRITICAL ERROR: Daemon process died during stress test!")
            break
            
        # Wait 0.7s to prevent hitting client/daemon debounce limits (0.5s)
        time.sleep(0.7)
        
    end_time = time.time()
    elapsed = end_time - start_time
    
    print("\nStress Test Completed.")
    print(f"Elapsed Time: {elapsed:.2f} seconds")
    print(f"Successful Toggles: {success_toggles}/{total_toggles}")
    
    # Analyze stats
    final_pid = get_daemon_pid()
    crashed = (final_pid != initial_pid or final_pid is None)
    
    if not crashed:
        final_rss = process.memory_info().rss
        ram_delta = final_rss - initial_rss
        avg_cpu = sum(cpu_measurements) / len(cpu_measurements) if cpu_measurements else 0
        max_cpu = max(cpu_measurements) if cpu_measurements else 0
        avg_ram = sum(ram_measurements) / len(ram_measurements) if ram_measurements else 0
        max_ram = max(ram_measurements) if ram_measurements else 0
        
        print("\n=== PERFORMANCE STATISTICS ===")
        print(f"Avg CPU Usage: {avg_cpu:.2f}%")
        print(f"Max CPU Usage: {max_cpu:.2f}%")
        print(f"Initial RAM (RSS): {initial_rss / (1024 * 1024):.2f} MB")
        print(f"Final RAM (RSS): {final_rss / (1024 * 1024):.2f} MB")
        print(f"RAM Leak Delta: {ram_delta / (1024 * 1024):.2f} MB")
        print(f"Avg RAM: {avg_ram / (1024 * 1024):.2f} MB")
        print(f"Max RAM: {max_ram / (1024 * 1024):.2f} MB")
    else:
        avg_cpu = max_cpu = avg_ram = max_ram = ram_delta = final_rss = 0
        print("\n=== PERFORMANCE STATISTICS ===")
        print("Unavailable: Daemon crashed during test.")
        
    journal_errors = get_journal_errors()
    
    # Save report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "daemon_crashed": crashed,
        "elapsed_seconds": elapsed,
        "toggles_run": total_toggles,
        "toggles_successful": success_toggles,
        "initial_rss_mb": initial_rss / (1024 * 1024),
        "final_rss_mb": final_rss / (1024 * 1024),
        "ram_delta_mb": ram_delta / (1024 * 1024),
        "avg_cpu_percent": avg_cpu,
        "max_cpu_percent": max_cpu,
        "avg_ram_mb": avg_ram / (1024 * 1024),
        "max_ram_mb": max_ram / (1024 * 1024),
        "journal_errors": journal_errors
    }
    
    report_path = "/home/rai/.local/share/voice_type/stress_test_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=4)
    print(f"Stress test report written to: {report_path}")
    
    # Exit with code 1 if crashed
    if crashed or success_toggles < total_toggles:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()

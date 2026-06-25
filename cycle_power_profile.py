import subprocess

try:
    # Get current profile
    current = subprocess.check_output(["powerprofilesctl", "get"]).decode().strip()

    # Cycle logic: power-saver -> balanced -> performance -> power-saver
    if current == "power-saver":
        next_profile = "balanced"
    elif current == "balanced":
        next_profile = "performance"
    else:
        next_profile = "power-saver"

    # Set next profile
    subprocess.check_call(["powerprofilesctl", "set", next_profile])
    print(f"Switched from {current} to {next_profile}")
except Exception as e:
    print(f"Error cycling power profile: {e}")

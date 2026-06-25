#!/usr/bin/env python3
import os
import sys
import json
import time
import signal
import subprocess
from gi.repository import Gtk, GLib

# Try importing AppIndicator3.
try:
    from gi.repository import AppIndicator3
except ImportError:
    # Fallback to standard Gtk if AppIndicator3 is not available
    AppIndicator3 = None

HEALTH_FILE = "/tmp/voice_type.health"
PID_FILE = "/tmp/voice_type.pid"

class VoiceTypeTray:
    def __init__(self):
        self.last_state = None
        self.last_status = None
        
        # Determine the initial icon
        icon_name = "audio-input-microphone"
        
        if AppIndicator3:
            self.indicator = AppIndicator3.Indicator.new(
                "voice_type_indicator",
                icon_name,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        else:
            self.indicator = None
            print("AppIndicator3 is not available. Tray icon will not be displayed.", file=sys.stderr)
            sys.exit(1)

        # Create menu
        self.menu = Gtk.Menu()
        
        # Status item
        self.status_item = Gtk.MenuItem(label="Status: Initializing...")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Toggle item
        self.toggle_item = Gtk.MenuItem(label="Toggle Recording")
        self.toggle_item.connect("activate", self.on_toggle)
        self.menu.append(self.toggle_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Quit item
        self.quit_item = Gtk.MenuItem(label="Quit Voice Dictation")
        self.quit_item.connect("activate", self.on_quit)
        self.menu.append(self.quit_item)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        # Start state polling timer (every 150ms)
        GLib.timeout_add(150, self.poll_state)

    def on_toggle(self, widget):
        # Call the toggle script in the background
        try:
            subprocess.Popen(["/home/rai/Scripts/voice_type_toggle.sh"])
        except Exception as e:
            print(f"Failed to toggle: {e}", file=sys.stderr)

    def on_quit(self, widget):
        print("Quit requested from tray menu. Terminating daemon...", flush=True)
        # Find and terminate the main daemon process
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                print(f"Error terminating daemon: {e}", file=sys.stderr)
        Gtk.main_quit()

    def poll_state(self):
        if not os.path.exists(HEALTH_FILE):
            self.update_ui("OFFLINE", "OFFLINE")
            return True
            
        try:
            with open(HEALTH_FILE, "r") as f:
                data = json.load(f)
            
            # Extract status and state from health file
            status = data.get("status", "UNKNOWN")
            state = data.get("state", "IDLE")
            
            self.update_ui(status, state)
        except Exception as e:
            # Handle potential JSON read collision gracefully
            pass
            
        return True

    def update_ui(self, status, state):
        if state == self.last_state and status == self.last_status:
            return
            
        self.last_state = state
        self.last_status = status
        
        # Update Menu Label
        if status == "LOADING":
            self.status_item.set_label("Status: Loading Model...")
            icon_name = "process-working"
        elif status == "OFFLINE":
            self.status_item.set_label("Status: Offline")
            icon_name = "dialog-error"
        else:
            self.status_item.set_label(f"Status: {state}")
            if state == "RECORDING":
                icon_name = "media-record"
            elif state == "TRANSCRIBING":
                icon_name = "process-working"
            else:
                icon_name = "audio-input-microphone"
                
        # Update Tray Icon
        if self.indicator:
            self.indicator.set_icon_full(icon_name, f"Voice Type: {state}")

def main():
    # Graceful exit on SIGTERM/SIGINT
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
    
    # Initialize GTK application
    app = VoiceTypeTray()
    Gtk.main()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
mic_indicator.py  –  Extremely small pulsing red dot (top-right corner)
================================================================
* Fixed drawing size  –  avoids window manager minimum size scaling issues
* Top-right corner of the primary monitor
* Click-through  –  mouse events pass through to the window below
* Non-focusable  –  does not steal keyboard focus or interrupt typing
* High transparency, pulsing red recording dot
* Start to show, SIGTERM/kill to hide
"""

import os
# Force X11 backend so that window position (move) and focus settings are respected
# by the window manager under Wayland/Xwayland.
os.environ["GDK_BACKEND"] = "x11"

import sys
import math
import signal
import subprocess
import json

HEALTH_FILE = "/tmp/voice_type.health"



def _load_session_env():
    try:
        res = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True, text=True
        )
        for line in res.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
    except Exception:
        pass


_load_session_env()

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_foreign("cairo")   # MUST be before `import cairo`
import cairo
from gi.repository import Gtk, Gdk, GLib

# ── tunables ──────────────────────────────────────────────────────────────────
# Request a reasonable default window size (e.g. 100x100), but we will make it
# completely transparent and draw a fixed-size dot in its top-right corner.
# This bypasses the window manager's minimum window size limits.
WINDOW_SIZE  = 100

DOT_RADIUS   = 7.35  # Fixed dot radius (reverted to previous size)
OFFSET_X     = 12   # px from right edge of the window
OFFSET_Y     = 12   # px from top edge of the window

ORANGE = (0.95, 0.5, 0.1)



class MicOSD(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        # ── window properties ─────────────────────────────────────────────────
        self.set_title("mic-osd")
        self.set_wmclass("mic-osd", "mic-osd")
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.set_resizable(False)
        # Prevent stealing keyboard focus or interrupting the user
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        
        # NOTIFICATION hint: guarantees it never steals focus or grabs input
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_default_size(WINDOW_SIZE, WINDOW_SIZE)

        # ── RGBA transparency ─────────────────────────────────────────────────
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        # ── drawing area ──────────────────────────────────────────────────────
        da = Gtk.DrawingArea()
        da.connect("draw", self._on_draw)
        self.add(da)

        # ── pulse animation ───────────────────────────────────────────────────
        self._pulse = 0.0
        self._pdir  = 1
        self.state  = "RECORDING"
        self.spin_angle = 0.0
        GLib.timeout_add(20, self._tick)   # ~50 fps
        GLib.timeout_add(100, self._check_state)

        # ── click-through + position after window is mapped ───────────────────
        self.connect("realize", self._on_realize)
        self.show_all()
        GLib.idle_add(self._reposition)

    # ── make all mouse events pass through the window ─────────────────────────
    def _on_realize(self, _widget):
        try:
            gdk_win = self.get_window()
            gdk_win.set_override_redirect(True)
            empty = cairo.Region()                   # zero-area input region
            gdk_win.input_shape_combine_region(empty, 0, 0)
            print("[mic_indicator] Set window to override-redirect successfully.")
        except Exception as e:
            print(f"[mic_indicator] realize setup failed: {e}", file=sys.stderr)

    # ── snap to top-right corner of primary monitor ───────────────────────────
    def _reposition(self):
        try:
            display  = Gdk.Display.get_default()
            mon      = display.get_primary_monitor() or display.get_monitor(0)
            geo      = mon.get_geometry()
            # Align the top-right corner of our window to the top-right corner of the monitor
            x = geo.x + geo.width  - WINDOW_SIZE
            y = geo.y
            self.move(x, y)
        except Exception as e:
            print(f"[mic_indicator] reposition failed: {e}", file=sys.stderr)
        return False   # don't repeat

    # ── animation tick ────────────────────────────────────────────────────────
    def _check_state(self):
        try:
            if os.path.exists(HEALTH_FILE):
                with open(HEALTH_FILE, "r") as f:
                    data = json.load(f)
                self.state = data.get("state", "RECORDING")
        except Exception:
            pass
        return True

    # ── animation tick ────────────────────────────────────────────────────────
    def _tick(self):
        self._pulse += 0.04 * self._pdir
        if   self._pulse >= 1.0: self._pulse, self._pdir =  1.0, -1
        elif self._pulse <= 0.0: self._pulse, self._pdir =  0.0,  1
        
        self.spin_angle = getattr(self, "spin_angle", 0.0) + 0.10
        if self.spin_angle >= 2 * math.pi:
            self.spin_angle -= 2 * math.pi
            
        self.queue_draw()
        return True   # keep alive

    # ── draw frame ────────────────────────────────────────────────────────────
    def _on_draw(self, widget, cr):
        w  = widget.get_allocated_width()
        
        # Clear the entire window to be completely transparent
        cr.set_operator(cairo.Operator.SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.Operator.OVER)

        # Calculate coordinates in the top-right of the window
        cx = w - OFFSET_X - DOT_RADIUS
        cy = OFFSET_Y + DOT_RADIUS

        if getattr(self, "state", "RECORDING") == "TRANSCRIBING":
            # 1. Outer spinning cyan arc (processing animation)
            cr.set_line_width(2.5)
            cr.set_source_rgba(0.12, 0.73, 0.95, 0.9)  # Beautiful Cyan
            cr.arc(cx, cy, DOT_RADIUS + 3.0, self.spin_angle, self.spin_angle + math.pi * 0.75)
            cr.stroke()

            # 2. Central pulsing cyan dot
            cr.arc(cx, cy, DOT_RADIUS * 0.7, 0, 2 * math.pi)
            cr.set_source_rgba(0.12, 0.73, 0.95, 0.5 + 0.3 * self._pulse)
            cr.fill()
        else:
            # 1. Outer pulsing halo (decreased transparency)
            halo_r = DOT_RADIUS * (1.0 + 1.2 * self._pulse)
            cr.arc(cx, cy, halo_r, 0, 2 * math.pi)
            cr.set_source_rgba(*ORANGE, 0.25 * self._pulse)
            cr.fill()

            # 2. Central solid orange dot (decreased transparency / clear to see)
            cr.arc(cx, cy, DOT_RADIUS, 0, 2 * math.pi)
            cr.set_source_rgba(*ORANGE, 0.85)
            cr.fill()


def main():
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGINT,  lambda *_: Gtk.main_quit())

    win = MicOSD()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()

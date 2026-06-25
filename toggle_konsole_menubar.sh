#!/usr/bin/env bash
# Script to toggle Konsole menu bar via D-Bus for the active window.

# Find all running Konsole D-Bus session services
services=$(busctl --user list 2>/dev/null | awk '{print $1}' | grep '^org.kde.konsole-' || true)

if [ -z "$services" ]; then
    # No running Konsole instances found
    exit 0
fi

# Iterate over all services and find the active window
for service in $services; do
    windows=$(busctl --user tree "$service" 2>/dev/null | grep -oE '/konsole/MainWindow_[0-9]+' | sort -u || true)
    
    for window in $windows; do
        is_active=$(busctl --user get-property "$service" "$window" org.qtproject.Qt.QWidget isActiveWindow 2>/dev/null || true)
        
        if [ "$is_active" = "b true" ]; then
            # Found the active focused Konsole window.
            # Call trigger on the options_show_menubar action.
            action_path="${window}/actions/options_show_menubar"
            busctl --user call "$service" "$action_path" org.qtproject.Qt.QAction trigger >/dev/null 2>&1
            exit 0
        fi
    done
done

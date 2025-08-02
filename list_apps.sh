#!/bin/bash

# ==============================================================================
# Android App and Path Lister Script
# ------------------------------------------------------------------------------
# This script lists all installed application packages on a connected Android
# device or emulator and provides the full path to their base APK file.
#
# Prerequisites:
#   - adb must be installed and in your system's PATH.
#   - An Android device or emulator must be connected and authorized for debugging.
# ==============================================================================

# --- Check for prerequisites ---

# Check if adb is available
if ! command -v adb &> /dev/null; then
    echo "Error: adb command not found. Please ensure the Android SDK is installed and adb is in your system's PATH."
    exit 1
fi

echo "Listing all installed app packages and their APK paths..."
echo "------------------------------------------------------------------------"

# The core command is `adb shell pm list packages -f`.
# The `-f` flag is crucial as it includes the path to the APK file.
# Example output format: "package:/data/app/com.example.app-1/base.apk=com.example.app"

# Use `adb shell pm list packages -f` to get the list of apps with their paths.
# We then process the output to make it more readable.
# The `sed` command is used here to reformat the output string.
# 's/package://g' removes the "package:" prefix.
# 's/base.apk=/ : /g' formats the output to be "path : package_name".
adb shell pm list packages -f | sed 's/package://g; s/base.apk=/ : /g'

echo "------------------------------------------------------------------------"
echo "Process complete."
echo "If you have a large number of apps, you can filter the output using 'grep'."
echo "Example: ./list_apps.sh | grep 'my.app.package'"
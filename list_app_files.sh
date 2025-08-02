#!/bin/bash

# ==============================================================================
# Android App Package and File Lister Script
# ------------------------------------------------------------------------------
# This script lists the path to the base APK and all associated split APK files
# for a specified app's package on a connected Android device or emulator.
#
# Usage:
#   ./list_app_files.sh <package_name>
#
# Arguments:
#   <package_name>      The package name of the Android app (e.g., com.google.android.apps.maps).
#
# Prerequisites:
#   - adb must be installed and in your system's PATH.
#   - An Android device or emulator must be connected and authorized for debugging.
# ==============================================================================

# --- Function to display usage information ---
show_usage() {
    echo "Usage: $0 <package_name>"
    echo
    echo "This script lists the paths to all APK files (base and split) for an app."
    exit 1
}

# --- Check for prerequisites and arguments ---

# Check if adb is available
if ! command -v adb &> /dev/null; then
    echo "Error: adb command not found. Please ensure the Android SDK is installed and adb is in your system's PATH."
    exit 1
fi

# Check if exactly one argument is provided
if [ "$#" -ne 1 ]; then
    echo "Error: Invalid number of arguments."
    show_usage
fi

PACKAGE_NAME="$1"

# --- Main script logic ---

echo "--- APK files for Package: $PACKAGE_NAME ---"

# The `adb shell pm path` command is the key. It is specifically designed to
# return the full paths to all APK files associated with a given package,
# including the base APK and any split configuration files.
# The output is prefixed with "package:", which we remove for clarity.
APK_PATHS=$(adb shell pm path "$PACKAGE_NAME" | sed 's/package://g')

# Check if any paths were found.
if [ -z "$APK_PATHS" ]; then
    echo "Error: Could not find any APK paths for package '$PACKAGE_NAME'."
    echo "Please ensure the app is installed on the connected device."
    exit 1
fi

echo
echo "APK Paths Found:"
echo "----------------"
# Print the raw output, which already lists all the APK files.
echo "$APK_PATHS"

echo
echo "--- Process complete ---"
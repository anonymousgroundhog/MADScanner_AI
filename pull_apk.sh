#!/bin/bash

# ==============================================================================
# Android APK and Split-APK Puller Script
# ------------------------------------------------------------------------------
# This script automates the process of pulling an application's APK and its
# associated split configuration files from a connected Android device or emulator
# using the Android Debug Bridge (adb).
#
# Usage:
#   ./pull_apk.sh <package_name> <destination_directory>
#
# Arguments:
#   <package_name>        The package name of the Android app (e.g., com.google.android.apps.maps).
#   <destination_directory> The local directory where the files will be saved.
#
# Prerequisites:
#   - adb must be installed and in your system's PATH.
#   - An Android device or emulator must be connected and authorized for debugging.
# ==============================================================================

# --- Function to display usage information ---
show_usage() {
    echo "Usage: $0 <package_name> <destination_directory>"
    echo
    echo "This script pulls the specified app's APK and any associated split APKs."
    echo "It requires the app's package name and a local directory to save the files."
    exit 1
}

# --- Check for prerequisites and arguments ---

# Check if adb is available
if ! command -v adb &> /dev/null; then
    echo "Error: adb command not found. Please ensure the Android SDK is installed and adb is in your system's PATH."
    exit 1
fi

# Check if exactly two arguments are provided
if [ "$#" -ne 2 ]; then
    echo "Error: Invalid number of arguments."
    show_usage
fi

PACKAGE_NAME="$1"
DEST_DIR="$2"

# --- Main script logic ---

echo "Searching for APK path(s) for package: $PACKAGE_NAME"

# Find the path(s) to the APK file(s) for the given package
# The `adb shell pm path` command returns one or more paths, separated by newlines
# e.g.,
# package:/data/app/com.example.app-1.apk
# package:/data/app/com.example.app-1.apk/split_config.xhdpi.apk
# We filter out the 'package:' prefix.
APK_PATHS=$(adb shell pm path "$PACKAGE_NAME" | sed 's/package://g')

# Check if any paths were found
if [ -z "$APK_PATHS" ]; then
    echo "Error: Could not find any APK paths for package '$PACKAGE_NAME'."
    echo "Please ensure the app is installed on the connected device."
    exit 1
fi

# Create the destination directory if it doesn't exist
if [ ! -d "$DEST_DIR" ]; then
    echo "Creating destination directory: $DEST_DIR"
    mkdir -p "$DEST_DIR"
fi

echo "Found APK path(s):"
echo "$APK_PATHS" | while read -r apk_path; do
    # Use basename to get the filename from the path
    apk_filename=$(basename "$apk_path")
    
    echo "Pulling $apk_filename..."
    # The adb pull command pulls the remote file to the local destination directory
    adb pull "$apk_path" "$DEST_DIR/$apk_filename"

    if [ "$?" -eq 0 ]; then
        echo "Successfully pulled $apk_filename to $DEST_DIR"
    else
        echo "Error: Failed to pull $apk_filename."
    fi
done

echo
echo "Process complete. All found APKs have been pulled to $DEST_DIR"
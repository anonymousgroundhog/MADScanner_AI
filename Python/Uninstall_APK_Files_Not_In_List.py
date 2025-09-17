import subprocess
import os
import sys

def run_adb_command(command):
    """
    Executes an ADB command and returns its standard output.

    Args:
        command (str): The full ADB command string to execute.

    Returns:
        str: The stripped standard output or standard error of the command.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True, # Will raise an error for non-zero exit codes
            shell=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Return the error message from ADB, e.g., if a package is not found
        return e.stderr.strip()
    except FileNotFoundError:
        print("❌ Error: 'adb' command not found. Ensure Android SDK Platform-Tools "
              "is installed and its directory is in your system's PATH.", file=sys.stderr)
        sys.exit(1) # Exit the script if ADB is not found


def main():
    """
    Main function to uninstall packages based on folder names.
    """
    print("--- Starting Uninstaller Script ---")

    # Determine paths based on the script's location
    # Assumes script is in '.../MADScanner_AI/Python/'
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Moves up to 'MADScanner_AI'
    apk_source_dir = os.path.join(project_root, "APK_Files_To_Analyze")

    print(f"🔍 Searching for packages in: {apk_source_dir}")

    if not os.path.isdir(apk_source_dir):
        print(f"❌ Error: Directory not found: {apk_source_dir}", file=sys.stderr)
        print("Please ensure the script is located in the 'Python' folder and 'APK_Files_To_Analyze' exists.", file=sys.stderr)
        return

    # Get a list of all directory names inside APK_Files_To_Analyze
    try:
        package_names = [name for name in os.listdir(apk_source_dir)
                         if os.path.isdir(os.path.join(apk_source_dir, name))]
    except Exception as e:
        print(f"❌ Error reading directories from {apk_source_dir}: {e}", file=sys.stderr)
        return

    if not package_names:
        print("✅ No package folders found in 'APK_Files_To_Analyze' to uninstall.")
        return

    print(f"Found {len(package_names)} package(s) to uninstall based on folder names.")
    
    # Verify ADB connection
    print("\nVerifying ADB connection...")
    devices_output = run_adb_command("adb devices")
    if "device" not in devices_output:
        print("⚠️ No Android emulator or device found. Please ensure one is running and connected via ADB.", file=sys.stderr)
        return
    print("✅ Android emulator/device detected.")
    
    # Loop through the package names and uninstall them
    uninstalled_count = 0
    print("\n--- Starting Uninstallation Process ---")
    for package in sorted(package_names):
        print(f"🗑️ Attempting to uninstall '{package}'...")
        output = run_adb_command(f"adb uninstall {package}")

        if "Success" in output:
            print(f"   ✅ Success")
            uninstalled_count += 1
        else:
            # ADB provides informative errors, e.g., if the package is not installed
            print(f"   ℹ️  Info: {output}")

    print("\n--- Script Finished ---")
    print(f"Successfully uninstalled {uninstalled_count} out of {len(package_names)} packages.")


if __name__ == "__main__":
    main()
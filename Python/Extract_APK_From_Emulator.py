import subprocess
import os
import re
import sys

def run_adb_command(command, check_output=True):
    """
    Executes an ADB command and returns its standard output.

    Args:
        command (str): The full ADB command string to execute.
        check_output (bool): If True, raises a CalledProcessError if the command
                             returns a non-zero exit code.

    Returns:
        str: The stripped standard output of the command.

    Raises:
        subprocess.CalledProcessError: If check_output is True and the command fails.
        FileNotFoundError: If 'adb' command is not found in system's PATH.
    """
    try:
        # Use shell=True for simpler command strings, let the shell handle parsing
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=check_output,
            shell=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing ADB command: '{command}'", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print("Error: 'adb' command not found. Ensure Android SDK Platform-Tools "
              "is installed and its directory is in your system's PATH.", file=sys.stderr)
        raise

def list_packages():
    """
    Lists all installed packages on the connected Android emulator/device.

    Returns:
        list[str]: A list of package names (e.g., 'com.android.settings').
                   Returns an empty list if no packages are found or an error occurs.
    """
    print("🚀 Listing all packages on the emulator...")
    try:
        # Run 'adb shell pm list packages' to get all installed package names
        output = run_adb_command("adb shell pm list packages")
        # Filter lines that start with 'package:' and remove the prefix
        packages = [line.replace("package:", "") for line in output.splitlines() if line.startswith("package:")]
        print(f"✅ Found {len(packages)} packages.")
        return packages
    except Exception as e:
        print(f"❌ Could not list packages: {e}", file=sys.stderr)
        return []

def get_apk_paths(package_name): # Renamed to plural 'paths'
    """
    Retrieves all full file paths of the APKs for a given package name on the emulator.
    This handles cases of split APKs where multiple paths might exist.

    Args:
        package_name (str): The full package name of the app (e.g., 'com.example.myapp').

    Returns:
        list[str]: A list of absolute paths to the APK files on the emulator's filesystem.
                   Returns an empty list if no paths can be found.
    """
    print(f"🔍 Getting APK paths for '{package_name}'...")
    try:
        # Run 'adb shell pm path <package_name>' to get all APK file locations
        output = run_adb_command(f"adb shell pm path {package_name}")
        # The output can be multiple lines, each like "package:/data/app/path/to/apk.apk"
        # We use re.findall to extract all path parts
        apk_paths = re.findall(r"package:(/.*\.apk)", output)
        if apk_paths:
            print(f"✨ Found {len(apk_paths)} APK path(s) for '{package_name}':")
            for path in apk_paths:
                print(f"   - {path}")
            return apk_paths
        else:
            print(f"⚠️ Could not find any APK paths for '{package_name}'. Output: {output.strip()}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"❌ Error getting APK paths for '{package_name}': {e}", file=sys.stderr)
        return []

def pull_apk(remote_path, local_destination_dir):
    """
    Pulls a single APK file from the emulator to a specified local directory.

    Args:
        remote_path (str): The absolute path to the APK file on the emulator.
        local_destination_dir (str): The local directory on your computer where
                                     the APK should be saved.

    Returns:
        bool: True if the APK was successfully pulled, False otherwise.
    """
    # Extract the filename from the remote path
    apk_filename = os.path.basename(remote_path)
    # Construct the full local filepath
    local_filepath = os.path.join(local_destination_dir, apk_filename)

    print(f"📥 Pulling '{apk_filename}' from emulator to '{local_filepath}'...")
    try:
        # Create the destination directory if it doesn't already exist
        os.makedirs(local_destination_dir, exist_ok=True)
        # Execute the 'adb pull' command.
        # Quoting local_filepath is crucial in case it contains spaces.
        run_adb_command(f'adb pull "{remote_path}" "{local_filepath}"')
        print(f"✅ Successfully pulled '{apk_filename}'")
        return True
    except Exception as e:
        print(f"❌ Error pulling '{apk_filename}': {e}", file=sys.stderr)
        return False

def main():
    """
    Main function to orchestrate the APK pulling process.
    """
    # Define the base directory where all APKs will be saved
    # This now places "APK_Files_To_Analyze" one directory up from the script's location
    output_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "APK_Files_To_Analyze")
    
    print("--- Starting APK Puller Script ---")

    # 1. Verify ADB connection and active emulator/device
    try:
        devices_output = run_adb_command("adb devices")
        if "device" not in devices_output:
            print("⚠️ No Android emulator or device found. Please ensure one is running and connected via ADB.", file=sys.stderr)
            return
        print("✅ Android emulator/device detected.")
    except Exception:
        print("❌ Failed to connect to ADB or no devices found. Please check your ADB setup.", file=sys.stderr)
        return

    # 2. Get fuzzy match string from the user
    fuzzy_match_string = input(
        "\nEnter a partial app or package name for fuzzy matching "
        "(e.g., 'chrome', 'settings', 'calculator'): "
    ).strip().lower()

    if not fuzzy_match_string:
        print("No fuzzy match string provided. Exiting.", file=sys.stderr)
        return

    # 3. List all packages on the emulator
    all_packages = list_packages()
    if not all_packages:
        print("No packages found on the emulator to process. Exiting.", file=sys.stderr)
        return

    # 4. Filter packages based on the fuzzy match string
    # A package is matched if the fuzzy_match_string is a substring of its lowercased name
    matched_packages = [pkg for pkg in all_packages if fuzzy_match_string in pkg.lower()]

    if not matched_packages:
        print(f"\n😔 No packages found matching '{fuzzy_match_string}'.", file=sys.stderr)
        return

    print(f"\n🎉 Found {len(matched_packages)} package(s) matching '{fuzzy_match_string}':")
    for pkg in matched_packages:
        print(f"- {pkg}")
    print("-" * 40) # Separator for readability

    # 5. Iterate through matched packages, get their APK paths, and pull them
    successful_pulls = 0
    total_apks_to_pull = 0 # Track total number of APKs identified
    for pkg_name in matched_packages:
        # Call the updated function to get all APK paths for the package
        apk_remote_paths = get_apk_paths(pkg_name) 
        total_apks_to_pull += len(apk_remote_paths)

        if apk_remote_paths:
            # Define the local directory for this specific package
            # e.g., ../APK_Files_To_Analyze/com.example.myapp/
            local_package_dir = os.path.join(output_base_dir, pkg_name)
            
            # Iterate through each APK path found for the current package
            for apk_path in apk_remote_paths:
                if pull_apk(apk_path, local_package_dir):
                    successful_pulls += 1
        print("-" * 40) # Separator for each package's process

    print(f"\n--- Script Finished ---")
    print(f"Summary: Successfully pulled {successful_pulls} out of {total_apks_to_pull} identified APK files.")
    if successful_pulls > 0:
        print(f"APKs are saved in the '{output_base_dir}' directory.")

if __name__ == "__main__":
    main()

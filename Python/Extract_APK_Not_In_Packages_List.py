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
        print(f"DEBUG: Executing ADB command: '{command}'")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=check_output,
            shell=True
        )
        print(f"DEBUG: ADB command output (stdout):\n{result.stdout.strip()}")
        if result.stderr.strip():
            print(f"DEBUG: ADB command output (stderr):\n{result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error executing ADB command: '{command}'", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print("❌ Error: 'adb' command not found. Ensure Android SDK Platform-Tools "
              "is installed and its directory is in your system's PATH.", file=sys.stderr)
        raise

def list_packages():
    """
    Lists all installed packages on the connected Android emulator/device.

    Returns:
        list[str]: A list of package names (e.g., 'com.android.settings').
                   Returns an empty list if no packages are found or an error occurs.
    """
    print("\n🚀 Listing all packages on the emulator...")
    try:
        output = run_adb_command("adb shell pm list packages")
        packages = [line.replace("package:", "").strip() for line in output.splitlines() if line.startswith("package:")]
        print(f"✅ Found {len(packages)} packages on emulator.")
        print(f"DEBUG: Packages found on emulator: {packages}")
        return packages
    except Exception as e:
        print(f"❌ Could not list packages: {e}", file=sys.stderr)
        return []

def get_apk_paths(package_name):
    """
    Retrieves all full file paths of the APKs for a given package name on the emulator.
    This handles cases of split APKs where multiple paths might exist.

    Args:
        package_name (str): The full package name of the app (e.g., 'com.example.myapp').

    Returns:
        list[str]: A list of absolute paths to the APK files on the emulator's filesystem.
                   Returns an empty list if no paths can be found.
    """
    print(f"\n🔍 Getting APK paths for '{package_name}'...")
    try:
        output = run_adb_command(f"adb shell pm path {package_name}")
        apk_paths = re.findall(r"package:(/.*\.apk)", output)
        if apk_paths:
            print(f"✨ Found {len(apk_paths)} APK path(s) for '{package_name}':")
            for path in apk_paths:
                print(f"   - {path}")
            print(f"DEBUG: APK paths for '{package_name}': {apk_paths}")
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
    apk_filename = os.path.basename(remote_path)
    local_filepath = os.path.join(local_destination_dir, apk_filename)

    print(f"\n📥 Pulling '{apk_filename}' from emulator to '{local_filepath}'...")
    try:
        os.makedirs(local_destination_dir, exist_ok=True)
        print(f"DEBUG: Local destination directory created/exists: '{local_destination_dir}'")
        run_adb_command(f'adb pull "{remote_path}" "{local_filepath}"')
        print(f"✅ Successfully pulled '{apk_filename}'")
        return True
    except Exception as e:
        print(f"❌ Error pulling '{apk_filename}': {e}", file=sys.stderr)
        return False

def load_known_packages(file_path):
    """
    Loads a set of package names from a text file. Each line is a package name.

    Args:
        file_path (str): The full path to the packages.txt file.

    Returns:
        set[str]: A set of package names found in the file. Returns an empty set if the file
                  does not exist or an error occurs.
    """
    known_packages = set()
    print(f"\nReading known packages from: {os.path.abspath(file_path)}")
    print(f"DEBUG: Does packages.txt file exist? {os.path.exists(file_path)}")

    if not os.path.exists(file_path):
        print(f"⚠️ Known packages file not found at: {os.path.abspath(file_path)}. Proceeding without a baseline.", file=sys.stderr)
        return known_packages
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                pkg = line.strip()
                if pkg:
                    known_packages.add(pkg)
        print(f"Loaded {len(known_packages)} known packages from '{os.path.basename(file_path)}'.")
        print(f"DEBUG: Known packages loaded: {known_packages}")
    except Exception as e:
        print(f"❌ Error reading known packages file '{os.path.abspath(file_path)}': {e}", file=sys.stderr)
    return known_packages

def write_packages_to_file(file_path, packages):
    """
    Writes a list of package names to a text file, one per line.

    Args:
        file_path (str): The full path to the packages.txt file.
        packages (list[str]): A list of package names to write.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        print(f"DEBUG: Directory for packages.txt created/exists: {os.path.dirname(file_path)}")
        with open(file_path, 'w', encoding='utf-8') as f:
            for pkg in sorted(packages):
                f.write(pkg + '\n')
        print(f"Updated known packages file: {os.path.abspath(file_path)}")
    except Exception as e:
        print(f"❌ Error writing packages to file '{os.path.abspath(file_path)}': {e}", file=sys.stderr)


def main():
    """
    Main function to orchestrate the APK pulling process for untracked APKs.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.join(script_dir, "..") 
    print(f"DEBUG: Script directory: {script_dir}")
    print(f"DEBUG: Project root directory (calculated): {project_root_dir}")

    output_base_dir = os.path.join(project_root_dir, "APK_Files_To_Analyze")
    packages_file_dir = os.path.join(project_root_dir, "Current_Emulator_Packages")
    packages_file_path = os.path.join(packages_file_dir, "packages.txt")
    print(f"DEBUG: Output base directory: {output_base_dir}")
    print(f"DEBUG: Packages file path: {packages_file_path}")

    print("\n--- Starting Untracked APK Puller Script ---")

    # 1. Verify ADB connection and active emulator/device
    try:
        print("Verifying ADB connection...")
        devices_output = run_adb_command("adb devices")
        if "device" not in devices_output:
            print("⚠️ No Android emulator or device found. Please ensure one is running and connected via ADB.", file=sys.stderr)
            return
        print("✅ Android emulator/device detected.")
    except Exception as e:
        print(f"❌ Failed to connect to ADB or no devices found: {e}. Please check your ADB setup.", file=sys.stderr)
        return

    # 2. Load known packages from packages.txt
    known_packages_set = load_known_packages(packages_file_path)
    
    # 3. List all currently installed packages on the emulator
    all_current_packages = list_packages()
    if not all_current_packages:
        print("No packages found on the emulator to process. Exiting.", file=sys.stderr)
        return

    # 4. Identify untracked packages: those in all_current_packages but not in known_packages_set
    print(f"\nDEBUG: --- Package Comparison Details ---")
    print(f"DEBUG: Packages currently on emulator ({len(all_current_packages)}):")
    for pkg in all_current_packages:
        print(f"DEBUG:   Emulator: '{pkg}' (length: {len(pkg)})")
    
    print(f"DEBUG: Known packages from '{os.path.basename(packages_file_path)}' ({len(known_packages_set)}):")
    for pkg in sorted(list(known_packages_set)): # Sort for consistent debug output
        print(f"DEBUG:   Known:    '{pkg}' (length: {len(pkg)})")

    untracked_packages = [pkg for pkg in all_current_packages if pkg not in known_packages_set]
    print(f"DEBUG: Untracked packages identified: {untracked_packages}")
    print(f"DEBUG: --- End Comparison Details ---")


    if not untracked_packages:
        print(f"\n🎉 No new untracked packages found on the emulator. All {len(all_current_packages)} packages are already in {os.path.basename(packages_file_path)}.")
        write_packages_to_file(packages_file_path, all_current_packages)
        return

    print(f"\n🎉 Found {len(untracked_packages)} untracked package(s) on the emulator:")
    for pkg in untracked_packages:
        print(f"- {pkg}")
    print("-" * 40)

    # 5. Iterate through untracked packages, get their APK paths, and pull them
    successful_pulls = 0
    total_apks_to_pull = 0
    pulled_package_names = set()

    for pkg_name in untracked_packages:
        apk_remote_paths = get_apk_paths(pkg_name) 
        total_apks_to_pull += len(apk_remote_paths)

        if apk_remote_paths:
            local_package_dir = os.path.join(output_base_dir, pkg_name)
            
            current_pkg_pull_success = False
            for apk_path in apk_remote_paths:
                if pull_apk(apk_path, local_package_dir):
                    successful_pulls += 1
                    current_pkg_pull_success = True
            
            if current_pkg_pull_success:
                pulled_package_names.add(pkg_name)
        print("-" * 40)

    print(f"\n--- Script Finished ---")
    print(f"Summary: Successfully pulled {successful_pulls} out of {total_apks_to_pull} identified APK files.")
    if successful_pulls > 0:
        print(f"APKs are saved in the '{output_base_dir}' directory.")
    
    # 6. Update packages.txt with all currently installed packages (including the newly pulled ones)
    print(f"\nUpdating {os.path.basename(packages_file_path)} to reflect current emulator packages...")
    write_packages_to_file(packages_file_path, all_current_packages)


if __name__ == "__main__":
    main()

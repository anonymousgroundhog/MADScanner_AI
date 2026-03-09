import subprocess
import os
import sys
import re


def run_adb_command(args):
    """
    Executes an ADB command and returns its standard output.

    Args:
        args (list[str]): ADB arguments (excluding 'adb' itself).

    Returns:
        str: The stripped standard output, or None on error.
    """
    try:
        result = subprocess.run(
            ["adb"] + args,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except FileNotFoundError:
        print("Error: 'adb' command not found. Ensure Android SDK Platform-Tools "
              "is installed and its directory is in your system's PATH.", file=sys.stderr)
        sys.exit(1)


def get_package_name(apk_path):
    """
    Extracts the package name from an APK file using aapt.

    Args:
        apk_path (str): Full path to the APK file.

    Returns:
        str | None: The package name, or None if it could not be determined.
    """
    try:
        result = subprocess.run(
            ["aapt", "dump", "badging", apk_path],
            capture_output=True,
            text=True
        )
        match = re.search(r"package: name='([^']+)'", result.stdout)
        if match:
            return match.group(1)
        print(f"  Warning: Could not find package name in aapt output for: {apk_path}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Error: 'aapt' command not found. Ensure Android SDK Build-Tools "
              "is installed and its directory is in your system's PATH.", file=sys.stderr)
        sys.exit(1)


def find_apk_files(base_dir):
    """
    Recursively finds all .apk files under base_dir.

    Args:
        base_dir (str): Root directory to search.

    Returns:
        list[str]: List of absolute paths to found APK files.
    """
    apk_files = []
    for root, _, files in os.walk(base_dir):
        for filename in files:
            if filename.lower().endswith(".apk"):
                apk_files.append(os.path.join(root, filename))
    return apk_files


def main():
    print("--- Starting APK Uninstaller ---")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    apk_source_dir = os.path.join(project_root, "APK_Files_To_Analyze")

    print(f"Searching for APK files in: {apk_source_dir}")

    if not os.path.isdir(apk_source_dir):
        print(f"Error: Directory not found: {apk_source_dir}", file=sys.stderr)
        print("Ensure the script is in the 'Python' folder and 'APK_Files_To_Analyze' exists.", file=sys.stderr)
        sys.exit(1)

    apk_files = find_apk_files(apk_source_dir)

    if not apk_files:
        print("No APK files found in 'APK_Files_To_Analyze'. Nothing to uninstall.")
        return

    print(f"Found {len(apk_files)} APK file(s).\n")

    # Verify ADB connection
    print("Verifying ADB connection...")
    devices_output = run_adb_command(["devices"])
    if "device" not in devices_output:
        print("No Android emulator or device found. Please ensure one is running and connected via ADB.", file=sys.stderr)
        sys.exit(1)
    print("Android emulator/device detected.\n")

    # Collect package names, skipping duplicates
    packages = {}
    print("Extracting package names from APK files...")
    for apk_path in sorted(apk_files):
        relative_path = os.path.relpath(apk_path, apk_source_dir)
        package_name = get_package_name(apk_path)
        if package_name:
            if package_name not in packages:
                packages[package_name] = relative_path
                print(f"  {relative_path} -> {package_name}")
            else:
                print(f"  {relative_path} -> {package_name} (duplicate, already queued)")
        else:
            print(f"  {relative_path} -> (skipped, could not extract package name)")

    if not packages:
        print("\nNo valid package names could be extracted. Nothing to uninstall.")
        return

    print(f"\n--- Starting Uninstallation of {len(packages)} package(s) ---")
    uninstalled_count = 0

    for package_name, source_path in sorted(packages.items()):
        print(f"Attempting to uninstall '{package_name}' (from {source_path})...")
        output = run_adb_command(["uninstall", package_name])

        if "Success" in output:
            print(f"  Success")
            uninstalled_count += 1
        else:
            print(f"  Info: {output if output else 'Package may not be installed'}")

    print(f"\n--- Script Finished ---")
    print(f"Successfully uninstalled {uninstalled_count} out of {len(packages)} package(s).")


if __name__ == "__main__":
    main()

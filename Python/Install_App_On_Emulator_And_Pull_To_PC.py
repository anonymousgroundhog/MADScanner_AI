import subprocess
import os
import re
import sys
import csv
import time
import argparse


def run_adb_command(command_parts, check_output=True):
    """
    Executes an ADB command (as a list of parts) and returns its standard output.

    Args:
        command_parts (list[str]): The command and its arguments as a list.
        check_output (bool): If True, raises CalledProcessError on non-zero exit.

    Returns:
        str: The stripped standard output of the command.
    """
    try:
        result = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            check=check_output,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing ADB command: '{' '.join(command_parts)}'", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(
            "Error: 'adb' command not found. Ensure Android SDK Platform-Tools "
            "is installed and its directory is in your system's PATH.",
            file=sys.stderr,
        )
        raise


def check_adb_connection():
    """
    Verifies that at least one Android device or emulator is connected via ADB.

    Returns:
        bool: True if a device is connected, False otherwise.
    """
    try:
        output = run_adb_command(["adb", "devices"])
        lines = [l for l in output.splitlines() if l and not l.startswith("List")]
        connected = [l for l in lines if "device" in l and "offline" not in l]
        if connected:
            print(f"  - Android device/emulator detected ({len(connected)} connected).")
            return True
        print("  - No Android emulator or device found.", file=sys.stderr)
        return False
    except Exception:
        return False


def read_package_names_from_csv(csv_path, column_name=None):
    """
    Reads package names from a CSV file.

    If column_name is provided, reads from that named column. Otherwise reads
    from the first column. Lines starting with '#' and blank values are skipped.

    Args:
        csv_path (str): Path to the CSV file.
        column_name (str | None): Header name of the column containing package names.

    Returns:
        list[str]: List of package name strings.
    """
    packages = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f) if column_name else csv.reader(f)

            if column_name:
                for row in reader:
                    value = row.get(column_name, "").strip()
                    if value and not value.startswith("#"):
                        packages.append(value)
            else:
                for i, row in enumerate(reader):
                    if not row:
                        continue
                    value = row[0].strip()
                    # Skip the header row if it looks like a header (no dots in package name)
                    if i == 0 and "." not in value:
                        print(f"  - Skipping header row: '{value}'")
                        continue
                    if value and not value.startswith("#"):
                        packages.append(value)

    except FileNotFoundError:
        print(f"Error: CSV file not found at '{csv_path}'.", file=sys.stderr)
    except Exception as e:
        print(f"Error reading CSV file: {e}", file=sys.stderr)

    return packages


def open_play_store_page(package_name):
    """
    Opens the Google Play Store page for a given package on the connected emulator.

    Args:
        package_name (str): The app's package name (e.g., 'com.example.myapp').
    """
    print(f"  - Opening Play Store page for '{package_name}'...")
    try:
        run_adb_command([
            "adb", "shell", "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", f"market://details?id={package_name}",
            "com.android.vending",
        ])
        print(f"  - Play Store opened for '{package_name}'.")
    except Exception as e:
        print(f"  - Failed to open Play Store for '{package_name}': {e}", file=sys.stderr)
        raise


def is_package_installed(package_name):
    """
    Checks whether a package is currently installed on the emulator.

    Args:
        package_name (str): The package name to check.

    Returns:
        bool: True if installed, False otherwise.
    """
    try:
        output = run_adb_command(
            ["adb", "shell", "pm", "list", "packages", package_name],
            check_output=False,
        )
        return f"package:{package_name}" in output
    except Exception:
        return False


def wait_for_installation(package_name, timeout=300, poll_interval=5):
    """
    Polls ADB until the package appears as installed or the timeout is reached.

    Args:
        package_name (str): The package name to wait for.
        timeout (int): Maximum seconds to wait.
        poll_interval (int): Seconds between each poll.

    Returns:
        bool: True if the app was installed within the timeout, False otherwise.
    """
    print(f"  - Waiting for '{package_name}' to be installed (timeout: {timeout}s)...")
    elapsed = 0
    while elapsed < timeout:
        if is_package_installed(package_name):
            print(f"  - '{package_name}' is now installed.")
            return True
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"    ({elapsed}s elapsed — still waiting...)")
    print(f"  - Timed out waiting for '{package_name}' to be installed.", file=sys.stderr)
    return False


def get_apk_paths(package_name):
    """
    Retrieves all APK file paths for a package on the emulator.
    Handles split APKs (base + split_config APKs).

    Args:
        package_name (str): The package name.

    Returns:
        list[str]: List of absolute paths to the APK files on the emulator.
    """
    print(f"  - Getting APK paths for '{package_name}'...")
    try:
        output = run_adb_command(["adb", "shell", "pm", "path", package_name])
        apk_paths = re.findall(r"package:(/.*\.apk)", output)
        if apk_paths:
            print(f"  - Found {len(apk_paths)} APK path(s):")
            for path in apk_paths:
                print(f"      {path}")
        else:
            print(f"  - No APK paths found for '{package_name}'.", file=sys.stderr)
        return apk_paths
    except Exception as e:
        print(f"  - Error getting APK paths for '{package_name}': {e}", file=sys.stderr)
        return []


def pull_apk(remote_path, local_dest_dir):
    """
    Pulls a single APK from the emulator to a local directory.

    Args:
        remote_path (str): Absolute path to the APK on the emulator.
        local_dest_dir (str): Local directory to save the file.

    Returns:
        bool: True on success, False on failure.
    """
    apk_filename = os.path.basename(remote_path)
    local_filepath = os.path.join(local_dest_dir, apk_filename)
    print(f"  - Pulling '{apk_filename}' -> '{local_filepath}'...")
    try:
        os.makedirs(local_dest_dir, exist_ok=True)
        run_adb_command(["adb", "pull", remote_path, local_filepath])
        print(f"  - Successfully pulled '{apk_filename}'.")
        return True
    except Exception as e:
        print(f"  - Error pulling '{apk_filename}': {e}", file=sys.stderr)
        return False


def uninstall_package(package_name):
    """
    Uninstalls a package from the emulator.

    Args:
        package_name (str): The package name to uninstall.

    Returns:
        bool: True if uninstalled successfully, False otherwise.
    """
    print(f"  - Uninstalling '{package_name}'...")
    try:
        output = run_adb_command(["adb", "uninstall", package_name], check_output=False)
        if "Success" in output:
            print(f"  - Successfully uninstalled '{package_name}'.")
            return True
        else:
            print(f"  - Uninstall may have failed for '{package_name}'. Output: {output}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"  - Error uninstalling '{package_name}': {e}", file=sys.stderr)
        return False


def process_package(package_name, output_base_dir, install_timeout=300):
    """
    Full pipeline for a single package: open Play Store, wait for install,
    pull APKs, then uninstall.

    Args:
        package_name (str): The package name to process.
        output_base_dir (str): Base directory; APKs are saved under <output_base_dir>/<package_name>/.
        install_timeout (int): Seconds to wait for the user to install the app.

    Returns:
        bool: True if APKs were pulled successfully, False otherwise.
    """
    print(f"\n{'='*60}")
    print(f"  Processing: {package_name}")
    print(f"{'='*60}")

    local_package_dir = os.path.join(output_base_dir, package_name)

    # Skip if already downloaded previously
    if os.path.isdir(local_package_dir) and os.listdir(local_package_dir):
        print(f"  - Output directory already exists and is non-empty. Skipping.")
        return True

    # If already installed on the device, skip Play Store step
    already_installed = is_package_installed(package_name)
    if already_installed:
        print(f"  - Package is already installed on the emulator. Skipping Play Store step.")
    else:
        try:
            open_play_store_page(package_name)
        except Exception:
            print(f"  - Could not open Play Store for '{package_name}'. Skipping.", file=sys.stderr)
            return False

        print(
            f"\n  ACTION REQUIRED: Please install '{package_name}' from the Play Store on the emulator.\n"
            f"  The script will automatically continue once the installation is detected.\n"
        )

        installed = wait_for_installation(package_name, timeout=install_timeout)
        if not installed:
            print(f"  - Skipping '{package_name}' — not installed within timeout.", file=sys.stderr)
            return False

    # Give the system a moment to finish writing APK files
    time.sleep(2)

    # Pull all APKs (base + splits)
    apk_paths = get_apk_paths(package_name)
    if not apk_paths:
        print(f"  - No APKs to pull for '{package_name}'.", file=sys.stderr)
        if not already_installed:
            uninstall_package(package_name)
        return False

    pulled_count = 0
    for remote_path in apk_paths:
        if pull_apk(remote_path, local_package_dir):
            pulled_count += 1

    print(f"  - Pulled {pulled_count}/{len(apk_paths)} APK(s) for '{package_name}'.")

    # Uninstall after pulling
    uninstall_package(package_name)

    return pulled_count > 0


def main():
    parser = argparse.ArgumentParser(
        description="Read package names from a CSV, open Play Store, pull APKs, and uninstall."
    )
    parser.add_argument(
        "csv_file",
        help="Path to the CSV file containing package names.",
    )
    parser.add_argument(
        "output_dir",
        help="Directory where pulled APKs will be saved. Each app gets its own subdirectory.",
    )
    parser.add_argument(
        "--column",
        default=None,
        help="Name of the CSV column containing package names. "
             "If omitted, the first column is used.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Seconds to wait for each app to be installed before skipping (default: 300).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of apps to download from the CSV. If omitted, all apps are processed.",
    )
    args = parser.parse_args()

    csv_path = os.path.abspath(args.csv_file)
    output_dir = os.path.abspath(args.output_dir)

    print("--- Starting Play Store APK Puller ---")
    print(f"  CSV file   : {csv_path}")
    print(f"  Output dir : {output_dir}")
    if args.column:
        print(f"  Column     : {args.column}")
    print(f"  Timeout    : {args.timeout}s per app")
    if args.limit:
        print(f"  Limit      : {args.limit} app(s)")
    print()

    # Verify ADB connection
    if not check_adb_connection():
        print("Please start an Android emulator and ensure ADB can see it.", file=sys.stderr)
        sys.exit(1)

    # Read package names from the CSV
    packages = read_package_names_from_csv(csv_path, column_name=args.column)
    if not packages:
        print("No package names found in the CSV. Exiting.", file=sys.stderr)
        sys.exit(1)

    if args.limit is not None:
        packages = packages[:args.limit]

    print(f"Found {len(packages)} package(s) to process:\n")
    for pkg in packages:
        print(f"  - {pkg}")
    print()

    # Process each package
    success_count = 0
    for pkg in packages:
        if process_package(pkg, output_dir, install_timeout=args.timeout):
            success_count += 1

    print(f"\n--- Finished ---")
    print(f"Successfully pulled APKs for {success_count}/{len(packages)} package(s).")
    print(f"APKs are saved under: {output_dir}")


if __name__ == "__main__":
    main()

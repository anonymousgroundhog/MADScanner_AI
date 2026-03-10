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


# Text fragments that the Play Store displays when an app is not available.
PLAY_STORE_UNAVAILABLE_STRINGS = [
    "isn't available",
    "not available",
    "item not found",
    "this app is not available",
    "not found",
    "doesn't exist",
]


def load_not_available(not_available_path):
    """
    Loads the set of packages recorded as not available on the Play Store.

    Args:
        not_available_path (str): Path to the not-available log file.

    Returns:
        set[str]: Set of package name strings.
    """
    if not os.path.exists(not_available_path):
        return set()
    with open(not_available_path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def record_not_available(not_available_path, package_name):
    """
    Appends a package name to the not-available log file so it is skipped in
    future runs.

    Args:
        not_available_path (str): Path to the not-available log file.
        package_name (str): The package name to record.
    """
    with open(not_available_path, "a", encoding="utf-8") as f:
        f.write(f"{package_name}\n")
    print(f"  - Recorded '{package_name}' in not-available list: {not_available_path}")


def tap_install_button(wait_for_ui=8, max_attempts=3):
    """
    Uses uiautomator (via adb shell) to find and tap the Install button on the
    Play Store page. Retries up to max_attempts times.

    Also detects when the Play Store reports that the app is not available,
    returning "not_available" immediately so the caller can record it.

    Args:
        wait_for_ui (int): Seconds to wait for the UI to settle before each attempt.
        max_attempts (int): Number of tap attempts before giving up.

    Returns:
        str: One of:
            "tapped"        — Install button was found and tapped.
            "not_available" — Play Store indicates the app is not available.
            "not_found"     — Install button was not found after all attempts.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"  - Looking for Install button (attempt {attempt}/{max_attempts})...")
        time.sleep(wait_for_ui)

        try:
            # Dump the current UI hierarchy to a temp file on the device
            run_adb_command(
                ["adb", "shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"],
                check_output=False,
            )

            dump_xml = run_adb_command(
                ["adb", "shell", "cat", "/sdcard/ui_dump.xml"],
                check_output=False,
            )

            if not dump_xml:
                print(f"  - UI dump was empty, retrying...", file=sys.stderr)
                continue

            # Check for Play Store "not available" indicators before looking for Install
            dump_lower = dump_xml.lower()
            for unavailable_str in PLAY_STORE_UNAVAILABLE_STRINGS:
                if unavailable_str in dump_lower:
                    print(f"  - Play Store shows app is not available (matched: '{unavailable_str}').")
                    return "not_available"

            # Look for a node with text="Install" and extract its bounds.
            # Bounds format in uiautomator XML: bounds="[x1,y1][x2,y2]"
            match = re.search(
                r'text="Install"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                dump_xml,
            )
            if not match:
                # Some Play Store versions emit attributes in a different order
                match = re.search(
                    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="Install"',
                    dump_xml,
                )

            if not match:
                print(f"  - Install button not found in UI dump.", file=sys.stderr)
                continue

            x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            tap_x = (x1 + x2) // 2
            tap_y = (y1 + y2) // 2

            print(f"  - Found Install button at bounds [{x1},{y1}][{x2},{y2}]. Tapping ({tap_x},{tap_y})...")
            run_adb_command(["adb", "shell", "input", "tap", str(tap_x), str(tap_y)])
            print(f"  - Install button tapped.")
            return "tapped"

        except Exception as e:
            print(f"  - Error during Install button tap attempt {attempt}: {e}", file=sys.stderr)

    print(f"  - Could not tap Install button after {max_attempts} attempts.", file=sys.stderr)
    return "not_found"


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


def process_package(package_name, output_base_dir, not_available_path, install_timeout=300):
    """
    Full pipeline for a single package: check if already pulled, check not-available
    list, open Play Store, auto-tap Install, wait for install, pull APKs, then uninstall.

    Args:
        package_name (str): The package name to process.
        output_base_dir (str): Base directory; APKs are saved under <output_base_dir>/<package_name>/.
        not_available_path (str): Path to the file tracking packages not on Play Store.
        install_timeout (int): Seconds to wait for installation to complete.

    Returns:
        str: One of:
            "downloaded"    — APKs were successfully pulled this run.
            "skipped"       — Package was already downloaded or already installed.
            "not_available" — Package is not on the Play Store (recorded to file).
            "failed"        — An error prevented the download.
    """
    print(f"\n{'='*60}")
    print(f"  Processing: {package_name}")
    print(f"{'='*60}")

    local_package_dir = os.path.join(output_base_dir, package_name)

    # Skip if APKs were already pulled in a previous run
    if os.path.isdir(local_package_dir) and os.listdir(local_package_dir):
        print(f"  - Already downloaded (output directory is non-empty). Moving to next app.")
        return "skipped"

    # Skip if the package is already installed on the emulator (e.g. leftover from a
    # previous interrupted run). Move on so the limit is filled by a fresh app.
    if is_package_installed(package_name):
        print(f"  - Package is already installed on the emulator. Moving to next app.")
        return "skipped"

    # Open the Play Store app page
    try:
        open_play_store_page(package_name)
    except Exception:
        print(f"  - Could not open Play Store for '{package_name}'. Skipping.", file=sys.stderr)
        return "failed"

    # Auto-tap the Install button (also detects "not available" pages)
    tap_result = tap_install_button()
    if tap_result == "not_available":
        print(f"  - '{package_name}' is not available on the Play Store.", file=sys.stderr)
        record_not_available(not_available_path, package_name)
        return "not_available"
    if tap_result != "tapped":
        print(f"  - Could not tap Install for '{package_name}'. Skipping.", file=sys.stderr)
        return "failed"

    # Wait for the package manager to confirm installation
    installed = wait_for_installation(package_name, timeout=install_timeout)
    if not installed:
        print(f"  - '{package_name}' was not installed within {install_timeout}s. Skipping.", file=sys.stderr)
        return "failed"

    # Give the system a moment to finish writing APK files to disk
    time.sleep(2)

    # Pull all APKs (base + splits)
    apk_paths = get_apk_paths(package_name)
    if not apk_paths:
        print(f"  - No APKs to pull for '{package_name}'.", file=sys.stderr)
        uninstall_package(package_name)
        return "failed"

    pulled_count = 0
    for remote_path in apk_paths:
        if pull_apk(remote_path, local_package_dir):
            pulled_count += 1

    print(f"  - Pulled {pulled_count}/{len(apk_paths)} APK(s) for '{package_name}'.")

    # Uninstall after pulling to keep the emulator clean
    uninstall_package(package_name)

    return "downloaded" if pulled_count > 0 else "failed"


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

    # Not-available log lives alongside the CSV file
    not_available_path = os.path.join(os.path.dirname(csv_path), "not_available.txt")

    # Load previously recorded unavailable packages and filter them out upfront
    not_available_set = load_not_available(not_available_path)
    if not_available_set:
        before = len(packages)
        packages = [p for p in packages if p not in not_available_set]
        filtered = before - len(packages)
        print(f"  Filtered   : {filtered} package(s) excluded (recorded as not available in {not_available_path})")

    total_in_csv = len(packages)
    limit = args.limit
    print(f"Found {total_in_csv} package(s) to consider.")
    if limit is not None:
        print(f"Will download up to {limit} new app(s), skipping any already present.\n")
    else:
        print()

    # Walk the full CSV. Only freshly downloaded apps count toward --limit.
    # Skipped and not-available apps are passed over so the limit is filled
    # by genuinely new downloads.
    downloaded_count = 0
    skipped_count = 0
    not_available_count = 0
    failed_count = 0

    total_to_process = min(limit, total_in_csv) if limit is not None else total_in_csv

    for pkg_index, pkg in enumerate(packages, start=1):
        if limit is not None and downloaded_count >= limit:
            break

        apps_remaining = total_to_process - downloaded_count - 1
        bar_total = total_to_process
        bar_filled = downloaded_count
        bar_width = 30
        filled = int(bar_width * bar_filled / bar_total) if bar_total > 0 else 0
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\n[{bar}] {downloaded_count}/{total_to_process} downloaded | "
              f"{apps_remaining} app(s) remaining | package {pkg_index}/{total_in_csv}")

        status = process_package(pkg, output_dir, not_available_path, install_timeout=args.timeout)
        if status == "downloaded":
            downloaded_count += 1
        elif status == "skipped":
            skipped_count += 1
        elif status == "not_available":
            not_available_count += 1
        else:
            failed_count += 1

    print(f"\n--- Finished ---")
    print(f"  Downloaded    : {downloaded_count}")
    print(f"  Skipped       : {skipped_count} (already present)")
    print(f"  Not available : {not_available_count} (recorded to {not_available_path})")
    print(f"  Failed        : {failed_count}")
    print(f"APKs are saved under: {output_dir}")


if __name__ == "__main__":
    main()

import subprocess
import os
import re
import sys
import csv
import time
import argparse
import datetime


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------

def run_adb_command(command_parts, check_output=True):
    """
    Executes an ADB command (as a list of parts) and returns its standard output.
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


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------

def load_play_store_confirmed_packages(play_store_csv_path):
    """
    Reads the output CSV from Check_Packages_On_Google_Play.py and returns the
    set of package names whose status is 'found' (i.e. confirmed on Play Store).

    Args:
        play_store_csv_path (str): Path to the Play Store results CSV.

    Returns:
        set[str]: Package names confirmed as available on the Play Store.
    """
    confirmed = set()
    if not os.path.isfile(play_store_csv_path):
        print(f"Error: Play Store CSV not found: '{play_store_csv_path}'", file=sys.stderr)
        sys.exit(1)

    with open(play_store_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "package" not in reader.fieldnames:
            print(
                f"Error: Play Store CSV '{play_store_csv_path}' must have a 'package' column.",
                file=sys.stderr,
            )
            sys.exit(1)

        status_col = "status" if "status" in (reader.fieldnames or []) else None
        for row in reader:
            pkg = row["package"].strip()
            if not pkg:
                continue
            if status_col:
                if row[status_col].strip().lower() == "found":
                    confirmed.add(pkg)
            else:
                # No status column — treat every row as confirmed
                confirmed.add(pkg)

    return confirmed


def read_package_names_from_csv(csv_path, column_name=None):
    """
    Reads package names from a CSV file.
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


# ---------------------------------------------------------------------------
# Play Store interaction
# ---------------------------------------------------------------------------

def open_play_store_page(package_name):
    """Opens the Google Play Store page for a given package on the connected emulator."""
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


PLAY_STORE_UNAVAILABLE_STRINGS = [
    "isn't available",
    "not available",
    "item not found",
    "this app is not available",
    "not found",
    "doesn't exist",
    "your device isn't compatible",
]


def load_not_available(not_available_path):
    """Loads the set of packages recorded as not available on the Play Store."""
    if not os.path.exists(not_available_path):
        return set()
    with open(not_available_path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def record_not_available(not_available_path, package_name):
    """Appends a package name to the not-available log file."""
    with open(not_available_path, "a", encoding="utf-8") as f:
        f.write(f"{package_name}\n")
    print(f"  - Recorded '{package_name}' in not-available list: {not_available_path}")


def _dump_ui_xml():
    """Dumps the current Play Store UI hierarchy and returns the XML string (or '')."""
    run_adb_command(
        ["adb", "shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"],
        check_output=False,
    )
    return run_adb_command(
        ["adb", "shell", "cat", "/sdcard/ui_dump.xml"],
        check_output=False,
    )


def _check_unavailable(dump_xml):
    """
    Returns the matched unavailability string if any PLAY_STORE_UNAVAILABLE_STRINGS
    are present in the UI dump, otherwise returns None.
    """
    dump_lower = dump_xml.lower()
    for unavailable_str in PLAY_STORE_UNAVAILABLE_STRINGS:
        if unavailable_str in dump_lower:
            return unavailable_str
    return None


def tap_install_button(wait_for_ui=8, max_attempts=3):
    """
    Uses uiautomator (via adb shell) to find and tap the Install button.

    Performs an initial UI check after the page loads. If any
    PLAY_STORE_UNAVAILABLE_STRINGS are detected (e.g. 'not available',
    'your device isn't compatible') the function returns "not_available"
    immediately without attempting any install taps.

    Returns:
        str: "tapped", "not_available", or "not_found"
    """
    # --- Upfront unavailability check (single wait, no tap attempted) ---
    print("  - Waiting for Play Store page to load before checking availability...")
    time.sleep(wait_for_ui)
    try:
        dump_xml = _dump_ui_xml()
        if dump_xml:
            matched = _check_unavailable(dump_xml)
            if matched:
                print(
                    f"  - Play Store shows app is not available "
                    f"(matched: '{matched}'). Skipping immediately."
                )
                return "not_available"
    except Exception as e:
        print(f"  - Warning: upfront availability check failed: {e}", file=sys.stderr)

    # --- Retry loop: look for the Install button and tap it ---
    for attempt in range(1, max_attempts + 1):
        print(f"  - Looking for Install button (attempt {attempt}/{max_attempts})...")
        if attempt > 1:
            time.sleep(wait_for_ui)

        try:
            dump_xml = _dump_ui_xml()

            if not dump_xml:
                print("  - UI dump was empty, retrying...", file=sys.stderr)
                continue

            # Re-check unavailability in case the page updated between attempts
            matched = _check_unavailable(dump_xml)
            if matched:
                print(f"  - Play Store shows app is not available (matched: '{matched}').")
                return "not_available"

            match = re.search(
                r'text="Install"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                dump_xml,
            )
            if not match:
                match = re.search(
                    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="Install"',
                    dump_xml,
                )

            if not match:
                print("  - Install button not found in UI dump.", file=sys.stderr)
                continue

            x1, y1, x2, y2 = (
                int(match.group(1)), int(match.group(2)),
                int(match.group(3)), int(match.group(4)),
            )
            tap_x = (x1 + x2) // 2
            tap_y = (y1 + y2) // 2

            print(f"  - Found Install button at bounds [{x1},{y1}][{x2},{y2}]. Tapping ({tap_x},{tap_y})...")
            run_adb_command(["adb", "shell", "input", "tap", str(tap_x), str(tap_y)])
            print("  - Install button tapped.")
            return "tapped"

        except Exception as e:
            print(f"  - Error during Install button tap attempt {attempt}: {e}", file=sys.stderr)

    print(f"  - Could not tap Install button after {max_attempts} attempts.", file=sys.stderr)
    return "not_found"


# ---------------------------------------------------------------------------
# Package management helpers
# ---------------------------------------------------------------------------

def is_package_installed(package_name):
    """Checks whether a package is currently installed on the emulator."""
    try:
        output = run_adb_command(
            ["adb", "shell", "pm", "list", "packages", package_name],
            check_output=False,
        )
        return f"package:{package_name}" in output
    except Exception:
        return False


def wait_for_installation(package_name, timeout=300, poll_interval=5):
    """Polls ADB until the package appears as installed or the timeout is reached."""
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
    """Retrieves all APK file paths for a package on the emulator."""
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
    """Pulls a single APK from the emulator to a local directory."""
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
    """Uninstalls a package from the emulator."""
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


# ---------------------------------------------------------------------------
# Per-package pipeline
# ---------------------------------------------------------------------------

def process_package(package_name, output_base_dir, not_available_path, install_timeout=300):
    """
    Full pipeline for a single package: check if already pulled, check not-available
    list, open Play Store, auto-tap Install, wait for install, pull APKs, then uninstall.

    Returns:
        str: "downloaded", "skipped", "not_available", or "failed"
    """
    print(f"\n{'='*60}")
    print(f"  Processing: {package_name}")
    print(f"{'='*60}")

    local_package_dir = os.path.join(output_base_dir, package_name)

    if os.path.isdir(local_package_dir) and os.listdir(local_package_dir):
        print("  - Already downloaded (output directory is non-empty). Moving to next app.")
        return "skipped"

    if is_package_installed(package_name):
        print("  - Package is already installed on the emulator. Moving to next app.")
        return "skipped"

    try:
        open_play_store_page(package_name)
    except Exception:
        print(f"  - Could not open Play Store for '{package_name}'. Skipping.", file=sys.stderr)
        return "failed"

    tap_result = tap_install_button()
    if tap_result == "not_available":
        print(f"  - '{package_name}' is not available on the Play Store.", file=sys.stderr)
        record_not_available(not_available_path, package_name)
        return "not_available"
    if tap_result != "tapped":
        print(f"  - Could not tap Install for '{package_name}'. Skipping.", file=sys.stderr)
        return "failed"

    installed = wait_for_installation(package_name, timeout=install_timeout)
    if not installed:
        print(f"  - '{package_name}' was not installed within {install_timeout}s. Skipping.", file=sys.stderr)
        return "failed"

    time.sleep(2)

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

    uninstall_package(package_name)

    return "downloaded" if pulled_count > 0 else "failed"


# ---------------------------------------------------------------------------
# Single loop iteration
# ---------------------------------------------------------------------------

def run_loop_iteration(loop_num, packages, output_dir, not_available_path, limit, install_timeout):
    """
    Runs one full loop iteration: processes up to `limit` packages and returns
    per-iteration stats and elapsed wall-clock time in seconds.
    """
    print(f"\n{'#'*70}")
    print(f"  LOOP ITERATION {loop_num}")
    print(f"{'#'*70}")

    iter_start = time.monotonic()

    downloaded_count = 0
    skipped_count = 0
    not_available_count = 0
    failed_count = 0

    total_to_process = min(limit, len(packages)) if limit is not None else len(packages)

    for pkg_index, pkg in enumerate(packages, start=1):
        if limit is not None and downloaded_count >= limit:
            break

        apps_remaining = total_to_process - downloaded_count - 1
        bar_total = total_to_process
        bar_filled = downloaded_count
        bar_width = 30
        filled = int(bar_width * bar_filled / bar_total) if bar_total > 0 else 0
        bar = "#" * filled + "-" * (bar_width - filled)
        print(
            f"\n[{bar}] {downloaded_count}/{total_to_process} downloaded | "
            f"{apps_remaining} app(s) remaining | package {pkg_index}/{len(packages)}"
        )

        status = process_package(pkg, output_dir, not_available_path, install_timeout=install_timeout)
        if status == "downloaded":
            downloaded_count += 1
        elif status == "skipped":
            skipped_count += 1
        elif status == "not_available":
            not_available_count += 1
        else:
            failed_count += 1

    iter_elapsed = time.monotonic() - iter_start

    print(f"\n--- Loop {loop_num} complete ---")
    print(f"  Downloaded    : {downloaded_count}")
    print(f"  Skipped       : {skipped_count} (already present)")
    print(f"  Not available : {not_available_count}")
    print(f"  Failed        : {failed_count}")
    print(f"  Elapsed time  : {_fmt(iter_elapsed)}")

    return {
        "loop": loop_num,
        "downloaded": downloaded_count,
        "skipped": skipped_count,
        "not_available": not_available_count,
        "failed": failed_count,
        "elapsed_seconds": iter_elapsed,
    }


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------

def _fmt(seconds):
    """Format a duration in seconds as HH:MM:SS.mmm"""
    td = datetime.timedelta(seconds=seconds)
    total_s = int(td.total_seconds())
    ms = round((seconds - int(seconds)) * 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read package names from a CSV, open Play Store, pull APKs, and uninstall. "
            "Supports multiple loop iterations with per-loop and average timing."
        )
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
        help="Maximum number of apps to download per loop iteration. "
             "If omitted, all apps in the CSV are processed each iteration.",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=1,
        help="Number of loop iterations to run (default: 1).",
    )
    parser.add_argument(
        "--play-store-csv",
        default=None,
        metavar="PATH",
        help="Path to the output CSV from Check_Packages_On_Google_Play.py. "
             "When provided, only packages with status 'found' in that file will be processed. "
             "If omitted, all packages from the input CSV are used.",
    )
    args = parser.parse_args()

    if args.loops < 1:
        print("Error: --loops must be at least 1.", file=sys.stderr)
        sys.exit(1)

    csv_path = os.path.abspath(args.csv_file)
    output_dir = os.path.abspath(args.output_dir)

    print("--- Starting Play Store APK Puller (Loop Mode) ---")
    print(f"  CSV file   : {csv_path}")
    print(f"  Output dir : {output_dir}")
    if args.column:
        print(f"  Column     : {args.column}")
    print(f"  Timeout    : {args.timeout}s per app")
    if args.limit:
        print(f"  Limit      : {args.limit} app(s) per loop")
    print(f"  Loops      : {args.loops}")
    if args.play_store_csv:
        print(f"  Filter CSV : {os.path.abspath(args.play_store_csv)} (Play Store confirmed only)")
    print()

    if not check_adb_connection():
        print("Please start an Android emulator and ensure ADB can see it.", file=sys.stderr)
        sys.exit(1)

    packages = read_package_names_from_csv(csv_path, column_name=args.column)
    if not packages:
        print("No package names found in the CSV. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Optional: filter to only packages confirmed on the Play Store
    if args.play_store_csv:
        play_store_csv_path = os.path.abspath(args.play_store_csv)
        confirmed = load_play_store_confirmed_packages(play_store_csv_path)
        before = len(packages)
        packages = [p for p in packages if p in confirmed]
        filtered = before - len(packages)
        print(
            f"  Play Store filter: {len(packages)} package(s) kept, "
            f"{filtered} excluded (not found or not checked)."
        )
        if not packages:
            print("No packages remain after Play Store filter. Exiting.", file=sys.stderr)
            sys.exit(1)

    not_available_path = os.path.join(os.path.dirname(csv_path), "not_available.txt")

    not_available_set = load_not_available(not_available_path)
    if not_available_set:
        before = len(packages)
        packages = [p for p in packages if p not in not_available_set]
        filtered = before - len(packages)
        print(
            f"  Filtered   : {filtered} package(s) excluded "
            f"(recorded as not available in {not_available_path})"
        )

    print(f"Found {len(packages)} package(s) to consider per loop.")
    print()

    # ------------------------------------------------------------------
    # Run all loop iterations
    # ------------------------------------------------------------------
    iteration_results = []

    for loop_num in range(1, args.loops + 1):
        result = run_loop_iteration(
            loop_num=loop_num,
            packages=packages,
            output_dir=output_dir,
            not_available_path=not_available_path,
            limit=args.limit,
            install_timeout=args.timeout,
        )
        iteration_results.append(result)

    # ------------------------------------------------------------------
    # Final timing summary
    # ------------------------------------------------------------------
    elapsed_times = [r["elapsed_seconds"] for r in iteration_results]
    average_elapsed = sum(elapsed_times) / len(elapsed_times)

    print(f"\n{'='*70}")
    print("  TIMING SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Loop':<10} {'Elapsed Time':<18} {'Downloaded':>12} {'Skipped':>9} {'Failed':>8}")
    print(f"  {'-'*10} {'-'*18} {'-'*12} {'-'*9} {'-'*8}")
    for r in iteration_results:
        print(
            f"  {r['loop']:<10} {_fmt(r['elapsed_seconds']):<18} "
            f"{r['downloaded']:>12} {r['skipped']:>9} {r['failed']:>8}"
        )
    print(f"\n  Average loop time : {_fmt(average_elapsed)}")
    print(f"  Total wall time   : {_fmt(sum(elapsed_times))}")
    print(f"{'='*70}")
    print(f"\nAPKs are saved under: {output_dir}")


if __name__ == "__main__":
    main()

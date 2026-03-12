import subprocess
import os
import sys
import json
import csv
import argparse


DEFAULT_SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "emulator_snapshot.json"
)


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


def load_snapshot_json(snapshot_path):
    """Loads package names from a JSON snapshot file."""
    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    packages = data.get("packages", [])
    timestamp = data.get("timestamp", "unknown")
    print(f"Snapshot loaded (JSON): {len(packages)} package(s) recorded at {timestamp}")
    return set(packages), timestamp


def load_snapshot_csv(snapshot_path):
    """
    Loads package names from a CSV file. Looks for a 'package' column
    (case-insensitive); falls back to the first column if not found.
    """
    packages = []
    with open(snapshot_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        package_col = None
        for h in headers:
            if h.strip().lower() == "package":
                package_col = h
                break

        if package_col:
            print(f"Using CSV column '{package_col}' for package names.")
            for row in reader:
                value = row[package_col].strip()
                if value:
                    packages.append(value)
        elif headers:
            first_col = headers[0]
            print(f"No 'package' column found in CSV. Using first column: '{first_col}'.")
            for row in reader:
                value = row[first_col].strip()
                if value:
                    packages.append(value)
        else:
            # No header row — read as plain list
            f.seek(0)
            plain_reader = csv.reader(f)
            for row in plain_reader:
                if row and row[0].strip():
                    packages.append(row[0].strip())

    print(f"Snapshot loaded (CSV): {len(packages)} package(s)")
    return set(packages), "N/A (CSV source)"


def load_snapshot(snapshot_path):
    """
    Loads a package snapshot from a JSON or CSV file.

    Args:
        snapshot_path (str): Path to the snapshot file (.json or .csv).

    Returns:
        tuple[set[str], str]: Set of package names and a timestamp string.
    """
    if not os.path.isfile(snapshot_path):
        print(f"Error: Snapshot file not found: {snapshot_path}", file=sys.stderr)
        print("Run Snapshot_Installed_Apps_On_Emulator.py first to create a snapshot.", file=sys.stderr)
        sys.exit(1)

    ext = os.path.splitext(snapshot_path)[1].lower()
    if ext == ".csv":
        return load_snapshot_csv(snapshot_path)
    else:
        return load_snapshot_json(snapshot_path)


def get_installed_packages():
    """
    Retrieves all installed package names from the connected emulator/device.

    Returns:
        set[str]: Set of currently installed package names.
    """
    output = run_adb_command(["shell", "pm", "list", "packages"])
    packages = set()
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            packages.add(line[len("package:"):].strip())
    return packages


def uninstall_packages(packages):
    """
    Attempts to uninstall each package via ADB and reports results.

    Args:
        packages (list[str]): Package names to uninstall.

    Returns:
        int: Count of successfully uninstalled packages.
    """
    uninstalled_count = 0
    for package in packages:
        print(f"Attempting to uninstall '{package}'...")
        output = run_adb_command(["uninstall", package])

        if "Success" in output:
            print(f"  Success")
            uninstalled_count += 1
        else:
            print(f"  Info: {output if output else 'Package may not be installed or already removed'}")
    return uninstalled_count


def main():
    parser = argparse.ArgumentParser(
        description="Uninstall any app packages installed on the emulator/device after "
                    "a baseline snapshot was taken. Compares the current package list "
                    "against the snapshot and removes newly added packages."
    )
    parser.add_argument(
        "--snapshot",
        default=DEFAULT_SNAPSHOT_PATH,
        help=f"Path to the snapshot file (.json or .csv) created by Snapshot_Installed_Apps_On_Emulator.py "
             f"or a CSV with package names. Default: {DEFAULT_SNAPSHOT_PATH}"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List new packages that would be uninstalled without actually removing them."
    )
    args = parser.parse_args()

    snapshot_path = os.path.abspath(args.snapshot)

    print("--- Uninstall New Apps Since Snapshot ---")

    # Verify ADB connection
    print("Verifying ADB connection...")
    devices_output = run_adb_command(["devices"])
    if "device" not in devices_output:
        print("No Android emulator or device found. Please ensure one is running and connected via ADB.",
              file=sys.stderr)
        sys.exit(1)
    print("Android emulator/device detected.\n")

    # Load snapshot
    snapshot_packages, snapshot_timestamp = load_snapshot(snapshot_path)

    # Get current packages
    print("\nRetrieving currently installed packages...")
    current_packages = get_installed_packages()
    print(f"Found {len(current_packages)} package(s) currently installed.")

    # Diff: packages present now but not in the snapshot
    new_packages = sorted(current_packages - snapshot_packages)

    if not new_packages:
        print("\nNo new packages found since snapshot was taken. Nothing to uninstall.")
        print("--- Done ---")
        return

    print(f"\n{len(new_packages)} new package(s) found since snapshot ({snapshot_timestamp}):")
    for pkg in new_packages:
        print(f"  {pkg}")

    if args.dry_run:
        print("\n[Dry run] No packages were uninstalled.")
        print("--- Done ---")
        return

    print(f"\n--- Starting Uninstallation of {len(new_packages)} new package(s) ---")
    uninstalled_count = uninstall_packages(new_packages)

    print(f"\n--- Script Finished ---")
    print(f"Successfully uninstalled {uninstalled_count} out of {len(new_packages)} new package(s).")


if __name__ == "__main__":
    main()

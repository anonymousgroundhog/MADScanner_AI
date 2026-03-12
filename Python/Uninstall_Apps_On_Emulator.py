import subprocess
import os
import sys
import csv
import argparse


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


def collect_packages_from_directory(directory):
    """
    Collects package names from subdirectory names within the given directory.

    Args:
        directory (str): Path to the directory containing package name subdirectories.

    Returns:
        list[str]: List of package names found as subdirectory names.
    """
    if not os.path.isdir(directory):
        print(f"Error: Directory not found: {directory}", file=sys.stderr)
        sys.exit(1)

    packages = [
        name for name in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, name))
    ]

    if not packages:
        print(f"No subdirectories found in: {directory}")

    return sorted(packages)


def collect_packages_from_csv(csv_path):
    """
    Collects package names from a CSV file. Looks for a column named 'package'
    (case-insensitive); if not found, uses the first column.

    Args:
        csv_path (str): Path to the CSV file.

    Returns:
        list[str]: List of package names read from the CSV.
    """
    if not os.path.isfile(csv_path):
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    packages = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Find a column named 'package' (case-insensitive)
        package_col = None
        for h in headers:
            if h.strip().lower() == "package":
                package_col = h
                break

        if package_col:
            print(f"Using column '{package_col}' for package names.")
            for row in reader:
                value = row[package_col].strip()
                if value:
                    packages.append(value)
        else:
            # Fall back to first column
            if not headers:
                # No header row — re-read as plain list
                f.seek(0)
                plain_reader = csv.reader(f)
                for row in plain_reader:
                    if row and row[0].strip():
                        packages.append(row[0].strip())
            else:
                first_col = headers[0]
                print(f"No 'package' column found. Using first column: '{first_col}'.")
                for row in reader:
                    value = row[first_col].strip()
                    if value:
                        packages.append(value)

    return packages


def uninstall_packages(packages):
    """
    Attempts to uninstall each package via ADB and reports results.

    Args:
        packages (list[str]): Package names to uninstall.
    """
    print(f"\n--- Starting Uninstallation of {len(packages)} package(s) ---")
    uninstalled_count = 0

    for package in packages:
        print(f"Attempting to uninstall '{package}'...")
        output = run_adb_command(["uninstall", package])

        if "Success" in output:
            print(f"  Success")
            uninstalled_count += 1
        else:
            print(f"  Info: {output if output else 'Package may not be installed or already removed'}")

    print(f"\n--- Script Finished ---")
    print(f"Successfully uninstalled {uninstalled_count} out of {len(packages)} package(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Uninstall Android app packages from an emulator/device via ADB. "
                    "Accepts a directory (subdirectory names treated as package names) "
                    "or a CSV file containing package names."
    )
    parser.add_argument(
        "source",
        help="Path to a directory (subdirs = package names) or a CSV file containing package names."
    )
    args = parser.parse_args()

    source = os.path.abspath(args.source)

    # Determine source type and collect packages
    if os.path.isdir(source):
        print(f"--- Starting APK Uninstaller (directory mode) ---")
        print(f"Collecting package names from subdirectories in: {source}")
        packages = collect_packages_from_directory(source)
    elif os.path.isfile(source):
        print(f"--- Starting APK Uninstaller (CSV mode) ---")
        print(f"Collecting package names from CSV file: {source}")
        packages = collect_packages_from_csv(source)
    else:
        print(f"Error: '{source}' is not a valid directory or file.", file=sys.stderr)
        sys.exit(1)

    if not packages:
        print("No packages found. Nothing to uninstall.")
        return

    # Deduplicate while preserving order
    seen = set()
    unique_packages = []
    for p in packages:
        if p not in seen:
            seen.add(p)
            unique_packages.append(p)

    if len(unique_packages) < len(packages):
        print(f"Removed {len(packages) - len(unique_packages)} duplicate(s). "
              f"Processing {len(unique_packages)} unique package(s).")
    else:
        print(f"Found {len(unique_packages)} package(s) to uninstall.")

    # Verify ADB connection
    print("\nVerifying ADB connection...")
    devices_output = run_adb_command(["devices"])
    if "device" not in devices_output:
        print("No Android emulator or device found. Please ensure one is running and connected via ADB.",
              file=sys.stderr)
        sys.exit(1)
    print("Android emulator/device detected.\n")

    uninstall_packages(unique_packages)


if __name__ == "__main__":
    main()

import subprocess
import os
import sys
import json
import argparse
from datetime import datetime


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


def get_installed_packages():
    """
    Retrieves all installed package names from the connected emulator/device.

    Returns:
        list[str]: Sorted list of installed package names.
    """
    output = run_adb_command(["shell", "pm", "list", "packages"])
    packages = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            packages.append(line[len("package:"):].strip())
    return sorted(packages)


def main():
    parser = argparse.ArgumentParser(
        description="Take a snapshot of all currently installed app packages on the "
                    "connected Android emulator/device and save them to a JSON file."
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_SNAPSHOT_PATH,
        help=f"Path to save the snapshot JSON file. Default: {DEFAULT_SNAPSHOT_PATH}"
    )
    args = parser.parse_args()

    snapshot_path = os.path.abspath(args.output)

    print("--- Emulator Package Snapshot ---")

    # Verify ADB connection
    print("Verifying ADB connection...")
    devices_output = run_adb_command(["devices"])
    if "device" not in devices_output:
        print("No Android emulator or device found. Please ensure one is running and connected via ADB.",
              file=sys.stderr)
        sys.exit(1)
    print("Android emulator/device detected.\n")

    print("Retrieving installed packages...")
    packages = get_installed_packages()

    if not packages:
        print("Warning: No packages found on device. Snapshot will be empty.", file=sys.stderr)

    print(f"Found {len(packages)} installed package(s).")

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "package_count": len(packages),
        "packages": packages
    }

    output_dir = os.path.dirname(snapshot_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\nSnapshot saved to: {snapshot_path}")
    print(f"Timestamp: {snapshot['timestamp']}")
    print("--- Done ---")


if __name__ == "__main__":
    main()

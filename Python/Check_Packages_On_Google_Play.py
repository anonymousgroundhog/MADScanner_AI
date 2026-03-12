import os
import sys
import csv
import argparse
from google_play_scraper import app, exceptions


def load_packages_from_csv(csv_path):
    """
    Reads package names from a CSV file. Looks for a 'package' column
    (case-insensitive); falls back to the first column if not found.

    Args:
        csv_path (str): Path to the input CSV file.

    Returns:
        list[str]: List of package names.
    """
    if not os.path.isfile(csv_path):
        print(f"Error: Input CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    packages = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

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
        elif headers:
            first_col = headers[0]
            print(f"No 'package' column found. Using first column: '{first_col}'.")
            for row in reader:
                value = row[first_col].strip()
                if value:
                    packages.append(value)
        else:
            # No header row — plain list
            f.seek(0)
            plain_reader = csv.reader(f)
            for row in plain_reader:
                if row and row[0].strip():
                    packages.append(row[0].strip())

    return packages


def load_already_checked_packages(output_csv):
    """
    Reads the output CSV (if it exists) and returns the set of package names
    that have already been checked, so they can be skipped on subsequent runs.

    Args:
        output_csv (str): Path to the output CSV file.

    Returns:
        set[str]: Package names already present in the output file.
    """
    if not os.path.isfile(output_csv):
        return set()

    already_checked = set()
    with open(output_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "package" in reader.fieldnames:
            for row in reader:
                pkg = row["package"].strip()
                if pkg:
                    already_checked.add(pkg)

    return already_checked


def check_package_on_play_store(package_name):
    """
    Looks up a package on the Google Play Store.

    Args:
        package_name (str): The Android package name to look up.

    Returns:
        dict with keys:
            - 'package'  : the package name
            - 'app_name' : title from Play Store, or 'not_discovered'
            - 'status'   : 'found', 'not_discovered', or 'error: <reason>'
    """
    try:
        info = app(package_name, lang="en", country="us")
        return {
            "package": package_name,
            "app_name": info.get("title", "not_discovered"),
            "status": "found",
        }
    except exceptions.NotFoundError:
        return {
            "package": package_name,
            "app_name": "not_discovered",
            "status": "not_discovered",
        }
    except Exception as e:
        return {
            "package": package_name,
            "app_name": "not_discovered",
            "status": f"error: {e}",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Check whether Android app packages exist on the Google Play Store. "
                    "Reads package names from a CSV file and appends results to an output CSV. "
                    "Packages already present in the output file are skipped automatically."
    )
    parser.add_argument(
        "input_csv",
        help="Path to the input CSV file containing package names."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write/append the results CSV. Defaults to 'play_store_results.csv' "
             "in the same directory as the input file."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of new packages to check in this run. "
             "Already-checked packages do not count toward this limit."
    )
    args = parser.parse_args()

    input_csv = os.path.abspath(args.input_csv)

    if args.output:
        output_csv = os.path.abspath(args.output)
    else:
        input_dir = os.path.dirname(input_csv)
        output_csv = os.path.join(input_dir, "play_store_results.csv")

    print("--- Google Play Store Package Checker ---")
    print(f"Input CSV : {input_csv}")
    print(f"Output CSV: {output_csv}")
    if args.limit:
        print(f"Limit     : {args.limit} package(s) per run")
    print()

    # Load all packages from input
    all_packages = load_packages_from_csv(input_csv)

    if not all_packages:
        print("No package names found in the input CSV. Exiting.")
        return

    # Deduplicate input while preserving order
    seen = set()
    unique_packages = []
    for p in all_packages:
        if p not in seen:
            seen.add(p)
            unique_packages.append(p)

    if len(unique_packages) < len(all_packages):
        print(f"Removed {len(all_packages) - len(unique_packages)} duplicate(s) from input.")

    # Load already-checked packages from the output file
    already_checked = load_already_checked_packages(output_csv)

    if already_checked:
        print(f"Skipping {len(already_checked)} package(s) already present in output CSV.")

    # Filter to only unchecked packages
    pending_packages = [p for p in unique_packages if p not in already_checked]

    if not pending_packages:
        print("All packages in the input CSV have already been checked. Nothing to do.")
        return

    # Apply per-run limit
    if args.limit is not None:
        batch = pending_packages[:args.limit]
        print(f"{len(pending_packages)} unchecked package(s) remaining. "
              f"Processing {len(batch)} this run.\n")
    else:
        batch = pending_packages
        print(f"{len(batch)} unchecked package(s) to process.\n")

    # Prepare output file — write header only if file doesn't exist yet
    output_dir = os.path.dirname(output_csv)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    write_header = not os.path.isfile(output_csv)
    fieldnames = ["package", "app_name", "status"]

    found_count = 0
    not_discovered_count = 0

    with open(output_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        for i, package in enumerate(batch, start=1):
            print(f"[{i}/{len(batch)}] Checking '{package}'...", end=" ", flush=True)
            result = check_package_on_play_store(package)

            if result["status"] == "found":
                print(f"Found: {result['app_name']}")
                found_count += 1
            else:
                print(result["status"])
                not_discovered_count += 1

            writer.writerow(result)
            f.flush()  # Write each result immediately in case of interruption

    remaining = len(pending_packages) - len(batch)
    print(f"\n--- Results ---")
    print(f"Found         : {found_count}")
    print(f"Not discovered: {not_discovered_count}")
    print(f"Results saved to: {output_csv}")
    if remaining > 0:
        print(f"Remaining unchecked packages: {remaining} (re-run to continue)")
    else:
        print("All packages have been checked.")
    print("--- Done ---")


if __name__ == "__main__":
    main()

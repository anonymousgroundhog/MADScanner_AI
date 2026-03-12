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
    Also returns the existing fieldnames so we can detect schema mismatches.

    Args:
        output_csv (str): Path to the output CSV file.

    Returns:
        tuple[set[str], list[str]]: Package names already present and the CSV fieldnames.
    """
    if not os.path.isfile(output_csv):
        return set(), []

    already_checked = set()
    existing_fields = []
    with open(output_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fields = list(reader.fieldnames or [])
        if "package" in existing_fields:
            for row in reader:
                pkg = row["package"].strip()
                if pkg:
                    already_checked.add(pkg)

    return already_checked, existing_fields


def check_package_on_play_store(package_name):
    """
    Looks up a package on the Google Play Store.

    Args:
        package_name (str): The Android package name to look up.

    Returns:
        dict with keys:
            - 'package'      : the package name
            - 'app_name'     : title from Play Store, or 'not_discovered'
            - 'category'     : primary genre/category, or 'not_discovered'
            - 'contains_ads' : True/False, or 'not_discovered'
            - 'status'       : 'found', 'not_discovered', or 'error: <reason>'
    """
    try:
        info = app(package_name, lang="en", country="us")
        return {
            "package": package_name,
            "app_name": info.get("title", "not_discovered"),
            "category": info.get("genre", "not_discovered") or "not_discovered",
            "contains_ads": info.get("containsAds", False),
            "status": "found",
        }
    except exceptions.NotFoundError:
        return {
            "package": package_name,
            "app_name": "not_discovered",
            "category": "not_discovered",
            "contains_ads": "not_discovered",
            "status": "not_discovered",
        }
    except Exception as e:
        return {
            "package": package_name,
            "app_name": "not_discovered",
            "category": "not_discovered",
            "contains_ads": "not_discovered",
            "status": f"error: {e}",
        }


def migrate_output_csv(output_csv, fieldnames):
    """
    If the existing output CSV is missing the new 'category' or 'contains_ads' columns,
    rewrite it in-place adding those columns with 'legacy' as the placeholder value
    so that previously checked rows are not lost.

    Args:
        output_csv (str): Path to the existing output CSV.
        fieldnames  (list[str]): The full target fieldnames list.
    """
    tmp_path = output_csv + ".migration_tmp"
    rows = []
    with open(output_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            for col in fieldnames:
                if col not in row:
                    row[col] = "legacy"
            writer.writerow({k: row[k] for k in fieldnames})

    os.replace(tmp_path, output_csv)
    print(f"Migrated output CSV to include new columns: {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="Check whether Android app packages exist on the Google Play Store. "
                    "Reads package names from a CSV file and appends results to an output CSV. "
                    "Packages already present in the output file are skipped automatically. "
                    "Now also captures app category and whether the app contains ads."
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
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="Re-check packages that were previously recorded as 'legacy' (missing category/"
             "contains_ads data from an older run). These are processed after any new packages."
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
    if args.recheck:
        print("Mode      : recheck legacy entries (missing category/contains_ads)")
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
    already_checked, existing_fields = load_already_checked_packages(output_csv)

    fieldnames = ["package", "app_name", "category", "contains_ads", "status"]

    # Migrate old CSVs that are missing the new columns
    if os.path.isfile(output_csv) and existing_fields:
        missing_cols = [c for c in fieldnames if c not in existing_fields]
        if missing_cols:
            print(f"Output CSV is missing columns {missing_cols}. Migrating...")
            migrate_output_csv(output_csv, fieldnames)

    # Filter to only unchecked packages
    pending_packages = [p for p in unique_packages if p not in already_checked]

    # Collect legacy packages that need rechecking (category/contains_ads = 'legacy')
    legacy_packages = []
    if args.recheck and os.path.isfile(output_csv):
        with open(output_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("category", "") == "legacy" or row.get("contains_ads", "") == "legacy":
                    pkg = row["package"].strip()
                    if pkg:
                        legacy_packages.append(pkg)

    # Packages that are already checked AND not being rechecked are truly skipped
    truly_skipped = len(already_checked) - len(legacy_packages)
    if truly_skipped > 0:
        print(f"Skipping {truly_skipped} package(s) already present in output CSV.")
    if legacy_packages:
        print(f"Found {len(legacy_packages)} legacy package(s) to recheck (missing category/ads data).")

    if not pending_packages and not legacy_packages:
        print("All packages in the input CSV have already been checked. Nothing to do.")
        return

    # Apply per-run limit across new + legacy combined
    combined = pending_packages + [p for p in legacy_packages if p not in set(pending_packages)]
    if args.limit is not None:
        batch = combined[:args.limit]
        print(f"\n{len(combined)} package(s) queued "
              f"({len(pending_packages)} new, {len(legacy_packages)} legacy recheck). "
              f"Processing {len(batch)} this run.\n")
    else:
        batch = combined
        print(f"\n{len(batch)} package(s) queued "
              f"({len(pending_packages)} new, {len(legacy_packages)} legacy recheck).\n")

    # Prepare output file — write header only if file doesn't exist yet
    output_dir = os.path.dirname(output_csv)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    write_header = not os.path.isfile(output_csv)

    # For legacy rechecks, rewrite the output file removing the stale legacy rows
    recheck_set = set(legacy_packages) & set(batch)
    if recheck_set:
        tmp_path = output_csv + ".recheck_tmp"
        print(f"Preparing recheck: rewriting output CSV to remove {len(recheck_set)} legacy row(s)...", flush=True)
        kept = 0
        with open(output_csv, newline="", encoding="utf-8") as src, \
             open(tmp_path, "w", newline="", encoding="utf-8") as dst:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                if row["package"].strip() not in recheck_set:
                    writer.writerow({k: row.get(k, "") for k in fieldnames})
                    kept += 1
        os.replace(tmp_path, output_csv)
        print(f"Done. Kept {kept} existing row(s). Starting recheck...\n", flush=True)
        write_header = False  # Header already written

    found_count = 0
    not_discovered_count = 0

    with open(output_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        total = len(batch)
        for i, package in enumerate(batch, start=1):
            remaining_now = total - i
            tag = " [recheck]" if package in recheck_set else ""
            print(f"[{i}/{total} | {remaining_now} remaining] Checking '{package}'{tag}...", end=" ", flush=True)
            result = check_package_on_play_store(package)

            if result["status"] == "found":
                print(f"Found: {result['app_name']} | Category: {result['category']} | Ads: {result['contains_ads']}")
                found_count += 1
            else:
                print(result["status"])
                not_discovered_count += 1

            writer.writerow(result)
            f.flush()  # Write each result immediately in case of interruption

    new_count = len([p for p in batch if p not in recheck_set])
    remaining = len(pending_packages) - new_count
    print(f"\n--- Results ---")
    print(f"Found         : {found_count}")
    print(f"Not discovered: {not_discovered_count}")
    if recheck_set:
        print(f"Rechecked     : {len(recheck_set)}")
    print(f"Results saved to: {output_csv}")
    if remaining > 0:
        print(f"Remaining unchecked packages: {remaining} (re-run to continue)")
    else:
        print("All packages have been checked.")
    print("--- Done ---")


if __name__ == "__main__":
    main()

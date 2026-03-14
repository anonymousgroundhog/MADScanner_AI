import os
import sys
import csv
import re
import time
import argparse
import datetime
import subprocess

from google_play_scraper import app as gplay_app, search, exceptions


# ---------------------------------------------------------------------------
# Google Play Store categories
# Maps human-friendly category names to search query strings.
# ---------------------------------------------------------------------------

PLAY_STORE_CATEGORIES = {
    "ART_AND_DESIGN":      "art and design apps",
    "AUTO_AND_VEHICLES":   "auto and vehicles apps",
    "BEAUTY":              "beauty apps",
    "BOOKS_AND_REFERENCE": "books and reference apps",
    "BUSINESS":            "business apps",
    "COMICS":              "comics apps",
    "COMMUNICATION":       "communication apps",
    "DATING":              "dating apps",
    "EDUCATION":           "education apps",
    "ENTERTAINMENT":       "entertainment apps",
    "EVENTS":              "events apps",
    "FINANCE":             "finance apps",
    "FOOD_AND_DRINK":      "food and drink apps",
    "HEALTH_AND_FITNESS":  "health and fitness apps",
    "HOUSE_AND_HOME":      "house and home apps",
    "LIBRARIES_AND_DEMO":  "libraries and demo apps",
    "LIFESTYLE":           "lifestyle apps",
    "MAPS_AND_NAVIGATION": "maps and navigation apps",
    "MEDICAL":             "medical apps",
    "MUSIC_AND_AUDIO":     "music and audio apps",
    "NEWS_AND_MAGAZINES":  "news and magazines apps",
    "PARENTING":           "parenting apps",
    "PERSONALIZATION":     "personalization apps",
    "PHOTOGRAPHY":         "photography apps",
    "PRODUCTIVITY":        "productivity apps",
    "SHOPPING":            "shopping apps",
    "SOCIAL":              "social apps",
    "SPORTS":              "sports apps",
    "TOOLS":               "tools apps",
    "TRAVEL_AND_LOCAL":    "travel and local apps",
    "VIDEO_PLAYERS":       "video player apps",
    "WEATHER":             "weather apps",
    "GAME_ACTION":         "action games",
    "GAME_ADVENTURE":      "adventure games",
    "GAME_ARCADE":         "arcade games",
    "GAME_BOARD":          "board games",
    "GAME_CARD":           "card games",
    "GAME_CASINO":         "casino games",
    "GAME_CASUAL":         "casual games",
    "GAME_EDUCATIONAL":    "educational games",
    "GAME_MUSIC":          "music games",
    "GAME_PUZZLE":         "puzzle games",
    "GAME_RACING":         "racing games",
    "GAME_ROLE_PLAYING":   "role playing games",
    "GAME_SIMULATION":     "simulation games",
    "GAME_SPORTS":         "sports games",
    "GAME_STRATEGY":       "strategy games",
    "GAME_TRIVIA":         "trivia games",
    "GAME_WORD":           "word games",
}


# ---------------------------------------------------------------------------
# Play Store scraping
# ---------------------------------------------------------------------------

def fetch_apps_for_category(cat_name, search_query, count, lang="en", country="us"):
    """
    Fetches up to `count` app listings for a given Play Store category by
    searching with a representative query string. For each result, calls
    app() to retrieve the accurate containsAds flag.

    Returns a list of dicts, each containing:
        package, app_name, category, contains_ads
    """
    results = []
    print(f"  Fetching up to {count} app(s) for '{cat_name}' (query: \"{search_query}\")...")
    try:
        hits = search(search_query, n_hits=count, lang=lang, country=country)
    except Exception as e:
        print(f"  Warning: search failed for '{cat_name}': {e}", file=sys.stderr)
        return results

    for entry in hits:
        pkg = entry.get("appId", "").strip()
        if not pkg:
            continue

        # Fetch full app details to get accurate containsAds value
        contains_ads = "unknown"
        try:
            details = gplay_app(pkg, lang=lang, country=country)
            contains_ads = details.get("containsAds", "unknown")
        except Exception:
            pass

        results.append({
            "package":      pkg,
            "app_name":     entry.get("title", "unknown"),
            "category":     cat_name,
            "contains_ads": contains_ads,
        })

    print(f"  -> Got {len(results)} app(s) for '{cat_name}'.")
    return results


# ---------------------------------------------------------------------------
# ADB helpers (mirrored from Install_App_On_Emulator_And_Pull_To_PC_Loop_Test.py)
# ---------------------------------------------------------------------------

def run_adb_command(command_parts, check_output=True):
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


def open_play_store_page(package_name):
    run_adb_command([
        "adb", "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", f"market://details?id={package_name}",
        "com.android.vending",
    ])


PLAY_STORE_UNAVAILABLE_STRINGS = [
    "isn't available",
    "not available",
    "item not found",
    "this app is not available",
    "not found",
    "doesn't exist",
    "your device isn't compatible",
]


def _dump_ui_xml():
    run_adb_command(
        ["adb", "shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"],
        check_output=False,
    )
    return run_adb_command(
        ["adb", "shell", "cat", "/sdcard/ui_dump.xml"],
        check_output=False,
    )


def _check_unavailable(dump_xml):
    dump_lower = dump_xml.lower()
    for s in PLAY_STORE_UNAVAILABLE_STRINGS:
        if s in dump_lower:
            return s
    return None


def tap_install_button(wait_for_ui=8, max_attempts=3):
    print("  - Waiting for Play Store page to load before checking availability...")
    time.sleep(wait_for_ui)
    try:
        dump_xml = _dump_ui_xml()
        if dump_xml:
            matched = _check_unavailable(dump_xml)
            if matched:
                print(f"  - App not available (matched: '{matched}'). Skipping.")
                return "not_available"
    except Exception as e:
        print(f"  - Warning: upfront availability check failed: {e}", file=sys.stderr)

    for attempt in range(1, max_attempts + 1):
        print(f"  - Looking for Install button (attempt {attempt}/{max_attempts})...")
        if attempt > 1:
            time.sleep(wait_for_ui)
        try:
            dump_xml = _dump_ui_xml()
            if not dump_xml:
                continue

            matched = _check_unavailable(dump_xml)
            if matched:
                print(f"  - App not available (matched: '{matched}').")
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
            tap_x, tap_y = (x1 + x2) // 2, (y1 + y2) // 2
            print(f"  - Tapping Install at ({tap_x},{tap_y})...")
            run_adb_command(["adb", "shell", "input", "tap", str(tap_x), str(tap_y)])
            return "tapped"
        except Exception as e:
            print(f"  - Error during tap attempt {attempt}: {e}", file=sys.stderr)

    return "not_found"


def is_package_installed(package_name):
    try:
        output = run_adb_command(
            ["adb", "shell", "pm", "list", "packages", package_name],
            check_output=False,
        )
        return f"package:{package_name}" in output
    except Exception:
        return False


def wait_for_installation(package_name, timeout=300, poll_interval=5):
    print(f"  - Waiting for '{package_name}' to install (timeout: {timeout}s)...")
    elapsed = 0
    while elapsed < timeout:
        if is_package_installed(package_name):
            print(f"  - '{package_name}' installed.")
            return True
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"    ({elapsed}s elapsed...)")
    print(f"  - Timed out waiting for '{package_name}'.", file=sys.stderr)
    return False


def get_apk_paths(package_name):
    try:
        output = run_adb_command(["adb", "shell", "pm", "path", package_name])
        return re.findall(r"package:(/.*\.apk)", output)
    except Exception:
        return []


def pull_apk(remote_path, local_dest_dir):
    apk_filename = os.path.basename(remote_path)
    local_filepath = os.path.join(local_dest_dir, apk_filename)
    try:
        os.makedirs(local_dest_dir, exist_ok=True)
        run_adb_command(["adb", "pull", remote_path, local_filepath])
        return True
    except Exception as e:
        print(f"  - Error pulling '{apk_filename}': {e}", file=sys.stderr)
        return False


def uninstall_package(package_name):
    try:
        run_adb_command(["adb", "uninstall", package_name], check_output=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CSV log helpers
# ---------------------------------------------------------------------------

LOG_FIELDNAMES = ["package", "app_name", "category", "contains_ads", "status"]


def load_log(log_path):
    """Returns a dict of package -> row for all entries already in the log."""
    existing = {}
    if not os.path.isfile(log_path):
        return existing
    with open(log_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pkg = row.get("package", "").strip()
            if pkg:
                existing[pkg] = row
    return existing


def append_log_row(log_path, row):
    """Appends a single row to the CSV log, writing the header if the file is new."""
    write_header = not os.path.isfile(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in LOG_FIELDNAMES})


# ---------------------------------------------------------------------------
# Per-app download pipeline
# ---------------------------------------------------------------------------

def download_app(entry, output_base_dir, install_timeout):
    """
    Full pipeline for a single app entry (dict with package, app_name, category,
    contains_ads).

    Returns status string: "downloaded", "skipped", "not_available", or "failed"
    """
    package = entry["package"]
    local_package_dir = os.path.join(output_base_dir, package)

    print(f"\n{'='*60}")
    print(f"  Processing: {package}  [{entry['category']}]")
    print(f"{'='*60}")

    if os.path.isdir(local_package_dir) and os.listdir(local_package_dir):
        print("  - Already downloaded. Skipping.")
        return "skipped"

    if is_package_installed(package):
        print("  - Already installed on emulator. Skipping.")
        return "skipped"

    try:
        print(f"  - Opening Play Store page for '{package}'...")
        open_play_store_page(package)
    except Exception as e:
        print(f"  - Could not open Play Store: {e}", file=sys.stderr)
        return "failed"

    tap_result = tap_install_button()
    if tap_result == "not_available":
        return "not_available"
    if tap_result != "tapped":
        print(f"  - Could not tap Install.", file=sys.stderr)
        return "failed"

    if not wait_for_installation(package, timeout=install_timeout):
        return "failed"

    time.sleep(2)

    apk_paths = get_apk_paths(package)
    if not apk_paths:
        print(f"  - No APK paths found for '{package}'.", file=sys.stderr)
        uninstall_package(package)
        return "failed"

    pulled = sum(1 for p in apk_paths if pull_apk(p, local_package_dir))
    print(f"  - Pulled {pulled}/{len(apk_paths)} APK(s).")
    uninstall_package(package)
    return "downloaded" if pulled > 0 else "failed"


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------

def _fmt(seconds):
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
            "Download APKs directly from Google Play Store by category. "
            "Fetches the top-free apps for each requested category, installs them "
            "on a connected Android emulator via ADB, pulls the APKs to disk, "
            "then uninstalls. Results are logged to a CSV of your choice."
        )
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        metavar="CATEGORY",
        default=None,
        help=(
            "One or more Play Store category names to download from "
            "(e.g. TOOLS GAMES_ACTION EDUCATION). "
            "Defaults to ALL categories if not specified. "
            f"Available: {', '.join(sorted(PLAY_STORE_CATEGORIES))}."
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        metavar="N",
        help="Number of apps to fetch per category (default: 10).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Directory where pulled APKs will be saved. Each app gets its own subdirectory.",
    )
    parser.add_argument(
        "--log",
        default=None,
        metavar="FILE",
        help=(
            "Path to the CSV log file where results are recorded. "
            "Columns: package, app_name, category, contains_ads, status. "
            "Existing entries are skipped to support resume."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        metavar="SECS",
        help="Seconds to wait for each app to install before timing out (default: 300).",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="Language code for Play Store queries (default: en).",
    )
    parser.add_argument(
        "--country",
        default="us",
        help="Country code for Play Store queries (default: us).",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="Print all available category names and exit.",
    )
    args = parser.parse_args()

    if args.list_categories:
        print("Available Play Store categories:")
        for name in sorted(PLAY_STORE_CATEGORIES):
            print(f"  {name}")
        return

    # Enforce required args for normal runs
    if not args.output_dir or not args.log:
        parser.error("--output-dir and --log are required unless --list-categories is used.")

    # Resolve categories
    if args.categories:
        unknown = [c for c in args.categories if c.upper() not in PLAY_STORE_CATEGORIES]
        if unknown:
            print(f"Error: Unknown category/categories: {', '.join(unknown)}", file=sys.stderr)
            print(f"Run with --list-categories to see available options.", file=sys.stderr)
            sys.exit(1)
        selected_categories = {c.upper(): PLAY_STORE_CATEGORIES[c.upper()] for c in args.categories}
    else:
        selected_categories = PLAY_STORE_CATEGORIES

    output_dir = os.path.abspath(args.output_dir)
    log_path = os.path.abspath(args.log)

    print("--- Play Store Category APK Downloader ---")
    print(f"  Categories  : {', '.join(selected_categories) if args.categories else f'ALL ({len(selected_categories)})'}")
    print(f"  Apps/cat    : {args.count}")
    print(f"  Output dir  : {output_dir}")
    print(f"  Log file    : {log_path}")
    print(f"  Timeout     : {args.timeout}s per app")
    print(f"  Lang/Country: {args.lang}/{args.country}")
    print()

    # Check ADB
    if not check_adb_connection():
        print("Please start an Android emulator and ensure ADB can see it.", file=sys.stderr)
        sys.exit(1)

    # Load existing log to resume/skip already-processed packages
    already_logged = load_log(log_path)
    if already_logged:
        print(f"  Resuming: {len(already_logged)} package(s) already in log — will be skipped.")
    print()

    os.makedirs(output_dir, exist_ok=True)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Counters
    total_downloaded = 0
    total_skipped = 0
    total_not_available = 0
    total_failed = 0
    start_time = time.monotonic()

    for cat_name, cat_value in selected_categories.items():
        print(f"\n{'#'*70}")
        print(f"  CATEGORY: {cat_name}")
        print(f"{'#'*70}")

        apps = fetch_apps_for_category(
            cat_name, cat_value, args.count,
            lang=args.lang, country=args.country,
        )

        if not apps:
            print(f"  No apps returned for '{cat_name}'. Moving on.")
            continue

        cat_downloaded = 0

        for i, entry in enumerate(apps, start=1):
            pkg = entry["package"]
            print(f"\n  [{i}/{len(apps)}] {pkg}")

            # Skip if APKs already exist on disk (check before log to handle log/disk mismatch)
            local_package_dir = os.path.join(output_dir, pkg)
            if os.path.isdir(local_package_dir) and os.listdir(local_package_dir):
                print(f"  - Output directory already contains APK(s) for '{pkg}'. Skipping.")
                total_skipped += 1
                if pkg not in already_logged:
                    row = {
                        "package":      pkg,
                        "app_name":     entry["app_name"],
                        "category":     cat_name,
                        "contains_ads": entry["contains_ads"],
                        "status":       "skipped",
                    }
                    append_log_row(log_path, row)
                    already_logged[pkg] = row
                continue

            # Skip if already in log with a terminal status
            if pkg in already_logged:
                prior_status = already_logged[pkg].get("status", "")
                print(f"  - Already logged with status '{prior_status}'. Skipping.")
                total_skipped += 1
                continue

            status = download_app(entry, output_dir, args.timeout)

            row = {
                "package":      pkg,
                "app_name":     entry["app_name"],
                "category":     cat_name,
                "contains_ads": entry["contains_ads"],
                "status":       status,
            }
            append_log_row(log_path, row)
            already_logged[pkg] = row  # keep in-memory index up to date

            if status == "downloaded":
                total_downloaded += 1
                cat_downloaded += 1
            elif status == "skipped":
                total_skipped += 1
            elif status == "not_available":
                total_not_available += 1
            else:
                total_failed += 1

        print(f"\n  Category '{cat_name}' complete. Downloaded: {cat_downloaded}/{len(apps)}")

    elapsed = time.monotonic() - start_time

    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print(f"  Downloaded    : {total_downloaded}")
    print(f"  Skipped       : {total_skipped} (already logged or present)")
    print(f"  Not available : {total_not_available}")
    print(f"  Failed        : {total_failed}")
    print(f"  Elapsed time  : {_fmt(elapsed)}")
    print(f"\n  APKs saved to : {output_dir}")
    print(f"  Log file      : {log_path}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

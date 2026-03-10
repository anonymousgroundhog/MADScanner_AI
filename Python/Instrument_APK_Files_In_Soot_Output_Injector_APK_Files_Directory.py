import os
import shutil
import subprocess
import getpass
import datetime
import sys
import time
import re
import argparse
import concurrent.futures
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException


CATEGORY_PREFIXES = (
    "Art_and_Design_",
    "Auto_and_Vehicles_",
    "Beauty_",
    "Books_Reference_",
    "Business_",
    "Comics_",
    "Communication_",
    "Dating_",
    "Educational_",
    "Entertainment_",
    "Events_",
    "Finance_",
    "Food_and_Drinks_",
    "Games_",
    "Health_and_Fitness_",
    "House_and_Home_",
    "Lifestyle_",
    "Maps_and_Navigation_",
    "Medical_",
    "Music_and_Audio_",
    "News_magazine_",
    "Parenting_",
    "Personalization_",
    "Photography_",
    "Productivity_",
    "Shopping_",
    "Social_media_",
    "Sports_",
    "Tools_",
    "Travel_and_local_",
    "Video_players_and_editors_",
    "weather_",
)


def print_progress(current, total, failed, label=""):
    bar_width = 30
    filled = int(bar_width * current / total) if total > 0 else 0
    bar = "#" * filled + "-" * (bar_width - filled)
    remaining = total - current
    suffix = f" | {label}" if label else ""
    print(f"\n[{bar}] {current}/{total} | {remaining} left | failed: {failed}{suffix}")


def run_command(command_parts, check_output=False, cwd=None, error_message="Error executing command"):
    """Executes a shell command and returns (stdout, stderr)."""
    try:
        process = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            check=check_output,
            cwd=cwd,
        )
        return process.stdout.strip(), process.stderr.strip()
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {' '.join(command_parts)}", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Error: Command '{command_parts[0]}' not found.", file=sys.stderr)
        raise


def cleanup_directories(root_dir):
    """
    Removes any file other than 'signed-base.apk' from all subdirectories
    within root_dir. Skips subdirs that only contain signed-base.apk already.
    """
    print(f"--- Cleaning up directories under '{root_dir}' ---\n")
    if not os.path.isdir(root_dir):
        print(f"Error: The directory '{root_dir}' does not exist.")
        return

    for dirpath, _dirnames, filenames in os.walk(root_dir):
        to_remove = [f for f in filenames if f != "signed-base.apk"]
        if not to_remove:
            continue
        print(f"Processing directory: {dirpath}")
        for filename in to_remove:
            file_path_to_remove = os.path.join(dirpath, filename)
            try:
                os.remove(file_path_to_remove)
                print(f"  - Removed: {filename}")
            except OSError as e:
                print(f"  - Error removing {filename}: {e}")
        print()


def find_matching_apks(source_dir, search_dir):
    """
    Walks source_dir to find directories containing 'signed-base.apk', then
    copies matching split_config APKs from search_dir into those directories.
    Skips packages where split configs are already present.
    """
    print(f"--- Searching for matching APKs and copying split_config files ---\n")

    if not os.path.isdir(source_dir):
        print(f"Error: The source directory '{source_dir}' does not exist.")
        return
    if not os.path.isdir(search_dir):
        print(f"Error: The search directory '{search_dir}' does not exist.")
        return

    # Build a lookup: package_name -> directory path, by walking search_dir once
    search_index = {}
    for root, _dirs, files in os.walk(search_dir):
        if "base.apk" in files:
            pkg = os.path.basename(root)
            search_index[pkg] = root

    for root, _dirs, files in os.walk(source_dir):
        if "signed-base.apk" not in files:
            continue

        pkg = os.path.basename(root)
        print(f"Checking for match: {pkg}")

        if pkg not in search_index:
            print(f"  - No match found for '{pkg}' in {search_dir}\n")
            continue

        target_path = search_index[pkg]

        # Collect split configs not yet copied
        to_copy = []
        for filename in os.listdir(target_path):
            if filename.startswith("split_config") and filename.endswith(".apk"):
                dst_file = os.path.join(root, filename)
                if not os.path.exists(dst_file):
                    to_copy.append(filename)

        if not to_copy:
            print(f"  - Split configs already present for '{pkg}'. Skipping copy.")
            continue

        print(f"  - Match found: {target_path}")
        for filename in to_copy:
            src_file = os.path.join(target_path, filename)
            dst_file = os.path.join(root, filename)
            try:
                shutil.copy(src_file, dst_file)
                print(f"    - Copied '{filename}' to '{root}'")
            except shutil.Error as e:
                print(f"    - Error copying '{filename}': {e}")
        print()


def _sign_single_apk(task):
    """
    Worker function for parallel post-processing.
    task = (dirpath, filename, keystore_path, keystore_pass)

    Zipaligns and signs the split_config APK, leaving the original in place.
    Skips if the final signed file already exists.
    Returns (filename, success_bool).
    """
    dirpath, filename, keystore_path, keystore_pass = task
    apk_path = os.path.join(dirpath, filename)
    base_name, ext = os.path.splitext(filename)
    aligned_apk_path = os.path.join(dirpath, f"{base_name}-aligned{ext}")
    final_signed_path = os.path.join(dirpath, f"signed_{filename}")

    if os.path.exists(final_signed_path):
        print(f"  - Already signed: {filename}. Skipping.")
        return filename, True

    try:
        subprocess.run(
            ["zipalign", "-f", "-v", "4", apk_path, aligned_apk_path],
            check=True, capture_output=True, text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        stderr = e.stderr if hasattr(e, "stderr") else str(e)
        print(f"  ❌ zipalign failed for '{filename}': {stderr}", file=sys.stderr)
        return filename, False

    try:
        subprocess.run(
            ["apksigner", "sign", "--ks", keystore_path,
             "--ks-pass", f"pass:{keystore_pass}", aligned_apk_path],
            check=True, capture_output=True, text=True,
        )
        os.rename(aligned_apk_path, final_signed_path)
        # Clean up any .idsig files in the same dir
        for f in os.listdir(dirpath):
            if f.endswith(".idsig"):
                os.remove(os.path.join(dirpath, f))
        print(f"  ✅ Signed: {final_signed_path}")
        return filename, True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        stderr = e.stderr if hasattr(e, "stderr") else str(e)
        print(f"  ❌ apksigner failed for '{filename}': {stderr}", file=sys.stderr)
        if os.path.exists(aligned_apk_path):
            os.remove(aligned_apk_path)
        return filename, False


def get_keystore_password(keystore_path):
    """
    Verifies the keystore exists and prompts for the password once.

    Returns:
        tuple[str, str] | None: (keystore_path, password) or None on failure.
    """
    if not os.path.exists(keystore_path):
        print(f"Error: Keystore not found at '{keystore_path}'", file=sys.stderr)
        return None
    try:
        keystore_pass = getpass.getpass(prompt="Enter keystore password: ")
        return keystore_path, keystore_pass
    except Exception as error:
        print(f"Could not read password: {error}", file=sys.stderr)
        return None


def sign_missing_base_apks(root_dir, keystore_path, keystore_pass, workers=4):
    """
    Walks root_dir and for any subdirectory that contains a 'base.apk' but no
    'signed-base.apk', zipaligns and signs it to produce 'signed-base.apk'.

    Args:
        root_dir (str): Directory to scan (the --injected-dir).
        keystore_path (str): Path to the keystore file.
        keystore_pass (str): Keystore password.
        workers (int): Parallel worker count.
    """
    print(f"\n--- Signing missing base APKs in '{root_dir}' ---\n")

    tasks = []
    for dirpath, _dirs, filenames in os.walk(root_dir):
        if "base.apk" in filenames and "signed-base.apk" not in filenames:
            tasks.append((dirpath, "base.apk", keystore_path, keystore_pass))

    if not tasks:
        print("  - All base APKs already signed. Nothing to do.")
        return

    print(f"  Found {len(tasks)} unsigned base APK(s). Signing with {workers} worker(s)...")

    # _sign_single_apk produces "signed_base.apk" (underscore), but we need
    # "signed-base.apk" (hyphen) to match the convention the rest of the script
    # expects. We handle the rename here after signing.
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_sign_base_apk, dirpath, keystore_path, keystore_pass): dirpath
            for dirpath, _, _, _ in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            dirpath = futures[future]
            try:
                if not future.result():
                    failed += 1
            except Exception as e:
                print(f"  ❌ Unexpected error signing base.apk in '{dirpath}': {e}", file=sys.stderr)
                failed += 1

    print(f"\n  sign_missing_base_apks complete: {len(tasks) - failed} signed, {failed} failed.")


def _sign_base_apk(dirpath, keystore_path, keystore_pass):
    """
    Zipaligns and signs base.apk in dirpath, producing signed-base.apk.
    Leaves base.apk in place. Skips if signed-base.apk already exists.

    Returns:
        bool: True on success, False on failure.
    """
    apk_path = os.path.join(dirpath, "base.apk")
    aligned_path = os.path.join(dirpath, "base-aligned.apk")
    signed_path = os.path.join(dirpath, "signed-base.apk")

    if os.path.exists(signed_path):
        print(f"  - Already signed: {signed_path}. Skipping.")
        return True

    try:
        subprocess.run(
            ["zipalign", "-f", "-v", "4", apk_path, aligned_path],
            check=True, capture_output=True, text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        stderr = e.stderr if hasattr(e, "stderr") else str(e)
        print(f"  ❌ zipalign failed for base.apk in '{dirpath}': {stderr}", file=sys.stderr)
        return False

    try:
        subprocess.run(
            ["apksigner", "sign", "--ks", keystore_path,
             "--ks-pass", f"pass:{keystore_pass}", aligned_path],
            check=True, capture_output=True, text=True,
        )
        os.rename(aligned_path, signed_path)
        # Clean up any .idsig files produced by apksigner
        for f in os.listdir(dirpath):
            if f.endswith(".idsig"):
                os.remove(os.path.join(dirpath, f))
        print(f"  ✅ Signed base APK → {signed_path}")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        stderr = e.stderr if hasattr(e, "stderr") else str(e)
        print(f"  ❌ apksigner failed for base.apk in '{dirpath}': {stderr}", file=sys.stderr)
        if os.path.exists(aligned_path):
            os.remove(aligned_path)
        return False


def process_apks(root_dir, keystore_path, keystore_pass, workers=4):
    """
    Finds split_config APKs in subdirectories, zipaligns and signs them in parallel.
    """
    print(f"--- Processing split_config APKs in '{root_dir}' ---\n")

    tasks = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.startswith("split_config") and filename.endswith(".apk"):
                tasks.append((dirpath, filename, keystore_path, keystore_pass))

    if not tasks:
        print("  - No split_config APKs found to process.")
        return

    print(f"  Found {len(tasks)} split_config APK(s). Processing with {workers} worker(s)...")
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for fname, ok in executor.map(_sign_single_apk, tasks):
            if not ok:
                failed += 1

    print(f"\n  process_apks complete: {len(tasks) - failed} succeeded, {failed} failed.")


def start_logcat_capture():
    """
    Creates a 'logcat_logs' directory and starts capturing logcat output
    to a timestamped file within it.
    """
    print("--- Starting logcat capture ---")
    log_dir = "logcat_logs"
    try:
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filepath = os.path.join(log_dir, f"logcat_{timestamp}.log")
        log_file = open(log_filepath, "w")
        subprocess.Popen(["adb", "logcat"], stdout=log_file, stderr=subprocess.STDOUT)
        print(f"  Logcat running → {log_filepath}")
    except FileNotFoundError:
        print("Error: 'adb' not found.", file=sys.stderr)
    except Exception as e:
        print(f"An error occurred starting logcat: {e}", file=sys.stderr)


def get_apk_info(apk_path):
    """Uses aapt to extract package name and launchable activity from an APK."""
    print(f"  - Extracting package and activity from {os.path.basename(apk_path)}...")
    try:
        stdout, _ = run_command(["aapt", "dump", "badging", apk_path], check_output=True)
        package_match = re.search(r"package: name='([^']+)'", stdout)
        activity_match = re.search(r"launchable-activity: name='([^']+)'", stdout)
        if package_match and activity_match:
            package_name = package_match.group(1)
            main_activity = activity_match.group(1)
            print(f"    - Found Package: {package_name}, Activity: {main_activity}")
            return package_name, main_activity
        else:
            print(
                f"    - Could not extract package or activity from {os.path.basename(apk_path)}.",
                file=sys.stderr,
            )
            return None
    except Exception as e:
        print(f"    - Error running aapt: {e}", file=sys.stderr)
        return None


def robust_click_on_elements(driver, locator_strategy, locator_value, text_filters=None, max_attempts=3):
    """Finds and clicks elements robustly, optionally filtered by text."""
    if text_filters and not isinstance(text_filters, (list, tuple)):
        text_filters = [text_filters]
    if text_filters:
        text_filters = [f.lower() for f in text_filters]

    for _ in range(max_attempts):
        try:
            elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((locator_strategy, locator_value))
            )
            clicked_something = False
            for element in elements:
                if not element.is_displayed():
                    continue
                if text_filters is None:
                    element_text = element.text
                    element.click()
                    print(f"  -> Clicked '{element_text}' (no filter)")
                    clicked_something = True
                    time.sleep(1)
                else:
                    element_text_lower = element.text.lower()
                    for f in text_filters:
                        if f in element_text_lower:
                            element.click()
                            print(f"  -> Clicked '{element.text}' (matches '{f}')")
                            clicked_something = True
                            time.sleep(1)
                            break
            if not clicked_something:
                break
        except (TimeoutException, NoSuchElementException):
            break
        except Exception as e:
            print(f"Unexpected error during robust click: {e}")
            break


def click_ad_locations(driver, expected_activity):
    """Clicks predefined screen-percentage-based coordinates to trigger ads."""
    print("\n  - Dynamically calculating ad locations...")
    try:
        window_size = driver.get_window_size()
        width = window_size.get("width", 1080)
        height = window_size.get("height", 1920)
        mid_x = width * 0.5
        ad_coordinates = [
            (mid_x, height * 0.15),
            (mid_x, height * 0.95),
            (mid_x, height * 0.50),
        ]
        print(f"  - Screen size: {width}x{height}.")
    except Exception as e:
        print(f"  - WARNING: Could not get window size. Using defaults. Error: {e}", file=sys.stderr)
        ad_coordinates = [(500, 250), (500, 1800), (500, 1000)]

    print("\n  - Clicking on ad locations...")
    for x, y in ad_coordinates:
        try:
            int_x, int_y = int(x), int(y)
            print(f"    - Tapping at ({int_x}, {int_y})")
            driver.tap([(int_x, int_y)])
            time.sleep(5)
            current_activity = driver.current_activity
            if current_activity != expected_activity:
                print(f"    - Navigated to '{current_activity}'. Returning...")
                driver.back()
                time.sleep(2)
                final_activity = driver.current_activity
                if final_activity == expected_activity:
                    print("    - Successfully returned.")
                else:
                    print(f"    - Failed to return. Current: '{final_activity}'")
        except Exception as e:
            print(f"    - Could not tap at ({int(x)}, {int(y)}): {e}", file=sys.stderr)


def ensure_app_in_foreground(driver, app_package):
    """Checks if the app is in the foreground and activates it if not."""
    try:
        state = driver.query_app_state(app_package)
        if state < 4:
            print(f"  - App not in foreground (state: {state}). Activating...")
            driver.activate_app(app_package)
            time.sleep(3)
            print("  - App activated.")
    except Exception as e:
        print(f"  - Could not ensure app in foreground: {e}", file=sys.stderr)


def check_for_play_store_popup(driver):
    """Returns True if a 'Get this app from Play' popup is visible."""
    try:
        elements = WebDriverWait(driver, 2).until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//*[contains(@text, 'Get this app from Play')]")
            )
        )
        for el in elements:
            if el.is_displayed():
                print("  - POPUP DETECTED: 'Get this app from Play'. Stopping test.", file=sys.stderr)
                return True
    except (TimeoutException, NoSuchElementException):
        return False
    except Exception as e:
        print(f"  - Error during Play Store popup check: {e}", file=sys.stderr)
    return False


def collect_app_dirs(root_dir):
    """
    Walks root_dir and returns a list of directories that contain 'signed-base.apk'.
    Uses os.scandir for efficiency.
    """
    app_dirs = []
    for dirpath, _dirs, files in os.walk(root_dir):
        if "signed-base.apk" in files:
            app_dirs.append(dirpath)
    return app_dirs


def run_appium_tests(root_dir, original_apk_dir=None):
    """
    Walks root_dir to find signed-base.apk directories, installs and runs
    Appium tests for each app, with a progress bar.
    Skips apps whose logcat output already exists.
    """
    print("\n--- Starting Automated Ad-Clicking Test ---")

    if not os.path.isdir(root_dir):
        print(f"Error: Instrumented APKs directory not found at '{root_dir}'.", file=sys.stderr)
        sys.exit(1)

    # Build original APK index for package verification and split config lookup
    if original_apk_dir is None:
        original_apk_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "APK_Files_To_Analyze"
        )
    original_index = {}
    if os.path.isdir(original_apk_dir):
        for orig_root, _, orig_files in os.walk(original_apk_dir):
            if "base.apk" in orig_files:
                pkg = os.path.basename(orig_root)
                original_index[pkg] = orig_root
    else:
        print(
            f"  Warning: original APK directory not found at '{original_apk_dir}'. "
            "Split config matching will be skipped.",
            file=sys.stderr,
        )

    # Collect all candidate app dirs upfront so we can show a real progress bar
    app_dirs = collect_app_dirs(root_dir)
    total = len(app_dirs)
    if total == 0:
        print("  No signed-base.apk directories found. Nothing to test.")
        return

    print(f"  Found {total} app(s) to test.\n")

    tested_count = 0
    failed_count = 0

    for idx, app_dir_path in enumerate(app_dirs, start=1):
        app_dir_name = os.path.basename(app_dir_path)
        print_progress(idx - 1, total, failed_count, label=app_dir_name)
        print(f"--- Processing Application: {app_dir_name} ({idx}/{total}) ---")

        signed_base_apk = os.path.join(app_dir_path, "signed-base.apk")
        files = os.listdir(app_dir_path)

        # Extract package info from the signed APK
        apk_info = get_apk_info(signed_base_apk)
        if not apk_info:
            failed_count += 1
            continue
        app_package, app_activity = apk_info

        # Verify signed APK package name matches original base.apk
        if app_dir_name in original_index:
            original_base_apk = os.path.join(original_index[app_dir_name], "base.apk")
            original_info = get_apk_info(original_base_apk)
            if original_info:
                original_package = original_info[0]
                if original_package != app_package:
                    print(
                        f"  ⚠️ Package mismatch: signed='{app_package}' vs original='{original_package}'. Skipping.",
                        file=sys.stderr,
                    )
                    failed_count += 1
                    continue
                print(f"  ✓ Package names match: '{app_package}'")
            else:
                print(f"  ⚠️ Could not verify original base.apk for '{app_dir_name}'. Proceeding.", file=sys.stderr)
        else:
            print(f"  ⚠️ No original APK dir found for '{app_dir_name}'. Skipping package verification.", file=sys.stderr)

        # Collect APKs to install:
        #   1. The signed injected base APK (replaces the original base.apk)
        #   2. Re-signed split_config APKs from the injected dir (consistent signature)
        #   3. Any remaining helper/library APKs from the original --apk-dir that are
        #      not base.apk and not already covered by a signed version in the injected dir
        apk_paths = [signed_base_apk]

        # Signed split configs from injected dir
        signed_split_names = set()
        for fname in files:
            if fname.startswith("signed_split_config") and fname.endswith(".apk"):
                apk_paths.append(os.path.join(app_dir_path, fname))
                # Track the original name this signed file covers (signed_split_config_x -> split_config_x)
                signed_split_names.add(fname[len("signed_"):])

        # Helper/library APKs from the original APK dir (everything except base.apk and
        # any split_config already covered by a signed version above)
        if app_dir_name in original_index:
            orig_dir = original_index[app_dir_name]
            for fname in os.listdir(orig_dir):
                if not fname.endswith(".apk"):
                    continue
                if fname == "base.apk":
                    continue
                if fname in signed_split_names:
                    # Already have a re-signed version — skip the unsigned original
                    continue
                apk_paths.append(os.path.join(orig_dir, fname))
                print(f"  - Including helper APK from original dir: {fname}")

        print(f"  - Installing {len(apk_paths)} APK(s) for {app_package}:")
        for p in apk_paths:
            print(f"      {p}")

        try:
            run_command(
                ["adb", "install-multiple", "-r"] + apk_paths,
                check_output=True,
                error_message=f"Error installing APKs for {app_package}",
            )
            print(f"    - Installation successful for {app_package}.")
        except Exception:
            print(f"  - Installation failed for {app_package}. Skipping.", file=sys.stderr)
            failed_count += 1
            continue

        driver = None
        try:
            options = UiAutomator2Options()
            options.platform_name = "Android"
            options.app_package = app_package
            options.app_activity = app_activity
            options.no_reset = True
            options.auto_grant_permissions = True

            print("  - Connecting to Appium server...")
            driver = webdriver.Remote("http://127.0.0.1:4723/wd/hub", options=options)
            print("  - Driver connected. Waiting for app to load...")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//*[@displayed='true']"))
            )
            print("  - App is ready.")

            skip_app = False

            print("\n  - Handling initial permission dialogs...")
            robust_click_on_elements(
                driver, By.CLASS_NAME, "android.widget.Button",
                text_filters=["allow", "while using the app", "ok", "accept"],
            )

            if check_for_play_store_popup(driver):
                skip_app = True

            if not skip_app:
                ensure_app_in_foreground(driver, app_package)
                click_ad_locations(driver, app_activity)
                if check_for_play_store_popup(driver):
                    skip_app = True

            if not skip_app:
                ensure_app_in_foreground(driver, app_package)
                print("\n  - Swiping the screen...")
                driver.swipe(500, 1600, 500, 400, 1000)
                time.sleep(2)
                if check_for_play_store_popup(driver):
                    skip_app = True

            if not skip_app:
                ensure_app_in_foreground(driver, app_package)
                robust_click_on_elements(
                    driver, By.CLASS_NAME, "android.widget.Button", text_filters=["close"]
                )

            tested_count += 1

        except Exception as e:
            print(f"  - Error during Appium test for {app_package}: {e}", file=sys.stderr)
            failed_count += 1
        finally:
            if driver:
                print("\n  - Test finished. Quitting driver.")
                driver.quit()

            print(f"  - Uninstalling {app_package}...")
            try:
                run_command(["adb", "uninstall", app_package], check_output=True)
                print(f"  - Uninstalled {app_package}.")
            except Exception as e:
                print(f"  - Failed to uninstall {app_package}: {e}", file=sys.stderr)

    # Final progress bar at 100%
    print_progress(total, total, failed_count)
    print(f"\n--- Completed All Tests ---")
    print(f"  Tested  : {tested_count}")
    print(f"  Failed  : {failed_count}")


def stop_logcat_capture():
    """Stops the adb logcat process by killing the adb server."""
    print("--- Stopping logcat capture ---")
    try:
        subprocess.run(["adb", "kill-server"], check=True, capture_output=True, text=True)
        print("  ADB server killed. Logcat stopped.")
    except FileNotFoundError:
        print("Error: 'adb' not found.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error killing adb server: {e.stderr}", file=sys.stderr)
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instrument and test injected APK files.")
    parser.add_argument(
        "--apk-dir",
        default=None,
        help="Path to the directory containing original APKs. "
             "Defaults to '../APK_Files_To_Analyze' relative to this script.",
    )
    parser.add_argument(
        "--injected-dir",
        default="Soot_Output_Injector_APK_Files",
        help="Path to the directory containing injected/signed APKs. "
             "Defaults to 'Soot_Output_Injector_APK_Files' relative to this script.",
    )
    parser.add_argument(
        "--sign-workers",
        type=int,
        default=4,
        help="Number of parallel workers for zipalign/sign. Default: 4.",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    injected_apk_dir = (
        os.path.abspath(args.injected_dir)
        if os.path.isabs(args.injected_dir)
        else os.path.join(script_dir, args.injected_dir)
    )
    original_apk_dir = (
        os.path.abspath(args.apk_dir) if args.apk_dir
        else os.path.join(script_dir, "..", "APK_Files_To_Analyze")
    )

    script_keystore = os.path.join(script_dir, "..", "my-release-key.keystore")
    keystore_info = get_keystore_password(script_keystore)
    if keystore_info is None:
        sys.exit(1)
    keystore_path, keystore_pass = keystore_info

    sign_missing_base_apks(injected_apk_dir, keystore_path, keystore_pass, workers=args.sign_workers)
    find_matching_apks(injected_apk_dir, original_apk_dir)
    process_apks(injected_apk_dir, keystore_path, keystore_pass, workers=args.sign_workers)
    start_logcat_capture()
    run_appium_tests(injected_apk_dir, original_apk_dir)
    stop_logcat_capture()

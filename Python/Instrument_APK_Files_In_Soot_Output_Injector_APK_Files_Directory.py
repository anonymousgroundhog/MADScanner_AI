import os
import shutil
import subprocess
import getpass
import datetime
import sys
import time
import re
import glob
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# --- NEW: Category prefixes to strip (from screenshot) ---
# We add the trailing underscore to strip it as well.
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
# --------------------------------------------------------

def cleanup_directories(root_dir):
    """
    Removes any file other than 'signed-base.apk' from all subdirectories
    within a given root directory.

    Args:
        root_dir (str): The path to the root directory.
    """
    print(f"--- Cleaning up directories under '{root_dir}' ---\n")
    
    # Check if the provided path exists and is a directory
    if not os.path.isdir(root_dir):
        print(f"Error: The directory '{root_dir}' does not exist.")
        return

    # os.walk() generates the file names in a directory tree.
    for dirpath, dirnames, filenames in os.walk(root_dir):
        print(f"Processing directory: {dirpath}")
        
        # Iterate over a copy of the filenames list to safely remove items
        for filename in filenames:
            # If the file is not the one we want to keep...
            if filename != "signed-base.apk":
                file_path_to_remove = os.path.join(dirpath, filename)
                try:
                    os.remove(file_path_to_remove)
                    print(f"  - Removed: {filename}")
                except OSError as e:
                    print(f"  - Error removing {filename}: {e}")
        
        print() # Add a blank line for better readability

def find_matching_apks(source_dir, search_dir):
    """
    Walks source_dir at any depth to find directories containing 'signed-base.apk',
    then locates the matching package directory anywhere in search_dir and copies
    all split_config APKs from it into the source subdirectory.
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
    for root, dirnames, files in os.walk(search_dir):
        if "base.apk" in files:
            pkg = os.path.basename(root)
            search_index[pkg] = root

    # Walk source_dir to find every directory that contains a signed-base.apk
    for root, dirnames, files in os.walk(source_dir):
        if "signed-base.apk" not in files:
            continue

        pkg = os.path.basename(root)
        print(f"Checking for match: {pkg}")

        if pkg not in search_index:
            print(f"  - No match found for '{pkg}' in {search_dir}\n")
            continue

        target_path = search_index[pkg]
        print(f"  - Match found: {target_path}")

        for filename in os.listdir(target_path):
            if filename.startswith("split_config") and filename.endswith(".apk"):
                src_file = os.path.join(target_path, filename)
                dst_file = os.path.join(root, filename)
                try:
                    shutil.copy(src_file, dst_file)
                    print(f"    - Copied '{filename}' to '{root}'")
                except shutil.Error as e:
                    print(f"    - Error copying '{filename}': {e}")
        print()

def process_apks(root_dir):
    """
    Finds files starting with 'split_config' in subdirectories, 
    zip-aligns them, signs them, and renames the final output.
    Prompts for the keystore password securely.

    Args:
        root_dir (str): The path to the root directory containing APKs.
    """
    print(f"--- Processing APKs in '{root_dir}' for alignment and signing ---\n")

    keystore_path = "../my-release-key.keystore"
    if not os.path.exists(keystore_path):
        print(f"Error: Keystore not found at '{keystore_path}'")
        return

    # Securely prompt for the keystore password once.
    try:
        keystore_pass = getpass.getpass(prompt='Enter keystore password: ')
    except Exception as error:
        print(f"Could not read password: {error}")
        return

    # Walk through the directory to find the APKs
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.startswith("split_config") and filename.endswith(".apk"):
                apk_path = os.path.join(dirpath, filename)
                print(f"Processing: {apk_path}")

                # Define intermediate and final file paths
                base_name, ext = os.path.splitext(filename)
                aligned_apk_path = os.path.join(dirpath, f"{base_name}-aligned{ext}")
                final_signed_path = os.path.join(dirpath, f"signed_{filename}")

                # 1. Zipalign the APK
                zipalign_cmd = ['zipalign', '-f', '-v', '4', apk_path, aligned_apk_path]
                print("  - Running zipalign...")
                try:
                    subprocess.run(zipalign_cmd, check=True, capture_output=True, text=True)
                except FileNotFoundError:
                    print("    - Error: 'zipalign' command not found. Ensure it is in your system's PATH.")
                    continue
                except subprocess.CalledProcessError as e:
                    print(f"    - Error during zipalign: {e.stderr}")
                    continue

                # 2. Sign the aligned APK using apksigner
                apksigner_cmd = [
                    'apksigner', 'sign',
                    '--ks', keystore_path,
                    '--ks-pass', f'pass:{keystore_pass}',
                    aligned_apk_path
                ]
                print("  - Running apksigner...")
                try:
                    subprocess.run(apksigner_cmd, check=True, capture_output=True, text=True)
                    
                    # 3. Rename the signed file to its final name
                    try:
                        os.rename(aligned_apk_path, final_signed_path)
                        print(f"    - Successfully signed and created: {final_signed_path}")
                        
                        # 4. Clean up the original split_config apk
                        os.remove(apk_path)
                        print(f"    - Removed original file: {apk_path}")

                    except OSError as e:
                        print(f"    - Error renaming/removing files: {e}")

                except FileNotFoundError:
                    print("    - Error: 'apksigner' command not found. Ensure it is in your system's PATH.")
                    # Clean up the intermediate aligned file if signing fails
                    if os.path.exists(aligned_apk_path):
                        os.remove(aligned_apk_path)
                    continue
                except subprocess.CalledProcessError as e:
                    print(f"    - Error during signing: {e.stderr}")
                    # Clean up the intermediate aligned file if signing fails
                    if os.path.exists(aligned_apk_path):
                        os.remove(aligned_apk_path)
                
                print() # Add a blank line for readability

def start_logcat_capture():
    """
    Creates a 'logcat_logs' directory and starts capturing logcat output
    to a timestamped file within it.
    """
    print("--- Starting logcat capture ---")
    log_dir = "logcat_logs"

    try:
        # Create the directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)

        # Generate a timestamped filename
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"logcat_{timestamp}.log"
        log_filepath = os.path.join(log_dir, log_filename)

        # Open the file to write the logcat output
        log_file = open(log_filepath, "w")

        # Start the logcat process
        print(f"Starting adb logcat. Output will be saved to: {log_filepath}")
        subprocess.Popen(['adb', 'logcat'], stdout=log_file, stderr=subprocess.STDOUT)
        print("Logcat is running in the background. Press Ctrl+C in this terminal to stop the script.")
        print("NOTE: Stopping the script may not stop the logcat process. Use the 'stop_logcat_capture' function for that.")


    except FileNotFoundError:
        print("Error: 'adb' command not found. Ensure Android Debug Bridge is installed and in your system's PATH.")
    except Exception as e:
        print(f"An error occurred: {e}")

def run_command(command_parts, check_output=False, error_message="Error executing command"):
    """Executes a shell command."""
    try:
        process = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            check=check_output,
        )
        return process.stdout.strip(), process.stderr.strip()
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {' '.join(command_parts)}", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Error: Command '{command_parts[0]}' not found.", file=sys.stderr)
        raise

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
            print(f"    - Could not extract package or main activity from {os.path.basename(apk_path)}.", file=sys.stderr)
            return None
    except Exception as e:
        print(f"    - Error running aapt: {e}", file=sys.stderr)
        return None

def robust_click_on_elements(driver, locator_strategy, locator_value, text_filters=None, max_attempts=3):
    """
    Finds and clicks on elements robustly.
    Can accept a single string or a list of strings for text_filters.
    """
    # --- MODIFIED: Handle single string or list for text_filters ---
    if text_filters and not isinstance(text_filters, (list, tuple)):
        # If a single string is passed, wrap it in a list
        text_filters = [text_filters]
    
    if text_filters:
        # Convert all filters to lowercase once
        text_filters = [f.lower() for f in text_filters]
    # -----------------------------------------------------------------

    for _ in range(max_attempts):
        try:
            elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((locator_strategy, locator_value))
            )
            
            clicked_something = False
            for element in elements:
                if not element.is_displayed():
                    continue

                # --- MODIFIED: Check against list of filters ---
                if text_filters is None:
                    # No filter, just click
                    element_text = element.text
                    element.click()
                    print(f"  -> Clicked '{element_text}' (no filter)")
                    clicked_something = True
                    time.sleep(1)
                else:
                    # Check against all text filters
                    element_text = element.text
                    element_text_lower = element_text.lower()
                    for f in text_filters:
                        if f in element_text_lower:
                            element.click()
                            print(f"  -> Clicked '{element_text}' (matches '{f}')")
                            clicked_something = True
                            time.sleep(1)
                            break # Move to the next element
            # -----------------------------------------------
            
            if not clicked_something:
                # If we went through all elements and didn't click, we're done
                break

        except (TimeoutException, NoSuchElementException):
            break 
        except Exception as e:
            print(f"An unexpected error occurred during robust click: {e}")
            break

def click_ad_locations(driver, expected_activity):
    """
    Clicks on predefined coordinates, and if navigation occurs,
    attempts to return to the original app activity.
    
    FIXED: Replaced hard-coded coordinates with dynamic, screen-percentage-based
    coordinates to reliably click banner locations on different screen sizes.
    """
    print("\n  - Dynamically calculating ad locations...")
    try:
        window_size = driver.get_window_size()
        width = window_size.get('width', 1080) # Default to 1080p if not found
        height = window_size.get('height', 1920) # Default to 1080p if not found
        
        mid_x = width * 0.5
        
        # Define coordinates based on screen percentage
        ad_coordinates = [
            (mid_x, height * 0.15), # Top banner (15% from top)
            (mid_x, height * 0.95), # Bottom banner (95% from top) <-- Clicks bottom-middle
            (mid_x, height * 0.50), # Middle of the screen
        ]
        print(f"  - Screen size detected: {width}x{height}. Clicking relative locations.")
        
    except Exception as e:
        print(f"  - WARNING: Could not get window size. Defaulting to hard-coded coordinates. Error: {e}", file=sys.stderr)
        # Fallback to original hard-coded values if window size fails
        ad_coordinates = [
            (500, 250),  # Top banner
            (500, 1800), # Bottom banner
            (500, 1000), # Middle of the screen for interstitial ads
        ]

    print("\n  - Clicking on ad locations...")
    for x, y in ad_coordinates:
        try:
            # Taps require integers
            int_x = int(x)
            int_y = int(y)
            
            print(f"    - Tapping at coordinate: ({int_x}, {int_y})")
            driver.tap([(int_x, int_y)])
            time.sleep(5)  # Allow time for potential navigation

            current_activity = driver.current_activity
            if current_activity != expected_activity:
                print(f"    - Navigated away to '{current_activity}'. Attempting to return.")
                driver.back()
                time.sleep(2) # Wait for app to return

                # Verify we are back
                final_activity = driver.current_activity
                if final_activity == expected_activity:
                    print("    - Successfully returned to the app.")
                else:
                    print(f"    - Failed to return to the app. Current activity: '{final_activity}'")
            else:
                print("    - Did not navigate away from the app.")

        except Exception as e:
            print(f"    - Could not tap at ({int_x}, {int_y}): {e}", file=sys.stderr)

def ensure_app_in_foreground(driver, app_package):
    """
    Checks if the app is in the foreground and activates it if not.
    """
    try:
        # App state: 0=not installed, 1=not running, 2=running in background or suspended, 3=running in background, 4=running in foreground
        state = driver.query_app_state(app_package)
        if state < 4:
            print(f"  - App is not in the foreground (state: {state}). Activating...")
            driver.activate_app(app_package)
            time.sleep(3)  # Wait for app to come to the foreground
            print("  - App activated.")
    except Exception as e:
        print(f"  - Could not ensure app is in foreground: {e}", file=sys.stderr)

# --- NEW: Function to check for Play Store popup ---
def check_for_play_store_popup(driver):
    """
    Checks if a 'Get this app from Play' popup is visible.
    Returns True if found, False otherwise.
    """
    try:
        # Use a short timeout so this check is fast
        # Find any text view on the screen containing the text
        text_elements = WebDriverWait(driver, 2).until(
            EC.presence_of_all_elements_located((By.XPATH, "//*[contains(@text, 'Get this app from Play')]"))
        )
        if text_elements:
             # Check if any of the found elements are actually visible
             for el in text_elements:
                 if el.is_displayed():
                    print(f"  - POPUP DETECTED: 'Get this app from Play' is visible. Stopping test.", file=sys.stderr)
                    return True
    except (TimeoutException, NoSuchElementException):
        # No text elements found or timeout, which is normal
        return False
    except Exception as e:
        # Other potential errors
        print(f"  - Error during Play Store popup check: {e}", file=sys.stderr)
        return False
    return False
# --------------------------------------------------

def run_appium_tests(root_dir):
    """
    Walks root_dir at any depth to find directories containing 'signed-base.apk',
    locates matching split_config APKs from the original APK_Files_To_Analyze tree,
    verifies the signed APK and original base.apk share the same package name,
    then runs adb install-multiple and Appium tests.
    """
    print("\n--- Starting Automated Ad-Clicking Test ---")

    if not os.path.isdir(root_dir):
        print(f"Error: Instrumented APKs directory not found at '{root_dir}'.", file=sys.stderr)
        sys.exit(1)

    # Build a lookup of package_name -> original app dir from APK_Files_To_Analyze
    original_apk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "APK_Files_To_Analyze")
    original_index = {}
    if os.path.isdir(original_apk_dir):
        for orig_root, _, orig_files in os.walk(original_apk_dir):
            if "base.apk" in orig_files:
                pkg = os.path.basename(orig_root)
                original_index[pkg] = orig_root
    else:
        print(f"  Warning: original APK directory not found at '{original_apk_dir}'. Split config matching will be skipped.", file=sys.stderr)

    # Walk root_dir to find every directory containing a signed-base.apk
    for app_dir_path, _, files in os.walk(root_dir):
        if "signed-base.apk" not in files:
            continue

        app_dir_name = os.path.basename(app_dir_path)
        print(f"\n--- Processing Application: {app_dir_name} ---")

        signed_base_apk = os.path.join(app_dir_path, "signed-base.apk")

        # Extract package info from the signed APK
        apk_info = get_apk_info(signed_base_apk)
        if not apk_info:
            continue
        app_package, app_activity = apk_info

        # Verify signed APK package name matches original base.apk package name
        if app_dir_name in original_index:
            original_base_apk = os.path.join(original_index[app_dir_name], "base.apk")
            original_info = get_apk_info(original_base_apk)
            if original_info:
                original_package = original_info[0]
                if original_package != app_package:
                    print(f"  ⚠️ Package mismatch: signed APK has '{app_package}' but original base.apk has '{original_package}'. Skipping.", file=sys.stderr)
                    continue
                print(f"  ✓ Package names match: '{app_package}'")
            else:
                print(f"  ⚠️ Could not verify original base.apk for '{app_dir_name}'. Proceeding without verification.", file=sys.stderr)
        else:
            print(f"  ⚠️ No original APK directory found for '{app_dir_name}'. Skipping package verification.", file=sys.stderr)

        # Collect APKs to install: signed-base.apk + all signed split_config APKs from this dir
        apk_paths = [signed_base_apk]
        if app_dir_name in original_index:
            for fname in os.listdir(original_index[app_dir_name]):
                if fname.startswith("split_config") and fname.endswith(".apk"):
                    apk_paths.append(os.path.join(original_index[app_dir_name], fname))

        # Also pick up any signed split_config APKs already copied into the output dir
        for fname in files:
            fpath = os.path.join(app_dir_path, fname)
            if fname.startswith("signed_split_config") and fname.endswith(".apk") and fpath not in apk_paths:
                apk_paths.append(fpath)

        print(f"  - Installing {len(apk_paths)} APK(s) for {app_package}:")
        for p in apk_paths:
            print(f"      {p}")

        command = ["adb", "install-multiple", "-r"] + apk_paths
        try:
            run_command(command, check_output=True, error_message=f"Error installing APKs for {app_package}")
            print(f"    - Installation successful for {app_package}.")
        except Exception:
            print(f"  - Installation failed for {app_package}. Skipping Appium test.", file=sys.stderr)
            continue

        # 4. Appium Driver Setup and Interaction
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
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[@displayed='true']")))
            print("  - App is ready.")

            # --- NEW: Flag to skip this app's test ---
            skip_app = False
            # ------------------------------------------

            # --- MODIFIED: Handle permissions *immediately* after app start ---
            print("\n  - Handling initial permission dialogs...")
            # We will try to click any button that looks like an "accept" button
            permission_buttons = ["allow", "while using the app", "ok", "accept"]
            robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", text_filters=permission_buttons)
            # -----------------------------------------------------------------
            
            # --- MODIFIED: Check for Play Store popup ---
            if check_for_play_store_popup(driver):
                skip_app = True # Set flag to skip
            # ------------------------------------------

            if not skip_app:
                # Ensure app is in the foreground after handling dialogs
                ensure_app_in_foreground(driver, app_package)
                
                # Click on predefined ad coordinates
                click_ad_locations(driver, app_activity)

                # --- MODIFIED: Check for Play Store popup ---
                if check_for_play_store_popup(driver):
                    skip_app = True # Set flag to skip
                # ------------------------------------------

            if not skip_app:
                # Ensure app is in the foreground before swiping
                ensure_app_in_foreground(driver, app_package)
                
                # Swipe the screen to potentially trigger more ads
                print("\n  - Swiping the screen...")
                driver.swipe(500, 1600, 500, 400, 1000)
                time.sleep(2)
                
                # --- MODIFIED: Check for Play Store popup ---
                if check_for_play_store_popup(driver):
                    skip_app = True # Set flag to skip
                # ------------------------------------------
            
            if not skip_app:
                # Ensure app is in the foreground for the final check
                ensure_app_in_foreground(driver, app_package)
                # Final check for close buttons on any new ads
                robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", text_filters=["close"])

        except Exception as e:
            print(f"  - Error during Appium test for {app_package}: {e}", file=sys.stderr)
        finally:
            if driver:
                print("\n  - Test finished. Quitting driver.")
                driver.quit()

            # Uninstall the app
            print(f"  - Attempting to uninstall {app_package}...")
            try:
                run_command(["adb", "uninstall", app_package], check_output=True)
                print(f"  - Successfully uninstalled {app_package}.")
            except Exception as e:
                print(f"  - Failed to uninstall {app_package}: {e}", file=sys.stderr)

    print("\n--- Completed All Tests ---")

def stop_logcat_capture():
    """
    Stops the adb logcat process by killing the adb server.
    """
    print("--- Stopping logcat capture by killing the adb server ---")
    try:
        subprocess.run(['adb', 'kill-server'], check=True, capture_output=True, text=True)
        print("ADB server killed successfully. Logcat should now be stopped.")
    except FileNotFoundError:
        print("Error: 'adb' command not found. Ensure Android Debug Bridge is installed and in your system's PATH.")
    except subprocess.CalledProcessError as e:
        print(f"Error while trying to kill the adb server: {e.stderr}")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    # Specify the directory with injected APKs
    injected_apk_dir = "Soot_Output_Injector_APK_Files"
    # Specify the directory with original APKs to analyze
    original_apk_dir = "../APK_Files_To_Analyze"
    
    # You can uncomment any of the lines below to run the desired function
    
    cleanup_directories(injected_apk_dir)
    find_matching_apks(injected_apk_dir, original_apk_dir)
    process_apks(injected_apk_dir)
    start_logcat_capture()
    run_appium_tests(injected_apk_dir)
    stop_logcat_capture()


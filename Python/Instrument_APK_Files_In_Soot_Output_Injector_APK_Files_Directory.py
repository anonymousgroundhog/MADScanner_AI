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
    Iterates through subdirectories in source_dir, finds a matching directory
    in the search_dir tree, and copies files starting with 'split_config' 
    from the matched directory back to the source subdirectory.

    Args:
        source_dir (str): The directory containing the subdirectories to check.
        search_dir (str): The root directory to search within for matching names.
    """
    print(f"--- Searching for matching APKs and copying split_config files ---\n")

    # Check if the source and search directories exist
    if not os.path.isdir(source_dir):
        print(f"Error: The source directory '{source_dir}' does not exist.")
        return
    if not os.path.isdir(search_dir):
        print(f"Error: The search directory '{search_dir}' does not exist.")
        return

    # Iterate through the items in the source directory
    for item in os.listdir(source_dir):
        source_item_path = os.path.join(source_dir, item)
        
        # Check if the item is a directory
        if os.path.isdir(source_item_path):
            subdirectory_name = item
            print(f"Checking for: {subdirectory_name}")
            
            match_found = False
            # Walk through the entire directory tree of the search directory
            for root, dirnames, _ in os.walk(search_dir):
                # Check if our subdirectory name exists in the list of directories at this level
                if subdirectory_name in dirnames:
                    target_path = os.path.join(root, subdirectory_name)
                    print(f"  - Match found: {target_path}")
                    match_found = True

                    # Copy files starting with "split_config" from the target to the source
                    for filename in os.listdir(target_path):
                        if filename.startswith("split_config"):
                            source_file = os.path.join(target_path, filename)
                            destination_file = os.path.join(source_item_path, filename)
                            try:
                                shutil.copy(source_file, destination_file)
                                print(f"    - Copied '{filename}' to '{source_item_path}'")
                            except shutil.Error as e:
                                print(f"    - Error copying '{filename}': {e}")
                    
                    print() # Add a blank line for readability
                    break  # Exit the os.walk loop for this item as we found a match
            
            if not match_found:
                print(f"  - No match found within the subdirectories of {search_dir}\n")

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

def robust_click_on_elements(driver, locator_strategy, locator_value, text_filter=None, max_attempts=3):
    """Finds and clicks on elements robustly."""
    for _ in range(max_attempts):
        try:
            elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((locator_strategy, locator_value))
            )
            for element in elements:
                if element.is_displayed() and (text_filter is None or text_filter.lower() in element.text.lower()):
                    element.click()
                    print(f"  -> Clicked '{element.text}'")
                    time.sleep(1)
        except (TimeoutException, NoSuchElementException):
            break 
        except Exception as e:
            print(f"An unexpected error occurred during robust click: {e}")
            break

def click_ad_locations(driver, expected_activity):
    """
    Clicks on predefined coordinates, and if navigation occurs,
    attempts to return to the original app activity.
    """
    print("\n  - Clicking on predefined ad locations...")
    ad_coordinates = [
        (500, 250),  # Top banner
        (500, 1800), # Bottom banner
        (500, 1000), # Middle of the screen for interstitial ads
    ]

    for x, y in ad_coordinates:
        try:
            print(f"    - Tapping at coordinate: ({x}, {y})")
            driver.tap([(x, y)])
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
            print(f"    - Could not tap at ({x}, {y}): {e}", file=sys.stderr)

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

def run_appium_tests(root_dir):
    """
    Installs and runs Appium tests on all processed APKs in the root directory.
    """
    print("\n--- Starting Automated Ad-Clicking Test ---")

    if not os.path.isdir(root_dir):
        print(f"Error: Instrumented APKs directory not found at '{root_dir}'.", file=sys.stderr)
        sys.exit(1)

    # Iterate through each app-specific subdirectory
    for app_dir_name in os.listdir(root_dir):
        app_dir_path = os.path.join(root_dir, app_dir_name)
        
        if not os.path.isdir(app_dir_path):
            continue

        print(f"\n--- Processing Application: {app_dir_name} ---")

        # Find the base APK to extract info for Appium
        base_apk_path = os.path.join(app_dir_path, "signed-base.apk")
        if not os.path.exists(base_apk_path):
            print(f"  - 'signed-base.apk' not found in '{app_dir_name}'. Cannot determine app activity. Skipping.", file=sys.stderr)
            continue

        apk_info = get_apk_info(base_apk_path)
        if not apk_info:
            continue
        
        app_package, app_activity = apk_info

        # Install all 'signed*.apk' files from the subdirectory
        print(f"  - Attempting to install multiple APKs for {app_package}")
        apk_paths = glob.glob(os.path.join(app_dir_path, "signed*.apk"))

        if not apk_paths:
            print(f"  - No 'signed*.apk' files found for installation in {app_dir_path}.", file=sys.stderr)
            continue

        command = ["adb", "install-multiple"] + apk_paths
        try:
            run_command(command, check_output=True, error_message=f"Error installing APKs for {app_package}")
            print(f"    - Installation successful for {app_package}.")
        except Exception:
            # Error is printed by run_command
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

            # Ensure app is in the foreground before starting
            ensure_app_in_foreground(driver, app_package)
            # Click on predefined ad coordinates
            click_ad_locations(driver, app_activity)

            # Ensure app is in the foreground before handling permissions
            ensure_app_in_foreground(driver, app_package)
            # Handle common permission dialogs
            robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "allow")
            
            # Ensure app is in the foreground before swiping
            ensure_app_in_foreground(driver, app_package)
            # Swipe the screen to potentially trigger more ads
            print("\n  - Swiping the screen...")
            driver.swipe(500, 1600, 500, 400, 1000)
            time.sleep(2)
            
            # Ensure app is in the foreground for the final check
            ensure_app_in_foreground(driver, app_package)
            # Final check for close buttons on any new ads
            robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "close")

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
    
    # cleanup_directories(injected_apk_dir)
    # find_matching_apks(injected_apk_dir, original_apk_dir)
    # process_apks(injected_apk_dir)
    start_logcat_capture()
    run_appium_tests(injected_apk_dir)
    stop_logcat_capture()


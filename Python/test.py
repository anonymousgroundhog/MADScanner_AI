import sys
import time
import os
import subprocess
import re # Import regex module
import shutil # For high-level file operations like copy

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from ppadb.client import Client as AdbClient

# --- Helper Functions ---

def run_command(command_parts, check_output=False, cwd=None, error_message="Error executing command"):
    """
    Executes a shell command (as a list of parts).

    Args:
        command_parts (list[str]): The command and its arguments as a list.
        check_output (bool): If True, raises a CalledProcessError if the command
                             returns a non-zero exit code.
        cwd (str | None): The current working directory to run the command from.
                          If None, uses the default for subprocess.run.
        error_message (str): Custom message to print if an error occurs.

    Returns:
        tuple[str, str]: A tuple containing (stdout, stderr).

    Raises:
        subprocess.CalledProcessError: If check_output is True and the command fails.
        FileNotFoundError: If the executable is not found.
    """
    try:
        process = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            check=check_output,
            cwd=cwd
        )
        return process.stdout.strip(), process.stderr.strip()
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {' '.join(command_parts)}", file=sys.stderr)
        print(f"Stdout: {e.stdout.strip()}", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Error: Command '{command_parts[0]}' not found. "
              f"Ensure it's in your system's PATH. ({error_message})", file=sys.stderr)
        raise

def install_multiple_apks(apk_paths, package_name_for_logging):
    """
    Installs multiple APK files for a single app on the connected Android emulator/device
    using 'adb install-multiple'.

    Args:
        apk_paths (list[str]): A list of full paths to the APK files on the local filesystem.
        package_name_for_logging (str): The package name for logging purposes.

    Returns:
        bool: True if installation was successful, False otherwise.
    """
    if not apk_paths:
        print(f"  - No APKs provided for installation for {package_name_for_logging}.", file=sys.stderr)
        return False

    print(f"  - Attempting to install multiple APKs for {package_name_for_logging}:")
    for apk_path in apk_paths:
        print(f"    - {os.path.basename(apk_path)}")
    
    # Use -r for reinstall (in case it's already installed) and -t for test packages
    command = ["adb", "install-multiple", "-r", "-t"] + apk_paths
    
    try:
        stdout, stderr = run_command(command, check_output=True)
        print(f"    - Installation successful for {package_name_for_logging}.")
        # print(f"      ADB stdout: {stdout}") # Uncomment for verbose ADB output
        return True
    except Exception as e:
        print(f"    ❌ Error installing APKs for {package_name_for_logging}: {e}", file=sys.stderr)
        return False

def get_apk_info(apk_path):
    """
    Uses aapt to extract package name and launchable activity from an APK.

    Args:
        apk_path (str): The full path to the APK file.

    Returns:
        tuple[str, str] | None: A tuple (package_name, main_activity) if found,
                                 otherwise None.
    """
    print(f"  - Extracting package and activity from {os.path.basename(apk_path)} using aapt...")
    try:
        # Run 'aapt dump badging' command
        # Ensure 'aapt' is in your system's PATH
        stdout, stderr = run_command(["aapt", "dump", "badging", apk_path], check_output=True)

        package_name = None
        main_activity = None

        # Regex to find package name: package: name='com.example.app' ...
        package_match = re.search(r"package: name='([^']+)'", stdout)
        if package_match:
            package_name = package_match.group(1)

        # Regex to find launchable activity: launchable-activity: name='com.example.app.MainActivity' ...
        activity_match = re.search(r"launchable-activity: name='([^']+)'", stdout)
        if activity_match:
            main_activity = activity_match.group(1)

        if package_name and main_activity:
            print(f"    - Found Package: {package_name}, Activity: {main_activity}")
            return package_name, main_activity
        else:
            print(f"    ⚠️ Could not extract package or main activity from {os.path.basename(apk_path)}.", file=sys.stderr)
            print(f"      aapt output (partial): {stdout[:500]}...", file=sys.stderr) # Print first 500 chars of output
            return None
    except Exception as e:
        print(f"    ❌ Error running aapt or parsing its output for {os.path.basename(apk_path)}: {e}", file=sys.stderr)
        return None

def process_and_sign_apk(apk_input_path, output_dir, parent_dir, script_dir):
    """
    Zipaligns, signs, and copies an APK to the specified output directory.

    Args:
        apk_input_path (str): The full path to the APK file to be processed.
        output_dir (str): The directory where the signed APK should be placed.
        parent_dir (str): Path to the parent directory (for keystore location).
        script_dir (str): Path to the script's directory (for cleaning .idsig).

    Returns:
        str | None: The full path to the signed APK if successful, None otherwise.
    """
    apk_filename = os.path.basename(apk_input_path)
    signed_apk_filename = f"signed-{apk_filename}"
    # Temporarily place the signed APK in the output_dir
    temp_signed_apk_path = os.path.join(output_dir, signed_apk_filename) 
    
    print(f"      - Processing and signing: {apk_filename}")
    try:
        # 1. Zipalign
        print(f"        - Zipaligning '{apk_filename}'...")
        stdout, stderr = run_command(
            ["zipalign", "-fv", "4", apk_input_path, temp_signed_apk_path],
            check_output=True,
            cwd=script_dir, # zipalign runs from script_dir
            error_message=f"Error zipaligning '{apk_filename}'"
        )
        # print(f"          Zipalign stdout: {stdout}") # Uncomment for verbose output

        # 2. Sign
        print(f"        - Signing '{signed_apk_filename}'...")
        run_command(
            ["apksigner", "sign", "--ks", os.path.join(parent_dir, "my-release-key.keystore"), # Keystore is one directory up
             "--ks-pass", "pass:password", temp_signed_apk_path],
            check_output=True,
            cwd=script_dir, # apksigner runs from script_dir
            error_message=f"Error signing '{apk_filename}'"
        )
        
        # 3. Clean up signature files generated by apksigner in the CWD (script_dir)
        for idsig_file in [f for f in os.listdir(script_dir) if f.endswith(".idsig")]:
            os.remove(os.path.join(script_dir, idsig_file))
            # print(f"        - Removed {idsig_file} from script directory.")

        # The signed APK is already in the `output_dir` (temp_signed_apk_path)
        print(f"        - Successfully signed and placed '{signed_apk_filename}' in '{os.path.basename(output_dir)}'.")
        return temp_signed_apk_path # Return the path to the signed APK
    except Exception as e:
        print(f"      ❌ Failed to process and sign '{apk_filename}': {e}", file=sys.stderr)
        # Clean up the partially signed file if an error occurred
        if os.path.exists(temp_signed_apk_path):
            os.remove(temp_signed_apk_path)
        return None


# --- Appium-related Functions ---

def get_connected_device():
    """
    Connects to the ADB server and returns the name of the first connected device.
    Raises an error if no device is found.
    """
    try:
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()

        if not devices:
            raise RuntimeError("No ADB devices or emulators found. Please ensure one is running.")
        
        device_name = devices[0].serial
        print(f"Detected ADB device: {device_name}")
        return device_name

    except ConnectionRefusedError:
        raise RuntimeError("Could not connect to ADB server. Please start the server using 'adb start-server'.")
    except Exception as e:
        raise RuntimeError(f"An error occurred while detecting ADB device: {e}")

def robust_click_on_elements(driver, locator_strategy, locator_value, text_filter=None, max_attempts=5):
    """
    Finds and clicks on elements robustly, handling multiple pop-ups or dynamic changes.
    Returns True if an element was clicked, False otherwise.
    """
    did_click = False
    for attempt in range(max_attempts):
        try:
            wait = WebDriverWait(driver, 5)
            elements = wait.until(EC.presence_of_all_elements_located((locator_strategy, locator_value)))

            for element in elements:
                if element.is_displayed() and (text_filter is None or text_filter.lower() in element.text.lower()):
                    element.click()
                    print(f"  -> Clicked '{element.text}' ({element.class_name})")
                    did_click = True
                    time.sleep(1)
                    break
            
            if not did_click:
                break
        except (TimeoutException, NoSuchElementException):
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            break
    
    return did_click

# --- Main Function ---

def main():
    # --- Define Paths based on script's location ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.join(script_dir, "..")
    
    # Path to the directory containing instrumented/signed APKs (within Python directory)
    soot_output_injector_apk_files_dir = os.path.join(script_dir, "Soot_Output_Injector_APK_Files")
    
    # Path to the directory containing original APKs, including helper libs (one dir up)
    apk_files_to_analyze_dir = os.path.join(parent_dir, "APK_Files_To_Analyze")

    print("\n--- Starting Automated Ad-Clicking Test for All Instrumented APKs ---")

    try:
        device_name = get_connected_device()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if the instrumented APKs directory exists
    if not os.path.isdir(soot_output_injector_apk_files_dir):
        print(f"❌ Instrumented APKs directory not found: '{os.path.abspath(soot_output_injector_apk_files_dir)}'.", file=sys.stderr)
        print("Please ensure your APK processing script successfully generated signed APKs in this directory.", file=sys.stderr)
        sys.exit(1)

    processed_app_count = 0

    # Iterate through each subdirectory within Soot_Output_Injector_APK_Files
    for package_dir_name in os.listdir(soot_output_injector_apk_files_dir):
        package_injected_apk_dir = os.path.join(soot_output_injector_apk_files_dir, package_dir_name)
        
        # Ensure it's a directory
        if not os.path.isdir(package_injected_apk_dir):
            print(f"Skipping non-directory item in {os.path.basename(soot_output_injector_apk_files_dir)}: {package_dir_name}")
            continue

        # --- Locate the main instrumented APK for the current package ---
        main_instrumented_apk_path = os.path.join(package_injected_apk_dir, "signed-base.apk") 
        
        if not os.path.isfile(main_instrumented_apk_path):
            print(f"\n⚠️ 'signed-base.apk' not found in '{os.path.abspath(package_injected_apk_dir)}'. Skipping this package.", file=sys.stderr)
            continue

        processed_app_count += 1
        print(f"\n--- Processing Application: {package_dir_name} ({processed_app_count}) ---")

        # --- Automatically get package and activity from the main APK ---
        # This is where the actual package name and main activity are determined
        # from the APK file itself using 'aapt' tool.
        apk_info = get_apk_info(main_instrumented_apk_path)
        if apk_info is None:
            print(f"❌ Failed to get APK information (package and activity) from {os.path.basename(main_instrumented_apk_path)}. Skipping this package.", file=sys.stderr)
            continue
        
        # These are the values that will be used by Appium
        app_package, app_activity = apk_info 
        print(f"✅ Discovered App Package for Appium: {app_package}")
        print(f"✅ Discovered App Launch Activity for Appium: {app_activity}")

        # --- Collect all APKs for unified installation ---
        apks_to_install_for_this_app = []
        
        # 1. Add the main instrumented APK (already signed and located in package_injected_apk_dir)
        apks_to_install_for_this_app.append(main_instrumented_apk_path)
        print(f"\n  - Added main instrumented APK: {os.path.basename(main_instrumented_apk_path)}")

        # 2. Process and add helper APKs (from APK_Files_To_Analyze/<package_dir_name>/)
        # These are original helper/split APKs that need to be signed and moved
        package_original_apk_dir = os.path.join(apk_files_to_analyze_dir, package_dir_name) 
        
        if os.path.isdir(package_original_apk_dir):
            print(f"  - Checking for and processing helper APKs in: {os.path.abspath(package_original_apk_dir)}")
            for item in os.listdir(package_original_apk_dir):
                # Exclude 'base.apk' as it's the one that gets instrumented and handled separately
                if item.endswith(".apk") and item.lower() != "base.apk":
                    helper_apk_original_path = os.path.join(package_original_apk_dir, item)
                    
                    # Process (zipalign, sign) and copy the helper APK to the signed output directory
                    # The signed helper APK will be placed directly into package_injected_apk_dir
                    signed_helper_apk_path = process_and_sign_apk(
                        apk_input_path=helper_apk_original_path,
                        output_dir=package_injected_apk_dir, # Place signed helper in this package's signed output dir
                        parent_dir=parent_dir,
                        script_dir=script_dir
                    )
                    if signed_helper_apk_path:
                        apks_to_install_for_this_app.append(signed_helper_apk_path)
                        print(f"    - Added signed helper APK: {os.path.basename(signed_helper_apk_path)}")
                    else:
                        print(f"    ❌ Failed to process and sign helper APK: {os.path.basename(helper_apk_original_path)}. Skipping it.", file=sys.stderr)
            print(f"  - Finished processing helper APKs for {app_package}.")
        else:
            print(f"  - No directory found for '{package_dir_name}' in APK_Files_To_Analyze. No helper APKs to process.")

        # --- Perform unified installation using install-multiple ---
        print(f"\n  --- Starting Unified APK Installation for {app_package} ---")
        if not apks_to_install_for_this_app:
            print(f"  ❌ No APKs to install for {app_package}. This should not happen if main APK was found. Skipping Appium test.", file=sys.stderr)
            continue # Skip to the next application if no APKs to install

        if not install_multiple_apks(apks_to_install_for_this_app, app_package):
            print(f"❌ Unified APK installation failed for {app_package}. Skipping Appium test for this package.", file=sys.stderr)
            continue # Skip to the next application if installation fails
        
        print(f"  --- Unified APK Installation Complete for {app_package} ---\n")

        # --- Appium Driver Setup and Interaction ---
        driver = None # Initialize driver to None for proper cleanup
        try:
            options = UiAutomator2Options()
            options.platform_name = "Android"
            options.device_name = device_name
            options.app_package = app_package       # Automatically determined from APK
            options.app_activity = app_activity     # Automatically determined from APK
            options.no_reset = True
            options.auto_grant_permissions = True
            options.adb_exec_timeout = 30000
            
            print("  Connecting to Appium server...")
            driver = webdriver.Remote("http://127.0.0.1:4723/wd/hub", options=options)
            print("  Driver connected successfully. Waiting for app to load...")
            # Wait until any element is displayed, indicating the app has loaded
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[@displayed='true']")))
            print("  App is ready.")

            # --- Handle Permissions (if any) ---
            print("\n  Attempting to handle permissions...")
            if not robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "allow"):
                print("    -> No 'Allow' buttons found.")

            # --- Click on the Ad and Navigate Back ---
            print("\n  Attempting to click on ads...")
            try:
                # We explicitly wait for the ad button.
                ad_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ACCESSIBILITY_ID, "OPEN"))
                )
                print("    -> Found ad button with Accessibility ID 'OPEN'. Clicking...")
                ad_button.click()
                
                # The page will change here. Wait for the new activity (browser) to open.
                time.sleep(5) 
                
                print("    -> Navigating back to the app...")
                driver.back()
                time.sleep(2) # Give the app time to reappear
                
                print("    -> Successfully returned to the app.")
                
            except (TimeoutException, NoSuchElementException):
                print("    -> No 'OPEN' ad button found on the screen.")
                
            # --- Check for lingering close buttons ---
            print("\n  Checking for any remaining pop-ups or ads...")
            if not robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "close"):
                print("    -> No 'close' buttons found.")

            # --- Swipe Screen ---
            print("\n  Swiping the screen to test for dynamic ads...")
            # Adjust coordinates if needed for different screen sizes/orientations
            driver.swipe(150, 800, 250, 200, 1000)
            time.sleep(2)

            # --- Final Check ---
            print("\n  Final check for any remaining ads...")
            if not robust_click_on_elements(driver, By.CLASS_NAME, "android.widget.Button", "close"):
                print("    -> No ads found after swipe.")

        except Exception as e:
            print(f"❌ Error during Appium test for {app_package}: {e}", file=sys.stderr)
        finally:
            print("\n  Test finished for this app. Quitting driver.")
            if driver:
                driver.quit()

            # --- Uninstall the app from the device ---
            print(f"  Attempting to uninstall {app_package} from the device...")
            try:
                # Use 'adb uninstall' to remove the app by its package name
                stdout, stderr = run_command(
                    ["adb", "uninstall", app_package],
                    check_output=True, # Raise an error if uninstall fails
                    error_message=f"Error uninstalling {app_package}"
                )
                print(f"  ✅ Successfully uninstalled {app_package}.")
                # print(f"    ADB uninstall stdout: {stdout}") # Uncomment for verbose ADB output
            except Exception as e:
                print(f"  ❌ Failed to uninstall {app_package}: {e}", file=sys.stderr)
    
    if processed_app_count == 0:
        print("\n😔 No instrumented applications were found in 'Soot_Output_Injector_APK_Files' to test.")
        print("Please ensure your APK processing script successfully generated signed APKs in that directory.")
    else:
        print(f"\n--- Completed Automated Ad-Clicking Test for {processed_app_count} application(s). ---")
    


if __name__ == "__main__":
    main()


import os
import subprocess # Used for running shell commands
# Removed: import zipfile, import shutil (no longer needed for APK extraction)
# Removed: import re (no longer strictly needed for byte regex, but kept for general utility if future regex needed)

def find_admob_apps(root_directory):
    """
    Recursively scans through directories to find APK files
    that contain Google AdMob library calls by using 'aapt dump badging'.

    Args:
        root_directory (str): The path to the root directory
                              containing the app folders or APKs.

    Returns:
        list: A list of paths to APK files that likely use AdMob.
    """
    admob_apps = []
    
    # Check if aapt command is available
    try:
        # Use 'command -v aapt' or 'which aapt' to check for aapt's existence
        subprocess.run(['aapt', 'version'], check=True, capture_output=True, text=True)
        print("aapt command found. Proceeding with scan.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: 'aapt' command not found. Please ensure Android Build Tools are installed and 'aapt' is in your system's PATH.")
        print("You can typically find 'aapt' in your Android SDK directory under 'build-tools/<version>/'.")
        return [] # Exit if aapt is not found

    # Signatures to look for within aapt dump badging output (as text)
    admob_signatures_text = [
        "meta-data: name='com.google.android.gms.ads.APPLICATION_ID'",
        "uses-permission: name='com.google.android.gms.permission.AD_ID'"
        # Note: We don't look for DEX-specific signatures here as aapt focuses on Manifest
        # For deeper analysis of DEX files for AdMob calls, you would need tools like dexdump or apktool.
    ]

    print(f"Starting scan for AdMob integrations in APK files under: {root_directory}\n")

    for dirpath, dirnames, filenames in os.walk(root_directory):
        for filename in filenames:
            if filename.endswith('.apk'):
                apk_path = os.path.join(dirpath, filename)
                app_name = os.path.basename(apk_path)
                found_in_apk = False

                print(f"  Checking APK: {app_name}")

                try:
                    # Run 'aapt dump badging' command
                    # capture_output=True captures stdout and stderr
                    # text=True decodes output as text
                    result = subprocess.run(['aapt', 'dump', 'badging', apk_path], 
                                            check=True, # Raise an exception for non-zero exit codes
                                            capture_output=True, 
                                            text=True, 
                                            errors='ignore') # Ignore decoding errors
                    
                    output = result.stdout
                    # print(f"    aapt output for {app_name}:\n{output[:500]}...\n") # Uncomment for debugging

                    # Scan the output for AdMob signatures
                    for signature in admob_signatures_text:
                        if signature.lower() in output.lower():
                            print(f"      ✅ Found AdMob signature '{signature}' in aapt badging output.")
                            found_in_apk = True
                            break # Found signature, no need to check others in this APK
                
                except subprocess.CalledProcessError as e:
                    # This happens if aapt returns an error (e.g., malformed APK)
                    print(f"    ⚠️ Error running 'aapt dump badging' for {app_name}: {e}")
                    print(f"    Stderr: {e.stderr}")
                except FileNotFoundError:
                    # This should be caught by the initial check, but good to have a fallback
                    print("    ⚠️ 'aapt' command not found. Please ensure it's in your PATH.")
                except Exception as e:
                    print(f"    ⚠️ An unexpected error occurred while processing {app_name}: {e}")
                finally:
                    # No temporary directories to clean up with this method!
                    pass

                if found_in_apk:
                    admob_apps.append(apk_path)
                    print(f"  ✨ APK '{app_name}' likely uses AdMob. 🎉\n")
                else:
                    print(f"  ❌ No AdMob signatures found in '{app_name}'.\n")

    return admob_apps

if __name__ == "__main__":
    # IMPORTANT: Replace 'path/to/your/apps_directory' with the actual
    # root directory where your APK files are located.
    # For example:
    # apps_root = "/home/user/my_android_apks"
    # apps_root = "C:\\Users\\YourUser\\Downloads\\APKs"
    
    # The dummy APK creation logic from the previous version is removed
    # as creating valid APKs with specific manifest entries requires
    # more sophisticated tools than simple zipfile manipulation to
    # correctly embed binary XML.
    
    apps_root_directory = input("Please enter the root directory to scan for APK files (e.g., /path/to/your/apks): ")
    
    if not os.path.isdir(apps_root_directory):
        print(f"Error: The provided path '{apps_root_directory}' is not a valid directory.")
    else:
        found_admob_apps = find_admob_apps(apps_root_directory)

        if found_admob_apps:
            print("\n-------------------------------------------------")
            print("The following APK files likely use Google AdMob:")
            print("-------------------------------------------------")
            for apk_path in found_admob_apps:
                print(f"- {apk_path}")
        else:
            print("\nNo APK files with Google AdMob integrations were found in the specified directory. 😔")


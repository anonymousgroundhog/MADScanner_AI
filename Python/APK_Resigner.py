import os
import subprocess
import shutil

# --- Configuration ---
# This script should be located in the 'Python' folder.
# The paths are relative to the script's location.

# The path to the directory containing APKs to be analyzed.
APK_FILES_DIR = "../APK_Files_To_Analyze"
# The path to the output directory where signed APKs will be stored.
SOOT_OUTPUT_DIR = "../sootOutput"
# The path to your keystore file for signing the APKs.
KEYSTORE_PATH = "../my-release-key.keystore"
# The password for the keystore.
KEYSTORE_PASS = "password"  # Replace with your actual keystore password
# The password for the key within the keystore.
KEY_PASS = "password"       # Replace with your actual key password

# --- Main Script Logic ---
def process_and_sign_apks():
    """
    Copies APKs (excluding 'base.apk') from a source directory to a target
    directory, maintaining the subdirectory structure. It then signs the copied
    APKs and cleans up the generated .idsig files.
    """
    print("🚀 Starting APK processing and signing script.")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Running from: {script_dir}")

    # --- Step 0: Prerequisite Checks ---
    if not os.path.exists(APK_FILES_DIR):
        print(f"❌ Error: Source directory not found at '{APK_FILES_DIR}'")
        return

    if not os.path.exists(KEYSTORE_PATH):
        print(f"❌ Error: Keystore file not found at '{KEYSTORE_PATH}'")
        return

    # Ensure the main output directory exists.
    os.makedirs(SOOT_OUTPUT_DIR, exist_ok=True)

    # --- Step 1: Walk through source directory to find APKs ---
    print(f"\nScanning for APKs in '{APK_FILES_DIR}'...")
    found_apks = 0
    for root, dirs, files in os.walk(APK_FILES_DIR):
        for filename in files:
            # Process .apk files only and specifically exclude 'base.apk'.
            if filename.endswith(".apk") and filename != "base.apk":
                found_apks += 1
                source_apk_path = os.path.join(root, filename)
                print(f"\nProcessing: {source_apk_path}")

                # --- Step 2: Determine destination path and copy the file ---
                # This preserves the subdirectory structure inside sootOutput.
                relative_dir = os.path.relpath(root, APK_FILES_DIR)
                output_dir = os.path.join(SOOT_OUTPUT_DIR, relative_dir)
                os.makedirs(output_dir, exist_ok=True)

                dest_apk_path = os.path.join(output_dir, filename)
                print(f"  -> Copying to: {dest_apk_path}")
                shutil.copy2(source_apk_path, dest_apk_path)

                # --- Step 3: Sign the copied APK ---
                # The 'apksigner' tool will sign the file in-place.
                # Note: No key alias is specified in the command, as requested.
                # 'apksigner' will use the first key available in the keystore.
                print("  -> Signing APK...")
                sign_command = [
                    "apksigner", "sign",
                    "--ks", KEYSTORE_PATH,
                    "--ks-pass", f"pass:{KEYSTORE_PASS}",
                    "--key-pass", f"pass:{KEY_PASS}",
                    dest_apk_path
                ]

                try:
                    # Using capture_output=True to hide verbose command output unless there's an error.
                    result = subprocess.run(sign_command, check=True, capture_output=True, text=True)
                    print(f"  ✅ Successfully signed '{filename}'.")
                except FileNotFoundError:
                    print("  ❌ Error: 'apksigner' not found. Please ensure the Android SDK 'build-tools' directory is in your system's PATH.")
                    continue # Skip to the next file
                except subprocess.CalledProcessError as e:
                    print(f"  ❌ Error: Failed to sign '{filename}'.")
                    print(f"     Details: {e.stderr}")
                    continue # Skip to the next file

                # --- Step 4: Clean up the .idsig file ---
                idsig_file_path = dest_apk_path + ".idsig"
                if os.path.exists(idsig_file_path):
                    try:
                        os.remove(idsig_file_path)
                        print(f"  -> Removed signature file: {idsig_file_path}")
                    except OSError as e:
                        print(f"  ⚠️ Warning: Could not remove {idsig_file_path}. Error: {e}")

    if found_apks == 0:
        print("\nNo APK files (other than 'base.apk') were found to process.")

    print("\n🎉 Script finished.")

if __name__ == "__main__":
    process_and_sign_apks()
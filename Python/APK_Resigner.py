import os
import subprocess
import shutil

# --- Configuration ---
# IMPORTANT: Update these paths to match your system setup.
# The path to the directory containing APKs to be analyzed.
APK_FILES_DIR = "../APK_Files_To_Analyze"
# The path to the output directory where signed APKs will be stored.
SOOT_OUTPUT_DIR = "../sootOutput"
# The path to your keystore file for signing the APKs.
KEYSTORE_PATH = "../my-release-key.keystore"
# The alias for the key within the keystore.
KEY_ALIAS = "sean" # Replace with your actual key alias
# The password for the keystore.
KEYSTORE_PASS = "password" # Replace with your actual password
# The password for the key.
KEY_PASS = "password" # Replace with your actual password

# --- Main Script Logic ---
def resign_apks():
    """
    Finds and re-signs all APK files in a directory, except for 'base.apk'.
    The signed files are then moved to a corresponding subdirectory in sootOutput.
    """
    print(f"Starting the APK re-signing process in '{APK_FILES_DIR}'.")

    if not os.path.exists(APK_FILES_DIR):
        print(f"Error: The directory '{APK_FILES_DIR}' was not found.")
        return

    # Check for the keystore file.
    if not os.path.exists(KEYSTORE_PATH):
        print(f"Error: The keystore file '{KEYSTORE_PATH}' was not found.")
        return

    # Ensure the sootOutput directory exists.
    if not os.path.exists(SOOT_OUTPUT_DIR):
        os.makedirs(SOOT_OUTPUT_DIR)
        print(f"Created directory: {SOOT_OUTPUT_DIR}")

    # Walk through the APK_Files_To_Analyze directory.
    for root, dirs, files in os.walk(APK_FILES_DIR):
        for filename in files:
            # Only process .apk files and skip 'base.apk'.
            if filename.endswith(".apk") and filename != "base.apk":
                full_path = os.path.join(root, filename)
                print(f"Found APK to re-sign: {full_path}")

                # Define output path for the signed APK.
                # It will be placed in a subdirectory of sootOutput with the same name as the original APK's parent directory.
                relative_path = os.path.relpath(root, APK_FILES_DIR)
                output_dir = os.path.join(SOOT_OUTPUT_DIR, relative_path)
                
                # Create the output directory if it doesn't exist.
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                signed_apk_path = os.path.join(output_dir, filename)

                # Step 1: Align the APK
                # zipalign is a tool provided in the Android SDK
                # It's recommended to align the APK for best performance before signing.
                print("Aligning APK...")
                aligned_apk_path = full_path.replace(".apk", "_aligned.apk")
                align_command = [
                    "zipalign", "-v", "4", full_path, aligned_apk_path
                ]
                
                try:
                    subprocess.run(align_command, check=True, capture_output=True, text=True)
                    print(f"Successfully aligned '{filename}'.")
                except FileNotFoundError:
                    print("Error: 'zipalign' not found. Please ensure the Android SDK 'build-tools' are in your system PATH.")
                    continue
                except subprocess.CalledProcessError as e:
                    print(f"Failed to align '{filename}': {e.stderr}")
                    continue

                # Step 2: Sign the aligned APK using apksigner
                # apksigner is also part of the Android SDK
                print("Signing APK...")
                sign_command = [
                    "apksigner", "sign",
                    "--ks", KEYSTORE_PATH,
                    "--ks-pass", f"pass:{KEYSTORE_PASS}",
                    "--key-pass", f"pass:{KEY_PASS}",
                    "--out", signed_apk_path,
                    aligned_apk_path
                ]

                try:
                    subprocess.run(sign_command, check=True, capture_output=True, text=True)
                    print(f"Successfully signed and moved '{filename}' to '{signed_apk_path}'.")
                except FileNotFoundError:
                    print("Error: 'apksigner' not found. Please ensure the Android SDK 'build-tools' are in your system PATH.")
                    continue
                except subprocess.CalledProcessError as e:
                    print(f"Failed to sign '{filename}': {e.stderr}")
                    continue

                # Clean up the intermediate aligned APK file
                os.remove(aligned_apk_path)
                print(f"Cleaned up temporary aligned file: {aligned_apk_path}")

    print("Re-signing process complete.")

if __name__ == "__main__":
    resign_apks()

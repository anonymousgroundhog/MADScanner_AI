import os
import sys

def rename_apks_to_base():
    """
    Scans subdirectories in '../APK_Files_To_Analyze' and renames a single APK 
    (not starting with 'split_') in each to 'base.apk'.
    """
    try:
        # The script is expected to be in a 'Python' directory.
        # This gets the absolute path to the directory containing this script.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # This constructs the path to the target directory, which is one level up
        # and then into 'APK_Files_To_Analyze'.
        target_base_dir = os.path.join(script_dir, '..', 'APK_Files_To_Analyze')

        # Best practice: get the absolute path for clear error messages.
        target_base_dir = os.path.abspath(target_base_dir)

        # Verify that the target directory actually exists.
        if not os.path.isdir(target_base_dir):
            print(f"Error: Directory not found at '{target_base_dir}'", file=sys.stderr)
            print("Please ensure the script is in a 'Python' directory and 'APK_Files_To_Analyze' is in the parent directory.", file=sys.stderr)
            sys.exit(1)

        print(f"Scanning subdirectories in '{target_base_dir}'...")

        # Iterate through each item (file or folder) in the base directory.
        for dir_name in os.listdir(target_base_dir):
            sub_dir_path = os.path.join(target_base_dir, dir_name)

            # We only want to process subdirectories.
            if os.path.isdir(sub_dir_path):
                print(f"\n--- Checking directory: {dir_name} ---")
                
                # Find all files that end with .apk but do not start with 'split_'.
                files_to_rename = [
                    f for f in os.listdir(sub_dir_path)
                    if f.endswith('.apk') and not f.startswith('split_')
                ]

                # Case 1: No matching APK files were found.
                if len(files_to_rename) == 0:
                    print("  - No target APK file found to rename. Skipping.")
                    continue
                
                # Case 2: More than one potential APK was found. Skip to avoid ambiguity.
                if len(files_to_rename) > 1:
                    print(f"  - WARNING: Found multiple potential APKs: {files_to_rename}. Skipping this directory to avoid errors.")
                    continue

                # Case 3: Exactly one matching APK was found.
                apk_to_rename = files_to_rename[0]
                original_path = os.path.join(sub_dir_path, apk_to_rename)
                new_path = os.path.join(sub_dir_path, 'base.apk')

                # If the file is already named correctly, do nothing.
                if original_path == new_path:
                    print("  - File is already named 'base.apk'. No action needed.")
                    continue

                # Perform the rename operation.
                try:
                    os.rename(original_path, new_path)
                    print(f"  - Success: Renamed '{apk_to_rename}' to 'base.apk'.")
                except OSError as e:
                    print(f"  - ERROR: Could not rename '{apk_to_rename}'. Reason: {e}", file=sys.stderr)

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

if __name__ == "__main__":
    rename_apks_to_base()
import os
import shutil, logging

# --- Configuration ---
# The path to the directory containing APKs to be cleaned up.
SOOT_OUTPUT_DIR = "../sootOutput"

# --- Main Script Logic ---
def cleanup_soot_output():
    """
    Checks all immediate subdirectories of SOOT_OUTPUT_DIR. If a subdirectory
    does not contain a file named "signed-base.apk", the entire subdirectory
    is removed.
    """
    print(f"Starting cleanup process in '{SOOT_OUTPUT_DIR}'.")

    # Check if the root directory exists.
    if not os.path.isdir(SOOT_OUTPUT_DIR):
        print(f"Error: The directory '{SOOT_OUTPUTD_IR}' was not found.")
        return

    # Get a list of immediate subdirectories to avoid errors while iterating.
    try:
        subdirectories = [d for d in os.listdir(SOOT_OUTPUT_DIR) if os.path.isdir(os.path.join(SOOT_OUTPUT_DIR, d))]
    except OSError as e:
        print(f"Error reading directory {SOOT_OUTPUT_DIR}: {e}")
        return
        
    if not subdirectories:
        print("No subdirectories found to process.")
        print("\nCleanup process complete.")
        return

    print(f"Found {len(subdirectories)} subdirectories to check.")
    
    # Process each subdirectory found.
    for dirname in subdirectories:
        dir_path = os.path.join(SOOT_OUTPUT_DIR, dirname)
        apk_path = os.path.join(dir_path, "signed-base.apk")

        print(f"\nChecking directory: {dir_path}")
        
        # Check if the required 'signed-base.apk' file exists within the subdirectory.
        if not os.path.isfile(apk_path):
            print(f" -> 'signed-base.apk' NOT found. Removing directory.")
            try:
                shutil.rmtree(dir_path)
                print(f" -> Successfully removed {dir_path}")
            except OSError as e:
                print(f" -> Error removing directory {dir_path}: {e}")
        else:
            print(f" -> 'signed-base.apk' found. Directory will be kept.")

    print("\nCleanup process complete.")

def remove_base_apk():
    """
    Recursively searches for 'base.apk' within the directory specified by
    SOOT_OUTPUT_DIR and removes any instances found.
    """
    if not os.path.isdir(SOOT_OUTPUT_DIR):
        logging.warning(f"Directory '{SOOT_OUTPUT_DIR}' not found. Nothing to remove.")
        return

    found_and_removed = False
    try:
        # os.walk traverses the directory tree top-down, searching for the file.
        for root, dirs, files in os.walk(SOOT_OUTPUT_DIR):
            if 'base.apk' in files:
                file_path = os.path.join(root, 'base.apk')
                logging.info(f"Found 'base.apk' at: {file_path}")
                try:
                    os.remove(file_path)
                    logging.info(f"Successfully removed {file_path}")
                    found_and_removed = True
                    # Continue searching in case there are multiple 'base.apk' files in other subdirectories
                except OSError as e:
                    logging.error(f"Error removing file {file_path}: {e}")

        if not found_and_removed:
            logging.warning(f"'base.apk' not found anywhere within {SOOT_OUTPUT_DIR}.")

    except Exception as e:
        logging.error(f"An unexpected error occurred during search: {e}")

if __name__ == "__main__":
    cleanup_soot_output()
    remove_base_apk()
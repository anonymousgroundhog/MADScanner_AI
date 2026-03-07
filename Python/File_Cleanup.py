import os
import shutil
import logging

# --- Configuration ---
# The path to the directory containing APKs to be cleaned up.
SOOT_OUTPUT_DIR = "../sootOutput"

# --- Main Script Logic ---
def cleanup_soot_output():
    """
    Recursively checks all subdirectories of SOOT_OUTPUT_DIR. If a subdirectory
    appears to be a failed APK output (contains .apk files but not 'base.apk' or
    'signed-base.apk' and no further subdirectories), it is removed.
    """
    print(f"Starting cleanup process in '{SOOT_OUTPUT_DIR}'.")

    # Check if the root directory exists.
    if not os.path.isdir(SOOT_OUTPUT_DIR):
        print(f"Error: The directory '{SOOT_OUTPUT_DIR}' was not found.")
        return

    # Using os.walk to traverse the entire directory tree.
    # topdown=False causes the walk to happen from the "bottom up", which is safer
    # for deleting directories as we go.
    for root, dirs, files in os.walk(SOOT_OUTPUT_DIR, topdown=False):
        # Skip the top-level directory itself from being evaluated for deletion.
        if root == SOOT_OUTPUT_DIR:
            continue

        # Check if the directory should be kept because it contains the final APK.
        if 'base.apk' in files or 'signed-base.apk' in files:
            print(f"\nChecking directory: {root}")
            print(f" -> Found 'base.apk' or 'signed-base.apk'. Directory will be kept.")
            continue

        # A directory is considered a "failed output" if it contains some .apk files,
        # but does not contain any further subdirectories to process.
        is_failed_output = not dirs and any(f.endswith('.apk') for f in files)

        if is_failed_output:
            print(f"\nChecking directory: {root}")
            print(f" -> Neither 'base.apk' nor 'signed-base.apk' found. Removing directory.")
            try:
                shutil.rmtree(root)
                print(f" -> Successfully removed {root}")
            except OSError as e:
                print(f" -> Error removing directory {root}: {e}")

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
                    
                    found_and_removed = True
                    # Continue searching in case there are multiple 'base.apk' files in other subdirectories
                except OSError as e:
                    logging.error(f"Error removing file {file_path}: {e}")

        if not found_and_removed:
            os.remove(file_path)
            logging.info(f"Successfully removed {file_path}")
            logging.warning(f"'base.apk' not found anywhere within {SOOT_OUTPUT_DIR}.")

    except Exception as e:
        logging.error(f"An unexpected error occurred during search: {e}")


if __name__ == "__main__":
    # Configure logging for the remove_base_apk function
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    cleanup_soot_output()
    remove_base_apk()
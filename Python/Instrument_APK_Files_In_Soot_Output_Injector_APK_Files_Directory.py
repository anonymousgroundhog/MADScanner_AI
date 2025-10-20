import os

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

if __name__ == "__main__":
    # Specify the target directory
    target_directory = "Soot_Output_Injector_APK_Files"
    cleanup_directories(target_directory)

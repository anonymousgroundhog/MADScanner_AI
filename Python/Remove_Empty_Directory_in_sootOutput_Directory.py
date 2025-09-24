import shutil, os

def remove_empty_dirs(path):
    """
    Recursively walks through a directory and removes any empty subdirectories.

    Args:
        path (str): The root path to start the traversal from.
    """
    if not os.path.isdir(path):
        print(f"Error: The path '{path}' does not exist or is not a directory.")
        return

    print(f"Starting to clean up empty directories in: {path}")
    
    # Walk the directory tree from the bottom up.
    # This is crucial because a directory can only be empty after its
    # subdirectories have been removed.
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        # Check if the current directory is empty
        try:
            # os.rmdir() will only remove a directory if it's empty.
            os.rmdir(dirpath)
            print(f"Removed empty directory: {dirpath}")
        except OSError as e:
            # This exception is raised if the directory is not empty.
            # We can safely ignore it and continue.
            pass

if __name__ == "__main__":
    # Define the directory to clean up.
    # Change this to your desired directory if it's not "sootOutput".
    target_dir = "../sootOutput"

    # Call the function to remove empty directories.
    remove_empty_dirs(target_dir)

    print("Cleanup complete.")

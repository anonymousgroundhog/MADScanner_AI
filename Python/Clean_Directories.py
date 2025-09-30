import os
import shutil

def clear_directory(directory_path):
    """
    Removes all files and subdirectories within a given directory.

    Args:
        directory_path (str): The absolute or relative path to the directory to clear.
    """
    if not os.path.isdir(directory_path):
        print(f"Directory not found: {directory_path}")
        return

    print(f"Clearing contents of: {directory_path}")
    # List all the files and folders in the directory
    for item_name in os.listdir(directory_path):
        item_path = os.path.join(directory_path, item_name)
        try:
            # If it's a file or a symlink, delete it
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
                print(f"  - Deleted file: {item_path}")
            # If it's a directory, delete it and all its contents
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"  - Deleted folder: {item_path}")
        except Exception as e:
            print(f"Failed to delete {item_path}. Reason: {e}")
    print(f"Finished clearing {directory_path}\n")

def main():
    """
    Main function to define and clear the target directories.
    """
    # Get the directory where this script is located (e.g., .../Python)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Go up one level to the project's root directory
    project_root = os.path.dirname(script_dir)
    
    # Define the paths to the directories you want to clear
    soot_output_path = os.path.join(project_root, 'sootOutput')
    apk_files_path = os.path.join(project_root, 'APK_Files_To_Analyze')
    
    # Clear the directories
    clear_directory(soot_output_path)
    clear_directory(apk_files_path)
    
    print("Script finished.")

if __name__ == "__main__":
    main()

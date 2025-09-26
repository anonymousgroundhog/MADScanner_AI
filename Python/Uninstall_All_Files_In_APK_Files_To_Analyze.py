import os
import shutil
import sys

def clear_directory_contents():
    """
    Finds the 'APK_Files_To_Analyze' directory and deletes all contents
    after receiving user confirmation.
    """
    print("--- 🧹 APK File Cleaner Script ---")

    # This path assumes the script is run from the 'Python' folder
    # and 'APK_Files_To_Analyze' is in the parent directory.
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        target_dir = os.path.join(project_root, "APK_Files_To_Analyze")
    except Exception as e:
        print(f"❌ Error determining file paths: {e}", file=sys.stderr)
        return

    print(f"Target directory: {target_dir}")

    # Check if the target directory exists
    if not os.path.isdir(target_dir):
        print(f"✅ Directory not found. Nothing to clean.")
        return

    # --- SAFETY WARNING AND CONFIRMATION ---
    print("\n⚠️ WARNING: This will permanently delete all files and folders inside:")
    print(f"   '{target_dir}'")
    
    # Ask for user confirmation
    # The .strip() removes accidental whitespace, and .lower() makes the check case-insensitive
    confirm = input("Are you sure you want to proceed? (y/n): ").strip().lower()

    if confirm == 'y':
        print("\nDeleting contents...")
        try:
            # Delete the entire directory tree
            shutil.rmtree(target_dir)
            
            # Recreate the directory as an empty one
            os.makedirs(target_dir)
            
            print("✅ Successfully cleared all contents.")
        except OSError as e:
            print(f"❌ Error during deletion: {e}", file=sys.stderr)
            print("Please check file permissions or if any files are in use.", file=sys.stderr)
    else:
        print("\nOperation cancelled by user.")

if __name__ == "__main__":
    clear_directory_contents()
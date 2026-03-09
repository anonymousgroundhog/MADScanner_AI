import subprocess
import os
import sys
import shutil # For high-level file operations like rmtree
import argparse

def run_command(command_parts, check_output=False, cwd=None, error_message="Error executing command"):
    """
    Executes a shell command (as a list of parts).

    Args:
        command_parts (list[str]): The command and its arguments as a list.
        check_output (bool): If True, raises a CalledProcessError if the command
                             returns a non-zero exit code.
        cwd (str | None): The current working directory to run the command from.
                          If None, uses the default for subprocess.run.
        error_message (str): Custom message to print if an error occurs.

    Returns:
        tuple[str, str]: A tuple containing (stdout, stderr).

    Raises:
        subprocess.CalledProcessError: If check_output is True and the command fails.
        FileNotFoundError: If the executable is not found.
    """
    try:
        process = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            check=check_output,
            cwd=cwd
        )
        return process.stdout.strip(), process.stderr.strip()
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {' '.join(command_parts)}", file=sys.stderr)
        print(f"Stdout: {e.stdout.strip()}", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Error: Command '{command_parts[0]}' not found. "
              f"Ensure it's in your system's PATH. ({error_message})", file=sys.stderr)
        raise

def main():
    """
    Main function to orchestrate the LogInjector process for all APK files.
    """
    parser = argparse.ArgumentParser(description="Inject logging into APK files using Soot.")
    parser.add_argument(
        "--apk-dir",
        default=None,
        help="Path to the directory containing APKs to analyze. "
             "Defaults to '../APK_Files_To_Analyze' relative to this script.",
    )
    args = parser.parse_args()

    # Define the script's directory (where this Python file resides, e.g., 'your_project/Python/')
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the parent directory (one level up from the script, e.g., 'your_project/')
    parent_dir = os.path.join(script_dir, "..")

    # Use the user-supplied path if provided, otherwise fall back to the default.
    if args.apk_dir:
        apk_files_base_dir = os.path.abspath(args.apk_dir)
    else:
        apk_files_base_dir = os.path.join(parent_dir, "APK_Files_To_Analyze")
    
    # Define the final output directory for injected and signed APKs.
    # This remains within the script's directory.
    final_output_dir = os.path.join(script_dir, "Soot_Output_Injector_APK_Files")

    # Define the global intermediate Soot output directory.
    # This is the base for app-specific soot output subdirectories.
    soot_global_output_base_dir = os.path.join(parent_dir, "sootOutput")

    print("--- Starting APK LogInjector Automation ---")
    print(f"Looking for APKs in: {os.path.abspath(apk_files_base_dir)}")

    # 1. Initial compilation and setup
    print("\n📦 Running initial compilation and setup (this cleans intermediate and final output directories)...")
    try:
        # Remove previous sootOutput (global) and final output directories to ensure a clean slate
        if os.path.exists(soot_global_output_base_dir):
            print(f"  - Removing existing '{os.path.basename(soot_global_output_base_dir)}' directory...")
            shutil.rmtree(soot_global_output_base_dir)
        if os.path.exists(final_output_dir):
            print(f"  - Removing existing '{os.path.basename(final_output_dir)}' directory...")
            shutil.rmtree(final_output_dir)

        # Create the global soot output directory
        os.makedirs(soot_global_output_base_dir, exist_ok=True)
        print(f"  - Created global soot output directory: {os.path.abspath(soot_global_output_base_dir)}")

        # Compile the LogInjector Java code
        # Jar_Libs and Java/LogInjector.java are relative to parent_dir
        print("  - Compiling Java/LogInjector.java...")
        run_command(
            ["javac", 
             "-cp", os.path.join(parent_dir, "Jar_Libs", "*"), # Jar_Libs is one directory up
             "-d", parent_dir, # Place compiled .class file one directory up
             os.path.join(parent_dir, "Java", "LogInjector.java")], # Java source is one directory up
            check_output=True,
            cwd=parent_dir, # Set CWD for javac to the parent directory
            error_message="Error compiling LogInjector.java"
        )
        print("  - LogInjector compiled successfully.")

        # Create the final output directory for injected and signed APKs
        os.makedirs(final_output_dir, exist_ok=True)
        print(f"  - Created final output directory: {os.path.abspath(final_output_dir)}")
        
    except Exception as e:
        print(f"❌ Initial setup or compilation failed: {e}", file=sys.stderr)
        sys.exit(1) # Exit if setup fails, as subsequent steps depend on it.

    # 2. Iterate over app subdirectories and run LogInjector for each APK
    processed_apks_count = 0
    if not os.path.isdir(apk_files_base_dir):
        print(f"⚠️ Directory '{os.path.abspath(apk_files_base_dir)}' not found. "
              "Please ensure it exists and contains APK subfolders.", file=sys.stderr)
        sys.exit(1) # Exit if the base APK directory doesn't exist.

    # Collect all APKs to process: (apk_path, label)
    # - For bare .apk files directly in apk_files_base_dir, label = filename stem
    # - For every base.apk found at any depth under apk_files_base_dir, label = its immediate parent directory name
    apk_targets = []

    # First check for bare .apk files directly in apk_files_base_dir
    for entry in os.listdir(apk_files_base_dir):
        entry_path = os.path.join(apk_files_base_dir, entry)
        if os.path.isfile(entry_path) and entry.lower().endswith(".apk"):
            apk_targets.append((entry_path, os.path.splitext(entry)[0]))

    # Walk the entire tree to find every base.apk regardless of depth.
    # The label is the immediate parent directory (the app package directory).
    for root, _dirs, files in os.walk(apk_files_base_dir):
        if "base.apk" in files:
            apk_path = os.path.join(root, "base.apk")
            label = os.path.basename(root)
            apk_targets.append((apk_path, label))

    file_number = 0
    number_of_files = len(apk_targets)
    for base_apk_input_path, _dir_name in apk_targets:
        # --- Start processing the APK ---
        file_number += 1
        print(f"\n--- Processing '{_dir_name}' ( {file_number} out of {number_of_files}) ---")
        print(f"Found input APK: {base_apk_input_path}")

        try:
            # Define the *final desired* app-specific output directory for the injected APK
            # This is `sootOutput/<app_name>/`
            _specific_soot_output_dest_dir = os.path.join(soot_global_output_base_dir, _dir_name)
            os.makedirs(_specific_soot_output_dest_dir, exist_ok=True)
            print(f"  - Created app-specific final output directory in Soot: {os.path.abspath(_specific_soot_output_dest_dir)}")

            # Define the temporary directory where LogInjector will place its output.
            loginjector_temp_output_dir = os.path.join(soot_global_output_base_dir, "sootOutput")
            print(f"  - Running LogInjector on '{os.path.basename(base_apk_input_path)}'...")
            run_command(
                ["java", "-Xmx25g",
                 "-cp", f"{parent_dir}:" + os.path.join(parent_dir, "Jar_Libs", "*"),
                 "LogInjector",
                 os.path.join(parent_dir, "Android", "platforms"),
                 base_apk_input_path],
                check_output=True,
                cwd=soot_global_output_base_dir,
                error_message=f"Error running LogInjector on {os.path.basename(base_apk_input_path)}"
            )

            loginjector_output_apk_path = os.path.join(loginjector_temp_output_dir, "base.apk")

            if not os.path.isfile(loginjector_output_apk_path):
                if os.path.isdir(loginjector_temp_output_dir):
                    found_apks_in_temp = [f for f in os.listdir(loginjector_temp_output_dir) if f.endswith(".apk")]
                else:
                    found_apks_in_temp = []
                if found_apks_in_temp:
                    loginjector_output_apk_path = os.path.join(loginjector_temp_output_dir, found_apks_in_temp[0])
                    print(f"  - Expected 'base.apk' not found, using '{os.path.basename(loginjector_output_apk_path)}' instead.")
                else:
                    print(f"⚠️ LogInjector did not produce any APK in '{loginjector_temp_output_dir}'. Skipping move for this app.", file=sys.stderr)
                    continue

            final_moved_apk_path = os.path.join(_specific_soot_output_dest_dir, os.path.basename(loginjector_output_apk_path))

            print(f"  - Moving injected APK from '{os.path.basename(loginjector_temp_output_dir)}/' to '{os.path.basename(_specific_soot_output_dest_dir)}/'...")
            shutil.move(loginjector_output_apk_path, final_moved_apk_path)

            if os.path.exists(loginjector_temp_output_dir):
                print(f"  - Removing temporary LogInjector output directory: '{os.path.basename(loginjector_temp_output_dir)}'.")
                shutil.rmtree(loginjector_temp_output_dir)

            processed_apks_count += 1
            print(f"  - LogInjector finished and APK moved for '{os.path.basename(base_apk_input_path)}'")

        except Exception as e:
            print(f"❌ Error during injection or file move for '{os.path.basename(base_apk_input_path)}': {e}", file=sys.stderr)

    if processed_apks_count == 0:
        print("\n😔 No APK files were found and processed in the specified directory structure.")
        print(f"Ensure '{os.path.abspath(apk_files_base_dir)}' contains either:")
        print(f"  - APK files directly (e.g. app.apk)")
        print(f"  - Subdirectories containing a 'base.apk' at any depth")
        sys.exit(0)

    # 3. Run post-processing on the accumulated sootOutput
    print("\n🎉 All LogInjector runs complete. Starting post-processing (zipalign, apksigner, copy)...")
    if not os.path.isdir(soot_global_output_base_dir) or not os.listdir(soot_global_output_base_dir):
        print("  - Global 'sootOutput' directory is empty or not found. No files to post-process.", file=sys.stderr)
    else:
        for _soot_output_sub_dir_name in os.listdir(soot_global_output_base_dir):
            _soot_output_sub_dir_path = os.path.join(soot_global_output_base_dir, _soot_output_sub_dir_name)

            if not os.path.isdir(_soot_output_sub_dir_path):
                print(f"Skipping non-directory item in {os.path.basename(soot_global_output_base_dir)}: {_soot_output_sub_dir_name}")
                continue

            print(f"  - Processing outputs for app: {_soot_output_sub_dir_name}")

            for item_name in os.listdir(_soot_output_sub_dir_path):
                item_full_path = os.path.join(_soot_output_sub_dir_path, item_name)

                if not os.path.isfile(item_full_path) or item_name == "Info.md":
                    print(f"  - Skipping non-APK file or Info.md in {_soot_output_sub_dir_name}: {item_name}")
                    continue

                try:
                    filename = item_name
                    print(f"    - Processing output file: {filename}")

                    signed_apk_path = os.path.join(_soot_output_sub_dir_path, f"signed-{filename}")

                    print(f"      - Zipaligning '{filename}'...")
                    stdout, stderr = run_command(
                        ["zipalign", "-fv", "4", item_full_path, signed_apk_path],
                        check_output=True,
                        cwd=script_dir,
                        error_message=f"Error zipaligning '{filename}'"
                    )
                    print(stdout)

                    print(f"      - Signing 'signed-{filename}'...")
                    run_command(
                        ["apksigner", "sign", "--ks", os.path.join(parent_dir, "my-release-key.keystore"),
                         "--ks-pass", "pass:password", signed_apk_path],
                        check_output=True,
                        cwd=script_dir,
                        error_message=f"Error signing '{filename}'"
                    )

                    for idsig_file in [f for f in os.listdir(script_dir) if f.endswith(".idsig")]:
                        os.remove(os.path.join(script_dir, idsig_file))
                        print(f"    - Removed {idsig_file} from script directory.")

                    final_app_output_dir = os.path.join(final_output_dir, _soot_output_sub_dir_name)
                    os.makedirs(final_app_output_dir, exist_ok=True)

                    print(f"    - Copying 'signed-{filename}' to {os.path.basename(final_output_dir)}/{_soot_output_sub_dir_name}/...")
                    shutil.copy(signed_apk_path, final_app_output_dir)
                    print(f"    - Successfully processed and copied signed '{filename}'")

                except Exception as e:
                    print(f"❌ Post-processing failed for '{item_name}' in '{_soot_output_sub_dir_name}': {e}", file=sys.stderr)

        for idsig_file in [f for f in os.listdir(script_dir) if f.endswith(".idsig")]:
            os.remove(os.path.join(script_dir, idsig_file))
            print(f"  - Cleaned up lingering {idsig_file} from script directory after all post-processing.")

    print(f"\n--- Script Finished ---")
    print(f"Summary: Successfully processed {processed_apks_count} APK file(s) and applied post-processing.")
    print(f"Injected and signed APKs are in '{os.path.abspath(final_output_dir)}' directory.")

if __name__ == "__main__":
    main()
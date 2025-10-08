import subprocess
import os
import sys
import shutil # For high-level file operations like rmtree

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
    # Define the script's directory (where this Python file resides, e.g., 'your_project/Python/')
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the parent directory (one level up from the script, e.g., 'your_project/')
    parent_dir = os.path.join(script_dir, "..")

    # Define the base directory for APK files: one level up from the script's location.
    # This correctly points to 'your_project/APK_Files_To_Analyze/'
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

    file_number=0
    number_of_files=len(os.listdir(apk_files_base_dir))
    for _dir_name in os.listdir(apk_files_base_dir):
        _full_path = os.path.join(apk_files_base_dir, _dir_name)
        
        if os.path.isdir(_full_path):
            # --- MODIFICATION START ---
            # Find any .apk file in the subdirectory
            apk_files_in_dir = [f for f in os.listdir(_full_path) if f.endswith(".apk")]

            if not apk_files_in_dir:
                print(f"⚠️ No APK file found in '{_full_path}'. Skipping.", file=sys.stderr)
                continue  # Skip to the next directory
            
            if len(apk_files_in_dir) > 1:
                print(f"⚠️ Multiple APKs found in '{_full_path}': {apk_files_in_dir}. Skipping to avoid ambiguity.", file=sys.stderr)
                continue # Skip to the next directory
            
            # Exactly one APK found, proceed with renaming and processing
            original_apk_name = apk_files_in_dir[0]
            original_apk_path = os.path.join(_full_path, original_apk_name)
            base_apk_input_path = os.path.join(_full_path, "base.apk")

            # Rename the found APK to 'base.apk' for processing, if it's not already named that.
            if original_apk_path != base_apk_input_path:
                print(f"  - Renaming '{original_apk_name}' to 'base.apk' in '{_dir_name}' for processing.")
                try:
                    shutil.move(original_apk_path, base_apk_input_path)
                except Exception as e:
                    print(f"❌ Failed to rename '{original_apk_name}': {e}. Skipping directory '{_dir_name}'.", file=sys.stderr)
                    continue
            # --- MODIFICATION END ---
            
            # --- Start processing the 'base.apk' ---
            file_number=file_number+1
            print(f"\n--- Processing '{_dir_name}' ( {file_number} out of {number_of_files}) ---")
            print(f"Found input APK: {base_apk_input_path}")

            # Define the *final desired* app-specific output directory for the injected APK
            # This is `sootOutput/<app_name>/`
            _specific_soot_output_dest_dir = os.path.join(soot_global_output_base_dir, _dir_name)
            os.makedirs(_specific_soot_output_dest_dir, exist_ok=True)
            print(f"  - Created app-specific final output directory in Soot: {os.path.abspath(_specific_soot_output_dest_dir)}")
            
            # Define the temporary directory where LogInjector will place its output.
            # Assuming LogInjector creates its 'sootOutput' subdirectory relative to its CWD.
            # So, if CWD is `soot_global_output_base_dir`, LogInjector will output to `soot_global_output_base_dir/sootOutput/`.
            loginjector_temp_output_dir = os.path.join(soot_global_output_base_dir, "sootOutput")

            try:
                print(f"  - Running LogInjector on '{os.path.basename(base_apk_input_path)}'...")
                # Set CWD for the Java command to `soot_global_output_base_dir`.
                # LogInjector's output (e.g., base.apk) will then appear in `soot_global_output_base_dir/sootOutput/`.
                run_command(
                    ["java", "-Xmx25g", 
                     "-cp", f"{parent_dir}:" + os.path.join(parent_dir, "Jar_Libs", "*"), # .class and Jar_Libs are one directory up
                     "LogInjector", 
                     os.path.join(parent_dir, "Android", "platforms"), # Android/platforms is one directory up
                     base_apk_input_path], 
                    check_output=True,
                    cwd=soot_global_output_base_dir, # CWD is now soot_global_output_base_dir
                    error_message=f"Error running LogInjector on {os.path.basename(base_apk_input_path)}"
                )
                
                # After LogInjector runs, its output is in `loginjector_temp_output_dir`.
                # We need to find the specific APK file (assuming "base.apk" by name).
                loginjector_output_apk_path = os.path.join(loginjector_temp_output_dir, "base.apk")
                
                # Check if the expected output APK exists. If not, try to find any APK.
                if not os.path.isfile(loginjector_output_apk_path):
                    found_apks_in_temp = [f for f in os.listdir(loginjector_temp_output_dir) if f.endswith(".apk")]
                    if found_apks_in_temp:
                        loginjector_output_apk_path = os.path.join(loginjector_temp_output_dir, found_apks_in_temp[0])
                        print(f"  - Expected 'base.apk' not found, using '{os.path.basename(loginjector_output_apk_path)}' instead.")
                    else:
                        print(f"⚠️ LogInjector did not produce any APK in '{loginjector_temp_output_dir}'. Skipping move for this app.", file=sys.stderr)
                        continue # Skip to next app

                # Define the final destination path for the moved APK.
                # This will be `sootOutput/<app_name>/base.apk`
                final_moved_apk_path = os.path.join(_specific_soot_output_dest_dir, os.path.basename(loginjector_output_apk_path))
                
                # Move the processed APK from the nested temporary location to the desired app-specific folder
                print(f"  - Moving injected APK from '{os.path.basename(loginjector_temp_output_dir)}/' to '{os.path.basename(_specific_soot_output_dest_dir)}/'...")
                shutil.move(loginjector_output_apk_path, final_moved_apk_path)
                
                # Clean up the temporary LogInjector output directory.
                # This removes the `sootOutput/` directory that LogInjector created within `soot_global_output_base_dir`.
                if os.path.exists(loginjector_temp_output_dir):
                    print(f"  - Removing temporary LogInjector output directory: '{os.path.basename(loginjector_temp_output_dir)}'.")
                    shutil.rmtree(loginjector_temp_output_dir)
                    
                processed_apks_count += 1
                print(f"  - LogInjector finished and APK moved for '{os.path.basename(base_apk_input_path)}'")

            except Exception as e:
                print(f"❌ Error during injection or file move for '{os.path.basename(base_apk_input_path)}': {e}", file=sys.stderr)
        else:
            print(f"Skipping non-directory item in {os.path.basename(apk_files_base_dir)}: {_full_path}")

    if processed_apks_count == 0:
        print("\n😔 No APK files were found and processed in the specified directory structure.")
        print(f"Ensure '{os.path.abspath(apk_files_base_dir)}' contains subdirectories, each with a single '.apk' file.")
        sys.exit(0)

    # 3. Run post-processing on the accumulated sootOutput
    print("\n🎉 All LogInjector runs complete. Starting post-processing (zipalign, apksigner, copy)...")
    try:
        # Check if the global soot output directory exists and is not empty
        if not os.path.isdir(soot_global_output_base_dir) or not os.listdir(soot_global_output_base_dir):
            print("  - Global 'sootOutput' directory is empty or not found. No files to post-process.", file=sys.stderr)
        else:
            # Iterate through each app subdirectory within the global sootOutput folder
            for _soot_output_sub_dir_name in os.listdir(soot_global_output_base_dir):
                _soot_output_sub_dir_path = os.path.join(soot_global_output_base_dir, _soot_output_sub_dir_name)
                
                if os.path.isdir(_soot_output_sub_dir_path):
                    print(f"  - Processing outputs for app: {_soot_output_sub_dir_name}")
                    
                    # Iterate through the files *within* this app's soot output subdirectory
                    for item_name in os.listdir(_soot_output_sub_dir_path):
                        item_full_path = os.path.join(_soot_output_sub_dir_path, item_name)
                        
                        if os.path.isfile(item_full_path) and item_name != "Info.md":
                            filename = item_name # This will likely be "base.apk" now
                            print(f"    - Processing output file: {filename}")
                            
                            signed_apk_path = os.path.join(_soot_output_sub_dir_path, f"signed-{filename}") 
                            
                            # Zipalign the APK
                            print(f"      - Zipaligning '{filename}'...")
                            stdout, stderr = run_command(
                                ["zipalign", "-fv", "4", item_full_path, signed_apk_path],
                                check_output=True,
                                cwd=script_dir, # zipalign runs from script_dir
                                error_message=f"Error zipaligning '{filename}'"
                            )
                            print(stdout)
                            
                            # Sign the APK
                            print(f"      - Signing 'signed-{filename}'...")
                            run_command(
                                ["apksigner", "sign", "--ks", os.path.join(parent_dir, "my-release-key.keystore"), # Keystore is one directory up
                                 "--ks-pass", "pass:password", signed_apk_path],
                                check_output=True,
                                cwd=script_dir, # apksigner runs from script_dir
                                error_message=f"Error signing '{filename}'"
                            )
                            
                            # Remove signature files generated by apksigner.
                            # These are typically created in the CWD of the `apksigner` command.
                            for idsig_file in [f for f in os.listdir(script_dir) if f.endswith(".idsig")]:
                                os.remove(os.path.join(script_dir, idsig_file))
                                print(f"    - Removed {idsig_file} from script directory.")
                            
                            # Copy the final signed APK to the dedicated final output directory,
                            # maintaining the app-specific subdirectory structure.
                            final_app_output_dir = os.path.join(final_output_dir, _soot_output_sub_dir_name)
                            os.makedirs(final_app_output_dir, exist_ok=True) # Ensure app sub-dir exists in final output
                            
                            print(f"    - Copying 'signed-{filename}' to {os.path.basename(final_output_dir)}/{_soot_output_sub_dir_name}/...")
                            shutil.copy(signed_apk_path, final_app_output_dir)
                            print(f"    - Successfully processed and copied signed '{filename}'")
                        else:
                            print(f"  - Skipping non-APK file or Info.md in {_soot_output_sub_dir_name}: {item_name}")
                else:
                    print(f"Skipping non-directory item in {os.path.basename(soot_global_output_base_dir)}: {_soot_output_sub_dir_name}")

            # Final cleanup of any lingering .idsig files from the main script directory after all post-processing.
            for idsig_file in [f for f in os.listdir(script_dir) if f.endswith(".idsig")]:
                os.remove(os.path.join(script_dir, idsig_file))
                print(f"  - Cleaned up lingering {idsig_file} from script directory after all post-processing.")

        print(f"\n--- Script Finished ---")
        print(f"Summary: Successfully processed {processed_apks_count} APK file(s) and applied post-processing.")
        print(f"Injected and signed APKs are in '{os.path.abspath(final_output_dir)}' directory.")
    except Exception as e:
        print(f"❌ Post-processing failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

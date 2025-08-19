import os
import subprocess
import re # Import regex for parsing aapt output
import hashlib # Import hashlib for SHA256 calculation
from google_play_scraper import app, exceptions # Import app function and exceptions from the scraper

def get_apk_info(directory_path, output_filepath):
    """
    Recursively walks through the specified directory, finds APK files,
    extracts their package name using 'aapt dump badging', fetches the
    app name from the Google Play Store, calculates the SHA256 hash,
    and writes the information to a specified output file.

    Args:
        directory_path (str): The path to the directory to scan.
        output_filepath (str): The path to the file where output will be saved.
    """
    print(f"Scanning directory: {directory_path}\n")

    found_apks = False
    with open(output_filepath, 'w', encoding='utf-8') as outfile:
        outfile.write(f"--- APK Information Report ---\n")
        outfile.write(f"Scanning directory: {directory_path}\n\n")

        for root, _, files in os.walk(directory_path):
            for file in files:
                if file.endswith(".apk"):
                    apk_filepath = os.path.join(root, file)
                    package_name = 'N/A'
                    app_name = 'N/A' # Initialize app_name for cases where Play Store lookup fails
                    sha256_hash = 'N/A' # Initialize SHA256 hash

                    try:
                        # --- Step 1: Calculate SHA256 hash of the APK file ---
                        hasher = hashlib.sha256()
                        with open(apk_filepath, 'rb') as f:
                            while chunk := f.read(8192): # Read in chunks to handle large files
                                hasher.update(chunk)
                        sha256_hash = hasher.hexdigest()

                        # --- Step 2: Get package name using aapt dump badging ---
                        command = ["aapt", "dump", "badging", apk_filepath]
                        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
                        output = result.stdout

                        # Extract package name using regex
                        package_match = re.search(r"package: name='([^']+)'", output)
                        if package_match:
                            package_name = package_match.group(1)

                        # --- Step 3: Fetch app name from Google Play Store using package name ---
                        if package_name != 'N/A':
                            try:
                                # Fetch app details from Google Play Store
                                play_store_info = app(package_name, lang='en', country='us')
                                app_name = play_store_info.get('title', 'Not found on Play Store')
                            except exceptions.NotFoundError:
                                app_name = "Not found on Play Store (Package not found)"
                            except exceptions.UnhandledResponseError as e:
                                app_name = f"Play Store Error: {e}"
                            except Exception as e:
                                app_name = f"Play Store Lookup Failed: {e}"

                        # Write to file
                        outfile.write(f"File: {apk_filepath}\n")
                        outfile.write(f"  App Name (Play Store): {app_name}\n")
                        outfile.write(f"  Package Name: {package_name}\n")
                        outfile.write(f"  SHA256 Hash: {sha256_hash}\n")
                        outfile.write("-" * 50 + "\n") # Separator for readability
                        found_apks = True

                    except FileNotFoundError:
                        error_msg = f"Error: 'aapt' command not found. Please ensure Android SDK Build-Tools are installed and 'aapt' is in your system's PATH.\nSkipping: {apk_filepath}\n"
                        outfile.write(error_msg)
                        outfile.write("-" * 50 + "\n")
                        print(error_msg) # Still print to console for immediate feedback
                    except subprocess.CalledProcessError as e:
                        error_msg = f"Error running 'aapt' on {apk_filepath}: {e}\nstderr: {e.stderr}\n"
                        outfile.write(error_msg)
                        outfile.write("-" * 50 + "\n")
                        print(error_msg) # Still print to console for immediate feedback
                    except Exception as e:
                        error_msg = f"Error processing {apk_filepath} or parsing aapt output: {e}\n"
                        outfile.write(error_msg)
                        outfile.write("-" * 50 + "\n")
                        print(error_msg) # Still print to console for immediate feedback
        
        if not found_apks:
            outfile.write("No APK files found in the specified directory or its subfolders.\n")
            print("No APK files found in the specified directory or its subfolders.")

    print(f"\nReport successfully saved to: {output_filepath}")


if __name__ == "__main__":
    target_directory = input("Enter the directory path to scan for APKs: ")
    output_filename = input("Enter the desired output filename (e.g., apk_report.txt): ")

    if os.path.isdir(target_directory):
        get_apk_info(target_directory, output_filename)
    else:
        print(f"Error: The directory '{target_directory}' does not exist or is not a valid directory.")


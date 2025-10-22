import os
import re
import glob
import sys

# --- Configuration ---
# The directory where your logcat files are stored
LOG_DIR = "logcat_logs"

# The specific keyword to filter for within debug lines
KEYWORD_FILTER = "SootInjection"

# The keyword to strip everything before (this keyword will be included)
STRIP_BEFORE_KEYWORD = "Entering method:"

# Keyword for Info logs
INFO_KEYWORD = "Received an install/uninstall event for package"

# --- Specific GMS Ads keyword to also filter for in output ---
GMS_ADS_KEYWORD = "com.google.android.gms.ads"
# -----------------------------------------------------------------

# --- FSM methods to also filter for ---
# Based on the provided FSM diagram
FSM_METHODS = (
    "onAdLoaded(",
    "initialize(",
    "build(",
    "attachInfo(",
    "onDestroy(",
    "onResume(",
    "onPause(",
    "onAdImpression(",
)

# --- Combine FSM methods with MainActivity for output filtering ---
# MODIFIED: Added "onCreate("
OUTPUT_METHODS = FSM_METHODS + ("MainActivity", "onCreate(",)
# ----------------------------------------

# Prefixes to ignore when identifying "app" packages
STANDARD_PACKAGE_PREFIXES = (
    "android.",
    "androidx.",
    "com.android.",
    "com.google.",
    "com.facebook.",
    "java.",
    "javax.",
    "dalvik.",
    "libcore.",
    "org.apache.",
    "junit.",
    "kotlin",
    "kotlinx.",
    "org.json.",
    "org.slf4j",
    "okio",
    "okhttp3",
)

# Enable color highlighting (disabled on Windows by default)
ENABLE_COLOR = not (os.name == 'nt')
# ---------------------

# --- ANSI Color Constants ---
GREEN = '\033[92m' if ENABLE_COLOR else ''
YELLOW = '\033[93m' if ENABLE_COLOR else ''
ENDC = '\033[0m' if ENABLE_COLOR else ''
# ----------------------------

# Define regex patterns for log levels.
# This looks for " D/" or " I/" (like in 'time' format)
# or " D " or " I " (like in 'threadtime' format).
DEBUG_PATTERN = re.compile(r'\sD[/\s]')
INFO_PATTERN = re.compile(r'\sI[/\s]')

# Regex to extract class name from method signature like "<com.example.App: void main()>"
CLASS_NAME_PATTERN = re.compile(r'<([^:]+):')

def get_log_file_choice():
    """
    Finds log files in the LOG_DIR and prompts the user to choose one.
    Returns the full path to the chosen file and its base name.
    """
    print(f"Scanning for log files in '{LOG_DIR}'...")
    
    # Find both .txt and .log files
    txt_files = glob.glob(os.path.join(LOG_DIR, "*.txt"))
    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
    
    all_log_files = txt_files + log_files
    
    if not all_log_files:
        print(f"\n--- ERROR ---")
        print(f"No .txt or .log files found in the '{LOG_DIR}' directory.")
        print("Please add your log files to that directory and try again.")
        sys.exit() # Exit the script

    print("\nAvailable log files:")
    # Display files with their base name only for clarity
    file_basenames = [os.path.basename(f) for f in all_log_files]
    for i, filename in enumerate(file_basenames):
        print(f"  {i + 1}: {filename}")

    # Loop until we get a valid choice
    choice = -1
    while True:
        try:
            raw_choice = input(f"\nPlease enter the number of the file you want to process (1-{len(all_log_files)}): ")
            choice = int(raw_choice)
            if 1 <= choice <= len(all_log_files):
                # Valid choice, break the loop
                break
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(all_log_files)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")
            
    # Get the chosen file's base name and full path
    chosen_basename = file_basenames[choice - 1]
    chosen_full_path = all_log_files[choice - 1]
    
    return chosen_full_path, chosen_basename

def extract_package_name(package_string):
    """
    Takes a string (package name or class name) and filters it.
    Returns (package_name, base_package_name) or (None, None) if filtered.
    """
    package_name = package_string
    
    # Check if it's a full class name and extract the package
    parts = package_string.split('.')
    if len(parts) > 1:
        # Check if the last part looks like a class name (starts with capital)
        # This is a heuristic and might not always be true, but helps distinguish
        if parts[-1][0].isupper(): 
            package_name = '.'.join(parts[:-1])
        else:
            package_name = package_string

    # --- Filter Logic ---
    # Check if the package is NOT a standard one
    if not any(package_name.startswith(prefix) for prefix in STANDARD_PACKAGE_PREFIXES):
        # --- Base Package Logic ---
        # Get the first 2 parts of the package name
        base_parts = package_name.split('.')[:2]
        base_package = '.'.join(base_parts)
        
        return package_name, base_package
        
    return None, None

def find_packages_and_stats(input_path):
    """
    Pass 1: Reads the log file to find all packages and stats without printing.
    Returns sets of found packages and line counts.
    """
    found_packages = set()
    found_base_packages = set()
    debug_lines_found = 0
    total_lines = 0

    with open(input_path, 'r', encoding='utf-8') as in_file:
        for i, line in enumerate(in_file):
            total_lines = i + 1
            
            # --- Source 1: Debug "MainActivity" lines ---
            # Check if our regex pattern matches AND all keywords are in the line
            if (DEBUG_PATTERN.search(line) and 
                KEYWORD_FILTER in line and 
                STRIP_BEFORE_KEYWORD in line and
                "MainActivity" in line):
                
                debug_lines_found += 1 # Count it
                
                try:
                    start_index = line.index(STRIP_BEFORE_KEYWORD)
                    processed_line = line[start_index:]
                    
                    # Now, try to extract the class name from the processed line
                    match = CLASS_NAME_PATTERN.search(processed_line)
                    if match:
                        full_class_name = match.group(1)
                        # Filter and extract package names
                        pkg, base_pkg = extract_package_name(full_class_name)
                        if pkg and base_pkg:
                            found_packages.add(pkg)
                            found_base_packages.add(base_pkg)
                                
                except ValueError:
                    pass # Should not happen due to 'in' checks
            
            # --- Source 2: Info "Install/Uninstall" lines ---
            elif (INFO_PATTERN.search(line) and INFO_KEYWORD in line):
                try:
                    # Find the package name after the keyword
                    start_index = line.index(INFO_KEYWORD) + len(INFO_KEYWORD)
                    # The package name is usually the next word, strip whitespace
                    package_from_info = line[start_index:].strip().split()[0]
                    
                    # Filter and extract package names
                    pkg, base_pkg = extract_package_name(package_from_info)
                    if pkg and base_pkg:
                        found_packages.add(pkg)
                        found_base_packages.add(base_pkg)
                        
                except Exception:
                    pass # Ignore if parsing this line fails
                    
    return found_packages, found_base_packages, total_lines, debug_lines_found

def print_highlighted_logs(input_path, input_basename, found_base_packages):
    """
    Pass 2: Reads the file again, printing matching debug lines and highlighting
    any base packages found in Pass 1. Also prints first occurrence of full package.
    
    MODIFIED: New logic. Prints debug lines that also contain:
              ((one of found_base_packages) AND ("MainActivity" OR "onCreate(" OR one of FSM_METHODS))
              OR
              (("com.google.android.gms.ads" AND one of FSM_METHODS))
    """
    print(f"\n--- Found Debug Lines from {input_basename} (matching '{KEYWORD_FILTER}' AND ((App Pkg AND (FSM Method OR 'MainActivity' OR 'onCreate')) OR (GMS Ads AND FSM Method))) ---")
    
    lines_printed = 0
    seen_full_packages = set() # <-- Track first occurrences
    seen_main_activity_for_pkg = set() # <-- NEW: Track first MainActivity occurrence per package

    # Combine all methods we want to check for apps
    APP_METHODS_TO_CHECK = FSM_METHODS + ("MainActivity", "onCreate(",)

    with open(input_path, 'r', encoding='utf-8') as in_file:
        for line in in_file:
            # We only print the Debug lines, not the Info lines
            # Check for base requirements first
            if (DEBUG_PATTERN.search(line) and 
                KEYWORD_FILTER in line and 
                STRIP_BEFORE_KEYWORD in line):
                
                # --- NEW FILTERING LOGIC ---
                
                # Condition 1: App-related logs
                has_app_pkg = any(pkg in line for pkg in found_base_packages)
                has_app_method = any(method in line for method in APP_METHODS_TO_CHECK)
                condition_1 = (has_app_pkg and has_app_method)
                
                # Condition 2: GMS Ads-related logs
                has_gms_ads = GMS_ADS_KEYWORD in line
                has_fsm_method = any(method in line for method in FSM_METHODS)
                condition_2 = (has_gms_ads and has_fsm_method)
                
                # Line must meet base requirements AND (Condition 1 OR Condition 2)
                if not (condition_1 or condition_2):
                    continue # Skip this line, it matches neither condition
                # --- End of new logic ---
                
                try:
                    start_index = line.index(STRIP_BEFORE_KEYWORD)
                    # Get the substring from that index to the end
                    processed_line = line[start_index:]
                    
                    # --- Check for first occurrence ---
                    current_full_pkg = None
                    current_base_pkg = None
                    
                    match = CLASS_NAME_PATTERN.search(processed_line)
                    if match:
                        full_class_name = match.group(1)
                        # Use the same extraction/filter logic
                        pkg, base_pkg = extract_package_name(full_class_name)
                        # Check if it's one of the packages we care about
                        if pkg and base_pkg in found_base_packages:
                            current_full_pkg = pkg
                            current_base_pkg = base_pkg
                    
                    # --- NEW LOGIC: Check for MainActivity first occurrence ---
                    is_main_activity_line = "MainActivity" in line
                    
                    if condition_1 and is_main_activity_line and current_base_pkg:
                        # This is an app-related log line for MainActivity
                        if current_base_pkg in seen_main_activity_for_pkg:
                            # We've already seen MainActivity for this package. Skip this line.
                            continue
                        else:
                            # First time seeing MainActivity for this package.
                            seen_main_activity_for_pkg.add(current_base_pkg)
                    # --- End of new logic ---

                    if current_full_pkg and current_full_pkg not in seen_full_packages:
                        print(f"\n  {YELLOW}>>> First occurrence of package: {current_full_pkg}{ENDC}")
                        seen_full_packages.add(current_full_pkg)
                    # --- End of check ---
                    
                    # This is the line to print, now we highlight it
                    highlighted_line = processed_line
                    
                    # --- Highlight base package ---
                    if current_base_pkg:
                        # Replace all occurrences of the base package with the highlighted version
                        highlighted_line = highlighted_line.replace(
                            current_base_pkg, 
                            f"{GREEN}{current_base_pkg}{ENDC}"
                        )
                    
                    # Highlight "MainActivity" (Yellow)
                    if "MainActivity" in highlighted_line:
                        highlighted_line = highlighted_line.replace(
                            "MainActivity",
                            f"{YELLOW}MainActivity{ENDC}"
                        )
                    
                    # Print the (potentially) highlighted line
                    # 'end=""' prevents adding an extra newline
                    print(highlighted_line, end='')
                    lines_printed += 1
                        
                except ValueError:
                    # This case is handled by the 'in' check, but good to have
                    pass
        
        # Add a newline if we printed lines, for cleaner separation
        if lines_printed > 0:
            print() # Ensures the "End" header is on a new line
            
    print(f"\n--- End of Debug Lines ---")

def extract_debug_logs():
    """
    Orchestrates the log extraction:
    1. Gets user file choice.
    2. Pass 1: Finds all packages and stats.
    3. Pass 2: Prints highlighted logs.
    4. Prints final summary reports.
    """
    
    # Get the user's file choice
    try:
        input_path, input_basename = get_log_file_choice()
    except SystemExit:
        # This happens if no files were found. get_log_file_choice handled the message.
        return 

    print(f"\nStarting log extraction...")
    print(f"  Input file: {input_path}")
    # MODIFIED: Updated summary text to reflect new logic
    print(f"  Filtering for: Debug lines containing '{KEYWORD_FILTER}' AND ((App Pkg AND (FSM Method OR 'MainActivity' OR 'onCreate')) OR ('{GMS_ADS_KEYWORD}' AND FSM Method))")
    print(f"  Filtering for: Info lines containing '{INFO_KEYWORD}'")
    print(f"  Stripping before: '{STRIP_BEFORE_KEYWORD}'")
    print(f"  Ignoring standard packages (android.*, java.*, etc.)")
    if ENABLE_COLOR:
        print(f"  {GREEN}Highlighting enabled.{ENDC}")


    try:
        # --- Pass 1: Find all packages and stats ---
        print("  Pass 1: Analyzing packages...")
        found_packages, found_base_packages, total_lines, debug_lines_found = find_packages_and_stats(input_path)
        
        # --- Pass 2: Print highlighted lines ---
        print("  Pass 2: Printing highlighted logs...")
        print_highlighted_logs(input_path, input_basename, found_base_packages)

        # --- Print Summaries ---
        print(f"\nExtraction complete.")
        print(f"  Processed {total_lines} total lines.")
        print(f"  Found {debug_lines_found} matching debug lines (containing 'MainActivity' for package discovery).")
        
        # --- Section: Print Full Packages ---
        if found_packages:
            print(f"\n--- Identified App Packages (from Debug 'MainActivity' & Info logs) ---")
            # Sort the list for clean, repeatable output
            for pkg in sorted(list(found_packages)):
                print(f"  {pkg}")
            print(f"--- End of Packages ---")
        else:
            print(f"\n--- No non-standard app packages identified. ---")
        # ----------------------------------------

        # --- New Section: Print Base Packages ---
        if found_base_packages:
            print(f"\n--- Identified Base Packages (from Debug 'MainActivity' & Info logs) ---")
            # Sort the list for clean, repeatable output
            for pkg in sorted(list(found_base_packages)):
                # Print the summary list highlighted as well
                print(f"  {GREEN}{pkg}{ENDC}")
            print(f"--- End of Base Packages ---")
        else:
            # This is unlikely if the other list was populated, but good to have
            print(f"\n--- No non-standard base app packages identified. ---")
        # ----------------------------------------

    except FileNotFoundError:
        # This check is now less likely but good to keep
        print(f"\n--- ERROR ---")
        print(f"File not found at: {input_path}")
    except Exception as e:
        print(f"\n--- ERROR ---")
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Create the log directory if it doesn't exist, just in case
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        print(f"Created directory: {LOG_DIR}")
        
    if not ENABLE_COLOR:
        print("(Note: Color highlighting is disabled on this OS, ANSI escape codes may not be supported.)")
        
    extract_debug_logs()


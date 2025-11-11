import os
import re
import glob
import sys
from collections import defaultdict
import json
import shutil

# --- Check for Graphviz ---
try:
    import graphviz
except ImportError:
    print(f"\n--- ERROR: Missing Dependency ---")
    print(f"This script requires the 'graphviz' Python library.")
    print(f"Please install it by running: pip install graphviz")
    print(f"\nIMPORTANT: You must ALSO install the Graphviz system executable.")
    print(f"  - Windows: Download installer from https://graphviz.org/download/")
    print(f"  - macOS (Homebrew): brew install graphviz")
    print(f"  - Linux (Ubuntu/Debian): sudo apt-get install graphviz")
    print(f"---------------------------------")
    sys.exit()
# --------------------------------

# --- Configuration ---
LOG_DIR = "logcat_logs"
APK_ANALYSIS_DIR = "../APK_Files_To_Analyze" 
KEYWORD_FILTER = "SootInjection"
STRIP_BEFORE_KEYWORD = "Entering method:"
INFO_KEYWORD = "Received an install/uninstall event for package"
GMS_ADS_KEYWORD = "com.google.android.gms.ads"
ON_CREATE_SIGNATURE = "void onCreate(android.os.Bundle)"
# -------------------------------------------------

# --- FSM Methods from model.jpg ---
FSM_METHODS = (
    "onAdLoaded(",
    "initialize(",
    "build(",
    "attachInfo(",
    "onDestroy(",
    "onResume(",
    "onPause(",
    "onAdImpression(",
    ON_CREATE_SIGNATURE,  # <-- Add onCreate to the list of methods to trace
)
# ----------------------------------

# --- START: MODIFIED - 6-METHOD RULE RESTORED ---
# The set of 6 methods required to trigger the transition to "Ads displayed"
REQUIRED_FOR_ADS_DISPLAYED = {
    "attachInfo(",
    "build(",
    "initialize(",
    "onAdLoaded(",
    "onResume(",
    "onPause("
}
# --- END: MODIFIED ---

# --- FSM State Machine Definitions (based on model.jpg) ---
STATE_START = "App has started"
STATE_ADS_DISPLAYED = "The app has started with Ads displayed"
STATE_ADV_SET = "The app has started with an adView was set"
STATE_NO_ADS = "The app has started with no Ads displayed"
STATE_AD_LOADED = "The app is running and the advertisement is loaded"
STATE_IMPRESSION = "The app is running and the advertisement impression is made"
STATE_ENGAGEMENT = "The app is running and the advertisement engagement is made"
# ---------------------------------------------------

# Transitions: { (from_state, method_call): to_state }
# --- START: MODIFIED - TRANSITIONS FIXED ---
# We are using the original script's transitions, BUT
# we are REMOVING the one line that causes the error you found.
FSM_TRANSITIONS = {
    # Transitions from STATE_START ("App has started")
    (STATE_START, ON_CREATE_SIGNATURE): STATE_START,  # Custom self-loop
    (STATE_START, "build("): STATE_ADV_SET,           # Transition per diagram
    (STATE_START, "initialize("): STATE_NO_ADS,       # Transition per diagram
    (STATE_START, "onAdLoaded("): STATE_AD_LOADED,    # Transition per diagram
    (STATE_START, "onPause("): STATE_ENGAGEMENT,      # Transition per diagram
    # (STATE_START, "onResume("): STATE_IMPRESSION,   # removed

    # Transitions from "Ads displayed" (STATE_ADS_DISPLAYED)
    (STATE_ADS_DISPLAYED, "onAdLoaded("): STATE_ADS_DISPLAYED,     # Self-loop
    (STATE_ADS_DISPLAYED, "onAdImpression("): STATE_ADS_DISPLAYED, # Self-loop
    (STATE_ADS_DISPLAYED, "onPause("): STATE_ENGAGEMENT,
    (STATE_ADS_DISPLAYED, "onDestroy("): STATE_START,

    # Transitions from "AdView was set" (STATE_ADV_SET)
    (STATE_ADV_SET, "build("): STATE_ADV_SET,  # Self-loop
    (STATE_ADV_SET, "initialize("): STATE_NO_ADS,
    (STATE_ADV_SET, "onDestroy("): STATE_START,

    # Transitions from "No Ads displayed" (STATE_NO_ADS)
    (STATE_NO_ADS, "initialize("): STATE_NO_ADS,  # Self-loop
    (STATE_NO_ADS, "onAdLoaded("): STATE_AD_LOADED,

    # Transitions from "Advertisement is loaded" (STATE_AD_LOADED)
    (STATE_AD_LOADED, "onAdLoaded("): STATE_AD_LOADED,  # Self-loop
    (STATE_AD_LOADED, "onResume("): STATE_IMPRESSION,

    # Transitions from "Advertisement impression is made" (STATE_IMPRESSION)
    (STATE_IMPRESSION, "onResume("): STATE_IMPRESSION,  # Self-loop
    (STATE_IMPRESSION, "onPause("): STATE_ENGAGEMENT,
    (STATE_IMPRESSION, "onDestroy("): STATE_ADV_SET,  # From diagram

    # Transitions from "Advertisement engagement is made" (STATE_ENGAGEMENT)
    (STATE_ENGAGEMENT, "onPause("): STATE_ENGAGEMENT,  # Self-loop
    (STATE_ENGAGEMENT, "onDestroy("): STATE_START,     # Per diagram arrow
}
# --- END: MODIFIED ---


# --- "Pass" states ---
PASS_STATES = {
    STATE_AD_LOADED,
    STATE_IMPRESSION,
    STATE_ENGAGEMENT,
    STATE_ADS_DISPLAYED, 
}
# ---------------------------------

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

# --- Category prefixes (informational, not used in logic) ---
CATEGORY_PREFIXES = [
    "Art_and_Design_", "Auto_and_Vehicles_", "Beauty_", "Books_Reference_",
    "Business_", "Comics_", "Communication_", "Dating_", "Educational_",
    "Entertainment_", "Events_", "Finance_", "Food_and_Drinks_", "Games_",
    "Health_and_Fitness_", "House_and_Home_", "Lifestyle_", "Maps_and_Navigation_",
    "Medical_", "Music_and_Audio_", "News_magazine_", "Parenting_",
    "Personalization_", "Photography_", "Productivity_", "Shopping_",
    "Social_media_", "Sports_", "Tools_", "Travel_and_local_",
    "Video_players_and_editors_", "weather_"
]
# -----------------------------------------------------

# Enable color highlighting (disabled on Windows by default)
ENABLE_COLOR = not (os.name == 'nt')
# ---------------------

# --- ANSI Color Constants ---
GREEN = '\033[92m' if ENABLE_COLOR else ''
YELLOW = '\033[93m' if ENABLE_COLOR else ''
RED = '\033[91m' if ENABLE_COLOR else ''  # For "Fail"
CYAN = '\033[96m' if ENABLE_COLOR else ''
ENDC = '\033[0m' if ENABLE_COLOR else ''
# ----------------------------

# Define regex patterns for log levels.
DEBUG_PATTERN = re.compile(r'\sD[/\s]')
INFO_PATTERN = re.compile(r'\sI[/\s]')

# Regex to extract class name from method signature
CLASS_NAME_PATTERN = re.compile(r'<([^:]+):')

# ---
def get_valid_apk_folder_names(search_dir):
    """
    Scans the specified directory and ALL its subdirectories to find folder names
    that look like packages (i.e., contain a dot).
    Returns a set of unique package folder names found.
    """
    valid_names = set()
    print(f"\nScanning '{search_dir}' and all subdirectories for app folder names...")
    if not os.path.isdir(search_dir):
        print(f"  {YELLOW}WARNING:{ENDC} Directory not found: {search_dir}")
        print(f"  Cannot validate app package names against folders.")
        return valid_names  # Return empty set

    for root, dirnames, _ in os.walk(search_dir, topdown=True):
        for dirname in dirnames:
            if '.' in dirname:
                valid_names.add(dirname)

    if valid_names:
        print(f"  Found {len(valid_names)} unique package-like folder names.")
    else:
        print(f"  {YELLOW}WARNING:{ENDC} No package-like folder names (e.g., 'com.example.app') found under {search_dir}.")
    return valid_names
# ---

def get_log_file_choice():
    """
    Finds log files in the LOG_DIR and prompts the user to choose one.
    Returns the full path to the chosen file and its base name.
    """
    print(f"Scanning for log files in '{LOG_DIR}'...")
    txt_files = glob.glob(os.path.join(LOG_DIR, "*.txt"))
    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
    all_log_files = txt_files + log_files

    if not all_log_files:
        print(f"\n--- ERROR ---")
        print(f"No .txt or .log files found in the '{LOG_DIR}' directory.")
        sys.exit()

    print("\nAvailable log files:")
    file_basenames = [os.path.basename(f) for f in all_log_files]
    for i, filename in enumerate(file_basenames):
        print(f"  {i + 1}: {filename}")

    choice = -1
    while True:
        try:
            raw_choice = input(f"\nPlease enter the number of the file (1-{len(all_log_files)}): ")
            choice = int(raw_choice)
            if 1 <= choice <= len(all_log_files):
                break
            else:
                print(f"Invalid choice.")
        except ValueError:
            print("Invalid input.")

    chosen_basename = file_basenames[choice - 1]
    chosen_full_path = all_log_files[choice - 1]
    return chosen_full_path, chosen_basename

# ---
def extract_package_name(package_string):
    """
    Takes a string (likely a full class name) and filters it.
    Returns the full_package_name or None if filtered/invalid.
    """
    full_potential_package_name = package_string
    parts = package_string.split('.')

    # Heuristic: If the last part starts uppercase, assume it's a class, remove it.
    if len(parts) > 1 and parts[-1] and parts[-1][0].isupper():
        full_potential_package_name = '.'.join(parts[:-1])

    # Filter against standard prefixes
    if full_potential_package_name and \
       (not any(full_potential_package_name.startswith(prefix) for prefix in STANDARD_PACKAGE_PREFIXES)):
        # Basic check: needs at least two parts (e.g., com.example)
        if len(full_potential_package_name.split('.')) >= 2:
            return full_potential_package_name

    return None  # Return None if filtered or looks invalid
# ---

# ---
def find_packages_and_stats(input_path):
    """
    Pass 1: Reads the log file to find all full packages and stats without printing.
    Returns a set of found full package names and line counts.
    """
    found_full_packages = set()  # Store full names like com.example.app
    debug_lines_found, total_lines = 0, 0
    with open(input_path, 'r', encoding='utf-8') as in_file:
        for i, line in enumerate(in_file):
            total_lines = i + 1
            
            # --- Source 1: ALL relevant Debug lines ---
            if (DEBUG_PATTERN.search(line) and KEYWORD_FILTER in line and
                STRIP_BEFORE_KEYWORD in line):
                debug_lines_found += 1 
                try:
                    start_index = line.index(STRIP_BEFORE_KEYWORD)
                    match = CLASS_NAME_PATTERN.search(line[start_index:])
                    if match:
                        full_class_name = match.group(1)
                        full_pkg = extract_package_name(full_class_name)
                        if full_pkg:
                            found_full_packages.add(full_pkg)
                except ValueError:
                    pass

            # --- Source 2: Info "Install/Uninstall" lines ---
            elif (INFO_PATTERN.search(line) and INFO_KEYWORD in line):
                try:
                    start_index = line.index(INFO_KEYWORD) + len(INFO_KEYWORD)
                    package_from_info = line[start_index:].strip().split()[0]
                    full_pkg = extract_package_name(package_from_info)
                    if full_pkg:
                        found_full_packages.add(full_pkg)
                except Exception:
                    pass
    return found_full_packages, total_lines, debug_lines_found
# ---

# --- START: MODIFIED - COMPLEX FSM LOGIC RESTORED ---
def print_highlighted_logs(input_path, input_basename, found_full_packages, 
                           app_fsm_traces, app_fsm_current_state, full_pkg_to_base_pkg, valid_folder_names):
    # Tracking for app root and libraries
    base_app_to_root_prefix = {}
    base_app_to_root_fullpkg = {}

    """
    Pass 2: Reads the file again, printing matching debug lines and highlighting,
            and building the FSM trace using the BASE package name as the key.
    """
    print(f"\n--- Found Debug Lines from {input_basename} (matching '{KEYWORD_FILTER}' AND (First Pkg OR (Main/onCreate) OR (GMS Ads + FSM))) ---")
    lines_printed, seen_full_packages = 0, set()
    last_seen_base_app_key = None 
    GMS_ADS_START_STRING = STRIP_BEFORE_KEYWORD + " <" + GMS_ADS_KEYWORD

    with open(input_path, 'r', encoding='utf-8') as in_file:
        for line in in_file:
            if not (DEBUG_PATTERN.search(line) and KEYWORD_FILTER in line and STRIP_BEFORE_KEYWORD in line):
                continue
            try:
                start_index = line.index(STRIP_BEFORE_KEYWORD)
                processed_line = line[start_index:]
                
                current_full_pkg_key = None 
                current_base_app_key = None 
                base_pkg_for_highlight = None 

                match = CLASS_NAME_PATTERN.search(processed_line)
                if match:
                    full_class_name = match.group(1)
                    full_pkg = extract_package_name(full_class_name)
                    
                    if full_pkg and full_pkg in found_full_packages:
                        current_full_pkg_key = full_pkg 
                        current_base_app_key = full_pkg_to_base_pkg.get(full_pkg) 
                        
                        if current_base_app_key:
                            last_seen_base_app_key = current_base_app_key 
                            base_pkg_for_highlight = '.'.join(current_base_app_key.split('.')[:2])
                        else:
                            current_base_app_key = current_full_pkg_key 
                            last_seen_base_app_key = current_full_pkg_key
                            base_pkg_for_highlight = '.'.join(current_full_pkg_key.split('.')[:2])

                is_gms_ads_line = processed_line.startswith(GMS_ADS_START_STRING)
                if is_gms_ads_line:
                    current_base_app_key = last_seen_base_app_key
                    if current_base_app_key:
                        base_pkg_for_highlight = '.'.join(current_base_app_key.split('.')[:2])

                # --- FSM Simulation ---
                fsm_method_found = None
                for fsm_method in FSM_METHODS:
                    if fsm_method in processed_line:
                        fsm_method_found = fsm_method
                        break
                
                # Only trace if we have a valid base key for this line AND it's GMS Ads
                if fsm_method_found and is_gms_ads_line and current_base_app_key and (current_base_app_key in valid_folder_names):
                    
                    # --- START: 6-METHOD (COMPLEX) FSM LOGIC ---
                    current_state_tuple = app_fsm_current_state[current_base_app_key]
                    current_state_str = current_state_tuple[0]
                    current_seen_methods = current_state_tuple[1]

                    new_state_str = current_state_str
                    new_seen_methods = current_seen_methods.copy()

                    # 1. Add method to our 'seen' set if it's one of the 6 triggers
                    if fsm_method_found in REQUIRED_FOR_ADS_DISPLAYED:
                        new_seen_methods.add(fsm_method_found)

                    # 2. SPECIAL: if we have all 6 in STATE_START → ADS_DISPLAYED
                    if current_state_str == STATE_START and REQUIRED_FOR_ADS_DISPLAYED.issubset(new_seen_methods):
                        new_state_str = STATE_ADS_DISPLAYED
                    else:
                        # 3. Otherwise follow standard transitions
                        transition_key = (current_state_str, fsm_method_found)
                        if transition_key in FSM_TRANSITIONS:
                            new_state_str = FSM_TRANSITIONS[transition_key]

                    # 4. Save the new state
                    app_fsm_current_state[current_base_app_key] = (new_state_str, new_seen_methods)
                    
                    # 5. Record the trace if the state changed
                    if new_state_str != current_state_str:
                        app_fsm_traces[current_base_app_key].append((current_state_str, fsm_method_found, new_state_str))
                    # --- END: 6-METHOD (COMPLEX) FSM LOGIC ---
                # --- End FSM Simulation ---

                # --- Log Printing Filter Logic (library-aware) ---
                is_mapped_to_valid = bool(current_base_app_key and (current_base_app_key in valid_folder_names))

                # Decide occurrence type
                occurrence_type = None  # 'app_first' | 'library_first' | None
                if current_full_pkg_key and (current_full_pkg_key not in seen_full_packages) and is_mapped_to_valid:
                    if current_base_app_key not in base_app_to_root_prefix:
                        parts = current_full_pkg_key.split('.')
                        root_prefix = '.'.join(parts[:-1]) if len(parts) > 1 else current_full_pkg_key
                        base_app_to_root_prefix[current_base_app_key] = root_prefix
                        base_app_to_root_fullpkg[current_base_app_key] = current_full_pkg_key
                        occurrence_type = 'app_first'
                    else:
                        root_prefix = base_app_to_root_prefix[current_base_app_key]
                        if current_full_pkg_key.startswith(root_prefix + '.'):
                            occurrence_type = 'library_first'
                        else:
                            occurrence_type = 'app_first'

                is_fsm_method_line = any(fsm in processed_line for fsm in FSM_METHODS)
                is_gms_ads_and_fsm = (is_gms_ads_line and is_fsm_method_line)
                if not (occurrence_type is not None or is_gms_ads_and_fsm):
                    continue
                # --- End Filter Logic ---

                # --- First occurrence banners (fixed f-strings) ---
                if occurrence_type:
                    if occurrence_type == 'app_first':
                        print(f"\n  {YELLOW}>>> First occurrence of APP package: {current_full_pkg_key}{ENDC}")
                        if current_base_app_key and current_base_app_key != current_full_pkg_key:
                            print(f"  {YELLOW}    (Mapping to base package: {current_base_app_key}){ENDC}")
                    else:
                        root_full = base_app_to_root_fullpkg.get(current_base_app_key, '')
                        print(f"\n  {YELLOW}>>> First occurrence of LIBRARY package: {current_full_pkg_key}{ENDC}")
                        print(f"  {YELLOW}    (Mapping to base package: {current_base_app_key}; library of: {root_full}){ENDC}")
                    seen_full_packages.add(current_full_pkg_key)

                # --- Highlighting ---
                highlighted_line = processed_line
                if base_pkg_for_highlight: 
                    highlighted_line = highlighted_line.replace(base_pkg_for_highlight, f"{GREEN}{base_pkg_for_highlight}{ENDC}")
                if "MainActivity" in highlighted_line:
                    highlighted_line = highlighted_line.replace("MainActivity", f"{YELLOW}MainActivity{ENDC}")
                if ON_CREATE_SIGNATURE in highlighted_line: 
                    highlighted_line = highlighted_line.replace(ON_CREATE_SIGNATURE, f"{YELLOW}{ON_CREATE_SIGNATURE}{ENDC}")
                if GMS_ADS_KEYWORD in highlighted_line:
                    highlighted_line = highlighted_line.replace(GMS_ADS_KEYWORD, f"{GREEN}{GMS_ADS_KEYWORD}{ENDC}")
                for fsm_method in FSM_METHODS:
                    if fsm_method in highlighted_line and fsm_method != ON_CREATE_SIGNATURE and f"{CYAN}{fsm_method}{ENDC}" not in highlighted_line:
                        highlighted_line = highlighted_line.replace(fsm_method, f"{CYAN}{fsm_method}{ENDC}")
                # --- End Highlighting ---

                print(highlighted_line, end=''); lines_printed += 1
            except ValueError:
                pass
        if lines_printed > 0:
            print()
    print(f"\n--- End of Debug Lines ---")
# --- END: MODIFIED ---

# ---
def print_fsm_reports(app_fsm_traces):
    """Prints the FSM traces generated during the log processing."""
    print(f"\n{YELLOW}--- Generated FSM State Traces (Based on model.jpg) ---{ENDC}")
    if not app_fsm_traces or all(not trace for trace in app_fsm_traces.values()):
        print("  No FSM transitions were found for any identified app.")
        print(f"--- End of FSM Traces ---"); return

    for app_key, trace in app_fsm_traces.items():
        print(f"\n--- FSM Trace for: {GREEN}{app_key}{ENDC} ---") 
        if not trace:
            print("  No FSM transitions found for this app.")
            continue
        start_state = trace[0][0] if trace else STATE_START
        print(f"  Start State: {start_state}")
        for i, (from_state, method_call, to_state) in enumerate(trace):
            method_name = ""
            if method_call == ON_CREATE_SIGNATURE:
                method_name = method_call 
            else:
                method_name = method_call.replace('(', '') 
            
            print(f"  {i + 1: >3}: [{from_state}] --({CYAN}{method_name}{ENDC})--> [{to_state}]")
    print(f"\n--- End of FSM Traces ---")
# ---

def generate_html_report(generated_pngs, output_dir, input_basename):
    """
    Generates a simple HTML file to display the generated PNG images.
    """
    print(f"\n{YELLOW}--- Generating FSM Report HTML ---{ENDC}")

    # --- Copy model.png ---
    MODEL_IMAGE_NAME = "model.png"
    model_image_path_dest = os.path.join(output_dir, MODEL_IMAGE_NAME)
    model_html_content = ""
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))
        model_image_src = os.path.join(script_dir, MODEL_IMAGE_NAME)
        if not os.path.exists(model_image_src):
            model_image_src = os.path.join(script_dir, "..", MODEL_IMAGE_NAME)

        if os.path.exists(model_image_src):
            shutil.copy(model_image_src, model_image_path_dest)
            print(f"  - Copied {MODEL_IMAGE_NAME} to log directory for report.")
            model_html_content = f"""
                <div class="rounded-lg shadow-md overflow-hidden bg-white mb-12">
                    <div class="p-4 bg-gray-50 border-b"><h2 class="text-2xl font-semibold">Correct Behavior Model Reference</h2></div>
                    <div class="p-4 bg-white"><img src="{MODEL_IMAGE_NAME}" alt="Correct FSM Behavior Model" class="w-full"></div>
                </div>"""
        else:
            raise FileNotFoundError 
    except FileNotFoundError:
        print(f"  - {YELLOW}WARNING:{ENDC} '{MODEL_IMAGE_NAME}' not found in script directory or parent directory.")
        model_html_content = f"""<div class="rounded-lg shadow-md bg-red-100 text-red-800 p-4 mb-12"><h2 class="text-2xl font-semibold mb-2 text-red-900">Correct Behavior Model Reference</h2><p><b>{RED}Error:{ENDC}</b> '{MODEL_IMAGE_NAME}' not found.</p></div>"""
    except Exception as e:
        print(f"  - {YELLOW}WARNING:{ENDC} Could not copy '{MODEL_IMAGE_NAME}'. Error: {e!r}")
    # -----------------------

    if not generated_pngs and not model_html_content:
        print("  No PNG files generated and no reference model found, skipping HTML report.")
        return
    elif not generated_pngs:
        print("  No PNG files were generated, but reference model found. Generating HTML report.")
    elif not model_html_content:
        print("  PNG files generated, but reference model not found. Generating HTML report.")

    base_name, _ = os.path.splitext(input_basename)
    output_filename = f"{base_name}_fsm_report.html"
    output_path = os.path.join(output_dir, output_filename)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>FSM Log Traces Report for {input_basename}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: #f4f4f5; }}
    </style>
</head>
<body class="p-8">
    <div class="container mx-auto max-w-6xl">
        <h1 class="text-3xl font-bold mb-2 text-gray-800">FSM State Diagram Traces</h1>
        <p class="text-lg text-gray-600 mb-8">Report for: {input_basename}</p>

        {model_html_content}

        <div id="diagrams-container" class="space-y-12">
"""
    if generated_pngs:
        for png_file, app_name, status, status_color in generated_pngs:
            html_content += f"""
                <div class="rounded-lg shadow-md overflow-hidden bg-white">
                    <div class="p-4 bg-gray-50 border-b flex justify-between items-center">
                        <h2 class="text-2xl font-semibold">{app_name}</h2>
                        <span class="text-sm font-medium px-3 py-1 rounded-full {status_color}">
                            {status}
                        </span>
                    </div>
                    <div class="p-4 bg-white">
                        <<img src="{png_file}" alt="FSM Diagram for {app_name}" class="w-full">
                    </div>
                </div>
    """
    else:
        html_content += '<p class="text-gray-600">No FSM diagrams were generated for any apps that passed all filters.</p>'

    html_content += """
        </div>
    </div>
</body>
</html>
"""

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  {GREEN}Success!{ENDC} Report saved to:")
        print(f"  {output_path}")
    except Exception as e:
        print(f"\n  {YELLOW}--- WARNING ---{ENDC}")
        print(f"  Could not write HTML report file. Error: {e!r}")

    print(f"--- End of Report Generation ---")


# ---
def generate_fsm_png_report(app_fsm_traces, output_dir, input_basename):
    """
    Generates a .png file for each app's FSM trace using graphviz.
    """
    print(f"\n{YELLOW}--- Generating FSM Visualization (PNGs - Traced Path Only) ---{ENDC}")

    generated_pngs = []

    if not app_fsm_traces or all(not trace for trace in app_fsm_traces.values()):
        print("  No validated (filtered) app traces found to generate diagrams for.")
        generate_html_report(generated_pngs, output_dir, input_basename)
        print(f"--- End of Visualization ---")
        return

    for app_name, trace in app_fsm_traces.items():
        try:
            print(f"  Generating diagram for: {app_name}...") 

            # --- Pass/Fail Logic ---
            status = "FAIL"; status_color = "bg-red-100 text-red-800"
            traced_states = set(); traced_methods = set(t[1] for t in trace)
            if trace: traced_states.add(trace[0][0]); traced_states.update(t[2] for t in trace)
            else: traced_states.add(STATE_START)
            if any(s in PASS_STATES for s in traced_states) or ON_CREATE_SIGNATURE in traced_methods:
                status = "PASS"; status_color = "bg-green-100 text-green-800"
            # --- End Pass/Fail Logic ---

            # --- Create the Graphviz Digraph ---
            dot_label = f"FSM Trace for {app_name}\nStatus: {status}" 
            dot = graphviz.Digraph(comment=f'FSM Trace for {app_name}')
            dot.attr(rankdir='TB', label=dot_label, fontsize='16', nodesep='0.5', ranksep='0.7')
            dot.attr(size="10,10", ratio="compress", dpi="150")

            start_node_for_diagram = STATE_START
            if trace: start_node_for_diagram = trace[0][0]

            dot.node('start_node_marker', shape='point', width='0.1')

            if not trace:
                dot.node(STATE_START, label=STATE_START, shape='box', style='rounded,filled', fillcolor='#c8e6c9', color='#388e3c')
                dot.edge('start_node_marker', STATE_START, style='invis')
            else:
                nodes_in_trace = set(); nodes_in_trace.add(trace[0][0]); nodes_in_trace.update(t[2] for t in trace)
                dot.edge('start_node_marker', start_node_for_diagram, style='invis')
                for state in nodes_in_trace:
                    dot.node(state, label=state, shape='box', style='rounded,filled', fillcolor='#c8e6c9', color='#388e3c')
                for i, (from_state, method, to_state) in enumerate(trace):
                    clean_method = ""
                    if method == ON_CREATE_SIGNATURE:
                        clean_method = method 
                    else:
                        clean_method = method.replace('(', '') 

                    dot.edge(from_state, to_state, label=f' {clean_method} ', color='#388e3c', penwidth='2.0', fontcolor='#388e3c')

            # --- Render PNG ---
            safe_app_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', app_name)
            base_log_name, _ = os.path.splitext(input_basename)
            output_basename = f'{base_log_name}_fsm_diagram_{safe_app_name}'
            output_path_base = os.path.join(output_dir, output_basename)
            png_filename = f"{output_basename}.png"

            try:
                dot.render(output_path_base, format='png', cleanup=True)
                print(f"    {GREEN}Success!{ENDC} Saved to {png_filename}")
                generated_pngs.append((png_filename, app_name, status, status_color))
            except graphviz.backend.execute.ExecutableNotFound:
                print(f"  {YELLOW}ERROR:{ENDC} 'dot' executable not found (part of Graphviz).")
                break
            except Exception as render_err:
                print(f"    {YELLOW}WARNING:{ENDC} Graphviz render failed for {app_name}: {render_err!r}")

        except Exception as e:
            print(f"\n  {YELLOW}--- WARNING ---{ENDC}")
            print(f"  Could not generate diagram for {app_name}. Error: {e!r}")
            if isinstance(e, graphviz.backend.execute.ExecutableNotFound) or \
               ("failed to execute" in str(e)) or ("No such file" in str(e)):
                print(f"  {YELLOW}Error: Graphviz executable not found.{ENDC}")
                break
    # --- Generate HTML report ---
    generate_html_report(generated_pngs, output_dir, input_basename)
    print(f"--- End of Visualization ---")
# ---


def extract_debug_logs():
    """Orchestrates the log extraction process."""
    try:
        input_path, input_basename = get_log_file_choice()
    except SystemExit:
        return

    print(f"\nStarting log extraction...")
    print(f"  Input file: {input_path}")
    if ENABLE_COLOR:
        print(f"  {GREEN}Highlighting enabled.{ENDC} ...")

    try:
        # --- Get valid base folder names ---
        valid_folder_names = get_valid_apk_folder_names(APK_ANALYSIS_DIR)
        
        # Pass 1: Find all potential packages
        print("  Pass 1: Analyzing packages...")
        found_full_packages, total_lines, debug_lines_found = find_packages_and_stats(input_path)

        # --- NEW: Create mapping from full package to base package ---
        full_pkg_to_base_pkg = {}
        if valid_folder_names:
            print("  Mapping full package names to base folder names...")
            for full_pkg in found_full_packages:
                # Find the longest matching folder name
                best_match = None
                for folder in valid_folder_names:
                    if full_pkg.startswith(folder):
                        if best_match is None or len(folder) > len(best_match):
                            best_match = folder
                if best_match:
                    full_pkg_to_base_pkg[full_pkg] = best_match
            print(f"    Mapped {len(full_pkg_to_base_pkg)} packages.")
        # -----------------------------------------------------------

        # --- START: MODIFIED - COMPLEX STATE TRACKER RESTORED ---
        # Now stores a tuple: (current_state_string, seen_methods_set)
        app_fsm_traces = defaultdict(list)
        app_fsm_current_state = defaultdict(lambda: (STATE_START, set()))
        # --- END: MODIFIED ---
        
        # Pass 2: Build traces, now using the base package key
        print("  Pass 2: Printing highlighted logs and generating FSM traces...")
        print_highlighted_logs(
            input_path, 
            input_basename, 
            found_full_packages, 
            app_fsm_traces, 
            app_fsm_current_state,
            full_pkg_to_base_pkg,  # --- Pass the map
            valid_folder_names
        )
        # ----------------------------------------------------

        # --- Filter 1: Filter traces based on valid folder names ---
        folder_filtered_traces = {}
        if valid_folder_names:
            print("\nFiltering FSM traces against valid APK folder names...")
            removed_count = 0
            for app_key, trace in app_fsm_traces.items():
                if app_key in valid_folder_names:
                    folder_filtered_traces[app_key] = trace
                else:
                    removed_count += 1
            
            if removed_count > 0:
                print(f"  Removed {removed_count} trace(s) for packages not matching folders in {APK_ANALYSIS_DIR}.")
            else:
                print(f"  All identified traces matched a valid folder.")
        else:
            print(f"  {YELLOW}WARNING:{ENDC} No valid app folders found, skipping folder filtering.")
            folder_filtered_traces = app_fsm_traces
        # --- END FILTER 1 BLOCK ---

        # --- START: Filter 2 ---
        # Remove packages with only 2 parts (e.g., com.l)
        final_filtered_traces = {}
        print("\nFiltering traces to remove simple 2-part packages...")
        removed_count_2 = 0
        for app_key, trace in folder_filtered_traces.items():
            if len(app_key.split('.')) == 2:
                removed_count_2 += 1
            else:
                final_filtered_traces[app_key] = trace

        if removed_count_2 > 0:
            print(f"  Removed {removed_count_2} trace(s) matching 2-part package pattern (e.g., com.l).")
        else:
            print("  No traces matched the 2-part package pattern.")
        
        app_fsm_traces = final_filtered_traces  # Use this final filtered dict
        # --- END FILTER 2 BLOCK ---

        print(f"\nExtraction complete.")
        print(f"  Processed {total_lines} total lines.")
        print(f"  Found {debug_lines_found} matching debug lines (containing '{KEYWORD_FILTER}' and '{STRIP_BEFORE_KEYWORD}').")

        # --- Print packages that *passed all filters* ---
        if app_fsm_traces:
            print(f"\n--- Packages Passing All Filters ---")
            for pkg in sorted(list(app_fsm_traces.keys())):
                print(f"  {GREEN}{pkg}{ENDC}")
            print(f"--- End of Filtered Packages ---")
        else:
            print(f"\n--- No packages passed all filters. ---")

        # Use the final filtered traces for reports
        print_fsm_reports(app_fsm_traces)
        generate_fsm_png_report(app_fsm_traces, LOG_DIR, input_basename)

    except FileNotFoundError:
        print(f"\n--- ERROR ---\nFile not found: {input_path}")
    except Exception as e:
        print(f"\n--- ERROR ---\nUnexpected error: {type(e)}\nDetails: {e!r}")

if __name__ == "__main__":
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR); print(f"Created directory: {LOG_DIR}")
    if not ENABLE_COLOR:
        print("(Note: Color highlighting disabled.)")
    extract_debug_logs()

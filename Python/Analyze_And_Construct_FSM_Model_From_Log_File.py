import os
import re
import glob
import sys
from collections import defaultdict
import json

# --- NEW: Check for Graphviz ---
# This new approach requires the 'graphviz' Python library
# and the Graphviz system executable.
try:
    import graphviz
except ImportError:
    print(f"\n--- ERROR: Missing Dependency ---")
    print(f"This script now requires the 'graphviz' Python library.")
    print(f"Please install it by running: pip install graphviz")
    print(f"\nIMPORTANT: You must ALSO install the Graphviz system executable.")
    print(f"  - Windows: Download installer from https://graphviz.org/download/")
    print(f"  - macOS (Homebrew): brew install graphviz")
    print(f"  - Linux (Ubuntu/Debian): sudo apt-get install graphviz")
    print(f"---------------------------------")
    sys.exit()
# --------------------------------

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

# --- Specific 'onCreate' signature to look for ---
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
)
# ----------------------------------

# --- FSM State Machine Definitions (based on model.jpg) ---
# States
STATE_START = "App has started"
STATE_ADS_DISPLAYED = "Ads displayed"
STATE_ADV_SET = "AdView was set"
STATE_NO_ADS = "No Ads displayed"
STATE_AD_LOADED = "Advertisement is loaded"
STATE_IMPRESSION = "Advertisement impression is made"
STATE_ENGAGEMENT = "Advertisement engagement is made"

# Transitions: { (from_state, method_call): to_state }
FSM_TRANSITIONS = {
    # Transitions from "App has started"
    (STATE_START, "attachInfo("): STATE_ADS_DISPLAYED,
    (STATE_START, "build("): STATE_ADV_SET,
    (STATE_START, "initialize("): STATE_NO_ADS,
    (STATE_START, "onAdLoaded("): STATE_AD_LOADED,
    (STATE_START, "onResume("): STATE_IMPRESSION,
    (STATE_START, "onPause("): STATE_ENGAGEMENT,

    # Transitions from "Ads displayed"
    (STATE_ADS_DISPLAYED, "onAdLoaded("): STATE_ADS_DISPLAYED, # Self-loop
    (STATE_ADS_DISPLAYED, "onAdImpression("): STATE_ADS_DISPLAYED, # Self-loop
    (STATE_ADS_DISPLAYED, "onPause("): STATE_ENGAGEMENT,
    (STATE_ADS_DISPLAYED, "onDestroy("): STATE_START,

    # Transitions from "AdView was set"
    (STATE_ADV_SET, "build("): STATE_ADV_SET, # Self-loop
    (STATE_ADV_SET, "initialize("): STATE_NO_ADS,
    (STATE_ADV_SET, "onDestroy("): STATE_START,

    # Transitions from "No Ads displayed"
    (STATE_NO_ADS, "initialize("): STATE_NO_ADS, # Self-loop
    (STATE_NO_ADS, "onAdLoaded("): STATE_AD_LOADED,

    # Transitions from "Advertisement is loaded"
    (STATE_AD_LOADED, "onAdLoaded("): STATE_AD_LOADED, # Self-loop
    (STATE_AD_LOADED, "onResume("): STATE_IMPRESSION,

    # Transitions from "Advertisement impression is made"
    (STATE_IMPRESSION, "onResume("): STATE_IMPRESSION, # Self-loop
    (STATE_IMPRESSION, "onPause("): STATE_ENGAGEMENT,

    # Transitions from "Advertisement engagement is made"
    (STATE_ENGAGEMENT, "onPause("): STATE_ENGAGEMENT, # Self-loop
}

# --- NEW: Define "Pass" states ---
# If an app reaches any of these states, it's considered a "Pass"
PASS_STATES = {
    STATE_AD_LOADED,
    STATE_IMPRESSION,
    STATE_ENGAGEMENT,
    STATE_ADS_DISPLAYED, # Reaching the state where ads are shown is also a pass
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

# Enable color highlighting (disabled on Windows by default)
ENABLE_COLOR = not (os.name == 'nt')
# ---------------------

# --- ANSI Color Constants ---
GREEN = '\033[92m' if ENABLE_COLOR else ''
YELLOW = '\033[93m' if ENABLE_COLOR else ''
RED = '\033[91m' if ENABLE_COLOR else '' # For "Fail"
CYAN = '\033[96m' if ENABLE_COLOR else ''
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
        if parts[-1] and parts[-1][0].isupper(): 
            package_name = '.'.join(parts[:-1])
        else:
            package_name = package_string

    # --- Filter Logic ---
    # Check if the package is NOT a standard one
    if package_name and (not any(package_name.startswith(prefix) for prefix in STANDARD_PACKAGE_PREFIXES)):
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

def print_highlighted_logs(input_path, input_basename, found_base_packages, app_fsm_traces, app_fsm_current_state):
    """
    Pass 2: Reads the file again, printing matching debug lines and highlighting,
            and building the FSM trace.
            
    MODIFIED: Now accepts app_fsm_current_state and simulates the FSM.
              app_fsm_traces will now store tuples of (from_state, method, to_state).
    """
    print(f"\n--- Found Debug Lines from {input_basename} (matching '{KEYWORD_FILTER}' AND (First Pkg OR (Main/onCreate) OR (GMS Ads + FSM))) ---")
    
    lines_printed = 0
    seen_base_packages = set()
    
    # Define the exact string to check for GMS Ads
    GMS_ADS_START_STRING = STRIP_BEFORE_KEYWORD + " <" + GMS_ADS_KEYWORD

    with open(input_path, 'r', encoding='utf-8') as in_file:
        for line in in_file:
            # Check for base requirements first
            if not (DEBUG_PATTERN.search(line) and 
                    KEYWORD_FILTER in line and 
                    STRIP_BEFORE_KEYWORD in line):
                continue

            try:
                start_index = line.index(STRIP_BEFORE_KEYWORD)
                processed_line = line[start_index:]
                
                # --- Get current package info ---
                current_full_pkg = None
                current_base_pkg = None
                current_app_key = None # This will be base_pkg or GMS_ADS_KEYWORD
                
                match = CLASS_NAME_PATTERN.search(processed_line)
                if match:
                    full_class_name = match.group(1)
                    pkg, base_pkg = extract_package_name(full_class_name)
                    if pkg and base_pkg in found_base_packages:
                        current_full_pkg = pkg
                        current_base_pkg = base_pkg
                        current_app_key = base_pkg # Use base package as the key
                
                # Check if it's a GMS Ads line
                if processed_line.startswith(GMS_ADS_START_STRING):
                    current_app_key = GMS_ADS_KEYWORD # Use GMS keyword as the key
                # --- End package info ---
                
                
                # --- FSM State Machine Simulation ---
                fsm_method_found = None
                for fsm_method in FSM_METHODS:
                    if fsm_method in processed_line:
                        fsm_method_found = fsm_method
                        break # Found the method for this line
                
                # If we found an FSM method AND it belongs to an app we're tracking
                if fsm_method_found and current_app_key:
                    # Get the app's current state
                    current_state = app_fsm_current_state[current_app_key]
                    
                    # Check if this is a valid transition
                    transition_key = (current_state, fsm_method_found)
                    if transition_key in FSM_TRANSITIONS:
                        # It's a valid transition, update the state
                        new_state = FSM_TRANSITIONS[transition_key]
                        app_fsm_current_state[current_app_key] = new_state
                        
                        # Record this transition for the diagram
                        app_fsm_traces[current_app_key].append(
                            (current_state, fsm_method_found, new_state)
                        )
                    # else:
                        # This was an "invalid" transition, (e.g., onResume in a state
                        # that doesn't handle it). We'll just ignore it and the
                        # app stays in its current_state.
                # --- End FSM Simulation ---
                
                
                # --- Log Printing Filter Logic ---
                is_first_occurrence = False
                if current_base_pkg and current_base_pkg not in seen_base_packages:
                    is_first_occurrence = True
                
                is_main_on_create = ("MainActivity" in processed_line and 
                                     ON_CREATE_SIGNATURE in processed_line)
                
                is_fsm_method_line = any(fsm_method in processed_line for fsm_method in FSM_METHODS)
                is_gms_ads_line = (processed_line.startswith(GMS_ADS_START_STRING) and is_fsm_method_line)
                
                
                # Line must meet one of these conditions to be printed
                if not (is_first_occurrence or is_main_on_create or is_gms_ads_line):
                    continue
                # --- End of logic ---


                # If it's the first occurrence, print the header and track it
                if is_first_occurrence:
                    print(f"\n  {YELLOW}>>> First occurrence of package: {current_full_pkg}{ENDC}")
                    seen_base_packages.add(current_base_pkg)
                
                
                # This is the line to print, now we highlight it
                highlighted_line = processed_line
                
                # --- Highlight base package ---
                if current_base_pkg:
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
                
                # Highlight "onCreate" signature (Yellow)
                if ON_CREATE_SIGNATURE in highlighted_line:
                    highlighted_line = highlighted_line.replace(
                        ON_CREATE_SIGNATURE,
                        f"{YELLOW}{ON_CREATE_SIGNATURE}{ENDC}"
                    )
                    
                # Highlight GMS Ads (Green)
                if GMS_ADS_KEYWORD in highlighted_line:
                    highlighted_line = highlighted_line.replace(
                        GMS_ADS_KEYWORD,
                        f"{GREEN}{GMS_ADS_KEYWORD}{ENDC}"
                    )
                
                # Highlight FSM methods (Cyan)
                for fsm_method in FSM_METHODS:
                    if fsm_method in highlighted_line:
                        highlighted_line = highlighted_line.replace(
                            fsm_method,
                            f"{CYAN}{fsm_method}{ENDC}"
                        )
                
                # Print the (potentially) highlighted line
                print(highlighted_line, end='')
                lines_printed += 1
                    
            except ValueError:
                pass
        
        if lines_printed > 0:
            print()
            
    print(f"\n--- End of Debug Lines ---")

def print_fsm_reports(app_fsm_traces):
    """
    Prints the FSM traces generated during the log processing.
    MODIFIED: Now prints (from_state, method, to_state) tuples.
    """
    print(f"\n{YELLOW}--- Generated FSM State Traces (Based on model.jpg) ---{ENDC}")
    
    # Filter out GMS ads from the trace list before checking emptiness
    app_only_traces = {k: v for k, v in app_fsm_traces.items() if k != GMS_ADS_KEYWORD}

    if not app_only_traces:
        print("  No FSM transitions found for any identified app.")
        print(f"--- End of FSM Traces ---")
        return

    all_empty = all(not trace for trace in app_only_traces.values())
    if all_empty:
        print("  No FSM transitions were found in the debug logs for any identified app.")
        print(f"--- End of FSM Traces ---")
        return

    for app_key, trace in app_fsm_traces.items():
        # --- NEW: Skip GMS Ads from this report ---
        if app_key == GMS_ADS_KEYWORD:
            continue
        # ----------------------------------------
        
        print(f"\n--- FSM Trace for: {GREEN}{app_key}{ENDC} ---")
        if not trace:
            print("  No FSM transitions found for this app.")
            continue
        
        # Print the first state
        if trace:
            print(f"  Start State: {trace[0][0]}")
        
            for i, (from_state, method_call, to_state) in enumerate(trace):
                method_name = method_call.replace('(', '')
                print(f"  {i + 1: >3}: [{from_state}] --({CYAN}{method_name}{ENDC})--> [{to_state}]")
            
    print(f"\n--- End of FSM Traces ---")

def generate_html_report(generated_pngs, output_dir):
    """
    Generates a simple HTML file to display the generated PNG images.
    MODIFIED: Now adds a Pass/Fail/Trace badge to each title.
    """
    print(f"\n{YELLOW}--- Generating FSM Report HTML ---{ENDC}")
    
    if not generated_pngs:
        print("  No PNG files were generated, skipping HTML report.")
        return

    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FSM Log Traces Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f4f4f5; /* Tailwind gray-100 */
        }
    </style>
</head>
<body class="p-8">
    <div class="container mx-auto max-w-6xl">
        <h1 class="text-3xl font-bold mb-8 text-gray-800">FSM State Diagram Traces</h1>
        <div class="space-y-12">
"""
    
    # Add each PNG to the HTML
    for png_file, app_name, status, status_color in generated_pngs:
        html_content += f"""
            <div class="rounded-lg shadow-md overflow-hidden bg-white">
                <div class="p-4 bg-gray-50 border-b flex justify-between items-center">
                    <h2 class="text-2xl font-semibold">{app_name}</h2>
                    <span class="text-sm font-medium px-3 py-1 rounded-full {status_color}">
                        {status}
                    </span>
                </div>
                <div class"p-4">
                    <img src="{png_file}" alt="FSM Diagram for {app_name}" class="w-full">
                </div>
            </div>
"""
    
    # Close the HTML tags
    html_content += """
        </div>
    </div>
</body>
</html>
"""
    
    output_filename = "fsm_report.html"
    output_path = os.path.join(output_dir, output_filename)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  {GREEN}Success!{ENDC} Report saved to:")
        print(f"  {output_path}")
    except Exception as e:
        print(f"\n  {YELLOW}--- WARNING ---{ENDC}")
        print(f"  Could not write HTML report file. Error: {e!r}")
        
    print(f"--- End of Report Generation ---")


def generate_fsm_png_report(app_fsm_traces, output_dir):
    """
    Generates a .png file for each app's FSM trace using graphviz
    and then generates a single HTML file to display them all.
    MODIFIED: Now determines "Pass/Fail" status and adds it to the title.
    """
    print(f"\n{YELLOW}--- Generating FSM Visualization (PNGs) ---{ENDC}")
    
    # Get all possible states from the transitions map
    all_states = set(s for s, _ in FSM_TRANSITIONS.keys())
    all_states.update(FSM_TRANSITIONS.values())
    all_states.add(STATE_START)

    # Store (filename, app_name, status, status_color) tuples for the HTML report
    generated_pngs = []

    for app_name, trace in app_fsm_traces.items():
        # --- NEW: Skip GMS Ads from diagram generation ---
        if app_name == GMS_ADS_KEYWORD:
            print(f"  Skipping diagram generation for: {app_name} (system package)")
            continue
        # -----------------------------------------------
        
        try:
            print(f"  Generating diagram for: {app_name}...")
            
            # --- Pass/Fail/Trace Logic ---
            status = "FAIL"
            status_color = "bg-red-100 text-red-800" # Tailwind classes for red
            
            # Get all states this app visited
            traced_states = set(t[0] for t in trace)
            traced_states.update(t[2] for t in trace)
            if not trace:
                traced_states.add(STATE_START) # Always count the start state
            
            # Check if any visited state is a "PASS" state
            if any(state in PASS_STATES for state in traced_states):
                status = "PASS"
                status_color = "bg-green-100 text-green-800" # Tailwind for green
            
            # --- End Pass/Fail Logic ---
            
            # Create lookup sets for this app's trace
            traced_transitions = set(f"{t[0]}|{t[1]}|{t[2]}" for t in trace)
            
            
            # --- Create the Graphviz Digraph ---
            # Add status to the main label
            dot_label = f"FSM Trace for {app_name}\nStatus: {status}"
            dot = graphviz.Digraph(comment=f'FSM for {app_name}')
            dot.attr(rankdir='TB', newrank='true', label=dot_label, fontsize='20')

            # 1. Define ALL states (nodes) first
            for state in all_states:
                state_attrs = {
                    'shape': 'box',
                    'style': 'rounded,filled',
                    'fillcolor': '#f8f8f8', # Default light gray
                    'color': '#aaaaaa',
                    'fontname': 'Helvetica'
                }
                # Highlight if this state was visited
                if state in traced_states:
                    state_attrs['fillcolor'] = '#c8e6c9' # Light green
                    state_attrs['color'] = '#388e3c'     # Dark green
                    state_attrs['stroke-width'] = '2'
                
                dot.node(name=state, label=state, **state_attrs)

            # Add the start state visual
            dot.node('start_node', shape='point', width='0.1')
            dot.edge('start_node', STATE_START, label='', style='invis') # Invisible edge for layout

            # 2. Define ALL transitions (edges)
            for (from_state, method), to_state in FSM_TRANSITIONS.items():
                clean_method = method.replace('(', '')
                
                edge_attrs = {
                    'label': f' {clean_method} ',
                    'color': '#aaaaaa', # Default light gray
                    'fontcolor': '#666666',
                    'fontname': 'Helvetica'
                }
                
                # Highlight if this transition was taken
                trace_key = f"{from_state}|{method}|{to_state}"
                if trace_key in traced_transitions:
                    edge_attrs['color'] = '#388e3c'     # Dark green
                    edge_attrs['penwidth'] = '3.0'
                    edge_attrs['fontcolor'] = '#388e3c'
                    
                dot.edge(from_state, to_state, **edge_attrs)

            # --- Render the .png file ---
            # Create a filename safe for all OSes
            safe_app_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', app_name)
            output_basename = f'fsm_diagram_{safe_app_name}'
            output_path_base = os.path.join(output_dir, output_basename)
            
            # This renders 'fsm_diagram_app_name.gv' and 'fsm_diagram_app_name.gv.png'
            # We set cleanup=True to remove the intermediate .gv file
            png_filename = f"{output_basename}.png"
            dot.render(output_path_base, format='png', cleanup=True)
            
            print(f"    {GREEN}Success!{ENDC} Saved to {png_filename}")
            generated_pngs.append((png_filename, app_name, status, status_color))

        except Exception as e:
            print(f"\n  {YELLOW}--- WARNING ---{ENDC}")
            print(f"  Could not generate diagram for {app_name}.")
            # Check if it's a Graphviz executable error
            if "failed to execute" in str(e) or "No such file" in str(e):
                print(f"  {YELLOW}Error: 'graphviz' executable not found.{ENDC}")
                print(f"  Please ensure Graphviz is installed and in your system's PATH.")
                print(f"  (See install instructions at the start of the script)")
            else:
                print(f"  Error details: {e!r}")
            # Stop trying to generate more, as it will likely fail too
            if "failed to execute" in str(e):
                break 
    
    # --- Now, generate the HTML report ---
    generate_html_report(generated_pngs, output_dir)
    
    print(f"--- End of Visualization ---")


def extract_debug_logs():
    """
    Orchestrates the log extraction:
    1. Gets user file choice.
    2. Pass 1: Finds all packages and stats.
    3. Pass 2: Prints highlighted logs and builds FSM traces.
    4. Prints final summary reports.
    5. Prints FSM traces.
    6. Generates FSM visualization PNGs and HTML report.
    """
    
    # Get the user's file choice
    try:
        input_path, input_basename = get_log_file_choice()
    except SystemExit:
        # This happens if no files were found. get_log_file_choice handled the message.
        return 

    print(f"\nStarting log extraction...")
    print(f"  Input file: {input_path}")
    print(f"  Filtering for: Debug lines containing '{KEYWORD_FILTER}' AND (First Pkg OR (Main/onCreate) OR (GMS Ads + FSM))")
    print(f"  Filtering for: Info lines containing '{INFO_KEYWORD}'")
    print(f"  Stripping before: '{STRIP_BEFORE_KEYWORD}'")
    print(f"  Ignoring standard packages (android.*, java.*, etc.)")
    if ENABLE_COLOR:
        print(f"  {GREEN}Highlighting enabled.{ENDC} ({YELLOW}Main{ENDC}, {GREEN}Pkg/Ads{ENDC}, {CYAN}FSM{ENDC})")


    try:
        # --- Pass 1: Find all packages and stats ---
        print("  Pass 1: Analyzing packages...")
        found_packages, found_base_packages, total_lines, debug_lines_found = find_packages_and_stats(input_path)
        
        # --- Create dictionaries for FSM simulation ---
        # Stores the list of (from, method, to) tuples for the diagram
        app_fsm_traces = defaultdict(list)
        # Stores the *current* state of each app
        app_fsm_current_state = defaultdict(lambda: STATE_START)
        # -----------------------------------------------
        
        # --- Pass 2: Print highlighted lines AND build FSM traces ---
        print("  Pass 2: Printing highlighted logs and generating FSM traces...")
        print_highlighted_logs(
            input_path, 
            input_basename, 
            found_base_packages, 
            app_fsm_traces,         # Pass the trace list
            app_fsm_current_state   # Pass the state tracker
        )

        # --- Print Summaries ---
        print(f"\nExtraction complete.")
        print(f"  Processed {total_lines} total lines.")
        print(f"  Found {debug_lines_found} matching debug lines (containing 'MainActivity' for package discovery).")
        
        # --- Section: Print Full Packages ---
        if found_packages:
            print(f"\n--- Identified App Packages (from Debug 'MainActivity' & Info logs) ---")
            for pkg in sorted(list(found_packages)):
                print(f"  {pkg}")
            print(f"--- End of Packages ---")
        else:
            print(f"\n--- No non-standard app packages identified. ---")
        # ----------------------------------------

        # --- New Section: Print Base Packages ---
        if found_base_packages:
            print(f"\n--- Identified Base Packages (from Debug 'MainActivity' & Info logs) ---")
            for pkg in sorted(list(found_base_packages)):
                print(f"  {GREEN}{pkg}{ENDC}")
            print(f"--- End of Base Packages ---")
        else:
            print(f"\n--- No non-standard base app packages identified. ---")
        # ----------------------------------------

        # --- Print FSM Report ---
        print_fsm_reports(app_fsm_traces)
        # ------------------------
        
        # --- Generate PNGs and HTML Report ---
        generate_fsm_png_report(app_fsm_traces, LOG_DIR)
        # ---------------------------------

    except FileNotFoundError:
        print(f"\n--- ERROR ---")
        print(f"File not found at: {input_path}")
    except Exception as e:
        print(f"\n--- ERROR ---")
        print(f"An unexpected error occurred. Error type: {type(e)}")
        print(f"Error details: {e!r}")

if __name__ == "__main__":
    # Create the log directory if it doesn't exist, just in case
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        print(f"Created directory: {LOG_DIR}")
        
    if not ENABLE_COLOR:
        print("(Note: Color highlighting is disabled on this OS, ANSI escape codes may not be supported.)")
        
    extract_debug_logs()


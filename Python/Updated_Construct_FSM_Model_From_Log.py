import re
import sys
import os
from collections import defaultdict

# --- FSM VALIDATION LOGIC ---
def validate_fsm(method_sequence):
    """
    Validates a sequence of methods against the specific FSM criteria.
    Returns: (status_boolean, status_message)
    """
    
    # Define the State Machine Dictionary
    # Keys = Current State
    # Values = Dictionary of {Method Name : Next State}
    
    transitions = {
        "Start": {
            "attachInfo": "Start",           # Loop (Criteria 5)
            "build": "AdViewSet"             # Criteria 1
        },
        "AdViewSet": {
            "build": "AdViewSet",            # Loop (Criteria 5)
            "initialize": "NoAdsDisplayed"   # Criteria 1
        },
        "NoAdsDisplayed": {
            "initialize": "NoAdsDisplayed",  # Loop (Criteria 5)
            "onAdLoaded": "AdLoaded"         # Criteria 1
        },
        "AdLoaded": {
            "onAdLoaded": "AdLoaded",        # Loop (Criteria 5)
            "onResume": "ImpressionMade",    # Criteria 2
            "onDestroy": "AdViewSet"         # Criteria 3 (Reset)
        },
        "ImpressionMade": {
            "onResume": "ImpressionMade",    # Loop (Criteria 5)
            "onPause": "EngagementMade",     # Criteria 2
            "onDestroy": "AdViewSet"         # Criteria 3 (Reset)
        },
        "EngagementMade": {
            "onPause": "EngagementMade",     # Loop (Criteria 5)
            "onDestroy": "AdViewSet"         # Criteria 3 (Reset)
        },
        # "AdsDisplayed" state is reached via the alternative path (Criteria 4).
        # Included here for completeness if logic jumps there.
        "AdsDisplayed": {
            "onAdLoaded": "AdsDisplayed",     # Loop (Criteria 5)
            "onAdImpression": "AdsDisplayed", # Loop (Criteria 5)
            "onPause": "EngagementMade"       # Criteria 4
        }
    }

    # Initial State
    current_state = "Start"
    
    for method in method_sequence:
        # Check if the method is a valid transition from the current state
        if method in transitions[current_state]:
            # Update state
            current_state = transitions[current_state][method]
        else:
            # INVALID TRANSITION FOUND
            return False, f"FAIL: Invalid transition '{method}' from state '{current_state}'"

    return True, "PASS"


# --- LOG PARSING LOGIC ---
def analyze_log_file(file_path):
    # Dictionary to map Process IDs (PID) to Package Names
    pid_to_package = {}
    
    # Dictionary to store matching logs grouped by package
    package_logs = defaultdict(list)

    # Keywords that MUST be present
    method_keywords = [
        "attachInfo", "build", "initialize", "onAdLoaded", 
        "onAdImpression", "onResume", "onPause", "onDestroy"
    ]

    required_provider = "com.google.android.gms.ads.MobileAdsInitProvider"
    required_header = "SootInjection: Entering method:"

    # Regex patterns
    crash_pattern = re.compile(r'Process:\s*(.*?),\s*PID:\s*(\d+)')
    start_proc_pattern = re.compile(r'Start proc (\d+):([a-zA-Z0-9._]+)/')
    bracket_pattern = re.compile(r'<(.*?)>')

    print(f"\nAnalyzing: {file_path}")
    print("=" * 60)

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # --- PASS 1: Build PID -> Package Map ---
            for line in f:
                if "E AndroidRuntime:" in line and "Process:" in line:
                    match = crash_pattern.search(line)
                    if match:
                        pid_to_package[match.group(2).strip()] = match.group(1).strip()
                
                if "Start proc" in line:
                    match = start_proc_pattern.search(line)
                    if match:
                        pid_to_package[match.group(1).strip()] = match.group(2).strip()

            # --- PASS 2: Collect Filtered Logs ---
            f.seek(0)
            
            for line in f:
                if required_header not in line: continue
                if required_provider not in line: continue
                if not any(k in line for k in method_keywords): continue

                parts = line.split()
                if len(parts) > 2:
                    current_pid = parts[2]
                    
                    if current_pid in pid_to_package:
                        package_name = pid_to_package[current_pid]
                        
                        # Extract method name
                        bracket_match = bracket_pattern.search(line)
                        if bracket_match:
                            full_signature = bracket_match.group(1).strip()
                            if '(' in full_signature:
                                pre_paren = full_signature.split('(')[0]
                                method_name = pre_paren.split()[-1]
                                package_logs[package_name].append(method_name)

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return

    # --- Print Results with Validation ---
    print(f"Found formatted sequences for {len(package_logs)} packages.")
    print("=" * 60)
    
    if package_logs:
        for app in sorted(package_logs.keys()):
            sequence = package_logs[app]
            
            # Run FSM Validation
            is_valid, status_msg = validate_fsm(sequence)
            
            print(f"\nPackage: {app}")
            print(f"Result:  {status_msg}")
            print("-" * 30)
            
            # Print sequence with arrows
            sequence_string = " -> ".join(sequence)
            print(f"Sequence: {sequence_string}")
            
    else:
        print(f"No logs found matching criteria.")

def select_log_file():
    log_dir = "logcat_logs"
    
    if not os.path.exists(log_dir):
        print(f"Error: Directory '{log_dir}' not found.")
        return None
    
    files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
    files.sort() 
    
    if not files:
        print(f"No .log files found in '{log_dir}'.")
        return None

    print(f"\nAvailable Log Files in '{log_dir}':")
    print("-" * 40)
    for index, filename in enumerate(files):
        print(f"{index + 1}. {filename}")
    print("-" * 40)

    while True:
        try:
            choice = input("Enter the number of the log file to analyze: ")
            selection = int(choice)
            if 1 <= selection <= len(files):
                return os.path.join(log_dir, files[selection - 1])
            else:
                print(f"Invalid selection.")
        except ValueError:
            print("Invalid input.")

if __name__ == "__main__":
    target_file = None
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        target_file = select_log_file()
    
    if target_file:
        analyze_log_file(target_file)

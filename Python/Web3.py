import re
import sys
import os
import time
from web3 import Web3

# --- 1. CONFIGURATION ---
LOG_DIR = "logcat_logs"
RPC_URL = "http://127.0.0.1:8545" 
CONTRACT_ADDRESS = "0x5E2fEd8E1B5A440cBFc56E237d53434EaBd4C87a"

# Methods defined in the FSM Model (Triggers)
VALID_FSM_METHODS = {
    "attachInfo", 
    "build", 
    "onAdLoaded", 
    "onAdImpression", 
    "onAdClicked", 
    "show"
}

# --- 2. BLOCKCHAIN SETUP ---
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print(f"Error: Unable to connect to Ganache at {RPC_URL}")
    sys.exit(1)

# Use the first account provided by Ganache
w3.eth.default_account = w3.eth.accounts[0]

# ABI matching the FSMViolationAuditor contract
ABI = [
    {"inputs": [{"internalType": "string", "name": "_pkg", "type": "string"}, {"internalType": "string", "name": "_method", "type": "string"}], "name": "recordTransition", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "getAllApps", "outputs": [{"internalType": "string[]", "name": "", "type": "string[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "string", "name": "_pkg", "type": "string"}], "name": "getAppMethods", "outputs": [{"internalType": "string[]", "name": "", "type": "string[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "string", "name": "_pkg", "type": "string"}], "name": "getViolationStatus", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"}
]

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)

# --- 3. DYNAMIC FILE SELECTION ---
def get_target_log():
    if len(sys.argv) > 1:
        return os.path.join(LOG_DIR, sys.argv[1])
    
    if not os.path.exists(LOG_DIR):
        print(f"Error: Directory '{LOG_DIR}' not found.")
        sys.exit(1)
        
    logs = [f for f in os.listdir(LOG_DIR) if f.endswith('.log')]
    if not logs:
        print(f"No .log files found in {LOG_DIR}")
        sys.exit(1)
        
    print("\nAvailable logs in logcat_logs/:")
    for i, log in enumerate(logs):
        print(f"[{i}] {log}")
    
    choice = input("\nSelect log index to analyze (or type filename): ")
    if choice.isdigit() and int(choice) < len(logs):
        return os.path.join(LOG_DIR, logs[int(choice)])
    return os.path.join(LOG_DIR, choice)

# --- 4. AUDIT & SCRAPING LOGIC ---
def run_fsm_audit(file_path):
    print(f"\n--- Starting FSM Audit: {file_path} ---")
    
    # Regex to identify app process and method entries
    pkg_pattern = re.compile(r"Process:\s+([\w\.]+)")
    method_pattern = re.compile(r"Entering method: <.*:\s+\w+\s+(\w+)\(.*\)>")

    app_last_method = {} 
    current_package = "Unknown"

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                # Update package context
                p_match = pkg_pattern.search(line)
                if p_match:
                    current_package = p_match.group(1)
                    continue
                
                # Identify FSM methods
                m_match = method_pattern.search(line)
                if m_match:
                    method_name = m_match.group(1)
                    
                    if method_name in VALID_FSM_METHODS:
                        # Only push if it's not a repeated consecutive call in the log
                        if app_last_method.get(current_package) != method_name:
                            print(f"[PUSH] {current_package} -> {method_name}")
                            try:
                                # Transaction parameters optimized for Ganache Docker
                                tx_hash = contract.functions.recordTransition(
                                    current_package, method_name
                                ).transact({
                                    'gas': 2000000,
                                    'gasPrice': w3.to_wei('20', 'gwei')
                                })
                                w3.eth.wait_for_transaction_receipt(tx_hash)
                                app_last_method[current_package] = method_name
                            except Exception as e:
                                print(f"Blockchain Write Error: {e}")

        # --- 5. RETRIEVAL & REPORTING ---
        print("\n" + "="*60)
        print("          FINAL AUDIT REPORT (BLOCKCHAIN)")
        print("="*60)
        
        # Small delay for node stability
        time.sleep(1)
        
        all_apps = contract.functions.getAllApps().call()
        if not all_apps:
            print("No app data found on-chain.")
            return

        for app in all_apps:
            history = contract.functions.getAppMethods(app).call()
            violation = contract.functions.getViolationStatus(app).call()
            
            status = "❌ VIOLATION" if violation else "✅ VALID"
            print(f"\nApp: {app}")
            print(f"Status: {status}")
            print(f"Sequence: {' -> '.join(history)}")

    except FileNotFoundError:
        print(f"Error: {file_path} not found.")

if __name__ == "__main__":
    target_file = get_target_log()
    run_fsm_audit(target_file)

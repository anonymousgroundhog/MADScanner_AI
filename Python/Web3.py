import re
import sys
import os
import time
from web3 import Web3

# --- 1. CONFIGURATION ---
LOG_DIR = "logcat_logs"
RPC_URL = "http://127.0.0.1:8545" 
CONTRACT_ADDRESS = "0xCB93edD7B93b903144B700CF8277550d638BF912"

# Model-specific triggers
VALID_FSM_METHODS = {"attachInfo", "build", "onAdLoaded", "onAdImpression", "onAdClicked", "show"}

# --- 2. BLOCKCHAIN SETUP ---
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print(f"Error: Unable to connect to Ganache at {RPC_URL}")
    sys.exit(1)

w3.eth.default_account = w3.eth.accounts[0]

ABI = [
    {"inputs": [{"internalType": "string", "name": "_pkg", "type": "string"}, {"internalType": "string", "name": "_method", "type": "string"}], "name": "recordTransition", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "getAllApps", "outputs": [{"internalType": "string[]", "name": "", "type": "string[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "string", "name": "_pkg", "type": "string"}], "name": "getAppMethods", "outputs": [{"internalType": "string[]", "name": "", "type": "string[]"}], "stateMutability": "view", "type": "function"}
]

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)

# --- 3. DYNAMIC FILE SELECTION ---
def get_target_log():
    # If a filename was passed as a command line argument
    if len(sys.argv) > 1:
        return os.path.join(LOG_DIR, sys.argv[1])
    
    # Otherwise, list files in the directory
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
    
    choice = input("\nSelect log index to analyze (or filename): ")
    if choice.isdigit() and int(choice) < len(logs):
        return os.path.join(LOG_DIR, logs[int(choice)])
    return os.path.join(LOG_DIR, choice)

# --- 4. AUDIT LOGIC ---
def run_fsm_audit(file_path):
    print(f"\n--- Starting Audit: {file_path} ---")
    
    pkg_pattern = re.compile(r"Process:\s+([\w\.]+)")
    method_pattern = re.compile(r"Entering method: <.*:\s+\w+\s+(\w+)\(.*\)>")

    app_last_method = {} 
    current_package = "Unknown"

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                p_match = pkg_pattern.search(line)
                if p_match:
                    current_package = p_match.group(1)
                    continue
                
                m_match = method_pattern.search(line)
                if m_match:
                    method_name = m_match.group(1)
                    if method_name in VALID_FSM_METHODS:
                        if app_last_method.get(current_package) != method_name:
                            print(f"[PUSH] {current_package} -> {method_name}")
                            try:
                                # Optimized for Ganache v7.9.2 Docker
                                tx_hash = contract.functions.recordTransition(
                                    current_package, method_name
                                ).transact({
                                    'gas': 2000000,
                                    'gasPrice': w3.to_wei('20', 'gwei')
                                })
                                w3.eth.wait_for_transaction_receipt(tx_hash)
                                app_last_method[current_package] = method_name
                            except Exception as e:
                                print(f"TX Error: {e}")

        # --- RETRIEVAL ---
        print("\n" + "="*50 + "\nBLOCKCHAIN RESULTS\n" + "="*50)
        time.sleep(1)
        apps = contract.functions.getAllApps().call()
        for app in apps:
            hist = contract.functions.getAppMethods(app).call()
            print(f"\nApp: {app}\nSequence: {' -> '.join(hist)}")

    except FileNotFoundError:
        print(f"Error: {file_path} not found.")

if __name__ == "__main__":
    target_file = get_target_log()
    run_fsm_audit(target_file)

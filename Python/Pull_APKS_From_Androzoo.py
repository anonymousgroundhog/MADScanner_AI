import requests
import csv
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
API_KEY = "YOUR_API_KEY"
CSV_FILE = "latest.csv"
DOWNLOAD_LIMIT = 50       # Total number of APKs you want to get
CONCURRENT_LIMIT = 20     # Strict AndroZoo limit
DOWNLOAD_DIR = "google_play_apks"

def download_one_apk(sha256, pkg_name):
    """Worker function to download a single APK."""
    file_path = os.path.join(DOWNLOAD_DIR, f"{sha256}.apk")
    
    if os.path.exists(file_path):
        return f"[!] Already exists: {pkg_name}"

    base_url = "https://androzoo.uni.lu/api/download"
    params = {'apikey': API_KEY, 'sha256': sha256}

    try:
        with requests.get(base_url, params=params, stream=True, timeout=30) as r:
            if r.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        f.write(chunk)
                return f"[+] Downloaded: {pkg_name}"
            else:
                return f"[-] Failed: {pkg_name} (Status {r.status_code})"
    except Exception as e:
        return f"[!] Error {pkg_name}: {e}"

def main():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # 1. Collect targets first (to avoid keeping the CSV file open during long downloads)
    targets = []
    print(f"[*] Scanning {CSV_FILE} for Google Play apps...")
    
    with open(CSV_FILE, mode='r', encoding='utf-8') as f:
        fieldnames = ['sha256', 'sha1', 'md5', 'apk_size', 'dex_size', 'dex_date', 
                      'pkg_name', 'vercode', 'vt_detection', 'vt_scan_date', 'markets']
        reader = csv.DictReader(f, fieldnames=fieldnames)
        
        for row in reader:
            if len(targets) >= DOWNLOAD_LIMIT:
                break
            
            if 'play.google.com' in (row.get('markets') or ''):
                targets.append((row['sha256'], row['pkg_name']))

    print(f"[*] Found {len(targets)} apps. Starting concurrent download (Max: {CONCURRENT_LIMIT})...")

    # 2. Use ThreadPoolExecutor to manage the 20 concurrent connections
    with ThreadPoolExecutor(max_workers=CONCURRENT_LIMIT) as executor:
        # Map the download function to our targets
        future_to_apk = {executor.submit(download_one_apk, sha, pkg): pkg for sha, pkg in targets}
        
        for future in as_completed(future_to_apk):
            result = future.result()
            print(result)

if __name__ == "__main__":
    main()

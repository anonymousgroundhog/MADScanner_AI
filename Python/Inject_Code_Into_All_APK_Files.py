import subprocess
import os
import sys
import shutil
import argparse
import concurrent.futures


def run_command(command_parts, check_output=False, cwd=None, error_message="Error executing command"):
    """
    Executes a shell command (as a list of parts).

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
            cwd=cwd,
        )
        return process.stdout.strip(), process.stderr.strip()
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {' '.join(command_parts)}", file=sys.stderr)
        print(f"Stdout: {e.stdout.strip()}", file=sys.stderr)
        print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(
            f"Error: Command '{command_parts[0]}' not found. "
            f"Ensure it's in your system's PATH. ({error_message})",
            file=sys.stderr,
        )
        raise


def collect_apk_targets(apk_files_base_dir):
    """
    Scans apk_files_base_dir and returns a list of (apk_path, label) tuples.

    - Bare .apk files at the top level → label is the filename stem.
    - base.apk found anywhere in the tree → label is the immediate parent dir name.

    Uses os.scandir for efficiency and avoids redundant stat calls.
    """
    apk_targets = []
    seen_labels = set()

    # Top-level bare APKs
    with os.scandir(apk_files_base_dir) as it:
        for entry in it:
            if entry.is_file() and entry.name.lower().endswith(".apk"):
                label = os.path.splitext(entry.name)[0]
                apk_targets.append((entry.path, label))
                seen_labels.add(label)

    # base.apk anywhere in the tree
    for root, _dirs, files in os.walk(apk_files_base_dir):
        if "base.apk" in files:
            label = os.path.basename(root)
            if label not in seen_labels:
                apk_targets.append((os.path.join(root, "base.apk"), label))
                seen_labels.add(label)

    return apk_targets


def needs_recompile(java_src, class_file):
    """Returns True if the .class is missing or older than the .java source."""
    if not os.path.exists(class_file):
        return True
    return os.path.getmtime(java_src) > os.path.getmtime(class_file)


def inject_apk(base_apk_input_path, _dir_name, parent_dir, soot_global_output_base_dir):
    """
    Runs LogInjector on a single APK and moves the result into sootOutput/<label>/.

    Returns:
        str: "ok", "skipped", or "failed"
    """
    _specific_soot_output_dest_dir = os.path.join(soot_global_output_base_dir, _dir_name)

    # Skip if already injected
    if os.path.isdir(_specific_soot_output_dest_dir):
        with os.scandir(_specific_soot_output_dest_dir) as it:
            if any(True for _ in it):
                return "skipped"

    try:
        os.makedirs(_specific_soot_output_dest_dir, exist_ok=True)

        loginjector_temp_output_dir = os.path.join(soot_global_output_base_dir, "sootOutput")

        run_command(
            [
                "java", "-Xmx25g",
                "-cp", f"{parent_dir}:" + os.path.join(parent_dir, "Jar_Libs", "*"),
                "LogInjector",
                os.path.join(parent_dir, "Android", "platforms"),
                base_apk_input_path,
            ],
            check_output=True,
            cwd=soot_global_output_base_dir,
            error_message=f"Error running LogInjector on {os.path.basename(base_apk_input_path)}",
        )

        loginjector_output_apk_path = os.path.join(loginjector_temp_output_dir, "base.apk")

        if not os.path.isfile(loginjector_output_apk_path):
            found = (
                [f for f in os.listdir(loginjector_temp_output_dir) if f.endswith(".apk")]
                if os.path.isdir(loginjector_temp_output_dir)
                else []
            )
            if found:
                loginjector_output_apk_path = os.path.join(loginjector_temp_output_dir, found[0])
                print(f"  [{_dir_name}] Expected 'base.apk' not found, using '{found[0]}' instead.")
            else:
                print(
                    f"  ⚠️ [{_dir_name}] LogInjector produced no APK. Cleaning up.",
                    file=sys.stderr,
                )
                shutil.rmtree(_specific_soot_output_dest_dir, ignore_errors=True)
                return "failed"

        final_moved_apk_path = os.path.join(
            _specific_soot_output_dest_dir, os.path.basename(loginjector_output_apk_path)
        )
        shutil.move(loginjector_output_apk_path, final_moved_apk_path)
        shutil.rmtree(loginjector_temp_output_dir, ignore_errors=True)

        print(f"  ✅ [{_dir_name}] Injection complete.")
        return "ok"

    except Exception as e:
        print(f"  ❌ [{_dir_name}] Injection failed: {e}", file=sys.stderr)
        shutil.rmtree(_specific_soot_output_dest_dir, ignore_errors=True)
        return "failed"


def post_process_app(app_name, soot_sub_dir_path, final_output_dir, script_dir, keystore_path):
    """
    Zipaligns, signs, and copies the injected APK for one app.
    Skips APKs that are already signed and copied.

    Returns:
        bool: True on success, False on failure.
    """
    for item_name in os.listdir(soot_sub_dir_path):
        # Skip non-APK files, Info.md, and already-signed APKs
        if not item_name.endswith(".apk") or item_name == "Info.md" or item_name.startswith("signed-"):
            continue

        item_full_path = os.path.join(soot_sub_dir_path, item_name)
        signed_apk_name = f"signed-{item_name}"
        signed_apk_path = os.path.join(soot_sub_dir_path, signed_apk_name)
        final_app_output_dir = os.path.join(final_output_dir, app_name)
        final_signed_copy = os.path.join(final_app_output_dir, signed_apk_name)

        # Skip if already signed and copied to final output
        if os.path.isfile(final_signed_copy):
            print(f"  [{app_name}] Already signed and copied. Skipping.")
            continue

        try:
            run_command(
                ["zipalign", "-fv", "4", item_full_path, signed_apk_path],
                check_output=True,
                cwd=script_dir,
                error_message=f"Error zipaligning '{item_name}'",
            )

            run_command(
                ["apksigner", "sign", "--ks", keystore_path, "--ks-pass", "pass:password", signed_apk_path],
                check_output=True,
                cwd=script_dir,
                error_message=f"Error signing '{signed_apk_name}'",
            )

            # Clean up .idsig files produced by apksigner
            for f in os.listdir(script_dir):
                if f.endswith(".idsig"):
                    os.remove(os.path.join(script_dir, f))

            os.makedirs(final_app_output_dir, exist_ok=True)
            shutil.copy(signed_apk_path, final_app_output_dir)
            print(f"  ✅ [{app_name}] Post-processing complete → {signed_apk_name}")

        except Exception as e:
            print(f"  ❌ [{app_name}] Post-processing failed for '{item_name}': {e}", file=sys.stderr)
            return False

    return True


def print_progress(current, total, failed, label=""):
    bar_width = 30
    filled = int(bar_width * current / total) if total > 0 else 0
    bar = "#" * filled + "-" * (bar_width - filled)
    remaining = total - current
    suffix = f" | {label}" if label else ""
    print(f"\n[{bar}] {current}/{total} | {remaining} left | failed: {failed}{suffix}")


def main():
    parser = argparse.ArgumentParser(description="Inject logging into APK files using Soot.")
    parser.add_argument(
        "--apk-dir",
        default=None,
        help="Path to the directory containing APKs to analyze. "
             "Defaults to '../APK_Files_To_Analyze' relative to this script.",
    )
    parser.add_argument(
        "--post-workers",
        type=int,
        default=4,
        help="Number of parallel workers for post-processing (zipalign/sign). Default: 4.",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, ".."))

    apk_files_base_dir = (
        os.path.abspath(args.apk_dir) if args.apk_dir
        else os.path.join(parent_dir, "APK_Files_To_Analyze")
    )

    final_output_dir = os.path.join(script_dir, "Soot_Output_Injector_APK_Files")
    soot_global_output_base_dir = os.path.join(os.path.dirname(apk_files_base_dir), "sootOutput")
    keystore_path = os.path.join(parent_dir, "my-release-key.keystore")

    print("--- Starting APK LogInjector Automation ---")
    print(f"  APK input  : {apk_files_base_dir}")
    print(f"  Soot output: {soot_global_output_base_dir}")
    print(f"  Final output: {final_output_dir}")

    if not os.path.isdir(apk_files_base_dir):
        print(f"⚠️ Directory '{apk_files_base_dir}' not found.", file=sys.stderr)
        sys.exit(1)

    # --- 1. Compile LogInjector only if source changed ---
    java_src = os.path.join(parent_dir, "Java", "LogInjector.java")
    class_file = os.path.join(parent_dir, "LogInjector.class")
    print("\n📦 Checking LogInjector compilation...")
    try:
        if needs_recompile(java_src, class_file):
            print("  - Compiling Java/LogInjector.java...")
            run_command(
                ["javac", "-cp", os.path.join(parent_dir, "Jar_Libs", "*"),
                 "-d", parent_dir, java_src],
                check_output=True,
                cwd=parent_dir,
                error_message="Error compiling LogInjector.java",
            )
            print("  - Compiled successfully.")
        else:
            print("  - Already up-to-date, skipping recompile.")

        os.makedirs(soot_global_output_base_dir, exist_ok=True)
        os.makedirs(final_output_dir, exist_ok=True)

    except Exception as e:
        print(f"❌ Setup/compilation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # --- 2. Collect APK targets ---
    apk_targets = collect_apk_targets(apk_files_base_dir)
    if not apk_targets:
        print("\n😔 No APK files found. Ensure the directory contains APKs or subdirs with base.apk.")
        sys.exit(0)

    # Separate already-done from pending so the progress bar reflects real work
    pending = []
    already_done = []
    for apk_path, label in apk_targets:
        dest = os.path.join(soot_global_output_base_dir, label)
        if os.path.isdir(dest) and any(True for _ in os.scandir(dest)):
            already_done.append(label)
        else:
            pending.append((apk_path, label))

    total = len(apk_targets)
    if already_done:
        print(f"\n  Skipping {len(already_done)} already-injected APK(s).")
    print(f"  {len(pending)} APK(s) to inject.\n")

    # --- 3. Injection loop (sequential — Soot is memory-heavy, not safe to parallelize) ---
    processed_apks_count = len(already_done)
    failed_count = 0
    number_to_inject = len(pending)

    for i, (base_apk_input_path, _dir_name) in enumerate(pending, start=1):
        print_progress(i - 1, number_to_inject, failed_count, label=_dir_name)
        print(f"--- Injecting '{_dir_name}' ({i}/{number_to_inject}) ---")
        print(f"    Input: {base_apk_input_path}")

        result = inject_apk(base_apk_input_path, _dir_name, parent_dir, soot_global_output_base_dir)
        if result == "ok":
            processed_apks_count += 1
        elif result == "failed":
            failed_count += 1

    # Final injection progress bar
    print_progress(number_to_inject, number_to_inject, failed_count)
    print(f"\n  Injection complete: {processed_apks_count} succeeded, {failed_count} failed.")

    if processed_apks_count == 0:
        print("\n😔 No APKs were successfully injected.")
        sys.exit(0)

    # --- 4. Post-processing: zipalign + sign in parallel ---
    print(f"\n🎉 Starting post-processing with {args.post_workers} worker(s) (zipalign → sign → copy)...")

    sub_dirs = [
        (name, os.path.join(soot_global_output_base_dir, name))
        for name in os.listdir(soot_global_output_base_dir)
        if os.path.isdir(os.path.join(soot_global_output_base_dir, name))
    ]

    post_failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.post_workers) as executor:
        futures = {
            executor.submit(post_process_app, name, path, final_output_dir, script_dir, keystore_path): name
            for name, path in sub_dirs
        }
        for future in concurrent.futures.as_completed(futures):
            app_name = futures[future]
            try:
                if not future.result():
                    post_failed += 1
            except Exception as e:
                print(f"  ❌ [{app_name}] Unexpected post-processing error: {e}", file=sys.stderr)
                post_failed += 1

    # Final .idsig cleanup
    for f in os.listdir(script_dir):
        if f.endswith(".idsig"):
            os.remove(os.path.join(script_dir, f))

    print(f"\n--- Script Finished ---")
    print(f"  Injected      : {processed_apks_count}")
    print(f"  Inject failed : {failed_count}")
    print(f"  Post failed   : {post_failed}")
    print(f"  Output        : {final_output_dir}")


if __name__ == "__main__":
    main()

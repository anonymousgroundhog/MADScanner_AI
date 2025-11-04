# file: Analyze_And_Construct_FSM_Model_From_Log_File_Test.py
#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import sys
import argparse
from collections import defaultdict
from typing import Optional, Iterable, Tuple, List, Dict

LOG_DIR = os.path.join(os.getcwd(), "logcat_logs")

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
FG_CYAN = "\033[36m"
FG_YELLOW = "\033[33m"
FG_MAGENTA = "\033[35m"
FG_GREEN = "\033[32m"

APP_FROM_BG_CLEAN = re.compile(r"PowerController\.BgClean:\s*App:\s*([a-zA-Z][\w.]+)")

# Strict extractor: capture payload between '<' and '>'
SOOT_PAYLOAD = re.compile(
    r"SootInjection:.*?Entering\s+method:\s*<\s*(?P<payload>[^>]+)\s*>\s*",
    re.IGNORECASE,
)

SEVERITY_DEBUG_HEAD = (" D ", " D/")
PID_RE = re.compile(
    r""" ^
         \s*\d{2}-\d{2} \s+ \d{2}:\d{2}:\d{2}\.\d{3}
         \s+ (?P<pid>\d+) \s+ (?P<tid>\d+) \s+ [VDIWEF] \s+ SootInjection:
    """,
    re.VERBOSE,
)

# Matches the LAST token that looks like methodName(...) in the right side
METHOD_CALL = re.compile(r"(?P<sig>([A-Za-z_<>$][\w<>$]*)\s*\([^)]*\))")

# ---- File utils --------------------------------------------------------------

def list_log_files(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    files = [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f)) and f.lower().endswith(".log")
    ]
    files.sort(key=lambda x: x.lower())
    return files

def choose_file(directory: str, files: list[str]) -> Optional[str]:
    print(f"{BOLD}Available .log files in{RESET} {directory}:\n")
    for i, f in enumerate(files, 1):
        print(f"  {FG_CYAN}{i:>2}{RESET}. {f}")
    print()
    while True:
        s = input(f"Enter file number 1-{len(files)} (or 'q' to quit): ").strip()
        if s.lower() in {"q", "quit", "exit"}:
            return None
        if s.isdigit():
            n = int(s)
            if 1 <= n <= len(files):
                return os.path.join(directory, files[n - 1])
        print(f"{FG_YELLOW}Invalid selection.{RESET}")

# ---- Parsing helpers ---------------------------------------------------------

def collect_apps_from_bgclean(lines: Iterable[str]) -> list[str]:
    seen: list[str] = []
    uniq = set()
    for line in lines:
        m = APP_FROM_BG_CLEAN.search(line)
        if m:
            pkg = m.group(1)
            if pkg not in uniq:
                uniq.add(pkg)
                seen.append(pkg)
    return seen

def is_debug_soot_injection(line: str) -> bool:
    if "SootInjection" not in line:
        return False
    head = line[:200]
    return any(marker in head for marker in SEVERITY_DEBUG_HEAD)

def parse_pid(line: str) -> Optional[int]:
    m = PID_RE.match(line)
    if not m:
        return None
    try:
        return int(m.group("pid"))
    except Exception:
        return None

def parse_soot_entering(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Returns (class_fqcn, method_signature, method_name).
    class_fqcn: token before ':' inside '<...>'
    method_signature: last 'name(...)' found before '>'
    method_name: name without args, e.g., 'onCreate', '<init>', 'attachInfo'
    """
    m = SOOT_PAYLOAD.search(line)
    if not m:
        return None
    payload = m.group("payload")
    if ":" not in payload:
        return None
    cls_raw, right = payload.split(":", 1)
    cls_fqcn = cls_raw.strip().replace("$", ".")
    matches = list(METHOD_CALL.finditer(right))
    if not matches:
        return None
    method_sig = matches[-1].group("sig").strip()
    if not method_sig.endswith(")"):
        return None
    method_name = method_sig.split("(", 1)[0].strip()
    return cls_fqcn, method_sig, method_name

def longest_pkg_match(class_name: str, app_pkgs: list[str]) -> Optional[str]:
    cands = [p for p in app_pkgs if class_name.startswith(p + ".") or class_name == p]
    return max(cands, key=len) if cands else None

# ---- Filter builders ---------------------------------------------------------

_GLOB_CACHE: Dict[int, re.Pattern] = {}

def _expand_multi(values: List[str]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        if not v:
            continue
        out.extend([p.strip() for p in v.split(",") if p.strip()])
    return out

def build_class_filters(filters: list[str]) -> list[Tuple[str, str]]:
    out: list[Tuple[str, str]] = []
    for pat in _expand_multi(filters):
        if "*" in pat and not pat.endswith("*"):
            rx = re.compile(pat.replace(".", r"\.").replace("*", ".*"), re.IGNORECASE)
            _GLOB_CACHE[id(rx)] = rx
            out.append(("regex", str(id(rx))))
        elif pat.endswith("*"):
            out.append(("prefix", pat[:-1].lower()))
        else:
            out.append(("substr", pat.lower()))
    return out

def class_matches_filters(cls: str, filters: list[Tuple[str, str]]) -> bool:
    if not filters:
        return True
    s = cls.lower()
    for mode, val in filters:
        if mode == "regex":
            if _GLOB_CACHE[int(val)].search(cls):
                return True
        elif mode == "prefix":
            if s.startswith(val):
                return True
        else:
            if val in s:
                return True
    return False

def build_call_filters(filters: list[str], preset: str) -> List[Tuple[str, str]]:
    """
    Filters applied to calls. Match against any of:
      - method_name (e.g., 'onCreate')
      - 'Class.methodName' (e.g., 'MainActivity.onCreate')
      - 'fully.qualified.Class methodName(' (combined line format)
    Modes: regex (glob), prefix ('foo*'), substring (default). Case-insensitive.
    Preset 'admob' adds common AdMob lifecycle calls from the FSM model.
    """
    preset_items: List[str] = []
    if preset.lower() == "admob":
        preset_items = [
            "attachInfo", "build", "initialize", "onAdLoaded", "onAdImpression",
            "onResume", "onPause", "onDestroy",
        ]
    patterns = _expand_multi(filters) + preset_items
    out: list[Tuple[str, str]] = []
    for pat in patterns:
        if "*" in pat and not pat.endswith("*"):
            rx = re.compile(pat.replace(".", r"\.").replace("*", ".*"), re.IGNORECASE)
            _GLOB_CACHE[id(rx)] = rx
            out.append(("regex", str(id(rx))))
        elif pat.endswith("*"):
            out.append(("prefix", pat[:-1].lower()))
        else:
            out.append(("substr", pat.lower()))
    return out

def call_matches_filters(cls: str, method_sig: str, method_name: str, filters: List[Tuple[str, str]]) -> bool:
    if not filters:
        return True
    s1 = method_name.lower()
    s2 = f"{cls.rsplit('.',1)[-1]}.{method_name}".lower()  # ShortClass.method
    s3 = f"{cls} {method_sig}".lower()
    for mode, val in filters:
        if mode == "regex":
            rx = _GLOB_CACHE[int(val)]
            if rx.search(s1) or rx.search(s2) or rx.search(s3):
                return True
        elif mode == "prefix":
            if s1.startswith(val) or s2.startswith(val) or s3.startswith(val):
                return True
        else:
            if val in s1 or val in s2 or val in s3:
                return True
    return False

# ---- Core analysis -----------------------------------------------------------

def analyze(
    path: str,
    show_sequence: bool,
    seq_limit: int,
    class_filters_raw: list[str],
    call_filters_raw: list[str],
    call_preset: str,
) -> None:
    with open(path, "r", errors="replace") as f:
        all_lines = f.readlines()

    app_pkgs = collect_apps_from_bgclean(all_lines)
    if not app_pkgs:
        print(f"{FG_YELLOW}No apps found via 'PowerController.BgClean: App:' in this log.{RESET}")

    cls_filters = build_class_filters(class_filters_raw)
    call_filters = build_call_filters(call_filters_raw, call_preset)

    # Pass 1: PID→App map (no filters to maximize attribution)
    pid_active_app: Dict[int, str] = {}
    for line in all_lines:
        if not is_debug_soot_injection(line):
            continue
        parsed = parse_soot_entering(line)
        if not parsed:
            continue
        cls, _, _ = parsed
        app = longest_pkg_match(cls, app_pkgs)
        if app:
            pid = parse_pid(line)
            if pid is not None:
                pid_active_app[pid] = app

    # Pass 2: apply filters and aggregate
    app_first_class: Dict[str, str] = {}
    app_sequences: Dict[str, List[Tuple[int, str, str]]] = defaultdict(list)  # (lineno, class, methodSig)
    app_unique_calls: Dict[str, List[str]] = defaultdict(list)               # "Class methodSig"
    app_seen_sig: Dict[str, set] = defaultdict(set)

    for idx, line in enumerate(all_lines, start=1):
        if not is_debug_soot_injection(line):
            continue
        parsed = parse_soot_entering(line)
        if not parsed:
            continue
        cls, method_sig, method_name = parsed

        if not class_matches_filters(cls, cls_filters):
            continue
        if not call_matches_filters(cls, method_sig, method_name, call_filters):
            continue

        app = longest_pkg_match(cls, app_pkgs)
        if not app:
            pid = parse_pid(line)
            if pid is not None and pid in pid_active_app:
                app = pid_active_app[pid]
        if not app:
            continue

        if app not in app_first_class:
            app_first_class[app] = cls  # highlight first class touching the app

        app_sequences[app].append((idx, cls, method_sig))

        sig = f"{cls} {method_sig}"
        if sig not in app_seen_sig[app]:
            app_seen_sig[app].add(sig)
            app_unique_calls[app].append(sig)

    # ---- Output
    print(f"\n{BOLD}File:{RESET} {path}")
    print(f"{BOLD}Apps discovered (from BgClean):{RESET}")
    if app_pkgs:
        for p in app_pkgs:
            print(f"  - {FG_MAGENTA}{p}{RESET}")
    else:
        print(f"  {DIM}(none){RESET}")

    if not app_sequences:
        print(f"\n{BOLD}No filtered SootInjection entries mapped to discovered apps.{RESET}")
        return

    print(f"\n{BOLD}Per-app calls (format: 'Class methodSignature') with first-class highlight:{RESET}")
    for app in sorted(app_sequences.keys(), key=lambda k: (-len(app_sequences[k]), k.lower())):
        seq = app_sequences[app]
        first_cls = app_first_class.get(app, "(unknown)")
        print(f"\n{BOLD}{app}{RESET}  ×{len(seq)}")
        print(f"  First class: {FG_GREEN}{first_cls}{RESET}")
        print(f"  Methods (unique ordered):")
        for sig in app_unique_calls[app]:
            print(f"    - {sig}")
        if show_sequence:
            print(f"  Sequence:")
            for i, (lineno, cls, method_sig) in enumerate(seq[:seq_limit], start=1):
                print(f"    {i:04d}. L{lineno}: {cls} {method_sig}")
            if len(seq) > seq_limit:
                print(f"    {DIM}… {len(seq) - seq_limit} more calls{RESET}")

# ---- CLI ---------------------------------------------------------------------

def build_cli() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="Analyze_And_Construct_FSM_Model_From_Log_File_Test",
        description="Filter per-app sequences by class and specific calls (e.g., MainActivity.onCreate, attachInfo, AdMob FSM calls).",
    )
    ap.add_argument("--logdir", default=LOG_DIR, help="Directory with .log files (default: ./logcat_logs)")
    ap.add_argument(
        "--class-filter",
        action="append",
        default=[],
        help=("Filter by class (ci). Supports substring ('com.google.android'), "
              "prefix with '*' ('com.google.android*'), or glob with '*' anywhere ('com.*.ads'). "
              "Use multiple --class-filter or comma-separated values."),
    )
    ap.add_argument(
        "--call-filter",
        action="append",
        default=[],
        help=("Filter by calls (ci). Match against method name, ShortClass.method, or 'Class methodSig'. "
              "Examples: 'onCreate', 'MainActivity.onCreate', 'attachInfo', 'onAdLoaded', 'initialize', "
              "'*.onPause'. Use multiple flags or comma-separated values. Supports '*' glob and prefix."),
    )
    ap.add_argument(
        "--call-preset",
        choices=["", "admob"],
        default="",
        help="Add a preset set of call names (e.g., 'admob' adds attachInfo/build/initialize/onAdLoaded/onAdImpression/onResume/onPause/onDestroy).",
    )
    ap.add_argument("--show-sequence", action="store_true", help="Also print full chronological sequence per app")
    ap.add_argument("--sequence-limit", type=int, default=2000, help="Max sequence items per app when --show-sequence")
    return ap.parse_args()

def main() -> int:
    args = build_cli()

    files = list_log_files(args.logdir)
    if not files:
        print(f"{FG_YELLOW}No *.log files found in {args.logdir}{RESET}")
        return 1

    path = choose_file(args.logdir, files)
    if not path:
        print("Aborted.")
        return 0

    analyze(
        path=path,
        show_sequence=args.show_sequence,
        seq_limit=args.sequence_limit,
        class_filters_raw=args.class_filter,
        call_filters_raw=args.call_filter,
        call_preset=args.call_preset,
    )
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)

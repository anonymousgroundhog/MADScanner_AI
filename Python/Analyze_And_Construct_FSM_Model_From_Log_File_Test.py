# file: Analyze_And_Construct_FSM_Model_From_Log_File_Test.py
#!/usr/bin/env python3
from __future__ import annotations

import os, re, sys, shutil, subprocess, argparse
from collections import defaultdict
from typing import Optional, Iterable, Tuple, List, Dict

LOG_DIR = os.path.join(os.getcwd(), "logcat_logs")
MODEL_IMG = os.path.join(os.getcwd(), "model.png")

RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
FG_CYAN="\033[36m"; FG_YELLOW="\033[33m"; FG_MAGENTA="\033[35m"; FG_GREEN="\033[32m"

FEW_STATE_THRESHOLD = 3  # small FSMs: render at 50% width

APP_FROM_BG_CLEAN = re.compile(r"PowerController\.BgClean:\s*App:\s*([a-zA-Z][\w.]+)")
SOOT_PAYLOAD = re.compile(r"SootInjection:.*?Entering\s+method:\s*<\s*(?P<payload>[^>]+)\s*>\s*", re.IGNORECASE)
SEVERITY_DEBUG_HEAD = (" D ", " D/")
PID_RE = re.compile(r"""^\s*\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+[VDIWEF]\s+SootInjection:""")
METHOD_CALL = re.compile(r"(?P<sig>([A-Za-z_<>$][\w<>$]*)\s*\([^)]*\))")

# Model methods visible in FSM/report/validation
CORRECT_BEHAVIOR_METHODS = {
    "attachInfo","build","initialize","onAdLoaded","onAdImpression","onResume","onPause","onDestroy",
}

def list_log_files(d: str) -> list[str]:
    if not os.path.isdir(d): return []
    files=[f for f in os.listdir(d) if os.path.isfile(os.path.join(d,f)) and f.lower().endswith(".log")]
    files.sort(key=str.lower); return files

def choose_file(d: str, files: list[str]) -> Optional[str]:
    print(f"{BOLD}Available .log files in{RESET} {d}:\n")
    for i,f in enumerate(files,1): print(f"  {FG_CYAN}{i:>2}{RESET}. {f}")
    print()
    while True:
        s=input(f"Enter file number 1-{len(files)} (or 'q'): ").strip().lower()
        if s in {"q","quit","exit"}: return None
        if s.isdigit() and 1<=int(s)<=len(files): return os.path.join(d,files[int(s)-1])
        print(f"{FG_YELLOW}Invalid selection.{RESET}")

def collect_apps_from_bgclean(lines: Iterable[str]) -> list[str]:
    out,seen=[],set()
    for line in lines:
        m=APP_FROM_BG_CLEAN.search(line)
        if m:
            pkg=m.group(1)
            if pkg not in seen: seen.add(pkg); out.append(pkg)
    return out

def is_debug_soot_injection(line: str) -> bool:
    if "SootInjection" not in line: return False
    return any(marker in line[:200] for marker in SEVERITY_DEBUG_HEAD)

def parse_pid(line: str) -> Optional[int]:
    m=PID_RE.match(line); 
    return int(m.group("pid")) if m else None

def parse_soot_entering(line: str) -> Optional[Tuple[str,str,str]]:
    m=SOOT_PAYLOAD.search(line); 
    if not m: return None
    payload=m.group("payload")
    if ":" not in payload: return None
    cls_raw,right=payload.split(":",1)
    cls_fqcn=cls_raw.strip().replace("$",".")
    matches=list(METHOD_CALL.finditer(right))
    if not matches: return None
    method_sig=matches[-1].group("sig").strip()
    if not method_sig.endswith(")"): return None
    method_name=method_sig.split("(",1)[0].strip()
    return cls_fqcn, method_sig, method_name

def longest_pkg_match(class_name: str, app_pkgs: list[str]) -> Optional[str]:
    c=[p for p in app_pkgs if class_name.startswith(p+".") or class_name==p]
    return max(c, key=len) if c else None

_GLOB_CACHE: Dict[int, re.Pattern] = {}

def _dedupe_order(items: List[str]) -> List[str]:
    seen=set(); out=[]
    for x in items:
        if x not in seen: seen.add(x); out.append(x)
    return out

def _expand_multi(values: List[str]) -> List[str]:
    out=[]
    for v in values or []:
        if v: out += [p.strip() for p in v.split(",") if p.strip()]
    return _dedupe_order(out)

def build_class_filters(filters: list[str]) -> list[Tuple[str,str]]:
    out=[]
    for pat in _expand_multi(filters):
        if "*" in pat and not pat.endswith("*"):
            rx=re.compile(pat.replace(".",r"\.").replace("*",".*"), re.IGNORECASE)
            _GLOB_CACHE[id(rx)]=rx; out.append(("regex",str(id(rx))))
        elif pat.endswith("*"):
            out.append(("prefix",pat[:-1].lower()))
        else:
            out.append(("substr",pat.lower()))
    return out

def class_matches_filters(cls: str, filters: list[Tuple[str,str]]) -> bool:
    if not filters: return True
    s=cls.lower()
    for mode,val in filters:
        if mode=="regex" and _GLOB_CACHE[int(val)].search(cls): return True
        if mode=="prefix" and s.startswith(val): return True
        if mode=="substr" and val in s: return True
    return False

def build_call_filters(filters: list[str], preset: str) -> List[Tuple[str,str]]:
    preset_items = sorted(CORRECT_BEHAVIOR_METHODS) if preset.lower()=="admob" else []
    out=[]
    for pat in _expand_multi(filters)+preset_items:
        if "*" in pat and not pat.endswith("*"):
            rx=re.compile(pat.replace(".",r"\.").replace("*",".*"), re.IGNORECASE)
            _GLOB_CACHE[id(rx)]=rx; out.append(("regex",str(id(rx))))
        elif pat.endswith("*"):
            out.append(("prefix",pat[:-1].lower()))
        else:
            out.append(("substr",pat.lower()))
    return _dedupe_order(out)

def call_matches_filters(cls: str, method_sig: str, method_name: str, filters: List[Tuple[str,str]]) -> bool:
    if not filters: return True
    s1=method_name.lower()
    s2=f"{cls.rsplit('.',1)[-1]}.{method_name}".lower()
    s3=f"{cls} {method_sig}".lower()
    for mode,val in filters:
        if mode=="regex":
            rx=_GLOB_CACHE[int(val)]
            if rx.search(s1) or rx.search(s2) or rx.search(s3): return True
        elif mode=="prefix":
            if s1.startswith(val) or s2.startswith(val) or s3.startswith(val): return True
        else:
            if val in s1 or val in s2 or val in s3: return True
    return False

# ---------------------------- FSM ----------------------------
FSM_STATES = {
    "STARTED": "The app has started",
    "ADVIEW_SET": "The app has started and an adView was set",
    "NO_ADS": "The app has started with no Ads displayed",
    "ADS_DISPLAYED": "The app has started with Ads displayed",
    "RUNNING_LOADED": "The app is running and the advertisement is loaded",
    "RUNNING_ENGAGEMENT": "The app is running and the advertisement engagement is made",
    "RUNNING_IMPRESSION": "The app is running and the advertisement impression is made",
    "DESTROYED": "onDestroy()",
}
STATE_ORDER = ["STARTED","NO_ADS","ADVIEW_SET","ADS_DISPLAYED",
               "RUNNING_LOADED","RUNNING_ENGAGEMENT","RUNNING_IMPRESSION","DESTROYED"]
STATE_RANK = {s:i for i,s in enumerate(STATE_ORDER)}

def _event_to_state(prev: str, event: str) -> str:
    e=event.lower()
    if e=="build": return "ADVIEW_SET"
    if e=="initialize": return "NO_ADS" if prev in {"STARTED","ADVIEW_SET"} else prev
    if e=="onadloaded": return "ADS_DISPLAYED" if prev in {"STARTED","ADVIEW_SET","NO_ADS"} else "RUNNING_LOADED"
    if e=="onresume": return "RUNNING_LOADED"
    if e=="onpause": return "RUNNING_ENGAGEMENT" if prev=="RUNNING_LOADED" else "ADS_DISPLAYED"
    if e=="onadimpression": return "RUNNING_IMPRESSION"
    if e=="ondestroy": return "DESTROYED"
    if e=="attachinfo": return "STARTED" if prev=="STARTED" else prev  # keep state after launch
    return prev

def fsm_from_sequence(seq: List[Tuple[int,str,str]], dedupe_inside_edge: bool=True
) -> Tuple[Dict[str,str], Dict[Tuple[str,str], List[str]]]:
    nodes={"STARTED":FSM_STATES["STARTED"]}
    edges_map: Dict[Tuple[str,str], List[str]] = {}
    current="STARTED"

    for _, _cls, method_sig in seq:
        method_name = method_sig.split("(",1)[0]
        nxt = _event_to_state(current, method_name)
        if nxt not in nodes: nodes[nxt]=FSM_STATES.get(nxt,nxt)
        key=(current,nxt)
        if key not in edges_map: edges_map[key]=[]

        # Only label attachInfo while at STARTED
        if method_name=="attachInfo" and current!="STARTED":
            current=nxt; continue

        if (not dedupe_inside_edge) or (method_name not in edges_map[key]):
            edges_map[key].append(method_name)
        current=nxt
    return nodes, edges_map

def emit_graphviz_dot(app: str, nodes: Dict[str,str], edges_map: Dict[Tuple[str,str], List[str]]) -> Tuple[str,int]:
    safe=app.replace(".","_").replace("-","_")
    lines=['digraph "'+safe+'" {','  rankdir=LR;','  node [shape=circle, fontsize=12];']
    for sid,label in nodes.items():
        if sid=="STARTED":
            lines.append(f'  "{sid}" [label="{label}", style=filled, fillcolor="#8EE88E"];')
        else:
            lines.append(f'  "{sid}" [label="{label}"];')
    drawn=0
    for (a,b), names in edges_map.items():
        lbls=[f"{n}()" for n in names if n in CORRECT_BEHAVIOR_METHODS]
        if not lbls: continue
        lines.append(f'  "{a}" -> "{b}" [label="'+"\\n".join(lbls)+'"];')
        drawn+=1
    lines.append("}")
    return "\n".join(lines), drawn

# ---------------------------- Validation ----------------------------
def validate_correct_behavior(seq: List[Tuple[int,str,str]]) -> Tuple[bool,List[str]]:
    """
    1) No reverse transitions w.r.t STATE_ORDER,
       EXCEPT allow ADVIEW_SET -> NO_ADS when triggered by initialize().
    2) Ordering pairs enforced: attachInfo→build, build→onAdLoaded, onAdLoaded→onAdImpression.
    """
    filtered = [(ln,c,ms) for (ln,c,ms) in seq if ms.split("(",1)[0] in CORRECT_BEHAVIOR_METHODS]
    if not filtered:
        return False, ["No model-relevant methods found"]

    issues: List[str] = []
    cur="STARTED"
    for _, _, ms in filtered:
        m = ms.split("(",1)[0]
        nxt = _event_to_state(cur, m)
        # Reverse transition check with permitted exception
        if STATE_RANK[nxt] < STATE_RANK[cur]:
            if not (m=="initialize" and cur=="ADVIEW_SET" and nxt=="NO_ADS"):  # allowed post-build init
                issues.append(f"Reverse transition: {FSM_STATES[cur]} --{m}()--> {FSM_STATES[nxt]}")
        cur = nxt

    # Simple ordering checks (only if both exist)
    names=[ms.split("(",1)[0] for _,_,ms in filtered]
    pos: Dict[str,List[int]] = defaultdict(list)
    for i,n in enumerate(names): pos[n].append(i)
    for a,b in [("attachInfo","build"),("build","onAdLoaded"),("onAdLoaded","onAdImpression")]:
        if pos[a] and pos[b] and not any(i<j for i in pos[a] for j in pos[b]):
            issues.append(f"Ordering: {a}() occurs after {b}()")

    return (not issues), issues

# ---------------------------- Rendering ----------------------------
def render_dot_to_png(dot_text: str, png_path: str) -> bool:
    dot=shutil.which("dot")
    if not dot: return False
    try:
        subprocess.run([dot,"-Tpng","-o",png_path], input=dot_text.encode("utf-8"), check=True)
    except Exception:
        return False
    return os.path.isfile(png_path)

def write_html_report(out_dir: str, app_cards: List[Dict[str,str]]) -> str:
    model_block = f"<img src='{os.path.relpath(MODEL_IMG,out_dir)}' alt='Correct behavior model' style='max-width:100%;height:auto;border-radius:10px;border:1px solid #eee'/>" if os.path.isfile(MODEL_IMG) else "<div class='meta'>model.png not found; place it next to the script.</div>"
    html=[]
    html.append("<!doctype html><html><head><meta charset='utf-8'><title>FSM Report</title>")
    html.append("""
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Helvetica,Arial,sans-serif;background:#f7f7f7;margin:0;padding:24px;line-height:1.35}
h1{margin:0 0 16px 0}
.section{margin-bottom:18px}
.model{background:#fff;border-radius:14px;box-shadow:0 4px 14px rgba(0,0,0,.08);padding:16px}
.list{display:flex;flex-direction:column;gap:16px;}
.card{background:#fff;border-radius:14px;box-shadow:0 4px 14px rgba(0,0,0,.08);padding:16px}
.badge{display:inline-block;border-radius:999px;padding:4px 10px;font-weight:600;font-size:12px}
.badge.pass{background:#e7f9ee;color:#0b7a35;border:1px solid #bfe8cf}
.badge.fail{background:#fde8e7;color:#8b1a14;border:1px solid #f5c3bf}
.meta{color:#555;font-size:12px;margin-top:6px}
img.fsm{width:100%;height:auto;border-radius:10px;border:1px solid #eee;background:#fff}
img.fsm.half{width:50vw;max-width:50vw;display:block;margin:0 auto;}
.err{color:#8b1a14;font-size:12px;margin-top:8px;white-space:pre-wrap}
</style>""")
    html.append("</head><body>")
    html.append("<h1>Per-App FSM Report</h1>")
    html.append("<div class='section model'><h2>Correct Behavior Model</h2>"+model_block+"</div>")
    html.append("<div class='list'>")
    for c in app_cards:
        half="half" if c.get("few_states")=="1" else ""
        html.append("<div class='card'>")
        html.append(f"<div style='display:flex;justify-content:space-between;align-items:center'><div style='font-weight:700'>{c['app']}</div><div class='badge {'pass' if c['pass']=='PASS' else 'fail'}'>{c['pass']}</div></div>")
        if c.get("png_rel"): html.append(f"<img class='fsm {half}' src='{c['png_rel']}' alt='FSM for {c['app']}'>")
        else: html.append("<div class='meta'>No PNG image available (Graphviz not found). DOT emitted.</div>")
        html.append(f"<div class='meta'>Nodes: {c['nodes']} • Edges: {c['edges']} (drawn)</div>")
        if c.get("issues"): html.append(f"<div class='err'>{c['issues']}</div>")
        html.append("</div>")
    html.append("</div></body></html>")
    path=os.path.join(out_dir,"report.html")
    with open(path,"w",encoding="utf-8") as fh: fh.write("\n".join(html))
    return path

# ---------------------------- Core ----------------------------
def analyze(
    path: str, show_sequence: bool, seq_limit: int,
    class_filters_raw: list[str], call_filters_raw: list[str], call_preset: str,
    emit_fsm: bool, emit_fsm_html: bool, out_dir: str, fsm_no_dedupe: bool,
) -> None:
    with open(path,"r",errors="replace") as f: lines=f.readlines()
    app_pkgs=collect_apps_from_bgclean(lines)
    if not app_pkgs: print(f"{FG_YELLOW}No apps found via 'PowerController.BgClean: App:' in this log.{RESET}")
    cls_filters=build_class_filters(class_filters_raw)
    call_filters=build_call_filters(call_filters_raw, call_preset)

    pid_active: Dict[int,str]={}
    for line in lines:
        if not is_debug_soot_injection(line): continue
        parsed=parse_soot_entering(line); 
        if not parsed: continue
        cls,_,_=parsed
        app=longest_pkg_match(cls,app_pkgs)
        if app:
            pid=parse_pid(line)
            if pid is not None: pid_active[pid]=app

    app_first: Dict[str,str]={}
    app_seq: Dict[str,List[Tuple[int,str,str]]]=defaultdict(list)
    seen_sig: Dict[str,set]=defaultdict(set)

    for i,line in enumerate(lines,1):
        if not is_debug_soot_injection(line): continue
        parsed=parse_soot_entering(line)
        if not parsed: continue
        cls,method_sig,method_name=parsed
        if not class_matches_filters(cls,cls_filters): continue
        if not call_matches_filters(cls,method_sig,method_name,call_filters): continue
        app=longest_pkg_match(cls,app_pkgs) or (pid_active.get(parse_pid(line)) if parse_pid(line) in pid_active else None)
        if not app: continue
        if app not in app_first: app_first[app]=cls
        app_seq[app].append((i,cls,method_sig))
        sig=f"{cls} {method_sig}"
        if sig not in seen_sig[app]: seen_sig[app].add(sig)

    print(f"\n{BOLD}File:{RESET} {path}")
    print(f"{BOLD}Apps discovered (from BgClean):{RESET}")
    if app_pkgs: 
        for p in app_pkgs: print(f"  - {FG_MAGENTA}{p}{RESET}")
    else: print(f"  {DIM}(none){RESET}")

    if not app_seq:
        print(f"\n{BOLD}No filtered SootInjection entries mapped to discovered apps.{RESET}")
        return

    print(f"\n{BOLD}Per-app calls with first-class highlight (model methods only):{RESET}")
    os.makedirs(out_dir,exist_ok=True)
    cards: List[Dict[str,str]]=[]

    for app in sorted(app_seq.keys(), key=lambda k:(-len(app_seq[k]),k.lower())):
        raw=app_seq[app]
        seq=[(ln,c,ms) for (ln,c,ms) in raw if ms.split("(",1)[0] in CORRECT_BEHAVIOR_METHODS]
        first_cls=app_first.get(app,"(unknown)")
        print(f"\n{BOLD}{app}{RESET}  ×{len(seq)} (model-filtered)")
        print(f"  First class: {FG_GREEN}{first_cls}{RESET}")
        print("  Methods (unique ordered):")
        seen_line=set()
        for ln,cls,ms in seq:
            sig=f"{cls} {ms}"
            if sig in seen_line: continue
            seen_line.add(sig); print(f"    - {sig}")
        if show_sequence:
            print("  Sequence:")
            for j,(ln,cls,ms) in enumerate(seq[:seq_limit],1):
                print(f"    {j:04d}. L{ln}: {cls} {ms}")
            if len(seq)>seq_limit: print(f"    {DIM}… {len(seq)-seq_limit} more calls{RESET}")

        nodes, edges_map = fsm_from_sequence(seq, dedupe_inside_edge=not fsm_no_dedupe)

        # render
        png_rel, drawn_edges = "", 0
        if emit_fsm or emit_fsm_html:
            dot, drawn_edges = emit_graphviz_dot(app, nodes, edges_map)
            safe=app.replace(".","_").replace("-","_")
            dot_path=os.path.join(out_dir, f"fsm_{safe}.dot")
            with open(dot_path,"w",encoding="utf-8") as fh: fh.write(dot)
            png_path=os.path.join(out_dir, f"fsm_{safe}.png")
            if render_dot_to_png(dot, png_path): png_rel=os.path.basename(png_path)

        # validate (with allowed initialize back-edge)
        passed, issues = validate_correct_behavior(seq)
        status="PASS" if passed else "FAIL"
        issues_str=" • ".join(issues) if issues else ""

        few_states="1" if len(nodes)<=FEW_STATE_THRESHOLD else "0"
        if emit_fsm_html:
            cards.append({
                "app":app,"nodes":str(len(nodes)),"edges":str(drawn_edges),
                "png_rel":png_rel,"pass":status,"issues":issues_str,"few_states":few_states
            })

    if emit_fsm_html:
        report=write_html_report(out_dir,cards)
        print(f"\n{BOLD}HTML report:{RESET} {report}")

def build_cli() -> argparse.ArgumentParser:
    ap=argparse.ArgumentParser(
        prog="Analyze_And_Construct_FSM_Model_From_Log_File_Test",
        description="FSM builder with forward-only validation (+ allowed initialize ADVIEW_SET→NO_ADS).",
    )
    ap.add_argument("--logdir", default=LOG_DIR)
    ap.add_argument("--class-filter", action="append", default=[])
    ap.add_argument("--call-filter", action="append", default=[])
    ap.add_argument("--call-preset", choices=["","admob"], default="")
    ap.add_argument("--show-sequence", action="store_true")
    ap.add_argument("--sequence-limit", type=int, default=2000)
    ap.add_argument("--emit-fsm", action="store_true")
    ap.add_argument("--emit-fsm-html", action="store_true")
    ap.add_argument("--out-dir", default="./fsm_out")
    ap.add_argument("--fsm-no-dedupe", action="store_true")
    return ap

def main()->int:
    args=build_cli().parse_args()
    files=list_log_files(args.logdir)
    if not files:
        print(f"{FG_YELLOW}No *.log files found in {args.logdir}{RESET}"); return 1
    path=choose_file(args.logdir, files)
    if not path: print("Aborted."); return 0
    analyze(
        path, args.show_sequence, args.sequence_limit,
        args.class_filter, args.call_filter, args.call_preset,
        args.emit_fsm, args.emit_fsm_html, args.out_dir, args.fsm_no_dedupe,
    ); return 0

if __name__=="__main__":
    try: sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted."); sys.exit(130)

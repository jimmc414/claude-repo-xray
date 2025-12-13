This is an excellent, high-value review. You have correctly identified that **Cyclomatic Complexity (CC) is a necessary but insufficient signal**. A file can be architecturally critical (the "Backbone") or historically volatile (the "Problem Child") without having high branching logic.

I fully accept the proposal to integrate **Temporal Signals** (Git) and **Topological Weights** (Dependency Graph) into the targeting mechanism. This transforms Phase 2 from a "complexity scanner" into a **Unified Targeting System**.

Here is the finalized plan and implementation.

-----

# Part 1: Phase 1 Integration Plan (The Temporal Upgrade)

We will upgrade the existing `repo-xray` skill to extract historical and topological signals. These provide immediate value in the `WARM_START.md` and serve as raw data for Phase 2.

### 1\. New Tool: `git_analysis.py`

**Location**: `.claude/skills/repo-xray/scripts/git_analysis.py`
**Purpose**: Extract behavioral history without reading code.
**Features**:

  * `--risk`: Calculates score based on Churn (frequency), Entropy (unique authors), and Hotfix keywords.
  * `--coupling`: Finds files that change together (temporal coupling) to uncover hidden dependencies.
  * `--freshness`: Categorizes files as Active, Aging, Stale, or Dormant.

### 2\. Update Tool: `dependency_graph.py`

**Features**:

  * `--orphans`: Identifies non-entry-point files with zero inbound imports (Dead Code candidates).
  * `--impact <file>`: Calculates "Blast Radius" (count of transitive dependents).

### 3\. Update Artifact: `WARM_START.md`

**Additions**:

  * **High Risk Files**: Table of volatile files.
  * **Hidden Coupling**: Files that change together.
  * **Potential Dead Code**: Orphans + Dormant files.

-----

# Part 2: Phase 2 Implementation Plan (The Semantic Investigator)

Phase 2 is now driven by a **Unified Priority Score (UPS)**.

### 1\. New Agent: `repo_investigator`

**Strategy**: "Triangulate, Trace, Verify".

  * **Triangulate**: Calculate UPS using `complexity.py --unified`.
  * **Trace**: Surgical read using `smart_read.py --focus-top`.
  * **Verify**: Safety check using `verify.py --safe`.

### 2\. Tooling Enhancements

  * **`complexity.py`**: Now accepts Phase 1 JSONs. Implements the reviewer's formula:
    $$ \text{UPS} = (CC_{norm} \times 0.35) + (Impact_{norm} \times 0.25) + (Risk_{norm} \times 0.25) + (Freshness_{score} \times 0.15) $$
  * **`smart_read.py`**: Added `--focus-top N` to auto-expand complex methods, reducing agent friction.
  * **`verify.py`**: Added `--safe` (AST-only) vs `--strict` (Runtime) modes.

-----

# Part 3: Implementation Code

### 1\. Phase 1 Tool: `git_analysis.py`

```python
#!/usr/bin/env python3
"""
Repo X-Ray: Git Analysis
Extracts historical signals: Risk, Coupling, and Freshness.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List

def run_git(cmd: List[str], cwd: str) -> str:
    try:
        # Use ISO-8859-1 to avoid decoding errors on binary filenames in history
        return subprocess.check_output(
            ["git"] + cmd, cwd=cwd, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace").strip()
    except subprocess.CalledProcessError:
        return ""

def get_files_list(cwd: str) -> List[str]:
    raw = run_git(["ls-files", "*.py"], cwd)
    return [f for f in raw.splitlines() if f.strip()]

def analyze_risk(cwd: str, files: List[str]) -> List[Dict]:
    """Calculate Risk Score based on Churn, Author Entropy, and Hotfixes."""
    # Use a safe delimiter for parsing logs
    log = run_git(["log", "--since=6.months", "--name-only", "--format=COMMIT::%an::%s"], cwd)
    
    stats = defaultdict(lambda: {"commits": 0, "authors": set(), "hotfixes": 0})
    current_author = ""
    is_hotfix = False
    
    for line in log.splitlines():
        if line.startswith("COMMIT::"):
            parts = line.split("::")
            if len(parts) >= 3:
                current_author = parts[1]
                subject = parts[2].lower()
                is_hotfix = any(w in subject for w in ["fix", "bug", "urgent", "revert", "hotfix"])
        elif line.strip() and line.endswith(".py"):
            f = line.strip()
            # Only track currently existing files
            if f in files: 
                s = stats[f]
                s["commits"] += 1
                s["authors"].add(current_author)
                if is_hotfix: s["hotfixes"] += 1

    results = []
    if not stats: return []
    
    max_churn = max(s["commits"] for s in stats.values())
    
    for f, s in stats.items():
        churn_norm = s["commits"] / max_churn
        author_score = min(len(s["authors"]), 5) / 5.0
        hotfix_score = min(s["hotfixes"], 3) / 3.0
        
        # Risk Formula: 40% Churn, 40% Hotfixes, 20% Authors
        risk = (churn_norm * 0.4) + (hotfix_score * 0.4) + (author_score * 0.2)
        
        if risk > 0.1:
            results.append({
                "file": f,
                "risk_score": round(risk, 2),
                "churn": s["commits"],
                "hotfixes": s["hotfixes"],
                "authors": len(s["authors"])
            })
            
    return sorted(results, key=lambda x: x['risk_score'], reverse=True)

def analyze_coupling(cwd: str) -> List[Dict]:
    """Find files that change together."""
    # Last 200 commits is usually sufficient for recent logical coupling
    log = run_git(["log", "-n", "200", "--name-only", "--format=COMMIT"], cwd)
    
    commits = []
    current_files = set()
    
    for line in log.splitlines():
        if line == "COMMIT":
            if current_files: commits.append(list(current_files))
            current_files = set()
        elif line.strip().endswith(".py"):
            current_files.add(line.strip())
    if current_files: commits.append(list(current_files))
    
    pairs = Counter()
    for files in commits:
        if len(files) > 20: continue # Skip bulk refactors
        files.sort()
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                pairs[(files[i], files[j])] += 1
                
    results = []
    for (f1, f2), count in pairs.most_common(20):
        if count >= 3:
            results.append({"file_a": f1, "file_b": f2, "count": count})
    return results

def analyze_freshness(cwd: str, files: List[str]) -> Dict:
    """Categorize by last modification time."""
    # Efficient single-pass for last modified timestamps
    log = run_git(["log", "--name-only", "--format=COMMIT::%ct"], cwd)
    
    last_seen = {}
    current_ts = 0
    
    for line in log.splitlines():
        if line.startswith("COMMIT::"):
            try: current_ts = int(line.split("::")[1])
            except: pass
        elif line.strip() and line.endswith(".py"):
            f = line.strip()
            if f not in last_seen:
                last_seen[f] = current_ts

    now = datetime.now().timestamp()
    res = {"active": [], "aging": [], "stale": [], "dormant": []}
    
    for f in files:
        ts = last_seen.get(f, now)
        days = (now - ts) / 86400
        entry = {"file": f, "days": int(days)}
        
        if days < 30: res["active"].append(entry)
        elif days < 90: res["aging"].append(entry)
        elif days < 180: res["stale"].append(entry)
        else: res["dormant"].append(entry)
        
    return res

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", default=".", nargs="?")
    parser.add_argument("--risk", action="store_true")
    parser.add_argument("--coupling", action="store_true")
    parser.add_argument("--freshness", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if not os.path.exists(os.path.join(args.directory, ".git")):
        if args.json: print("{}"); return
        print("Error: Not a git repository.", file=sys.stderr); return

    files = get_files_list(args.directory)
    out = {}
    
    if args.risk or args.json: out["risk"] = analyze_risk(args.directory, files)
    if args.coupling or args.json: out["coupling"] = analyze_coupling(args.directory)
    if args.freshness or args.json: out["freshness"] = analyze_freshness(args.directory, files)
    
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if "risk" in out:
            print(f"{'RISK':<6} {'FILE':<50} {'FACTORS'}")
            for r in out["risk"][:10]:
                print(f"{r['risk_score']:<6} {r['file']:<50} churn:{r['churn']} hotfix:{r['hotfixes']}")
        if "coupling" in out:
            print("\n=== COUPLING ===")
            for c in out["coupling"]:
                print(f"{c['count']:<4} {c['file_a']} <-> {c['file_b']}")

if __name__ == "__main__":
    main()
```

### 2\. Phase 2 Tool: `complexity.py` (Unified Targeter)

```python
#!/usr/bin/env python3
"""
Repo Investigator: Unified Complexity Scanner
Calculates "Unified Priority Score" using CC, Import Weight, Risk, and Freshness.
"""
import ast
import json
import argparse
import os
import sys

def calculate_cc(filepath):
    """Calculate raw Cyclomatic Complexity."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f: tree = ast.parse(f.read())
        score = 0
        methods = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
                        cc += 1
                    elif isinstance(child, ast.BoolOp):
                        cc += len(child.values) - 1
                if cc > 3: methods[node.name] = cc
                score += cc
        return score, methods
    except:
        return 0, {}

def normalize(values_dict):
    if not values_dict: return {}
    m = max(values_dict.values())
    return {k: v/m for k,v in values_dict.items()} if m > 0 else {k:0 for k in values_dict}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default=".")
    parser.add_argument("--unified", nargs=2, metavar=('DEPS_JSON', 'GIT_JSON'), help="Phase 1 JSON outputs")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # Load Context
    imports = {}
    risks = {}
    freshness_map = {}
    
    if args.unified:
        try:
            with open(args.unified[0]) as f: 
                deps = json.load(f)
                for mod, info in deps.get('modules', {}).items():
                    imports[info['file']] = len(info.get('imported_by', []))
            
            with open(args.unified[1]) as f: 
                git = json.load(f)
                for r in git.get('risk', []): risks[r['file']] = r['risk_score']
                
                # Freshness scoring: Active=1.0, Aging=0.7, Stale=0.4, Dormant=0.1
                f_data = git.get('freshness', {})
                for cat, score in [('active', 1.0), ('aging', 0.7), ('stale', 0.4), ('dormant', 0.1)]:
                    for item in f_data.get(cat, []):
                        freshness_map[item['file']] = score
        except Exception as e:
            print(f"Warning: Failed to load context: {e}", file=sys.stderr)

    # Scan Files
    raw_cc = {}
    hotspots = {}
    
    for root, _, files in os.walk(args.directory):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                cc, methods = calculate_cc(path)
                if cc > 0:
                    raw_cc[path] = cc
                    hotspots[path] = methods

    # Unified Scoring
    norm_cc = normalize(raw_cc)
    norm_imp = normalize(imports)
    # Risk is already normalized 0-1
    
    final_scores = []
    
    for path, cc_val in raw_cc.items():
        # Match paths (simple relative path check)
        rel_path = os.path.relpath(path, args.directory)
        if rel_path.startswith("./"): rel_path = rel_path[2:]
        
        s_cc = norm_cc.get(path, 0)
        s_imp = norm_imp.get(path, 0) # Fallback to 0 if not in graph
        s_risk = risks.get(rel_path, 0)
        s_fresh = freshness_map.get(rel_path, 0.5) # Default to mid if unknown
        
        # REVIEWER REQUESTED FORMULA:
        # Priority = (CC * 0.35) + (Import * 0.25) + (Risk * 0.25) + (Freshness * 0.15)
        score = (s_cc * 0.35) + (s_imp * 0.25) + (s_risk * 0.25) + (s_fresh * 0.15)
        
        final_scores.append({
            "path": path,
            "score": round(score, 3),
            "metrics": {"cc": cc_val, "imp_score": round(s_imp, 2), "risk": s_risk, "freshness": s_fresh},
            "hotspots": hotspots[path]
        })

    final_scores.sort(key=lambda x: x['score'], reverse=True)
    top = final_scores[:args.top]

    if args.json:
        print(json.dumps(top, indent=2))
    else:
        print(f"{'SCORE':<6} {'FILE':<50} {'DETAILS'}")
        for r in top:
            m = r['metrics']
            print(f"{r['score']:<6} {r['path']:<50} CC:{m['cc']} Imp:{m['imp_score']} Risk:{m['risk']}")

if __name__ == "__main__":
    main()
```

### 3\. Phase 2 Tool: `smart_read.py` (Auto-Focus)

```python
#!/usr/bin/env python3
"""
Repo Investigator: Smart Reader
Auto-detects and extracts complex methods while skeletonizing the rest.
"""
import ast
import sys
import argparse
from typing import Set

def get_complexity(node):
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
            cc += 1
    return cc

def get_source(lines, node):
    start = node.lineno - 1
    if hasattr(node, 'decorator_list') and node.decorator_list:
        start = node.decorator_list[0].lineno - 1
    return lines[start : node.end_lineno]

def smart_read(filepath, focus_top=0):
    try:
        with open(filepath, 'r', encoding='utf-8') as f: source = f.read()
    except Exception as e: return f"Error: {e}"
    
    lines = source.splitlines()
    tree = ast.parse(source)
    
    focus_methods = set()
    if focus_top > 0:
        candidates = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates.append((node.name, get_complexity(node)))
        candidates.sort(key=lambda x: x[1], reverse=True)
        focus_methods = {c[0] for c in candidates[:focus_top]}

    output = []
    
    for node in tree.body:
        # Keep imports and constants
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)):
            output.extend(get_source(lines, node))
            continue

        if isinstance(node, ast.ClassDef):
            output.append(f"\nclass {node.name}:")
            has_visible = False
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name in focus_methods:
                        output.extend(get_source(lines, child))
                        has_visible = True
                    else:
                        sig = lines[child.lineno-1].strip().split(':')[0]
                        output.append(f"    {sig} ... # L{child.lineno}")
                elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                    output.append("    " + lines[child.lineno-1].strip())
            if not has_visible: output.append("    # ... (Interface only)")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in focus_methods:
                output.append("")
                output.extend(get_source(lines, node))
            else:
                sig = lines[node.lineno-1].split(':')[0]
                output.append(f"{sig} ... # L{node.lineno}")

    return "\n".join(output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--focus-top", type=int, default=3)
    args = parser.parse_args()
    print(smart_read(args.file, args.focus_top))
```

### 4\. Phase 2 Tool: `verify.py` (Safe Verifier)

```python
#!/usr/bin/env python3
"""
Repo Investigator: Verifier
Tier 1: AST Check (Safe). Tier 2: Import Check (Strict).
"""
import ast
import importlib
import sys
import os
import argparse

def check_safe(path):
    if not os.path.exists(path): return False, "File not found"
    try:
        with open(path, 'r', encoding='utf-8') as f: tree = ast.parse(f.read())
    except Exception as e: return False, f"AST Parse Error: {e}"
    
    # Check if imported modules exist on disk (simple heuristic)
    missing = []
    root = os.getcwd()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = node.module if hasattr(node, 'module') else node.names[0].name
            if not mod or mod in sys.stdlib_module_names: continue
            
            # Convert dot path to file path
            rel_path = mod.replace('.', os.sep)
            # Check for .py or package dir
            if not (os.path.exists(rel_path + '.py') or 
                    os.path.exists(os.path.join(rel_path, '__init__.py'))):
                # Only flag if it looks like an internal module (starts with root dirs)
                first_part = rel_path.split(os.sep)[0]
                if os.path.isdir(first_part):
                    missing.append(mod)
                    
    if missing: return True, f"AST Valid (Warning: Potential missing imports: {', '.join(missing[:3])})"
    return True, "AST Valid"

def check_strict(module_name):
    try:
        sys.path.append(os.getcwd())
        importlib.import_module(module_name)
        return True, "Import Successful"
    except ImportError as e: return False, f"ImportError: {e}"
    except Exception as e: return False, f"Runtime Error: {e}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--mode", choices=["safe", "strict"], default="safe")
    args = parser.parse_args()

    # Normalize
    path = args.path
    if not path.endswith('.py'):
        module = path
        path = path.replace('.', os.sep) + '.py'
    else:
        module = path[:-3].replace(os.sep, '.')

    ok, msg = check_safe(path)
    if not ok:
        print(f"[FAIL] {msg}"); sys.exit(1)
        
    if args.mode == "strict":
        ok, msg = check_strict(module)
        if not ok:
            print(f"[FAIL] {msg}"); sys.exit(1)

    print(f"[OK] {msg}")

if __name__ == "__main__":
    main()
```
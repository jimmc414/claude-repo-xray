# Phase 1 Integration Plan: Git-Based Temporal Analysis

## 1. Overview

### What's Being Added

Phase 1 currently provides **structural analysis** through AST parsing:
- `mapper.py` - Directory tree with token estimates
- `skeleton.py` - Interface extraction (95% token reduction)
- `dependency_graph.py` - Import relationships
- `configure.py` - Auto-detection of project structure

This integration adds **temporal analysis** through git history:
- **Risk Scoring** - Identify volatile files from churn, hotfixes, and author entropy
- **Co-Modification Analysis** - Find hidden coupling not visible in imports
- **Freshness Tracking** - Categorize files by maintenance activity
- **Orphan Detection** - Surface dead code candidates
- **Impact Analysis** - Calculate blast radius before changes

### Why Add This

Structural analysis tells you *where* code is. Temporal analysis tells you:
- Which files are **risky** (changed frequently, many hotfixes)
- Which files are **coupled** (always change together, even without imports)
- Which files are **dead** (nobody uses them, nobody touches them)
- Which files are **fragile** (changing them breaks many other files)

This information enhances WARM_START.md and feeds into Phase 2's unified targeting.

### Design Principles

- **Stateless**: No session persistence, pure input/output
- **Deterministic**: Same git history produces same results
- **Pure Python**: Uses subprocess for git, no external dependencies
- **Consistent Style**: Matches existing repo-xray tool patterns

---

## 2. New Tool: git_analysis.py

**Location**: `.claude/skills/repo-xray/scripts/git_analysis.py`

### Command Reference

```bash
# All analysis modes
python .claude/skills/repo-xray/scripts/git_analysis.py [directory] [options]

# Risk scoring (churn + hotfixes + authors)
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --risk

# Co-modification pairs
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --coupling

# Freshness categories
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --freshness

# Combined JSON output (for Phase 2 consumption)
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --json
```

### Output Format

#### Risk Mode (--risk)
```
RISK   FILE                              FACTORS
0.87   src/api/auth.py                   churn:15 hotfix:3 authors:5
0.72   src/core/workflow.py              churn:8 hotfix:1 authors:3
0.65   src/db/migrations.py              churn:12 hotfix:2 authors:2
```

#### Coupling Mode (--coupling)
```
=== COUPLING ===
12   src/api/auth.py <-> src/api/session.py
8    src/models/user.py <-> src/db/user_repo.py
7    src/core/config.py <-> src/core/settings.py
```

#### Freshness Mode (--freshness)
```
FRESHNESS ANALYSIS
ACTIVE (23 files)    - Last 30 days
AGING (45 files)     - 30-90 days
STALE (12 files)     - 90-180 days
DORMANT (8 files)    - >180 days

DORMANT FILES:
  src/legacy/converter.py     (412 days)
  src/utils/old_helpers.py    (389 days)
```

#### JSON Mode (--json)
```json
{
  "risk": [
    {"file": "src/api/auth.py", "risk_score": 0.87, "churn": 15, "hotfixes": 3, "authors": 5}
  ],
  "coupling": [
    {"file_a": "src/api/auth.py", "file_b": "src/api/session.py", "count": 12}
  ],
  "freshness": {
    "active": [{"file": "src/api/auth.py", "days": 5}],
    "aging": [],
    "stale": [],
    "dormant": [{"file": "src/legacy/old.py", "days": 412}]
  }
}
```

### Full Implementation

```python
#!/usr/bin/env python3
"""
Repo X-Ray: Git Analysis

Extracts historical signals from git history:
- Risk scoring (churn, hotfixes, author entropy)
- Co-modification analysis (hidden coupling)
- Freshness tracking (active, aging, stale, dormant)

Usage:
    python git_analysis.py [directory] [options]

Examples:
    python git_analysis.py src/ --risk
    python git_analysis.py src/ --coupling
    python git_analysis.py src/ --freshness
    python git_analysis.py src/ --json
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Optional


def run_git(cmd: List[str], cwd: str) -> str:
    """Execute a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return result.stdout.strip()
    except subprocess.SubprocessError:
        return ""


def get_tracked_files(cwd: str) -> List[str]:
    """Get list of tracked Python files."""
    raw = run_git(["ls-files", "*.py"], cwd)
    return [f for f in raw.splitlines() if f.strip()]


def analyze_risk(cwd: str, files: List[str], months: int = 6) -> List[Dict]:
    """
    Calculate Risk Score based on:
    - Churn: Number of commits in period (40% weight)
    - Hotfixes: Commits with fix/bug/urgent/revert keywords (40% weight)
    - Author Entropy: Unique authors / total commits (20% weight)

    Higher score = higher risk (more volatile).
    """
    # Parse git log with custom delimiter
    log = run_git(
        ["log", f"--since={months}.months", "--name-only", "--format=COMMIT::%an::%s"],
        cwd
    )

    if not log:
        return []

    stats = defaultdict(lambda: {"commits": 0, "authors": set(), "hotfixes": 0})
    current_author = ""
    is_hotfix = False

    hotfix_keywords = {"fix", "bug", "urgent", "revert", "hotfix", "patch", "emergency"}

    for line in log.splitlines():
        if line.startswith("COMMIT::"):
            parts = line.split("::", 2)
            if len(parts) >= 3:
                current_author = parts[1]
                subject = parts[2].lower()
                is_hotfix = any(kw in subject for kw in hotfix_keywords)
        elif line.strip() and line.endswith(".py"):
            f = line.strip()
            if f in files:
                s = stats[f]
                s["commits"] += 1
                s["authors"].add(current_author)
                if is_hotfix:
                    s["hotfixes"] += 1

    if not stats:
        return []

    # Normalize and calculate risk score
    max_churn = max(s["commits"] for s in stats.values())
    results = []

    for f, s in stats.items():
        churn_norm = s["commits"] / max_churn if max_churn > 0 else 0
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

    return sorted(results, key=lambda x: x["risk_score"], reverse=True)


def analyze_coupling(cwd: str, max_commits: int = 200, min_cooccurrences: int = 3) -> List[Dict]:
    """
    Find files that change together even without import relationships.

    Strategy:
    1. Parse recent commits (name-only)
    2. Build co-occurrence matrix for Python files
    3. Filter to pairs with >= min_cooccurrences
    4. Skip bulk refactors (commits touching >20 files)
    """
    log = run_git(["log", "-n", str(max_commits), "--name-only", "--format=COMMIT"], cwd)

    if not log:
        return []

    commits = []
    current_files = set()

    for line in log.splitlines():
        if line == "COMMIT":
            if current_files:
                commits.append(list(current_files))
            current_files = set()
        elif line.strip().endswith(".py"):
            current_files.add(line.strip())

    if current_files:
        commits.append(list(current_files))

    # Count co-occurrences
    pairs = Counter()
    for files in commits:
        if len(files) > 20:
            continue  # Skip bulk refactors
        files = sorted(files)
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                pairs[(files[i], files[j])] += 1

    results = []
    for (f1, f2), count in pairs.most_common(20):
        if count >= min_cooccurrences:
            results.append({"file_a": f1, "file_b": f2, "count": count})

    return results


def analyze_freshness(cwd: str, files: List[str]) -> Dict[str, List[Dict]]:
    """
    Categorize files by last modification time.

    Categories:
    - Active: <30 days (being maintained)
    - Aging: 30-90 days (may need attention)
    - Stale: 90-180 days (possibly neglected)
    - Dormant: >180 days (stable or abandoned)
    """
    log = run_git(["log", "--name-only", "--format=COMMIT::%ct"], cwd)

    if not log:
        return {"active": [], "aging": [], "stale": [], "dormant": []}

    last_modified = {}
    current_ts = 0

    for line in log.splitlines():
        if line.startswith("COMMIT::"):
            try:
                current_ts = int(line.split("::")[1])
            except (IndexError, ValueError):
                pass
        elif line.strip() and line.endswith(".py"):
            f = line.strip()
            if f not in last_modified:
                last_modified[f] = current_ts

    now = datetime.now().timestamp()
    result = {"active": [], "aging": [], "stale": [], "dormant": []}

    for f in files:
        ts = last_modified.get(f, now)
        days = int((now - ts) / 86400)
        entry = {"file": f, "days": days}

        if days < 30:
            result["active"].append(entry)
        elif days < 90:
            result["aging"].append(entry)
        elif days < 180:
            result["stale"].append(entry)
        else:
            result["dormant"].append(entry)

    # Sort dormant by age (oldest first)
    result["dormant"].sort(key=lambda x: x["days"], reverse=True)

    return result


def print_risk(results: List[Dict]):
    """Print risk analysis in human-readable format."""
    if not results:
        print("No risk data found (no commits in analysis period)")
        return

    print(f"{'RISK':<6} {'FILE':<50} {'FACTORS'}")
    print("-" * 80)
    for r in results[:15]:
        factors = f"churn:{r['churn']} hotfix:{r['hotfixes']} authors:{r['authors']}"
        print(f"{r['risk_score']:<6} {r['file']:<50} {factors}")


def print_coupling(results: List[Dict]):
    """Print coupling analysis in human-readable format."""
    if not results:
        print("No significant coupling found")
        return

    print("\n=== CO-MODIFICATION PAIRS ===")
    print("Files that change together (hidden coupling)")
    print("-" * 60)
    for c in results:
        print(f"{c['count']:<4} {c['file_a']} <-> {c['file_b']}")


def print_freshness(results: Dict[str, List[Dict]]):
    """Print freshness analysis in human-readable format."""
    print("\n=== FRESHNESS ANALYSIS ===")
    for category, label in [
        ("active", "ACTIVE (last 30 days)"),
        ("aging", "AGING (30-90 days)"),
        ("stale", "STALE (90-180 days)"),
        ("dormant", "DORMANT (>180 days)")
    ]:
        items = results.get(category, [])
        print(f"\n{label}: {len(items)} files")

        if category == "dormant" and items:
            print("  Oldest files:")
            for item in items[:5]:
                print(f"    {item['file']} ({item['days']} days)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze git history for risk, coupling, and freshness signals"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current)"
    )
    parser.add_argument(
        "--risk",
        action="store_true",
        help="Calculate risk scores from churn, hotfixes, authors"
    )
    parser.add_argument(
        "--coupling",
        action="store_true",
        help="Find files that change together"
    )
    parser.add_argument(
        "--freshness",
        action="store_true",
        help="Categorize files by last modification"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output all analyses as JSON"
    )
    parser.add_argument(
        "--months",
        type=int,
        default=6,
        help="Months of history for risk analysis (default: 6)"
    )

    args = parser.parse_args()

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Check for git repository
    git_dir = os.path.join(args.directory, ".git")
    if not os.path.exists(git_dir):
        # Try parent directories
        check_dir = os.path.abspath(args.directory)
        while check_dir != os.path.dirname(check_dir):
            if os.path.exists(os.path.join(check_dir, ".git")):
                break
            check_dir = os.path.dirname(check_dir)
        else:
            if args.json:
                print("{}")
            else:
                print("Error: Not a git repository", file=sys.stderr)
            sys.exit(1)

    files = get_tracked_files(args.directory)

    if not files:
        if args.json:
            print("{}")
        else:
            print("No Python files found")
        return

    # Run requested analyses
    output = {}

    if args.json or args.risk:
        output["risk"] = analyze_risk(args.directory, files, args.months)

    if args.json or args.coupling:
        output["coupling"] = analyze_coupling(args.directory)

    if args.json or args.freshness:
        output["freshness"] = analyze_freshness(args.directory, files)

    # Output
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        if "risk" in output:
            print_risk(output["risk"])
        if "coupling" in output:
            print_coupling(output["coupling"])
        if "freshness" in output:
            print_freshness(output["freshness"])

        if not (args.risk or args.coupling or args.freshness):
            print("Use --risk, --coupling, --freshness, or --json to select analysis")


if __name__ == "__main__":
    main()
```

---

## 3. Updates to dependency_graph.py

### New Flags

#### --orphans Flag

Identifies files with zero inbound imports (potential dead code).

```bash
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --orphans
```

**Output**:
```
ORPHAN CANDIDATES (0 importers, excluding entry points)
CONFIDENCE  FILE                          NOTES
0.95        src/legacy/old_parser.py      No imports, not entry point pattern
0.85        src/utils/deprecated.py       No imports, name suggests deprecated
0.60        src/scripts/migrate.py        Might be CLI entry point
```

**Exclusion List** (files that are entry points, not orphans):
- `main.py`, `__main__.py`, `cli.py`, `app.py`, `wsgi.py`, `asgi.py`
- `test_*.py`, `*_test.py`, `conftest.py`
- `setup.py`, `manage.py`, `fabfile.py`
- Files containing `if __name__ == "__main__":`

#### --impact Flag

Calculates blast radius for a specific file.

```bash
python .claude/skills/repo-xray/scripts/dependency_graph.py --impact src/core/base.py
```

**Output**:
```
IMPACT ANALYSIS: src/core/base.py

Direct dependents (import this file): 12
  src/core/workflow.py
  src/core/engine.py
  src/api/handler.py
  ... (9 more)

Transitive dependents (2 levels): 47

WARNING: Changes to this file have wide blast radius.
SUGGESTION: Consider smaller, incremental changes with tests.
```

### Implementation Changes

Add to `dependency_graph.py` after the existing argument parser:

```python
# Add to argument parser
parser.add_argument(
    "--orphans",
    action="store_true",
    help="Find files with zero importers (dead code candidates)"
)
parser.add_argument(
    "--impact",
    metavar="FILE",
    help="Calculate blast radius for a specific file"
)


# Entry point patterns (not orphans)
ENTRY_POINT_PATTERNS = {
    "main.py", "__main__.py", "cli.py", "app.py", "wsgi.py", "asgi.py",
    "setup.py", "manage.py", "fabfile.py", "conftest.py"
}

ENTRY_POINT_PREFIXES = ("test_",)
ENTRY_POINT_SUFFIXES = ("_test.py",)


def is_entry_point(filepath: str, source: str = None) -> bool:
    """Check if file is likely an entry point (not an orphan)."""
    filename = os.path.basename(filepath)

    # Check filename patterns
    if filename in ENTRY_POINT_PATTERNS:
        return True
    if filename.startswith(ENTRY_POINT_PREFIXES):
        return True
    if any(filename.endswith(s) for s in ENTRY_POINT_SUFFIXES):
        return True

    # Check for if __name__ == "__main__"
    if source is None:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception:
            return False

    return 'if __name__ ==' in source or "if __name__==" in source


def find_orphans(graph: Dict) -> List[Dict]:
    """Find files with zero importers that aren't entry points."""
    modules = graph["modules"]
    orphans = []

    for name, info in modules.items():
        if len(info["imported_by"]) == 0:
            filepath = info["file"]
            if is_entry_point(filepath):
                continue

            # Calculate confidence
            confidence = 0.9
            filename = os.path.basename(filepath).lower()

            # Lower confidence for certain patterns
            if "script" in filepath.lower():
                confidence = 0.6
            elif "deprecated" in filename or "legacy" in filename or "old" in filename:
                confidence = 0.95
            elif "util" in filename or "helper" in filename:
                confidence = 0.7

            orphans.append({
                "file": filepath,
                "module": name,
                "confidence": confidence,
                "notes": get_orphan_notes(filepath, filename)
            })

    return sorted(orphans, key=lambda x: x["confidence"], reverse=True)


def get_orphan_notes(filepath: str, filename: str) -> str:
    """Generate notes explaining orphan classification."""
    if "deprecated" in filename or "legacy" in filename:
        return "Name suggests deprecated"
    if "old" in filename:
        return "Name suggests superseded"
    if "script" in filepath.lower():
        return "Might be CLI script"
    return "No imports, not entry point pattern"


def calculate_impact(graph: Dict, target_file: str, max_depth: int = 2) -> Dict:
    """Calculate blast radius for a file."""
    modules = graph["modules"]

    # Find the module for this file
    target_module = None
    for name, info in modules.items():
        if info["file"] == target_file or info["file"].endswith(target_file):
            target_module = name
            break

    if not target_module:
        return {"error": f"File not found: {target_file}"}

    # Direct dependents
    direct = modules[target_module]["imported_by"]

    # Transitive dependents (BFS)
    seen = set(direct)
    frontier = list(direct)
    for _ in range(max_depth - 1):
        next_frontier = []
        for mod in frontier:
            if mod in modules:
                for dep in modules[mod]["imported_by"]:
                    if dep not in seen:
                        seen.add(dep)
                        next_frontier.append(dep)
        frontier = next_frontier

    return {
        "file": target_file,
        "module": target_module,
        "direct_dependents": direct,
        "direct_count": len(direct),
        "transitive_dependents": list(seen),
        "transitive_count": len(seen)
    }


def print_orphans(orphans: List[Dict]):
    """Print orphan analysis."""
    if not orphans:
        print("No orphan candidates found")
        return

    print("ORPHAN CANDIDATES (0 importers, excluding entry points)")
    print(f"{'CONFIDENCE':<12} {'FILE':<40} {'NOTES'}")
    print("-" * 80)
    for o in orphans[:20]:
        print(f"{o['confidence']:<12.2f} {o['file']:<40} {o['notes']}")


def print_impact(impact: Dict):
    """Print impact analysis."""
    if "error" in impact:
        print(f"Error: {impact['error']}")
        return

    print(f"IMPACT ANALYSIS: {impact['file']}")
    print()
    print(f"Direct dependents (import this file): {impact['direct_count']}")
    for dep in impact['direct_dependents'][:10]:
        print(f"  {dep}")
    if impact['direct_count'] > 10:
        print(f"  ... ({impact['direct_count'] - 10} more)")

    print()
    print(f"Transitive dependents (2 levels): {impact['transitive_count']}")

    if impact['transitive_count'] > 10:
        print()
        print("WARNING: Changes to this file have wide blast radius.")
        print("SUGGESTION: Consider smaller, incremental changes with tests.")


# Add to main() dispatch logic
if args.orphans:
    orphans = find_orphans(graph)
    if args.json:
        print(json.dumps({"orphans": orphans}, indent=2))
    else:
        print_orphans(orphans)
elif args.impact:
    impact = calculate_impact(graph, args.impact)
    if args.json:
        print(json.dumps(impact, indent=2))
    else:
        print_impact(impact)
```

---

## 4. Updates to warm_start.md.template

Add these sections after Section 9 (Architecture Layers):

```markdown
---

## 10. Risk Assessment

### High-Risk Files (volatile in past 6 months)
{RISK_FILES_TABLE}

*Risk factors: churn (commit frequency), hotfixes (bug-fix commits), author entropy (coordination overhead)*

> Generated with: `python .claude/skills/repo-xray/scripts/git_analysis.py {SOURCE_DIR} --risk`

---

## 11. Hidden Coupling

### Files That Change Together
{COUPLING_TABLE}

*These files have no import relationship but are historically coupled. Changes to one often require changes to the other.*

> Generated with: `python .claude/skills/repo-xray/scripts/git_analysis.py {SOURCE_DIR} --coupling`

---

## 12. Potential Dead Code

### Orphan Files (zero importers)
{ORPHAN_TABLE}

### Dormant Files (no changes in 180+ days)
{DORMANT_TABLE}

*Candidates for removal or archival. Verify before deleting.*

> Generated with: `python .claude/skills/repo-xray/scripts/dependency_graph.py {SOURCE_DIR} --orphans`
> Generated with: `python .claude/skills/repo-xray/scripts/git_analysis.py {SOURCE_DIR} --freshness`
```

### Placeholder Definitions

| Placeholder | Source | Format |
|-------------|--------|--------|
| `{RISK_FILES_TABLE}` | `git_analysis.py --risk` | Markdown table: File, Risk, Factors |
| `{COUPLING_TABLE}` | `git_analysis.py --coupling` | Markdown table: File A, File B, Co-occurrences |
| `{ORPHAN_TABLE}` | `dependency_graph.py --orphans` | Markdown table: File, Confidence, Notes |
| `{DORMANT_TABLE}` | `git_analysis.py --freshness` (dormant) | Markdown table: File, Days Since Change |

---

## 5. Updates to repo_architect.md

Add to the "Your Tools" section:

```markdown
# Git Analysis (NEW)
python .claude/skills/repo-xray/scripts/git_analysis.py [directory] [options]

# Risk scoring from git history
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --risk

# Find files that change together (hidden coupling)
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --coupling

# Categorize by freshness (active/aging/stale/dormant)
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --freshness

# JSON output for Phase 2 consumption
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --json > git_analysis.json
```

Add to the "Operating Modes" section under `generate`:

```markdown
**8-Step Workflow (Updated):**
1. **Bootstrap** - Run `configure.py --dry-run` to detect project structure
2. **Survey** - Run `mapper.py --summary` to get codebase overview
3. **Map** - Run `dependency_graph.py --mermaid` to visualize architecture
4. **X-Ray** - Run `skeleton.py --priority critical` for interfaces
5. **Verify** - Identify and verify entry points
6. **Risk** - Run `git_analysis.py --risk` to identify volatile files (NEW)
7. **Coupling** - Run `git_analysis.py --coupling` to find hidden dependencies (NEW)
8. **Document** - Generate WARM_START.md using the template
```

Add optional section guidance:

```markdown
## Optional Sections (Updated)

Skip these placeholders when not applicable:
- `{WORKFLOW_MERMAID_DIAGRAM}` - Skip for simple architectures (<10 modules)
- `{EXECUTOR_CLASSES_TABLE}` - Skip if no Executor/Runner/Manager classes found
- `{RISK_FILES_TABLE}` - Skip if no files have risk score > 0.5
- `{COUPLING_TABLE}` - Skip if no significant coupling pairs found
- `{ORPHAN_TABLE}` - Skip if no orphan candidates detected
- `{DORMANT_TABLE}` - Skip if no files dormant >180 days
```

---

## 6. Testing Plan

### Test Environment
- Repository: `/mnt/c/python/kosmos`
- Should have sufficient git history for meaningful analysis

### Test Cases

#### 6.1 git_analysis.py Tests

```bash
# Test risk analysis
python .claude/skills/repo-xray/scripts/git_analysis.py /mnt/c/python/kosmos --risk
# Expected: List of files sorted by risk score

# Test coupling analysis
python .claude/skills/repo-xray/scripts/git_analysis.py /mnt/c/python/kosmos --coupling
# Expected: Pairs of files that change together

# Test freshness analysis
python .claude/skills/repo-xray/scripts/git_analysis.py /mnt/c/python/kosmos --freshness
# Expected: Categorized file counts and dormant file list

# Test JSON output
python .claude/skills/repo-xray/scripts/git_analysis.py /mnt/c/python/kosmos --json
# Expected: Valid JSON with risk, coupling, freshness keys

# Test on non-git directory
python .claude/skills/repo-xray/scripts/git_analysis.py /tmp --risk
# Expected: Error message about not being a git repository
```

#### 6.2 dependency_graph.py Tests

```bash
# Test orphan detection
python .claude/skills/repo-xray/scripts/dependency_graph.py /mnt/c/python/kosmos --orphans
# Expected: List of files with zero importers

# Test impact analysis
python .claude/skills/repo-xray/scripts/dependency_graph.py /mnt/c/python/kosmos --impact kosmos/core/base.py
# Expected: Direct and transitive dependent counts

# Test JSON output for orphans
python .claude/skills/repo-xray/scripts/dependency_graph.py /mnt/c/python/kosmos --orphans --json
# Expected: Valid JSON with orphans array
```

#### 6.3 Integration Tests

```bash
# Generate Phase 1 JSON outputs
python .claude/skills/repo-xray/scripts/dependency_graph.py /mnt/c/python/kosmos --json > deps.json
python .claude/skills/repo-xray/scripts/git_analysis.py /mnt/c/python/kosmos --json > git.json

# Verify JSON files are valid
python -c "import json; json.load(open('deps.json')); json.load(open('git.json')); print('Valid JSON')"
```

### Acceptance Criteria

1. All commands exit with code 0 on valid input
2. All commands exit with code 1 on invalid input with error message
3. JSON output is valid and parseable
4. Risk scores are between 0 and 1
5. Coupling pairs have count >= 3
6. Freshness categories sum to total file count
7. Orphan detection excludes known entry point patterns
8. Impact analysis shows reasonable blast radius

---

## 7. File Checklist

### New Files

| File | Action | Lines |
|------|--------|-------|
| `.claude/skills/repo-xray/scripts/git_analysis.py` | Create | ~300 |

### Modified Files

| File | Changes |
|------|---------|
| `.claude/skills/repo-xray/scripts/dependency_graph.py` | Add `--orphans` flag (~80 lines) |
| `.claude/skills/repo-xray/scripts/dependency_graph.py` | Add `--impact` flag (~50 lines) |
| `.claude/skills/repo-xray/templates/warm_start.md.template` | Add sections 10-12 (~40 lines) |
| `.claude/agents/repo_architect.md` | Add git_analysis.py commands, update workflow (~30 lines) |

### Estimated Total Changes
- New code: ~300 lines
- Modifications: ~200 lines
- **Total: ~500 lines**

---

## Summary

This plan enhances Phase 1 with git-based temporal analysis:

1. **git_analysis.py** - New tool providing risk, coupling, and freshness signals
2. **dependency_graph.py** - Extended with orphan detection and impact analysis
3. **warm_start.md.template** - Three new sections for risk, coupling, dead code
4. **repo_architect.md** - Updated workflow and tool documentation

These enhancements provide the temporal signals that Phase 2's unified targeting system needs to accurately identify important code beyond pure complexity metrics.

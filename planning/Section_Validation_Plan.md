# Section Validation Plan

Comprehensive plan to manually validate each WARM_START section and improve error handling across all Python scripts.

## Background

We discovered that `--format=COMMIT` was invalid git syntax, causing the coupling analysis to silently fail and return "No significant coupling found" when there were actually 9+ coupling pairs. This plan validates all sections to find similar issues.

---

## Section-by-Section Validation

### Section 1: System Context (Mermaid Diagram)

**What it should show:** Module dependency graph with ORCHESTRATION/CORE/FOUNDATION layers

**Manual validation:**
```bash
cd /mnt/c/python/kosmos
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/dependency_graph.py . --root kosmos --mermaid
```

**Verify against:**
```bash
# Check that key modules are detected
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/dependency_graph.py . --root kosmos --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Total modules: {len(d.get(\"modules\", {}))}')
print(f'Layers: {list(d.get(\"layers\", {}).keys())}')
for layer, modules in d.get('layers', {}).items():
    print(f'  {layer}: {len(modules)} modules')
"
```

**Potential issues:**
- [ ] Silent failure if directory doesn't exist
- [ ] Empty graph if root package not detected
- [ ] Missing edges if imports use relative paths

---

### Section 2: Architecture Overview

**What it should show:** Project description, module counts per layer, detected patterns

**Manual validation:**
```bash
# Check the generate_architecture_overview function output
cd /mnt/c/python/kosmos
python3 -c "
import sys
sys.path.insert(0, '/mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts')
from generate_warm_start import collect_all_data, generate_architecture_overview
data = collect_all_data('.', verbose=True)
overview, confidence = generate_architecture_overview(data)
print(f'Confidence: {confidence}')
print(overview)
"
```

**Potential issues:**
- [ ] Pattern detection may miss patterns if naming conventions differ
- [ ] Module counts could be wrong if layer classification fails

---

### Section 3: Entry Points

**What it should show:** Main entry points (CLI, workflow classes)

**Manual validation:**
```bash
# Find actual entry points manually
cd /mnt/c/python/kosmos
grep -r "if __name__" kosmos/ --include="*.py" -l | head -20

# Find workflow/main classes
grep -r "class.*Workflow" kosmos/ --include="*.py" -l
grep -r "def main" kosmos/ --include="*.py" -l
```

**Verify against generated:**
```bash
grep -A15 "### Entry Points" /mnt/c/python/claude-repo-xray/WARM_START.python-only.md
```

**Potential issues:**
- [x] FIXED: Was detecting utility scripts in .claude/, tests/, examples/
- [ ] May miss class-based entry points that don't have __main__
- [ ] Duplicates if same filename exists in multiple locations

---

### Section 4: Data Flow

**What it should show:** Flow diagram with actual class/method names

**Manual validation:**
```bash
# Check what class is being used for data flow
cd /mnt/c/python/kosmos
grep -A5 "^\[1\]" /mnt/c/python/claude-repo-xray/WARM_START.python-only.md

# Verify the class exists
grep -r "class.*research_loop\|ResearchWorkflow" kosmos/ --include="*.py"
```

**Potential issues:**
- [x] FIXED: Was using first entry point (wrong class)
- [ ] Generic placeholder text not replaced with actual methods
- [ ] Should detect actual method names from skeleton

---

### Section 5: Entry Points / Imports

**What it should show:** Valid Python import statements

**Manual validation:**
```bash
# Test the imports actually work
cd /mnt/c/python/kosmos
python3 -c "from kosmos import main; print('OK')"
python3 -c "from kosmos.workflow.research_loop import ResearchWorkflow; print('OK')"
```

**Verify against generated:**
```bash
grep -A10 "### Python API" /mnt/c/python/claude-repo-xray/WARM_START.python-only.md
```

**Potential issues:**
- [x] FIXED: Was using project name with hyphens (invalid Python)
- [ ] Generated imports may not match actual module structure

---

### Section 6: Context Hazards

**What it should show:** Large files that would consume too much context

**Manual validation:**
```bash
cd /mnt/c/python/kosmos
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/mapper.py . --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Total tokens: {d[\"total_tokens\"]:,}')
print(f'Large files (>10K tokens):')
for f in d.get('large_files', [])[:10]:
    print(f'  {f[\"tokens\"]:>10,} {f[\"path\"]}')
"
```

**Potential issues:**
- [ ] May include binary files that can't be read anyway
- [ ] Token estimation (chars/4) may be inaccurate

---

### Section 7: Quick Verification

**What it should show:** Commands to verify the setup works

**Manual validation:**
```bash
# Actually run the verification commands
cd /mnt/c/python/kosmos
python -m kosmos --help 2>&1 | head -5
pytest tests/ -x -q --collect-only 2>&1 | head -10
```

**Potential issues:**
- [ ] Commands may not work if project uses different CLI framework
- [ ] Test command assumes pytest

---

### Section 8: X-Ray Commands

**What it should show:** Commands to run repo-xray tools

**Manual validation:**
```bash
# Verify paths are correct
ls -la /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/*.py
```

**Potential issues:**
- [ ] Paths assume local installation, not global

---

### Section 9: Architecture Layers

**What it should show:** Modules organized by layer with import counts

**Manual validation:**
```bash
cd /mnt/c/python/kosmos
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/dependency_graph.py . --root kosmos --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
modules = d.get('modules', {})
print('Top 10 most imported modules:')
sorted_mods = sorted(modules.items(), key=lambda x: len(x[1].get('imported_by', [])), reverse=True)
for name, info in sorted_mods[:10]:
    print(f'  {len(info.get(\"imported_by\", [])):>3} imports: {name}')
"
```

**Potential issues:**
- [ ] Layer classification heuristics may miscategorize
- [ ] Circular imports may cause issues

---

### Section 10: Risk Assessment

**What it should show:** Files with high churn, hotfixes, multiple authors

**Manual validation:**
```bash
cd /mnt/c/python/kosmos
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/git_analysis.py . --risk

# Verify against raw git data
git log --since="6.months" --name-only --pretty=format: -- "kosmos/*.py" | sort | uniq -c | sort -rn | head -10
```

**Potential issues:**
- [x] FIXED: --format=COMMIT was invalid syntax
- [ ] May not work outside git repo
- [ ] Hotfix keyword detection is English-only

---

### Section 11: Hidden Coupling

**What it should show:** File pairs that change together

**Manual validation:**
```bash
cd /mnt/c/python/kosmos
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/git_analysis.py . --coupling

# Verify with raw git data
git log -n 100 --name-only --pretty=format:"===COMMIT===" -- "kosmos/**/*.py" | python3 -c "
import sys
from collections import Counter
commits, current = [], set()
for line in sys.stdin:
    line = line.strip()
    if line == '===COMMIT===':
        if current: commits.append(list(current))
        current = set()
    elif line.endswith('.py'): current.add(line)
if current: commits.append(list(current))

pairs = Counter()
for files in commits:
    if len(files) > 20: continue
    files = sorted(files)
    for i in range(len(files)):
        for j in range(i+1, len(files)):
            pairs[(files[i], files[j])] += 1

print('Top 10 co-modified pairs:')
for (f1, f2), count in pairs.most_common(10):
    if count >= 3:
        print(f'  {count}x: {f1} <-> {f2}')
"
```

**Potential issues:**
- [x] FIXED: --format=COMMIT was invalid syntax
- [ ] May miss coupling if commits touch >20 files (filtered out)

---

### Section 12: Potential Dead Code

**What it should show:** Orphan files (zero importers), dormant files

**Manual validation:**
```bash
cd /mnt/c/python/kosmos
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/dependency_graph.py . --root kosmos --orphans

# Verify freshness
python /mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/git_analysis.py . --freshness
```

**Potential issues:**
- [x] FIXED: --format=COMMIT::%ct was invalid syntax
- [ ] Entry point files may be flagged as orphans incorrectly
- [ ] Test files expected to be orphans

---

## Error Handling Improvements

### Current Issues Found

1. **Silent git failures:** `run_git()` returns empty string on failure, no error logging
2. **No validation of git output format:** Assumes format is correct
3. **Missing try/except in main functions:** Errors propagate silently

### Files to Update

| File | Functions to Fix |
|------|------------------|
| `git_analysis.py` | `run_git()`, `analyze_risk()`, `analyze_coupling()`, `analyze_freshness()` |
| `dependency_graph.py` | `build_dependency_graph()`, `auto_detect_root_package()` |
| `mapper.py` | `map_directory()` |
| `skeleton.py` | `get_skeleton()` |
| `generate_warm_start.py` | `collect_all_data()` |

### Proposed Changes

#### 1. Add verbose error logging to `run_git()`

```python
def run_git(args: List[str], cwd: str, verbose: bool = False) -> str:
    """Run git command and return output, with error handling."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            if verbose:
                print(f"Git command failed: git {' '.join(args)}", file=sys.stderr)
                print(f"  stderr: {result.stderr}", file=sys.stderr)
            return ""
        return result.stdout
    except subprocess.TimeoutExpired:
        if verbose:
            print(f"Git command timed out: git {' '.join(args)}", file=sys.stderr)
        return ""
    except Exception as e:
        if verbose:
            print(f"Git command error: {e}", file=sys.stderr)
        return ""
```

#### 2. Validate git output before parsing

```python
def analyze_coupling(cwd: str, max_commits: int = 200, min_cooccurrences: int = 3, verbose: bool = False) -> List[Dict]:
    log = run_git(["log", "-n", str(max_commits), "--name-only", "--pretty=format:COMMIT"], cwd, verbose)

    if not log:
        if verbose:
            print("Warning: No git log output for coupling analysis", file=sys.stderr)
        return []

    # Validate format
    if "COMMIT" not in log:
        if verbose:
            print("Warning: Git log output missing COMMIT markers", file=sys.stderr)
        return []

    # ... rest of function
```

#### 3. Add --verbose flag to all CLI tools

Each script should accept `--verbose` or `-v` to enable debug output.

#### 4. Add validation summary to generate_warm_start.py

```python
def validate_collected_data(data: Dict, verbose: bool = False) -> List[str]:
    """Check for missing or suspicious data."""
    warnings = []

    if not data.get("graph", {}).get("modules"):
        warnings.append("No modules detected in dependency graph")

    if not data.get("entry_points"):
        warnings.append("No entry points detected")

    if not data.get("risk"):
        warnings.append("No risk data (git analysis may have failed)")

    if not data.get("coupling"):
        warnings.append("No coupling data (git analysis may have failed)")

    if verbose and warnings:
        print("Validation warnings:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)

    return warnings
```

---

## Implementation Order

1. **Phase 1: Run all validation commands** (manual, ~30 min)
   - Execute each validation command above
   - Document any failures or unexpected output

2. **Phase 2: Fix error handling in git_analysis.py** (~30 min)
   - Update `run_git()` with verbose logging
   - Add output validation to each analysis function
   - Add `--verbose` flag to CLI

3. **Phase 3: Fix error handling in other scripts** (~45 min)
   - `dependency_graph.py`: Add validation for empty graphs
   - `mapper.py`: Add error handling for unreadable files
   - `skeleton.py`: Add error handling for unparseable files
   - `generate_warm_start.py`: Add validation summary

4. **Phase 4: Add integration tests** (~30 min)
   - Test that each tool produces expected output on kosmos
   - Test error cases (non-git repo, empty directory, etc.)

5. **Phase 5: Regenerate examples and verify** (~15 min)
   - Regenerate WARM_START.python-only.md
   - Verify all sections have data
   - Update WARM_START.claude-processed.md if needed

---

## Success Criteria

- [ ] All 12 sections produce valid, non-empty output for kosmos
- [ ] Running with `--verbose` shows clear progress/errors
- [ ] Silent failures are eliminated (errors logged to stderr)
- [ ] Validation warnings shown if data looks suspicious
- [ ] Tests pass for both kosmos and repo-xray codebases

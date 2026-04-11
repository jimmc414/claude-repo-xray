# Incremental Deep Crawl — Implementation Plan

> **Status:** Design document — not yet implemented. The `@deep_crawl refresh` command currently runs a full crawl.

## Problem

The deep crawl pipeline produces a 62K word onboarding document that takes ~800K tokens and ~30 minutes across 12+ agent spawns. When code changes, the entire pipeline re-runs from scratch. Changing 5 files costs the same as scanning 802.

The `@deep_crawl refresh` command exists in SKILL.md but runs a full crawl. There is no incremental processing.

## Solution

Use git diff + the existing reverse dependency graph + the existing findings-on-disk architecture to investigate only what changed and stitch results into the existing document.

**Cost model:** A typical PR touching 5 files affects ~15 modules (changed + 1-hop dependents). That's 15 Protocol B tasks + re-tracing affected critical paths + re-impact analysis for affected hub clusters + affected playbook re-generation, vs 50+ tasks for a full crawl. Assembly reads the merged findings directory (18 old + 15 new) and produces the same output format. Expected cost: ~100-150K tokens, ~8 minutes.

## Prerequisites

These already exist and are ready to use:

| Component | Location | What It Provides |
|-----------|----------|-----------------|
| `run_git()` | `lib/git_analysis.py:44` | Raw git command executor |
| `imported_by` field | `lib/import_analysis.py:257` | Reverse dependency lookup per module |
| `build_reverse_lookup()` | `lib/call_analysis.py:321` | "Who calls this function?" |
| `compute_investigation_targets()` | `lib/investigation_targets.py:765` | Priority computation (can filter by file set) |
| Findings on disk | `.deep_crawl/findings/{type}/{name}.md` | Individual per-module markdown files |
| CRAWL_PLAN.md checkboxes | Phase 2 orchestration | `[ ]`/`[x]` task completion tracking |
| Assembly from disk | Phase 3 | Reads findings directory → section files → DRAFT_ONBOARD.md |

## Architecture

```
@deep_crawl refresh
    │
    ▼
Phase 0b: DIFF ANALYSIS (new)
    ├── git diff {last_crawl_hash}..HEAD --name-status
    ├── compute_impact_scope(import_graph, changed_modules)
    ├── detect_facet_changes(changed_files, domain_profiles)
    ├── read docs/.onboard_changes.log (if exists)
    │   └── returns: changed + 1-hop importers + 2-hop importers
    │               + affected_impact_clusters + affected_playbooks
    │               + hint_sections (from change log)
    └── write .deep_crawl/DIFF_ANALYSIS.json
    │
    ▼
Phase 1b: INCREMENTAL PLAN (modified)
    ├── load previous CRAWL_PLAN.md
    ├── filter tasks: in-scope = pending, out-of-scope = skip
    ├── add new tasks for added files
    ├── remove tasks for deleted files
    └── write CRAWL_PLAN.md with incremental metadata
    │
    ▼
Phase 2: CRAWL (unchanged — operates on filtered plan)
    ├── sub-agents execute only pending tasks (Batches 1-4)
    ├── Batch 5: P7 impact re-analysis for affected hub clusters (Protocol E)
    ├── Batch 6: change scenario re-generation for affected playbooks (Protocol F)
    ├── write findings to .deep_crawl/findings_new/{type}/{name}.md
    └── batch_status sentinels as usual
    │
    ▼
Phase 2b: MERGE FINDINGS (new)
    ├── for each finding in findings_new/: overwrite findings/{same path}
    ├── for out-of-scope findings in findings/: keep as-is
    ├── for deleted files: remove corresponding finding
    ├── merge all 7 directories: traces, modules, cross_cutting, conventions,
    │   impact, playbooks, calibration
    └── write .deep_crawl/FINDINGS_INDEX.json (source + age per file)
    │
    ▼
Phase 2c: IMPACT REFRESH (new, incremental only)
    ├── for hub modules whose dependents changed: re-run Protocol E
    ├── for playbooks referencing in-scope modules: re-run Protocol F
    └── write updated findings to findings/impact/ and findings/playbooks/
    │
    ▼
Phase 3-6: ASSEMBLE → CROSS-REF → VALIDATE → DELIVER (unchanged)
    └── reads merged findings/ directory (all 7 subdirs), same as full crawl
```

**Key insight:** Phases 3-6 are completely agnostic to whether findings are fresh or reused. The merge step produces the same directory structure (all 7 finding subdirectories) as a full crawl, so assembly works unchanged.

**Structural skeleton note:** Phase 3 Step 1c generates `_skeleton.md` from findings files. In incremental mode, the skeleton reflects the **merged** findings directory (all 7 subdirectories), not just new findings. Since merge happens before Phase 3, this works automatically.

**CLAUDE.md handling note:** Phase 3 Step 1b temporarily renames CLAUDE.md to prevent self-reference during assembly. This applies in incremental mode too — the assembly phase is unchanged.

## Changes

### Change 1: Add `get_changed_files()` to git_analysis.py

**File:** `lib/git_analysis.py` (after line 67)
**Effort:** ~20 lines

```python
def get_changed_files(cwd: str, since_ref: str) -> Dict[str, str]:
    """
    Get Python files changed since a reference commit.

    Args:
        cwd: Working directory
        since_ref: Git ref to diff against (commit hash, branch, tag)

    Returns:
        {"path/to/file.py": "M", ...}  where status is M/A/D/R
        Empty dict if git fails or no Python files changed.
    """
    result = run_git(["diff", f"{since_ref}..HEAD", "--name-status"], cwd)
    files = {}
    for line in result.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            status, filepath = parts
            if filepath.endswith(".py"):
                files[filepath] = status[0]  # First char: M, A, D, R
    return files
```

Also add a helper to read the git hash from a previous crawl's metadata:

```python
def get_crawl_metadata_hash(crawl_dir: str) -> Optional[str]:
    """Read git hash from CRAWL_PLAN.md header."""
    plan_path = Path(crawl_dir) / "CRAWL_PLAN.md"
    if not plan_path.exists():
        return None
    with open(plan_path) as f:
        for line in f:
            if line.startswith("> Git commit:"):
                return line.split(":")[-1].strip()
    return None
```

### Change 2: Add `compute_impact_scope()` to import_analysis.py

**File:** `lib/import_analysis.py` (after `calculate_dependency_distance`)
**Effort:** ~40 lines

```python
def compute_impact_scope(
    graph: Dict[str, Any],
    changed_modules: Set[str],
    max_hops: int = 2
) -> Dict[str, Any]:
    """
    Given changed modules, compute the full blast radius via reverse imports.

    Uses the existing `imported_by` field in the import graph.

    Args:
        graph: Import graph from build_import_graph()
        changed_modules: Set of module name stems that changed
        max_hops: Depth of reverse dependency traversal (1=direct, 2=transitive)

    Returns:
        {
            "changed": set,
            "hop_1": set,           # Direct importers of changed modules
            "hop_2": set,           # Importers of hop_1 (if max_hops >= 2)
            "total_scope": set,     # Union of all
            "out_of_scope": set,    # Everything NOT in total_scope
            "scope_ratio": float,   # total_scope / all_modules
        }
    """
    modules = graph.get("modules", {})
    all_module_names = set(modules.keys())

    # Hop 1: direct importers of changed modules
    hop_1 = set()
    for mod in changed_modules:
        hop_1.update(modules.get(mod, {}).get("imported_by", []))
    hop_1 -= changed_modules  # Don't double-count

    # Hop 2: importers of hop_1
    hop_2 = set()
    if max_hops >= 2:
        for mod in hop_1:
            hop_2.update(modules.get(mod, {}).get("imported_by", []))
        hop_2 -= (changed_modules | hop_1)

    total_scope = changed_modules | hop_1 | hop_2
    out_of_scope = all_module_names - total_scope

    return {
        "changed": changed_modules,
        "hop_1": hop_1,
        "hop_2": hop_2,
        "total_scope": total_scope,
        "out_of_scope": out_of_scope,
        "scope_ratio": len(total_scope) / max(len(all_module_names), 1),
    }
```

### Change 3: Add `crawl_diff.py` to lib/

**File:** `lib/crawl_diff.py` (new file)
**Effort:** ~120 lines

This module provides the orchestration logic that the deep crawl skill calls. It does NOT contain LLM logic — it's pure Python, deterministic, and testable.

**Functions:**

```python
def analyze_diff(
    cwd: str,
    since_ref: str,
    import_graph: Dict,
    call_results: Dict,
) -> Dict[str, Any]:
    """
    Master function: given a git ref, compute what changed and what's affected.

    Returns DIFF_ANALYSIS.json structure:
    {
        "since_ref": "abc1234",
        "head_ref": "def5678",
        "changed_files": {"path": "M/A/D", ...},
        "changed_modules": ["mod1", "mod2"],
        "deleted_modules": ["mod3"],
        "added_modules": ["mod4"],
        "impact_scope": {<from compute_impact_scope>},
        "affected_traces": ["trace_name", ...],  # Traces whose hops include affected modules
        "affected_cross_cutting": ["concern", ...],  # Cross-cutting that reference affected modules
        "affected_impact_clusters": [...],   # Hub module clusters needing Protocol E re-analysis
        "affected_playbooks": [...],         # Playbook names needing Protocol F re-generation
        "facet_change_detected": bool,       # True if framework imports changed → recommend full
        "calibration_targets_affected": [...], # Which cal_a/b/c targets need re-running
        "hint_sections": [                       # From docs/.onboard_changes.log (advisory)
            {"timestamp": str, "file_line": str, "section_path": str, "description": str},
            ...
        ],
        "recommendation": "incremental" | "full",  # If scope_ratio > 0.5, recommend full
    }
    """
```

```python
def build_incremental_plan(
    diff_analysis: Dict,
    previous_plan_path: str,
    previous_findings_dir: str,
) -> Dict[str, Any]:
    """
    Build a filtered crawl plan from diff analysis + previous plan.

    Logic:
    - Tasks for changed/added modules: pending (re-investigate)
    - Tasks for deleted modules: removed
    - Tasks for affected (hop 1-2) modules: pending (re-investigate dependents)
    - Tasks for unaffected modules: skip (reuse findings)
    - Traces that pass through affected modules: pending (re-trace)
    - Traces entirely outside scope: skip (reuse findings)
    - Cross-cutting concerns: re-run if any affected module participates
    - Tasks for affected impact clusters: pending (Protocol E re-analysis)
    - Tasks for affected playbooks: pending (Protocol F re-generation)
    - P7 tasks for hub modules whose dependents are in-scope
    - Change scenario tasks for playbooks referencing in-scope modules
    - If hint_sections (from .onboard_changes.log) reference a section for an
      out-of-scope module: still mark that section for re-verification
    - If hint_sections reference a section for an in-scope module: annotate
      the task with the specific section to prioritize

    Returns CRAWL_PLAN structure suitable for Phase 1 output.
    """
```

```python
def merge_findings(
    previous_findings_dir: str,
    new_findings_dir: str,
    diff_analysis: Dict,
    output_dir: str,
) -> Dict[str, str]:
    """
    Merge old + new findings into output_dir.

    Handles all 7 finding directories:
    findings/{traces,modules,cross_cutting,conventions,impact,playbooks,calibration}

    Strategy:
    - New findings overwrite old for the same module/trace
    - Old findings kept for out-of-scope modules
    - Deleted module findings removed
    - Impact cluster findings re-merged for affected hubs
    - Playbook findings re-merged for affected scenarios
    - Calibration findings preserved unless target module changed
    - Writes FINDINGS_INDEX.json with source/age metadata

    Returns {"path/to/finding.md": "new"|"reused"|"deleted", ...}
    """
```

```python
def should_recommend_full_crawl(diff_analysis: Dict) -> Tuple[bool, str]:
    """
    Heuristic: when is incremental unsafe?

    Returns (True, reason) if full crawl recommended:
    - scope_ratio > 0.5 (more than half the codebase affected)
    - No previous crawl exists
    - Previous crawl is > 14 days old
    - Architectural changes detected (new top-level packages, deleted packages)
    - More than 50 files changed (major refactor)
    - Domain facet change detected (new framework import)
    """
```

```python
def parse_change_log(log_path: str) -> List[Dict[str, str]]:
    """
    Parse docs/.onboard_changes.log into structured section hints.

    Format per line: {ISO_TIMESTAMP} | {FILE:LINE} | {SECTION_PATH} | {DESCRIPTION}

    Returns list of:
    {
        "timestamp": str,
        "file_line": str,
        "section_path": str,   # e.g. "Gotchas / Process Management"
        "description": str,
    }

    Tolerates malformed lines (skip with warning to stderr).
    Returns empty list if file doesn't exist.
    """
```

After the diff crawl processes the log, archive it:
```bash
# Archive processed change log entries
if [ -f docs/.onboard_changes.log ]; then
    mv docs/.onboard_changes.log docs/.onboard_changes.log.processed
fi
```

### Change 4: Update SKILL.md with incremental refresh flow

**File:** `.claude/skills/deep-crawl/SKILL.md`
**Effort:** ~80 lines added to Phase 0 and Phase 1, plus new Phase 2b

**Phase 0 addition:** After existing setup, add diff detection:

```markdown
**For `refresh` mode only — Diff Analysis:**

```bash
# Read previous crawl's git hash
PREV_HASH=$(grep "Git commit:" .deep_crawl/CRAWL_PLAN.md | awk '{print $NF}')
CURRENT_HASH=$(git rev-parse --short HEAD)

if [ "$PREV_HASH" = "$CURRENT_HASH" ]; then
    echo "No changes since last crawl. Nothing to refresh."
    exit 0
fi

# Run xray on current state (needed for import graph)
python xray.py . --output json

# Compute diff analysis
python -c "
from lib.git_analysis import get_changed_files
from lib.import_analysis import build_import_graph
from lib.crawl_diff import analyze_diff
import json

diff = analyze_diff('.', since_ref='$PREV_HASH', ...)
with open('.deep_crawl/DIFF_ANALYSIS.json', 'w') as f:
    json.dump(diff, f, indent=2, default=str)
print(f'Changed: {len(diff[\"changed_files\"])} files')
print(f'Scope: {len(diff[\"impact_scope\"][\"total_scope\"])} modules')
print(f'Recommendation: {diff[\"recommendation\"]}')
"
```

If recommendation is "full", tell user and run full crawl.
If recommendation is "incremental", proceed with filtered plan.
```

**Phase 1 modification:** Conditional planning:

```markdown
**For `refresh` mode — Incremental Plan:**

Read DIFF_ANALYSIS.json. Build an incremental CRAWL_PLAN.md that:
1. Marks out-of-scope tasks as `[skip]` (not `[x]` — distinguish from completed)
2. Marks in-scope tasks as `[ ]` (pending)
3. Adds new tasks for added files
4. Removes tasks for deleted files
5. Includes incremental metadata in header:

> **Mode**: Incremental refresh (since {PREV_HASH})
> **Changed**: {N} files ({M} modified, {A} added, {D} deleted)
> **Scope**: {S} modules ({C} changed + {H1} hop-1 + {H2} hop-2)
> **Reusing**: {R} finding files from previous crawl
> **New tasks**: {T} of {TOTAL}
```

**New Phase 2b: MERGE FINDINGS** (between Phase 2 and Phase 3):

```markdown
### Phase 2b: MERGE FINDINGS (Incremental Only)

After Phase 2 investigation completes, merge old + new findings:

```bash
python -c "
from lib.crawl_diff import merge_findings
import json

with open('.deep_crawl/DIFF_ANALYSIS.json') as f:
    diff = json.load(f)

result = merge_findings(
    previous_findings_dir='.deep_crawl/findings_previous',
    new_findings_dir='.deep_crawl/findings',
    diff_analysis=diff,
    output_dir='.deep_crawl/findings_merged',
)

# Replace findings/ with merged version
import shutil
shutil.rmtree('.deep_crawl/findings')
shutil.move('.deep_crawl/findings_merged', '.deep_crawl/findings')

print(json.dumps({k: sum(1 for v in result.values() if v == k) for k in ['new', 'reused', 'deleted']}, indent=2))
"
```

Verify merge:
```bash
ls .deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks,calibration}/*.md | wc -l
# Should equal: previous count - deleted + added
```

Phase 3 (ASSEMBLE) proceeds unchanged — it reads findings/ and doesn't know or care whether files are fresh or reused.
```

### Change 5: Update CRAWL_PLAN.md template

**File:** `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template`
**Effort:** ~15 lines

Add optional incremental metadata section:

```markdown
{%- if MODE == "incremental" %}

## Incremental Refresh

> Previous crawl: {PREV_TIMESTAMP} at commit `{PREV_HASH}`
> Current HEAD: `{CURRENT_HASH}`
> Changed files: {CHANGED_COUNT} ({MOD_COUNT} modified, {ADD_COUNT} added, {DEL_COUNT} deleted)
> Impact scope: {SCOPE_COUNT} modules ({CHANGED_MOD_COUNT} changed + {HOP1_COUNT} hop-1 + {HOP2_COUNT} hop-2)
> Scope ratio: {SCOPE_RATIO}% of codebase

### Reused Findings (not re-investigated)
{REUSED_LIST}

### Scope Breakdown
| Layer | Changed | Hop 1 | Hop 2 | Total |
|-------|---------|-------|-------|-------|
{LAYER_TABLE}

{%- endif %}
```

### Change 6: Phase 0 findings directory management

**File:** `.claude/skills/deep-crawl/SKILL.md` Phase 0
**Effort:** ~10 lines

For incremental mode, before Phase 2 investigation:

```bash
# Preserve previous findings for merge
if [ -d .deep_crawl/findings ] && [ -f .deep_crawl/DIFF_ANALYSIS.json ]; then
    mv .deep_crawl/findings .deep_crawl/findings_previous
    mkdir -p .deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks,calibration}
fi
```

This way Phase 2 writes NEW findings to a clean directory, and Phase 2b merges them with the previous findings.

### Change 6½: Calibration handling for incremental mode

In incremental mode, check if any calibration target (CAL_A, CAL_B, CAL_C) is in the impact scope. If yes, re-run that calibration target at the elevated quality floor (400w/10 FACT per `quality_gates.json` `calibration_findings`) and copy the result to `findings/calibration/`. If no calibration targets changed, copy `findings_previous/calibration/*.md` into merged findings unchanged.

```python
# In merge_findings():
for cal_file in ["cal_a.md", "cal_b.md", "cal_c.md"]:
    cal_target = get_calibration_target_module(cal_file)
    if cal_target in diff_analysis["calibration_targets_affected"]:
        # Re-run calibration — task added to incremental plan
        pass  # New finding will be written by sub-agent
    else:
        # Reuse previous calibration
        shutil.copy(
            f"{previous_findings_dir}/calibration/{cal_file}",
            f"{output_dir}/calibration/{cal_file}"
        )
```

After merge, propagate calibration exemplars to their batch directories as in full crawl:
```bash
[ -f findings/calibration/cal_a.md ] && cp findings/calibration/cal_a.md findings/traces/00_calibration.md
[ -f findings/calibration/cal_b.md ] && cp findings/calibration/cal_b.md findings/modules/00_calibration.md
[ -f findings/calibration/cal_c.md ] && cp findings/calibration/cal_c.md findings/cross_cutting/00_calibration.md
```

### Change 6¾: Quality gate applicability in incremental mode

All Phase 3-6 quality gates apply identically in incremental mode since those phases are unchanged. Specifically:

- **Batch 2 elevated floor:** 400w/10 FACT for single-module Protocol B findings
- **Playbook quality gate:** 800w/30 FACT/8 common mistakes/3.0 citation density per playbook
- **Traceability gate (Step 5c):** Every completed task must appear in assembled sections
- **Fact-level completeness check (Step 8b):** Every [FACT] citation from findings retained in assembled output
- **Document size floors:** From `quality_gates.json` (`document_size_floors`) and `compression_targets.json`
- **Citation density tiers:** High-evidence >= 3.0, medium >= 2.0, narrative >= 1.0 per 100 words

These gates run against the **merged** findings directory and the assembled document. No incremental-specific adjustments are needed — the merge step produces the same directory structure as a full crawl, so all quality machinery operates unchanged.

### Change 7: Add tests for new scanner functions

**File:** `tests/test_crawl_diff.py` (new file)
**Effort:** ~150 lines

Test cases:
- `test_get_changed_files_basic` — Mock git output, verify parsing
- `test_get_changed_files_no_python` — Non-Python changes filtered out
- `test_get_changed_files_renames` — R status handled correctly
- `test_compute_impact_scope_single_file` — One changed file, verify hop 1+2
- `test_compute_impact_scope_hub_module` — Hub module change → large blast radius
- `test_compute_impact_scope_leaf_module` — Leaf module change → small blast radius
- `test_should_recommend_full_crawl_high_scope` — >50% scope → full
- `test_should_recommend_full_crawl_many_files` — >50 files → full
- `test_should_recommend_full_crawl_facet_change` — New framework import → full
- `test_merge_findings_new_overrides_old` — Same module, new wins
- `test_merge_findings_preserves_old` — Out-of-scope kept
- `test_merge_findings_removes_deleted` — Deleted module cleaned up
- `test_merge_findings_all_seven_directories` — Verify impact/playbooks/calibration handled
- `test_analyze_diff_affected_impact_clusters` — Hub module change → cluster flagged
- `test_analyze_diff_affected_playbooks` — Playbook reference change detected
- `test_calibration_reuse` — Unchanged calibration targets preserved from previous
- `test_calibration_refresh` — Changed calibration target re-investigated
- `test_parse_change_log_basic` — Standard format parsed correctly
- `test_parse_change_log_missing_file` — Returns empty list
- `test_parse_change_log_malformed_lines` — Skipped with warning
- `test_hint_sections_override_scope` — Out-of-scope module still checked if hinted

### Change 8: Update COMMANDS.md

**File:** `.claude/skills/deep-crawl/COMMANDS.md`
**Effort:** ~10 lines

```markdown
| `@deep_crawl refresh` | Sequential | **Incremental** update for code changes — investigates only changed files + dependents |
| `@deep_crawl refresh --full` | Sequential | Force full re-crawl (ignore incremental heuristics) |
| `@deep_crawl refresh --since origin/main` | Sequential | Incremental from specific git ref |
```

## Files Modified

| File | Type | Lines | Description |
|------|------|-------|-------------|
| `lib/git_analysis.py` | Modified | +30 | `get_changed_files()`, `get_crawl_metadata_hash()` |
| `lib/import_analysis.py` | Modified | +40 | `compute_impact_scope()` |
| `lib/crawl_diff.py` | **New** | ~180 | `analyze_diff()` (with impact/playbook/facet/calibration/hint fields), `build_incremental_plan()` (with P7 + Protocol F tasks + hint_sections), `merge_findings()` (all 7 directories), `should_recommend_full_crawl()` (with facet detection), `parse_change_log()` |
| `tests/test_crawl_diff.py` | **New** | ~220 | Tests for all new functions including impact clusters, playbooks, calibration, facet changes, change log parsing |
| `.claude/skills/deep-crawl/SKILL.md` | Modified | +100 | Phase 0b diff analysis, Phase 1b incremental plan, Phase 2b merge findings, Phase 2c impact refresh, calibration handling |
| `.claude/skills/deep-crawl/COMMANDS.md` | Modified | +10 | Updated refresh command description |
| `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template` | Modified | +15 | Incremental metadata section |

**Total new code:** ~470 lines Python + ~125 lines markdown instructions

## Execution Flow: `@deep_crawl refresh`

```
1. Phase 0: Setup
   ├── Verify .deep_crawl/ exists with previous crawl
   ├── Verify output/<repo>/data/xray.json exists (or re-run xray)
   └── Check git hash match

2. Phase 0b: Diff Analysis (NEW)
   ├── get_changed_files(cwd, since_ref=previous_hash)
   ├── compute_impact_scope(import_graph, changed_modules)
   ├── Check: should_recommend_full_crawl()?
   │   ├── YES → tell user, run full crawl
   │   └── NO → continue incremental
   └── Write DIFF_ANALYSIS.json

3. Phase 1b: Incremental Plan (MODIFIED)
   ├── Load previous CRAWL_PLAN.md
   ├── Filter tasks by scope
   ├── Write incremental CRAWL_PLAN.md
   └── Preserve previous findings → findings_previous/

4. Phase 2: Crawl Batches 1-4 (UNCHANGED)
   ├── Sub-agents execute only pending tasks
   └── Write findings to findings/ (clean directory)

4b. Phase 2: Crawl Batches 5-6 — Impact + Playbooks (Protocol E/F for affected clusters)
    ├── Protocol E for hub modules with in-scope dependents
    └── Protocol F for playbooks referencing in-scope modules

5. Phase 2b: Merge Findings (NEW)
   ├── merge_findings(findings_previous/, findings/, ...)
   ├── Handles all 7 directories: traces, modules, cross_cutting,
   │   conventions, impact, playbooks, calibration
   └── Replace findings/ with merged version

6. Phase 3-6: ASSEMBLE → CROSS-REF → VALIDATE → DELIVER (UNCHANGED)
   └── Reads merged findings/ (all 7 subdirs), produces DEEP_ONBOARD.md
```

## Edge Cases

**No previous crawl exists:**
- `should_recommend_full_crawl()` returns True
- Falls through to full crawl

**Previous crawl is stale (>14 days):**
- Recommend full crawl (configurable threshold)

**Scope ratio > 50% (major refactor):**
- Recommend full crawl — incremental overhead not worth it
- Log: "N files changed affecting M% of codebase. Running full crawl."

**File renamed (R status in git diff):**
- Treat as delete old + add new
- The old finding is removed, new finding generated
- Call graph and import graph from fresh xray handle the rename

**New top-level package added:**
- Recommend full crawl (architectural change)

**New framework import detected (facet change):**
- If `analyze_diff()` detects a new framework import that would add a domain facet (comparing pre/post framework detection against `domain_profiles.json`)
- Recommend full crawl (facet change is architectural)
- Log: "New domain facet detected ({facet}). Running full crawl."

**Cross-cutting concerns affected:**
- If a changed module participates in a cross-cutting concern (error handling, config, etc.), re-run that concern's Protocol C investigation
- Use grep on existing cross-cutting findings to detect references to changed modules

**Trace paths through affected modules:**
- If a critical path passes through an affected module, re-trace it
- Use the reverse call lookup to detect which traces include affected functions
- Re-trace produces updated finding → merge overwrites old

## Verification

```bash
# After implementing, test with:
cd /path/to/any/python/project

# Full crawl first
python /path/to/xray.py . --output both
@deep_crawl full

# Make a small change
echo "# test comment" >> some_module.py

# Incremental refresh
@deep_crawl refresh

# Verify:
cat .deep_crawl/DIFF_ANALYSIS.json | jq '.changed_files | length'  # Should be 1
cat .deep_crawl/DIFF_ANALYSIS.json | jq '.recommendation'          # Should be "incremental"
cat .deep_crawl/CRAWL_PLAN.md | grep -c "\[skip\]"                 # Should be > 0
cat .deep_crawl/CRAWL_PLAN.md | grep -c "\[ \]"                    # Should be small
wc -w .deep_crawl/DEEP_ONBOARD.md                                  # Should be similar to previous
diff .deep_crawl/DEEP_ONBOARD.md docs/DEEP_ONBOARD.md              # Should show targeted changes
```

## What This Enables

1. **Living documentation** — DEEP_ONBOARD.md stays fresh with every meaningful code change
2. **CI/CD integration** — Run `@deep_crawl refresh` as a post-merge hook; cost is proportional to change size
3. **PR review augmentation** — Before reviewing a PR, refresh the onboarding doc to see what the change affects
4. **Drift detection** — Compare pre/post DEEP_ONBOARD.md to see how a change affects documented behavior
5. **Post-hoc git enrichment** — After incremental assembly, `tools/enrich_onboard.py` can inject fresh git signals (risk, churn, velocity, coupling) into the updated document without re-investigation

## What This Does NOT Change

- The investigation protocols (A-F) — unchanged
- The assembly pipeline (Phase 3) — unchanged
- The cross-referencing (Phase 4) — unchanged
- The validation pipeline (Phase 5) — unchanged
- The delivery mechanism (Phase 6) — unchanged
- The evidence standards ([FACT], [PATTERN], [ABSENCE]) — unchanged
- The DEEP_ONBOARD.md template — unchanged

The incremental crawl only changes HOW MUCH of the pipeline runs, not WHAT it does. Every finding still meets the same evidence standards. The output document has the same structure and quality guarantees.

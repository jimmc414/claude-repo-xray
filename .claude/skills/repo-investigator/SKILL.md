# Repo Investigator

Semantic analysis tools for deep codebase understanding. Builds on Phase 1's structural analysis (repo-xray) to provide behavioral insights.

## Strategy: "Triangulate, Trace, Verify"

1. **Triangulate** - Use Unified Priority Score to find critical code
2. **Trace** - Surgically read complex methods, skeletonize the rest
3. **Verify** - Validate that imports and dependencies resolve

## Tools

### complexity.py - Unified Priority Scoring

Calculates priority score combining multiple signals to identify the "brain" of the codebase.

```bash
# Basic complexity scan (CC only)
python .claude/skills/repo-investigator/scripts/complexity.py [directory]

# Unified scoring with Phase 1 data (4-signal formula)
python .claude/skills/repo-investigator/scripts/complexity.py src/ \
  --unified deps.json git.json

# Enhanced scoring with test coverage (5-signal formula)
python .claude/skills/repo-investigator/scripts/complexity.py src/ \
  --unified deps.json git.json \
  --warm-start-debug ./WARM_START_debug

# Top N results with JSON output
python .claude/skills/repo-investigator/scripts/complexity.py src/ --top 10 --json
```

**Unified Priority Score Formulas:**

4-signal (default): `Priority = (CC * 0.35) + (ImportWeight * 0.25) + (RiskScore * 0.25) + (Freshness * 0.15)`

5-signal (with test coverage): `Priority = (CC * 0.30) + (ImportWeight * 0.20) + (RiskScore * 0.20) + (Freshness * 0.15) + (Untested * 0.15)`

**Options:**
- `--unified DEPS GIT` - Phase 1 JSON files for unified scoring
- `--warm-start-debug PATH` - Enable 5-signal formula with test coverage
- `--top N` - Limit results (default: 10)
- `--min-score N` - Filter by minimum score
- `--json` - JSON output
- `-v, --verbose` - Progress messages
- `--debug` - Write to PRIORITY_debug/

---

### smart_read.py - Surgical Reader

Reads full implementation of complex methods while skeletonizing the rest. Provides semantic context at ~10% token cost.

```bash
# Auto-expand top N complex methods
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py \
  --focus-top 3

# Expand specific methods
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py \
  --focus process_order validate_input

# Skeleton only (no expansion)
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py \
  --focus-top 0

# Coupled file analysis (show cross-references)
python .claude/skills/repo-investigator/scripts/smart_read.py \
  src/config.py src/providers/anthropic.py --coupled
```

**Options:**
- `--focus-top N` - Auto-expand top N complex methods (default: 3)
- `--focus NAME...` - Expand specific methods by name
- `--coupled` - Analyze multiple files together, show cross-references
- `-v, --verbose` - Progress messages
- `--debug` - Write to SMART_READ_debug/

---

### verify.py - Import Verifier

Validates that imports and symbols resolve correctly.

```bash
# Safe mode (AST-only, no execution)
python .claude/skills/repo-investigator/scripts/verify.py src/core/workflow.py --mode safe

# Strict mode (runtime import check)
python .claude/skills/repo-investigator/scripts/verify.py mypackage.core.workflow --mode strict

# Verify directory with untested modules first
python .claude/skills/repo-investigator/scripts/verify.py src/ \
  --prioritize-untested \
  --warm-start-debug ./WARM_START_debug

# JSON output
python .claude/skills/repo-investigator/scripts/verify.py src/ --json
```

**Options:**
- `--mode safe|strict` - Verification mode (default: safe)
- `--prioritize-untested` - Verify untested modules first
- `--warm-start-debug PATH` - Test coverage data for prioritization
- `--json` - JSON output
- `-v, --verbose` - Progress messages
- `--debug` - Write to VERIFY_debug/

---

### generate_hot_start.py - Single Command Generator

Generates complete HOT_START.md in a single command, parallel to Phase 1's generate_warm_start.py.

```bash
# Basic usage (CC-only if no Phase 1 data)
python .claude/skills/repo-investigator/scripts/generate_hot_start.py [directory]

# With custom output file
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ -o HOT_START.md

# Different detail levels
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ -d compact  # ~400 tokens
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ -d normal   # ~2700 tokens
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ -d verbose  # ~3000 tokens
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ -d full     # ~3500 tokens (default)

# With Phase 1 data directory
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ \
  --phase1-dir ./phase1_data

# Full analysis with debug output
python .claude/skills/repo-investigator/scripts/generate_hot_start.py src/ --debug -v
```

**Features:**
- Automated Logic Map generation from AST analysis
- Import verification with warning detection
- Hidden dependency detection (env vars, external services, config files)
- Works with or without Phase 1 data (CC-only vs unified scoring)
- Configurable detail levels for token budget control

**Detail Levels:**

| Level | Name | Tokens | Content |
|-------|------|--------|---------|
| 1 | compact | ~400 | Priority table + verification summary only |
| 2 | normal | ~2700 | Standard output with logic maps |
| 3 | verbose | ~3000 | Preserve string literals in logic maps |
| 4 | full | ~3500 | Add method signatures and docstrings (default) |

**Options:**
- `-d, --detail LEVEL` - Detail level: compact/1, normal/2, verbose/3, full/4 (default: full)
- `-o, --output FILE` - Output file path (default: HOT_START.md)
- `--phase1-dir PATH` - Directory containing deps.json, git.json
- `--top N` - Number of priority files to analyze (default: 10)
- `--json` - Output raw data as JSON
- `-v, --verbose` - Progress messages
- `--debug` - Write to HOT_START_debug/

---

## Workflow

### Option A: Single Command (Recommended)

```bash
# Generate HOT_START.md in one command
python .claude/skills/repo-investigator/scripts/generate_hot_start.py . -v

# With Phase 1 data for unified scoring
python .claude/skills/repo-xray/scripts/dependency_graph.py . --json > deps.json
python .claude/skills/repo-xray/scripts/git_analysis.py . --json > git.json
python .claude/skills/repo-investigator/scripts/generate_hot_start.py . -v
```

### Option B: Step-by-Step

For more control, run tools individually:

#### 1. Generate Phase 1 Data

```bash
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --json > deps.json
python .claude/skills/repo-xray/scripts/git_analysis.py . --json > git.json

# Optional: Generate test coverage data
python .claude/skills/repo-xray/scripts/generate_warm_start.py . --debug -v
```

#### 2. Calculate Unified Priorities

```bash
python .claude/skills/repo-investigator/scripts/complexity.py src/ \
  --unified deps.json git.json \
  --warm-start-debug ./WARM_START_debug \
  --top 10
```

#### 3. Surgical Read Top Files

```bash
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py --focus-top 3
```

#### 4. Verify Critical Modules

```bash
python .claude/skills/repo-investigator/scripts/verify.py src/ --mode safe
```

---

## Debug Output Chain

Each tool supports `--debug` to output intermediate data:

```
Phase 1: WARM_START.md + WARM_START_debug/
    ↓
Phase 2: generate_hot_start.py --debug → HOT_START.md + HOT_START_debug/
```

Or for step-by-step:

```
Phase 1: WARM_START_debug/
    ↓
Phase 2: complexity.py --debug → PRIORITY_debug/
    ↓
         smart_read.py --debug → SMART_READ_debug/
    ↓
         verify.py --debug → VERIFY_debug/
    ↓
         HOT_START.md
```

---

## Token Budget

| Operation | Tokens | Purpose |
|-----------|--------|---------|
| complexity.py output | ~200 | File targeting |
| smart_read.py (per file) | ~300-800 | Deep reading |
| verify.py output | ~50-200 | Validation |
| Full workflow | ~1000-2000 | Complete analysis |

---

## Output: HOT_START.md

The final output is a semantic companion to WARM_START.md containing:
- **Priority Table** - Top files ranked by unified score
- **Logic Maps** - Dense pseudocode of critical paths
- **Verified Modules** - Import validation results
- **Hidden Dependencies** - Environment variables, external services

See `templates/HOT_START.md.template` for the full template.

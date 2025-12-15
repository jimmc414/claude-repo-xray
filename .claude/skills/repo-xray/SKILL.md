---
name: repo-xray
description: AST-based Python codebase analysis. Use for exploring architecture, extracting interfaces, mapping dependencies, or generating onboarding documentation.
---

# repo-xray

X-Ray scanner for Python codebases. Extracts 37+ signals across structure, behavior, and history to solve the cold start problem for AI coding assistants.

## The Problem

```
Codebase:        2,000,000 tokens
Context Window:    200,000 tokens
Gap:                    10x

AI cannot read the whole codebase. It needs an intelligent map.
```

## The Solution

X-Ray produces two outputs:

| Output | Size | Purpose |
|--------|------|---------|
| **Markdown** | ~8-15K | Curated summary — read this first |
| **JSON** | ~30-50K | Complete reference — query as needed |

Together, they compress a multi-million token codebase into actionable intelligence.

---

## Quick Start

```bash
# Full analysis with both outputs
python xray.py /path/to/project --output both --out ./analysis

# This creates:
#   analysis.md   — Curated summary for orientation
#   analysis.json — Complete data for reference
```

## X-Ray Presets

```bash
python xray.py . --preset minimal   # ~2K tokens — quick survey
python xray.py . --preset standard  # ~8K tokens — balanced
python xray.py . --preset full      # ~15K tokens — comprehensive (default)
```

## Key Options

```bash
# Output format
--output markdown     # Markdown only
--output json         # JSON only
--output both         # Both formats (recommended for agent)

# Output location
--out ./analysis      # Write to analysis.md and/or analysis.json

# Disable sections
--no-logic-maps       # Skip complex function analysis
--no-hazards          # Skip large file warnings
--no-git              # Skip git history analysis

# Other
--verbose            # Show progress
--help               # All options
```

---

## What X-Ray Extracts

### Structure (understand what exists)
- File tree with token estimates
- Class and function skeletons
- Type annotation coverage
- Decorator inventory

### Architecture (understand relationships)
- Import graph with layers (orchestration → core → foundation)
- Dependency distance (BFS shortest paths)
- Circular dependencies
- Hub modules (most connected)
- Orphan files (dead code candidates)

### History (understand evolution)
- Risk scores (churn × hotfixes × author count)
- Co-modification coupling (files that change together)
- Freshness categories (active/aging/stale/dormant)
- Git expertise per file

### Complexity (understand difficulty)
- Cyclomatic complexity per function
- Complexity hotspots (ranked)
- Async patterns

### Behavior (understand what code does)
- Side effects by type (DB, API, file, subprocess)
- Cross-module call graph
- State mutations
- Logic maps for complex functions

### Context (understand how to use)
- Entry points (CLI, main, API routes)
- CLI arguments (argparse, Click, Typer)
- Environment variables with defaults
- Pydantic validators and constraints
- Linter rules from config files
- Test patterns and example

### Safety (understand what to avoid)
- Hazard files (large/generated — don't read)
- Glob patterns for exclusion

---

## Agent Workflow (Four Phases)

The `repo_xray` agent uses this skill in four phases:

### Phase 1: ORIENT
```bash
python xray.py . --output both --out /tmp/xray
```
Agent reads markdown summary for quick orientation. Builds mental model of codebase shape.

### Phase 2: INVESTIGATE (Two Passes)

**Pass 1: Signal Verification**
- Agent uses Read/Grep/Glob to verify X-Ray signals
- Confirms or downgrades architectural pillars
- Assesses complexity: essential vs accidental
- Queries JSON for specific lookups when needed

**Pass 2: Gap Discovery**
- Search for patterns X-Ray didn't surface
- Look for error handling, retry logic, implicit dependencies
- Document counterintuitive behaviors (Gotchas)

### Phase 3: SYNTHESIZE
Agent produces curated onboarding document using template.
Not a dump — intelligent analysis with judgment.

**Required sections:**
- TL;DR (5 bullets)
- Quick Orientation
- Architecture diagram
- Critical Components (with [VERIFIED] tags)
- Data Flow
- Gotchas (counterintuitive behaviors)
- What X-Ray Missed

### Phase 4: VALIDATE
Agent tests its own output before delivering.
- Can common questions be answered from the doc?
- Are quality metrics met?

---

## Investigation Depth Presets

| Preset | Pillars | Hotspots | Side Effects | Target Output |
|--------|---------|----------|--------------|---------------|
| `quick` | Top 3 (skeleton only) | None | None | ~5K tokens |
| `standard` | Top 5 (100 lines each) | Top 3 | Critical only | ~15K tokens |
| `thorough` | Top 10 (full read small, 200 lines large) | Top 5 | All | ~25K tokens |

**Usage:**
```
@repo_xray analyze              # standard depth (default)
@repo_xray analyze --depth thorough   # deep investigation
@repo_xray survey               # quick depth
```

---

## Confidence Levels

All agent insights must be marked with confidence:

| Level | Meaning | Example |
|-------|---------|---------|
| `[VERIFIED]` | Read actual code and confirmed | "[VERIFIED] Retry uses exponential backoff (2s, 4s, 8s)" |
| `[INFERRED]` | Logical deduction from related code | "[INFERRED] Cache invalidates on config reload" |
| `[X-RAY SIGNAL]` | Directly from X-Ray, not independently verified | "[X-RAY SIGNAL] CC=67 for main()" |

---

## Quality Metrics

Agent must report these metrics with every onboarding document:

| Metric | Target |
|--------|--------|
| Pillars investigated | ≥50% of top 10 |
| Hotspots with verdicts | ≥3 |
| [VERIFIED] insights | ≥10 |
| Gotchas documented | ≥3 |
| Error paths documented | ≥2 |
| Compression ratio | ≥50:1 |

---

## Domain Detection

Agent auto-detects domain and adjusts investigation:

| Domain | Indicators | Extra Investigation |
|--------|------------|---------------------|
| **Web API** | FastAPI, Flask, Django, routes/ | Auth, rate limiting, validation |
| **ML/AI** | torch, tensorflow, models/, training | Training loop, inference pipeline |
| **Scientific** | hypothesis, experiment, research | Validation logic, rigor scoring |
| **CLI Tool** | argparse, click, typer, commands/ | Command structure, config loading |
| **Data Pipeline** | airflow, dagster, etl, pipeline | DAG structure, idempotency |

---

## Output Structure

### Markdown Summary

```markdown
# Codebase Analysis: project-name

## Summary
[File counts, lines, tokens, type coverage]

## Architecture
[Mermaid diagram showing layers and connections]

## Architectural Pillars
[Top 10 most important files, ranked]

## Complexity Hotspots
[Functions with highest cyclomatic complexity]

## Critical Classes
[Key class skeletons with signatures]

## Logic Maps
[Control flow analysis for complex functions]

## Side Effects
[I/O operations by category]

## Hazards
[Large files to avoid reading]

## Entry Points
[CLI commands, main functions]

## Environment Variables
[Required and optional env vars]

[...additional sections based on preset...]
```

### JSON Reference

```json
{
  "metadata": {
    "generated_at": "...",
    "preset": "standard",
    "file_count": 247,
    "total_tokens": 890000
  },
  "summary": { ... },
  "structure": {
    "files": { "path": { "lines": N, "tokens": N, "classes": [], "functions": [] } }
  },
  "imports": {
    "graph": { ... },
    "layers": { "orchestration": [], "core": [], "foundation": [] },
    "circular": [],
    "distance": { ... }
  },
  "complexity": {
    "hotspots": [ { "function": "", "file": "", "cc": N } ]
  },
  "git": {
    "risk": [],
    "coupling": [],
    "freshness": { "active": [], "aging": [], "stale": [], "dormant": [] }
  },
  "side_effects": {
    "by_type": { "db": [], "api": [], "file": [], "subprocess": [] }
  },
  "hazards": [],
  "entry_points": [],
  "environment_variables": [],
  ...
}
```

---

## Token Budgets

### X-Ray Output Sizes

| Preset | Markdown | JSON | Total |
|--------|----------|------|-------|
| minimal | ~2K | ~10K | ~12K |
| standard | ~8K | ~30K | ~38K |
| full | ~15K | ~50K | ~65K |

### Agent Workflow Budget

| Phase | Tokens | Purpose |
|-------|--------|---------|
| ORIENT | ~15K | Read X-Ray markdown |
| INVESTIGATE | ~15-25K | Selective file reads, JSON queries |
| SYNTHESIZE | ~15K | Output document |
| VALIDATE | ~1K | Self-test |
| **Total** | **~45-55K** | Full analysis workflow |

Note: Agent reads markdown (~8-15K), queries JSON selectively (~5K).
Total agent consumption is typically 15-25K, not the full JSON size.

---

## Large Codebase Strategy

For codebases >500 files:

### Strategy: Divide and Conquer

```bash
# 1. Quick survey first
python xray.py . --preset minimal

# 2. Focus on specific areas
python xray.py ./src/core --preset full
python xray.py ./src/api --preset full

# 3. Or use full scan with selective --no-X flags
python xray.py . --no-logic-maps --no-test-example
```

### Strategy: Prioritize Ruthlessly

```
1. Full X-Ray scan (get all signals)
2. Investigate ONLY:
   - Top 10 pillars (not all)
   - Hotspots with CC > 20 (not CC > 10)
   - Critical path side effects only
3. Document gaps explicitly
```

### Size-Based Strategy

| Codebase Size | Files | Strategy | Investigation Depth |
|---------------|-------|----------|---------------------|
| Small | <100 | Full | Everything |
| Medium | 100-500 | Full | Top signals |
| Large | 500-2000 | Prioritized | Top 10 each category |
| Very Large | >2000 | Divide & Conquer | Subsystem focus |

---

## Configuration

### Project Config

Place `.xray.json` in project root for automatic detection:

```json
{
  "sections": {
    "logic_maps": { "enabled": true, "count": 5 },
    "critical_classes": { "enabled": true, "count": 10 },
    "hazards": true,
    "git": true
  }
}
```

### Generate Template

```bash
python xray.py --init-config > .xray.json
```

---

## Files

```
repo-xray/
├── xray.py                 # Main entry point
├── lib/
│   ├── ast_analysis.py     # Skeleton, complexity, types
│   ├── import_analysis.py  # Dependencies, layers, distance
│   ├── call_analysis.py    # Cross-module calls
│   ├── git_analysis.py     # Risk, coupling, freshness
│   ├── gap_features.py     # Logic maps, hazards, models
│   └── ...
├── formatters/
│   ├── markdown_formatter.py
│   └── json_formatter.py
├── configs/
│   └── presets.json
└── .claude/
    ├── agents/
    │   └── repo_xray.md    # Agent definition
    └── skills/
        └── repo-xray/
            ├── SKILL.md    # This file
            ├── COMMANDS.md # Quick reference
            └── templates/
                └── ONBOARD.md.template
```

---

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- Git (for history analysis)

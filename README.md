# repo-xray

Unified AST-based Python codebase analysis for AI coding assistants.

> **Quick start**: `python xray.py /path/to/project --verbose`

## The Problem

AI coding assistants face a cold start problem: a 200K token context window cannot directly ingest a codebase that may span millions of tokens, yet the assistant must understand the architecture to work effectively.

## The Solution

A **unified analysis tool** that extracts 28+ signals across 6 dimensions in a single pass:

- **Structure** (4): skeleton, tokens, files, interfaces
- **Architecture** (4): layers, orphans, circulars, import aliases
- **History** (5): risk scores, coupling pairs, freshness, commit sizes, expertise
- **Complexity** (4): cyclomatic complexity, hotspots, async patterns, type coverage
- **Behavior** (6): side effects (5 types), cross-module calls, reverse lookup
- **Coverage** (5): test files, functions, fixtures, tested/untested dirs

The tool produces a comprehensive reference (~2K-15K tokens depending on preset) that helps an AI effectively understand a multimillion token repository within a limited context window.

## Usage

### Basic Usage

```bash
# Full analysis (default)
python xray.py /path/to/project

# With preset for smaller output
python xray.py /path/to/project --preset minimal      # ~2K tokens
python xray.py /path/to/project --preset standard     # ~8K tokens
python xray.py /path/to/project --preset full         # ~15K tokens (default)

# With specific analyses only
python xray.py /path/to/project --skeleton --imports --git

# Output formats
python xray.py /path/to/project --output json         # JSON only (default)
python xray.py /path/to/project --output markdown     # Markdown only
python xray.py /path/to/project --output both         # Both formats

# Write to files
python xray.py /path/to/project --output both --out ./analysis
# Creates: analysis.json, analysis.md

# Verbose progress
python xray.py /path/to/project --verbose
```

### Claude-Driven Analysis

Paste one of these prompts into Claude Code:

```
Analyze this codebase using xray.py:
python xray.py . --verbose --preset standard
```

```
Generate complete analysis documentation:
python xray.py . --output both --out ./analysis --verbose
```

### Analysis Switches

Individual switches override presets:

| Switch | Description |
|--------|-------------|
| `--skeleton` | Extract code skeletons (classes, functions, signatures) |
| `--complexity` | Calculate cyclomatic complexity hotspots |
| `--git` | Analyze git history (risk, coupling, freshness) |
| `--imports` | Build import graph, detect orphans, alias tracking |
| `--calls` | Cross-module call analysis, reverse lookup |
| `--side-effects` | Detect I/O, network, DB operations |
| `--tests` | Test coverage and fixture analysis |
| `--tech-debt` | TODO/FIXME/HACK marker detection |
| `--types` | Type annotation coverage |
| `--decorators` | Decorator inventory |
| `--author-expertise` | Git blame expertise analysis |
| `--commit-sizes` | Commit size analysis |

### Presets

| Preset | Includes | Token Estimate |
|--------|----------|----------------|
| `minimal` | skeleton, imports | ~2K |
| `standard` | + complexity, git, calls, side-effects, tests, tech-debt | ~8K |
| `full` | All signals | ~15K |

### Gap Analysis Features (Markdown Enhancements)

These features enhance the markdown output with additional context:

| Switch | Description |
|--------|-------------|
| `--mermaid` | Include Mermaid architecture diagram |
| `--priority-scores` | Show Architectural Pillars (by import weight) + Maintenance Hotspots (by git risk) |
| `--inline-skeletons N` | Include skeleton code for top N critical classes (with docstrings) |
| `--hazards` | List large files and directories that may waste context |
| `--data-models` | Show Pydantic/dataclass/TypedDict models grouped by domain |
| `--logic-maps N` | Include logic maps for top N complex functions (with heuristics) |
| `--entry-points` | Highlight CLI entry points and main functions |
| `--side-effects-detail` | Show detailed side effects per file |
| `--layer-details` | Show import weight and file details per architectural layer |
| `--prose` | Generate natural language summary of the codebase |
| `--verify-imports` | Verify and count internal/external imports |
| `--explain` | Add explanatory blockquotes before each major section |
| `--persona-map` | Scan for and display agent prompts/personas |

**Example with gap analysis:**

```bash
python xray.py /path/to/project --output markdown --out ./analysis \
  --preset full --mermaid --priority-scores --hazards --data-models \
  --entry-points --prose --inline-skeletons 10 --layer-details --explain
```

## Example Output

### JSON Structure

```json
{
  "metadata": {
    "tool_version": "2.0.0",
    "generated_at": "2025-12-14T...",
    "target_directory": "/path/to/project",
    "preset": "full",
    "file_count": 150
  },
  "summary": {
    "total_files": 150,
    "total_lines": 45000,
    "total_tokens": 180000,
    "total_functions": 1200,
    "total_classes": 85,
    "type_coverage": 72.5
  },
  "structure": { ... },
  "complexity": { "hotspots": [...], "average_cc": 3.2 },
  "git": { "risk": [...], "coupling": [...], "freshness": {...} },
  "imports": { "graph": {...}, "aliases": [...], "orphans": [...] },
  "calls": { "cross_module": {...}, "most_called": [...] },
  "side_effects": { "by_type": {...}, "by_file": {...} },
  "tests": { "test_file_count": 50, "fixtures": [...] },
  "tech_debt": { "markers": {...}, "total_count": 45 }
}
```

### Markdown Output

```markdown
# Codebase Analysis: project-name

Generated: 2025-12-14 | Preset: full | Files: 150

## Summary

| Metric | Value |
|--------|-------|
| Python files | 150 |
| Total lines | 45,000 |
| Functions | 1,200 |
| Classes | 85 |
| Type coverage | 72.5% |

## Complexity Hotspots

| CC | Function | File |
|----|----------|------|
| 38 | `generate_skeleton` | ast_analysis.py |
| 27 | `analyze_file` | ast_analysis.py |
...
```

## Limitations

Uses Python's built-in AST parser, so currently Python-only.

---

## Analysis Signals

### Skeleton Extraction

**What**: Class definitions, method signatures, type annotations, decorators, constants with line numbers.

**Why**: Understanding interfaces doesn't require reading implementations. A 10K token file often has a 500 token skeleton.

**How**: AST parsing extracts declarations without function bodies. Achieves ~95% token reduction.

### Complexity Analysis

**What**: Cyclomatic complexity (CC) per function, hotspots, async patterns.

**Why**: High CC (>10) indicates complex code that's hard to test and understand.

**How**: Counts decision points: `if`, `elif`, `for`, `while`, `except`, `and`, `or`.

### Git History Analysis

**Risk Score** combines:
- **Churn**: Commit frequency (high = active/buggy)
- **Hotfix density**: Commits with "fix", "bug", "hotfix" keywords
- **Author count**: Many authors = coordination overhead

**Coupling Detection**: Files that change together across commits.

**Freshness**: Active (<30d), Aging (30-90d), Stale (90-180d), Dormant (>180d).

### Import Analysis

**What**: Dependency graph, architectural layers, orphan detection, circular dependencies.

**New features**:
- **Import aliases**: Tracks `import pandas as pd` patterns
- **Dependency distance**: Calculates transitive import hops
- **Hub detection**: Most connected modules

### Cross-Module Call Analysis (NEW)

**What**: Where functions are called across module boundaries.

**Why**: Understanding call relationships reveals impact of changes.

**Features**:
- Cross-module call site detection
- Reverse lookup ("Who calls this?")
- Most-called functions ranking
- Impact rating (low/medium/high)

### Side Effect Detection

**Categories**: Database, API, File I/O, Environment, Subprocess.

**How**: Pattern matching on function calls.

### Test Coverage

**What**: Test file counts, function estimates, fixtures, tested/untested modules.

**Why**: Test metadata reveals coverage gaps without reading test content.

---

## Installation

### Option 1: Clone and Use

```bash
git clone https://github.com/jimmc414/claude-repo-xray.git
cd claude-repo-xray
python xray.py /path/to/your/project --verbose
```

### Option 2: Copy to Project

```bash
# Copy the tool to your project
cp -r /path/to/claude-repo-xray/xray.py /path/to/your/project/
cp -r /path/to/claude-repo-xray/lib /path/to/your/project/
cp -r /path/to/claude-repo-xray/configs /path/to/your/project/
cp -r /path/to/claude-repo-xray/formatters /path/to/your/project/

cd /path/to/your/project
python xray.py . --verbose
```

### Option 3: Claude Skill

The tool is available as a Claude skill. Use the repo-xray skill to analyze codebases.

---

## File Structure

```
claude-repo-xray/
├── xray.py                     # Main entry point (unified tool)
├── README.md
├── lib/                        # Analysis modules
│   ├── __init__.py
│   ├── file_discovery.py       # File finding, ignore patterns
│   ├── ast_analysis.py         # Skeleton, complexity, types, decorators
│   ├── import_analysis.py      # Dependencies, aliases, distances
│   ├── call_analysis.py        # Cross-module calls, reverse lookup
│   ├── git_analysis.py         # Risk, coupling, freshness
│   ├── tech_debt_analysis.py   # TODO/FIXME markers
│   ├── test_analysis.py        # Test coverage, fixtures
│   └── gap_features.py         # Priority scores, hazards, data models, etc.
├── formatters/                 # Output formatting
│   ├── __init__.py
│   ├── json_formatter.py       # JSON output
│   └── markdown_formatter.py   # Markdown output
├── configs/                    # Configuration
│   ├── presets.json            # minimal/standard/full definitions
│   └── ignore_patterns.json    # Files/dirs to skip
├── tests/                      # Unit tests
│   └── test_gap_features.py    # Tests for gap analysis features
├── examples/                   # Example outputs
│   ├── WARM_START.md           # Legacy example
│   └── HOT_START.md            # Legacy example
├── archived/                   # Legacy scripts (for reference)
│   ├── generate_warm_start.py  # Old Phase 1 generator
│   └── generate_hot_start.py   # Old Phase 2 generator
└── .claude/                    # Claude skill integration
    └── skills/
        └── repo-xray/
```

---

## Token Budget

| Operation | Tokens | Use Case |
|-----------|--------|----------|
| `--preset minimal` | ~2K | Quick structural overview |
| `--preset standard` | ~8K | Balanced analysis |
| `--preset full` | ~15K | Complete analysis |
| `--skeleton` only | ~5K | Just code interfaces |
| `--imports` only | ~3K | Just dependencies |
| `--git` only | ~2K | Just history analysis |

---

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## License

MIT

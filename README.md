# repo-xray

Unified AST-based Python codebase analysis for AI coding assistants.

> **Quick start**: `python xray.py /path/to/project` (all sections enabled by default)

## The Problem

AI coding assistants face a cold start problem: a 200K token context window cannot directly ingest a codebase that may span millions of tokens, yet the assistant must understand the architecture to work effectively.

## The Solution

A **unified analysis tool** that extracts 37+ signals across 7 dimensions in a single pass:

- **Structure** (4): skeleton, tokens, files, interfaces
- **Architecture** (5): layers, orphans, circulars, import aliases, data flow
- **History** (5): risk scores, coupling pairs, freshness, commit sizes, expertise
- **Complexity** (4): cyclomatic complexity, hotspots, async patterns, type coverage
- **Behavior** (6): side effects (5 types), cross-module calls, reverse lookup
- **Coverage** (5): test files, functions, fixtures, tested/untested dirs
- **Context** (8): CLI args, instance vars, Pydantic validators, env defaults, test idioms, linter rules, hazard patterns, GitHub metadata

The tool produces a comprehensive reference (~2K-15K tokens depending on preset) that helps an AI effectively understand a multimillion token repository within a limited context window.

## Usage

### Basic Usage (v3.1 - Config-Driven)

**All sections are enabled by default.** No need to remember flags - just run:

```bash
python xray.py /path/to/project
```

This generates a complete analysis with all 25+ sections. To customize, disable what you don't need:

```bash
# Disable specific sections
python xray.py . --no-explain --no-persona-map

# Use a preset for smaller output
python xray.py . --preset minimal      # ~2K tokens
python xray.py . --preset standard     # ~8K tokens

# Use a custom config file
python xray.py . --config my_config.json

# Generate a config template to customize
python xray.py --init-config > .xray.json
```

### Configuration

The tool supports three ways to customize output:

1. **Project config**: Place `.xray.json` in your project root (auto-detected)
2. **Explicit config**: Use `--config path/to/config.json`
3. **CLI flags**: Use `--no-<section>` to disable specific sections

Generate a config template:

```bash
python xray.py --init-config > .xray.json
```

Example config (all sections shown, set to `false` to disable):

```json
{
  "sections": {
    "summary": true,
    "prose": true,
    "mermaid": true,
    "architectural_pillars": true,
    "maintenance_hotspots": true,
    "complexity_hotspots": true,
    "critical_classes": {"enabled": true, "count": 10},
    "data_models": true,
    "logic_maps": {"enabled": true, "count": 5},
    "hazards": true,
    "entry_points": true,
    "explain": true,
    "persona_map": true,
    "github_about": true,
    "data_flow": true,
    "cli_arguments": true,
    "instance_vars": true,
    "pydantic_validators": true,
    "hazard_patterns": true,
    "env_defaults": true,
    "test_example": true,
    "linter_rules": true
  }
}
```

### Disable Flags

Quickly disable sections without a config file:

| Flag | Disables |
|------|----------|
| `--no-prose` | Natural language summary |
| `--no-mermaid` | Architecture diagram |
| `--no-priority-scores` | Architectural Pillars + Maintenance Hotspots |
| `--no-critical-classes` | Critical class skeletons |
| `--no-data-models` | Pydantic/dataclass models |
| `--no-logic-maps` | Complex function logic maps |
| `--no-hazards` | Large file warnings |
| `--no-entry-points` | CLI entry points |
| `--no-explain` | Explanatory blockquotes |
| `--no-persona-map` | Agent prompts/personas |

### Presets

| Preset | Description | Token Estimate |
|--------|-------------|----------------|
| `minimal` | Structure + imports only | ~2K |
| `standard` | Core analysis, balanced output | ~8K |
| (default) | All sections enabled | ~15-20K |

### Output Options

```bash
# Output formats
python xray.py . --output markdown     # Markdown (default)
python xray.py . --output json         # JSON
python xray.py . --output both         # Both formats

# Write to files
python xray.py . --out ./analysis      # Creates analysis.md (and .json if both)

# Verbose progress
python xray.py . --verbose
```

### Available Sections

All sections are enabled by default. Here's what's included:

| Section | Description |
|---------|-------------|
| `summary` | File counts, lines, tokens, type coverage |
| `prose` | Natural language architecture overview |
| `mermaid` | Architecture diagram (viewable in GitHub/VS Code) |
| `architectural_pillars` | Most-imported files (understand these first) |
| `maintenance_hotspots` | High-risk files by git history |
| `complexity_hotspots` | Functions with highest cyclomatic complexity |
| `critical_classes` | Top N classes with skeleton code + docstrings |
| `data_models` | Pydantic/dataclass/TypedDict models by domain |
| `logic_maps` | Control flow analysis for complex functions |
| `import_analysis` | Architectural layers, orphans, circulars |
| `layer_details` | Import weight per layer |
| `git_risk` | Risk scores per file |
| `coupling` | Files that change together |
| `freshness` | Active/aging/stale/dormant files |
| `side_effects` | I/O, network, DB operations |
| `side_effects_detail` | Per-function side effects |
| `entry_points` | CLI and main() entry points |
| `environment_variables` | Env vars used in code |
| `hazards` | Large files that waste context |
| `test_coverage` | Test files, fixtures, coverage |
| `tech_debt_markers` | TODO/FIXME/HACK comments |
| `verify_imports` | Import path verification |
| `signatures` | Full method signatures |
| `state_mutations` | Attribute modifications |
| `verify_commands` | Verification commands |
| `explain` | Explanatory text before sections |
| `persona_map` | Agent prompts and personas |
| **v3.1 Features** | |
| `github_about` | GitHub repo description and topics |
| `data_flow` | Data flow direction annotation in Mermaid |
| `cli_arguments` | CLI argument extraction (argparse/click/typer) |
| `instance_vars` | Instance variables from `__init__` in class skeletons |
| `pydantic_validators` | Pydantic Field() constraints and validators |
| `hazard_patterns` | Glob patterns for hazard files |
| `env_defaults` | Environment variable default values |
| `test_example` | One-shot test file example ("Rosetta Stone") |
| `linter_rules` | Linter rules from pyproject.toml/ruff.toml |

---

## v3.1 Features (New)

### 1. GitHub About (`github_about`)

Pulls repository description and topics from GitHub to provide immediate context.

**How it works:**
1. Tries `gh` CLI first (works for private repos with auth)
2. Falls back to GitHub API (public repos only)
3. Shows error message if unavailable

**Output:**
```markdown
## Summary

> **About:** AST-based Python codebase analysis for AI coding assistants.
> **Topics:** python, ast, codebase-analysis, ai-tools
```

### 2. Data Flow Annotations (`data_flow`)

Adds data flow direction analysis to the Mermaid architecture diagram.

**How it works:**
- Analyzes cross-module call patterns
- Determines if system is push-based (higher layers call lower) or pull-based (lower call higher)

**Output:**
```markdown
*Data Flow: Foundation → Core → Orchestration (push-based)*
```

### 3. CLI Arguments Extraction (`cli_arguments`)

Extracts command-line arguments from entry points, supporting argparse, click, and typer.

**Output:**
```markdown
### CLI Arguments

**main.py:**

| Argument | Required | Default | Help |
|----------|----------|---------|------|
| `--query` | Yes | - | Query to execute |
| `--config` | No | config.json | Config file path |
| `--verbose` | No | False | Enable verbose output |
```

### 4. Instance Variables (`instance_vars`)

Shows `self.x = ...` assignments from `__init__` methods in class skeletons, helping AI understand object state.

**Output:**
```python
class DatabaseManager:  # L42
    def __init__(self, host: str, port: int = 5432)

    # Instance variables:
    self.connection = None
    self.pool_size = 10
    self.timeout = 30.0
    self._cache = {}

    def connect(self) -> Connection: ...
```

### 5. Pydantic Validators (`pydantic_validators`)

Extracts `Field()` constraints and `@validator` decorators from Pydantic models.

**Output:**
```markdown
**Config** [Pydantic] (config.py)

| Field | Type | Constraints |
|-------|------|-------------|
| `max_cost_usd` | float | gt=0, le=1000 |
| `timeout` | int | ge=1, default=30 |
| `name` | str | min_length=1 |

*Validators:* `validate_name`, `check_cost`
```

### 6. Hazard Glob Patterns (`hazard_patterns`)

Derives glob patterns from large file paths, making it easy to exclude them.

**Output:**
```markdown
### Patterns to Exclude

*Use these glob patterns to skip large files:*

- `data/artifacts/**` (3 files, ~50K tokens)
- `logs/*.json` (5 files, ~100K tokens)
- `cache/*.pkl` (2 files, ~20K tokens)
```

### 7. Environment Variable Defaults (`env_defaults`)

Extracts default values from `os.getenv()` calls, showing which vars are required vs optional.

**Output:**
```markdown
## Environment Variables

| Variable | Default | Required | Location |
|----------|---------|----------|----------|
| `DATABASE_URL` | - | **Yes** | config.py:10 |
| `LOG_LEVEL` | "INFO" | No | logging.py:5 |
| `TIMEOUT` | 30 | No | client.py:20 |
```

### 8. Test Example ("Rosetta Stone") (`test_example`)

Includes one complete, representative test file (≤50 lines) showing the project's testing patterns.

**Output:**
```markdown
## Testing Idioms

> **How to use:** Use this test as a template for writing new tests.

**Patterns used:** `pytest.fixture`, `unittest.mock.patch`, `pytest.mark`

**Example:** `tests/unit/test_service.py` (45 lines)

\`\`\`python
import pytest
from unittest.mock import Mock, patch
from myapp.service import MyService

@pytest.fixture
def mock_db():
    return Mock()

@pytest.mark.unit
def test_create_record(mock_db):
    with patch("myapp.service.database", mock_db):
        svc = MyService()
        result = svc.create("test")
        mock_db.insert.assert_called_once()
        assert result.id is not None
\`\`\`
```

### 9. Linter Rules (`linter_rules`)

Extracts linter configuration from pyproject.toml, ruff.toml, or .flake8 to help AI write compliant code.

**Output:**
```markdown
## Project Idioms

> **How to use:** Follow these rules to ensure your code passes CI.

**Linter:** ruff (from `pyproject.toml`)

| Rule | Value |
|------|-------|
| line_length | 100 |
| select | E, W, F, I, B |
| ignore | E501, B008 |

**Banned patterns:**
- `print()` - use logging instead
```

---

## Example Output

### JSON Structure

```json
{
  "metadata": {
    "tool_version": "3.1.0",
    "generated_at": "2025-12-15T...",
    "target_directory": "/path/to/project",
    "config": "defaults",
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

Generated: 2025-12-15 | Preset: None | Files: 150

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
│   ├── config_loader.py        # Configuration loading and merging
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
│   ├── default_config.json     # Full config (all sections enabled)
│   ├── minimal.json            # Minimal preset config
│   ├── standard.json           # Standard preset config
│   ├── presets.json            # Legacy preset definitions
│   └── ignore_patterns.json    # Files/dirs to skip
├── tests/                      # Unit tests
│   └── test_gap_features.py    # Tests for gap analysis features
├── examples/                   # Example outputs
│   ├── repo_xray_output_v31.md # v3.1 output for this repo
│   └── kosmos_xray_output_v31.md # v3.1 output for kosmos project
├── archived/                   # Legacy scripts (for reference)
│   ├── generate_warm_start.py  # Old Phase 1 generator
│   └── generate_hot_start.py   # Old Phase 2 generator
├── plans/                      # Implementation plans
│   └── deep-leaping-fern.md    # v3.1 feature plan
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
| (default - all sections) | ~15-20K | Complete analysis |
| With `--no-explain --no-persona-map` | ~12K | Full minus verbose sections |

---

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## License

MIT

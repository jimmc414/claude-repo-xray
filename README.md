# repo-xray

AST-based Python codebase analysis for AI coding assistants.

```bash
python xray.py /path/to/project
```

## The Problem

AI coding assistants face a cold start problem. A codebase might span 2 million tokens. A context window holds 200K. The assistant cannot read everything, yet must understand the architecture to work effectively.

Reading files at random wastes context on implementation details. Reading nothing leaves the assistant guessing. What's needed is a compressed representation—a map of the codebase that fits in context and tells the AI where to look.

## The Solution

This tool extracts 37 signals from a Python codebase in a single pass:

| Dimension | Signals |
|-----------|---------|
| Structure | Skeletons, tokens, files, interfaces |
| Architecture | Import layers, dependency distance, circular deps, hub modules |
| History | Risk scores, co-modification coupling, freshness, expertise |
| Complexity | Cyclomatic complexity, hotspots, async patterns |
| Behavior | Side effects (DB, API, file, subprocess), cross-module calls |
| Context | CLI arguments, env vars, Pydantic validators, linter rules |
| Safety | Hazard files, exclusion patterns |

Output: 2K-15K tokens (configurable) that compress a multi-million token codebase into actionable intelligence.

## Usage

```bash
# Full analysis (default)
python xray.py /path/to/project

# Quick survey
python xray.py . --preset minimal      # ~2K tokens

# Balanced analysis
python xray.py . --preset standard     # ~8K tokens

# Both markdown and JSON
python xray.py . --output both --out ./analysis
```

### Presets

| Preset | Output | Use Case |
|--------|--------|----------|
| `minimal` | ~2K tokens | Quick reconnaissance |
| `standard` | ~8K tokens | Balanced coverage |
| (default) | ~15K tokens | Comprehensive analysis |

### Selective Output

Disable sections you don't need:

```bash
python xray.py . --no-logic-maps --no-test-example --no-prose
```

Or create a `.xray.json` config in your project root:

```json
{
  "sections": {
    "logic_maps": { "enabled": true, "count": 5 },
    "hazards": true,
    "git": true
  }
}
```

Generate a config template: `python xray.py --init-config > .xray.json`

---

## Claude Code Integration

The tool includes Claude Code agents and skills that go beyond raw analysis. Instead of dumping X-Ray output, the agents use it as a map to guide intelligent investigation.

### The Design

```
X-Ray (the map)          repo_xray Agent           repo_retrospective Agent
----------------         -------------------       ------------------------
Extracts signals    -->  Investigates & curates   -->  QA & verification
~15K tokens              Adds judgment                 Ensures quality
Zero tokens              Uses Read/Grep/Glob           Scores actionability
```

### repo_xray Agent: Four-Phase Workflow

The `repo_xray` agent operates in four phases:

1. **ORIENT** — Run X-Ray, read the markdown summary, build mental model
2. **INVESTIGATE** — Use signals to guide deep reading with Read/Grep/Glob
   - **Pass 1**: Signal verification — confirm or downgrade X-Ray signals
   - **Pass 2**: Gap discovery — find what X-Ray missed
3. **SYNTHESIZE** — Produce curated onboarding documentation
4. **VALIDATE** — Self-test: "Can I answer common questions from this doc?"

This matters because X-Ray signals aren't always accurate. A "complexity hotspot" might be essential business logic or accidental complexity. A "pillar" module might be genuinely central or just a grab-bag of utilities. The agent verifies signals before including them in the final output.

### Confidence Levels

Every insight in the output is tagged:

| Level | Meaning |
|-------|---------|
| `[VERIFIED]` | Agent read the actual code and confirmed |
| `[INFERRED]` | Logical deduction from related code |
| `[X-RAY SIGNAL]` | Directly from X-Ray, not independently verified |

### What the Agent Produces

The final onboarding document includes:

- **TL;DR** — 5-bullet summary for 60-second orientation
- **Architecture diagram** — Mermaid visualization from X-Ray
- **Critical components** — Verified pillars with code context
- **Data flow** — Traced request path through the system
- **Gotchas** — Counterintuitive behaviors that would waste hours to discover
- **Debugging guide** — Common failure modes and remediation
- **Hazards** — Files to never read (would waste context)
- **Quality metrics** — Transparency about investigation depth

### Agent Modes

| Mode | Command | Purpose |
|------|---------|---------|
| `survey` | `@repo_xray survey` | Quick reconnaissance (~10K tokens) |
| `analyze` | `@repo_xray analyze` | Full onboarding document (~40K tokens) |
| `query` | `@repo_xray query "auth"` | Targeted investigation |
| `focus` | `@repo_xray focus ./src/api` | Deep dive on subsystem |
| `refresh` | `@repo_xray refresh` | Update existing analysis |

### Investigation Depth Presets

| Preset | Pillars | Hotspots | Side Effects | Output |
|--------|---------|----------|--------------|--------|
| `quick` | Top 3 (skeleton) | None | None | ~5K tokens |
| `standard` | Top 5 (100 lines) | Top 3 | Critical only | ~15K tokens |
| `thorough` | Top 10 (full read) | Top 5 | All | ~25K tokens |

---

## repo_retrospective Agent: Quality Assurance

The `repo_retrospective` agent provides QA for AI onboarding documentation. Run it at project end or mid-project to verify the onboarding document is effective.

### Five-Phase Workflow

1. **INVENTORY** — Catalog all claims in the onboarding document
2. **COVERAGE** — Compare against X-Ray source for gaps
3. **VERIFICATION** — Spot-check `[VERIFIED]` claims against actual code
4. **ACTIONABILITY** — Test if document answers 8 standard questions
5. **RECOMMENDATIONS** — Produce specific fixes

### Verdicts

| Verdict | Meaning |
|---------|---------|
| **Ship It** | High quality, ready for use |
| **Needs Minor Fixes** | Good, 1-3 small issues to address |
| **Needs Significant Rework** | Critical problems, re-run repo_xray |

### Retrospective Modes

| Mode | Command | Purpose |
|------|---------|---------|
| `full` | `@repo_retrospective full` | Complete QA (all 5 phases) |
| `quick` | `@repo_retrospective quick` | Verification audit only |
| `coverage` | `@repo_retrospective coverage` | Gap analysis only |
| `actionability` | `@repo_retrospective actionability` | Usability test only |

---

## Complete Workflow

```
Codebase (2M+ tokens)
       │
       ▼
X-Ray Scanner (Python AST, zero tokens, seconds)
       │
       ▼
Signal Extraction (~15K tokens)
       │
       ▼
repo_xray Agent (investigates, verifies, curates)
       │
       ▼
Warm Start Document (~15K tokens)
       │
       ▼
repo_retrospective Agent (QA)
       │
       ▼
Fresh Claude instance is productive immediately
```

**Cold start solved: Map + Judgment + Quality Assurance**

---

## Analysis Signals

### Skeleton Extraction

Extracts class definitions, method signatures, type annotations, and decorators—without function bodies. A 10K token file typically produces a 500 token skeleton. 95% reduction.

```python
class OrderEngine:  # L45
    def __init__(self, provider: PaymentProvider): ...
    def process(self, order: Order) -> Result: ...  # CC=25
    def validate(self, order: Order) -> bool: ...
```

### Complexity Analysis

Cyclomatic complexity per function. Counts decision points: `if`, `for`, `while`, `except`, `and`, `or`. High CC (>10) indicates code that's harder to understand and test.

Also counts `BoolOp` branches correctly—`if a and b and c` adds 2 to complexity, not 1.

### Import Analysis

Builds a dependency graph, then extracts:

- **Layers**: Orchestration (high imports, low importers), Core (balanced), Foundation (high importers)
- **Dependency distance**: BFS shortest paths between all module pairs
- **Hub modules**: Most connected modules (potential god objects)
- **Circular dependencies**: Bidirectional import pairs
- **Orphans**: Files with zero importers (dead code candidates)

### Git History Analysis

**Risk score** combines three signals:
- Churn (commit frequency)
- Hotfix density (commits containing "fix", "bug", "hotfix", "revert")
- Author count (coordination overhead)

**Co-modification coupling** finds files that change together even without import relationships. Uses frequent itemset mining on commit history, filtering bulk refactors (>20 files).

**Freshness**: Active (<30 days), Aging (30-90), Stale (90-180), Dormant (>180).

### Side Effect Detection

Categorizes function calls by side effect type:

| Category | Patterns |
|----------|----------|
| DB | `session.commit`, `cursor.execute`, `insert(`, `update(` |
| API | `requests.`, `httpx.`, `.post(`, `.put(` |
| File | `.write(`, `json.dump`, `pickle.dump` |
| Subprocess | `subprocess.`, `os.system`, `Popen(` |

Includes a whitelist to avoid false positives (`.get(`, `.read(`, `isinstance`).

### Logic Maps

For complex functions (CC > 15), generates a symbolic representation of control flow:

```
process_order(order):
  -> validate(order)
  -> valid?
     {status = processing}
     * for item in items:
       -> check_inventory(item)
       [DB: reserve(item)]
     -> calculate_total
     [DB: save(order)]
     -> Return(success)
```

Symbols: `->` control flow, `*` loop, `?` conditional, `{X}` state mutation, `[X]` side effect.

### Hazard Detection

Identifies files that would waste context:

- Large files (>10K tokens)
- Generated code (`**/generated_*.py`)
- Migrations, fixtures, artifacts

Outputs glob patterns for easy exclusion.

### Additional Signals

- **CLI arguments**: Extracted from argparse, Click, and Typer
- **Environment variables**: From `os.getenv()` with default values
- **Pydantic validators**: Field constraints and `@validator` decorators
- **Linter rules**: From pyproject.toml, ruff.toml, .flake8
- **Test patterns**: Representative test file as a "Rosetta Stone"

---

## Output Formats

### Markdown

Human-readable summary with tables, Mermaid diagrams, and code blocks. Renders in GitHub, VS Code, Obsidian.

### JSON

Structured data for programmatic consumption. The agent uses JSON for specific lookups while using markdown for orientation.

```bash
python xray.py . --output both --out ./analysis
# Creates: analysis.md, analysis.json
```

---

## Technical Details

### How It Works

Single-pass AST traversal using Python's `ast` module. Each file is parsed once; multiple analyzers extract different signals from the same tree.

Key techniques:
- `ast.walk()` for flat traversal (complexity counting)
- `ast.NodeVisitor` subclasses for stateful traversal (call graph)
- `collections.Counter` for frequency analysis
- `collections.deque` for BFS (dependency distance)
- Custom git log parsing with delimiter format

### Performance

For a 500-file codebase:
- AST analysis: ~2 seconds
- Git analysis: ~1 second (shells out to git)
- Total: ~5 seconds

No external dependencies. Stdlib only.

### Limitations

- Python only (uses Python's AST parser)
- Git history analysis requires a git repository
- Some signals are heuristic (side effect detection uses pattern matching)

---

## Installation

```bash
git clone https://github.com/jimmc414/claude-repo-xray.git
cd claude-repo-xray
python xray.py /path/to/your/project
```

Or copy `xray.py`, `lib/`, `formatters/`, and `configs/` to your project.

Requirements: Python 3.8+, no external dependencies.

---

## File Structure

```
repo-xray/
├── xray.py                     # Entry point
├── lib/
│   ├── ast_analysis.py         # Skeleton, complexity, types
│   ├── import_analysis.py      # Dependency graph, layers, distance
│   ├── call_analysis.py        # Cross-module calls
│   ├── git_analysis.py         # Risk, coupling, freshness
│   ├── gap_features.py         # Logic maps, hazards, data models
│   ├── test_analysis.py        # Test coverage
│   └── tech_debt_analysis.py   # TODO/FIXME markers
├── formatters/
│   ├── markdown_formatter.py
│   └── json_formatter.py
├── configs/
│   ├── default_config.json
│   └── presets.json
├── examples/
│   ├── kosmos_xray_output_v31.md    # X-Ray output example
│   ├── KOSMOS_ONBOARD.md            # Agent output v1
│   └── KOSMOS_ONBOARD_v2.md         # Agent output v2
└── .claude/
    ├── agents/
    │   ├── repo_xray.md             # Analysis agent
    │   └── repo_retrospective.md    # QA agent
    └── skills/
        ├── repo-xray/               # Analysis skill
        │   ├── SKILL.md
        │   ├── COMMANDS.md
        │   └── templates/
        │       └── ONBOARD.md.template
        └── repo-retrospective/      # QA skill
            ├── SKILL.md
            ├── COMMANDS.md
            └── templates/
                └── RETROSPECTIVE.md.template
```

---

## Why This Exists

AI coding assistants are powerful but context-limited. They can understand code they read, but they can't read everything. This creates a bootstrapping problem: the assistant needs to understand the architecture to know what to read, but needs to read to understand the architecture.

X-Ray provides the bootstrap. It compresses a codebase into signals that fit in context and guide further investigation. The agent layer adds judgment—turning raw signals into verified, curated documentation. The retrospective layer ensures quality—verifying that the documentation actually works.

The goal is not to replace reading code. It's to make reading code efficient by telling the AI where to look first.

---

## License

MIT

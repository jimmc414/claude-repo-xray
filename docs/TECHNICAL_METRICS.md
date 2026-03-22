# Repo X-Ray: Technical Metrics Reference

This document describes every technical metric collected by Repo X-Ray, the technology used to collect it, and how the metric is computed.

---

## Table of Contents

1. [Structural Signals](#1-structural-signals)
2. [Cyclomatic Complexity](#2-cyclomatic-complexity)
3. [Type Coverage](#3-type-coverage)
4. [Async Patterns](#4-async-patterns)
5. [Decorator Inventory](#5-decorator-inventory)
6. [Side Effect Detection](#6-side-effect-detection)
7. [Internal Call Graph](#7-internal-call-graph)
8. [Import Graph & Dependency Analysis](#8-import-graph--dependency-analysis)
9. [Cross-Module Call Analysis](#9-cross-module-call-analysis)
10. [Git History Signals](#10-git-history-signals)
11. [Test Coverage Estimation](#11-test-coverage-estimation)
12. [Technical Debt Markers](#12-technical-debt-markers)
13. [Priority Scoring & Ranking](#13-priority-scoring--ranking)
14. [Architecture Visualization](#14-architecture-visualization)
15. [Data Model Extraction](#15-data-model-extraction)
16. [Entry Point Detection](#16-entry-point-detection)
17. [CLI Arguments Extraction](#17-cli-arguments-extraction)
18. [Environment Variables](#18-environment-variables)
19. [Hazard File Detection](#19-hazard-file-detection)
20. [Logic Maps](#20-logic-maps)
21. [State Mutation Tracking](#21-state-mutation-tracking)
22. [Linter Rules Configuration](#22-linter-rules-configuration)
23. [GitHub Repository Metadata](#23-github-repository-metadata)

---

## 1. Structural Signals

**Collected by:** `lib/ast_analysis.py` — `analyze_file()`, `_extract_class_info()`, `_extract_function_info()`

**Technology:** Python `ast` module (Abstract Syntax Tree parsing)

Repo X-Ray parses every Python file into an AST and extracts a structural skeleton in a single pass. The skeleton captures the public interface of each file while stripping implementation details. This is the foundational analysis that feeds many downstream metrics.

### What is collected

| Metric | Description |
|--------|-------------|
| **Classes** | Name, base classes, decorators, docstrings, fields, methods, nested classes |
| **Functions** | Name, arguments (with type annotations), return type, decorators, docstring, line numbers |
| **Constants** | Module-level UPPERCASE name assignments |
| **Line count** | Total lines per file |
| **Token counts** | Original token count and skeleton token count (estimated at ~4 tokens per line) |

### How it works

The AST is walked once per file. For each `ClassDef` node, the class name, bases, decorator list, and body are extracted. For each `FunctionDef` / `AsyncFunctionDef` node, the function signature, arguments, type annotations, and docstring are extracted. Constants are identified by matching module-level `Assign` nodes where the target name is all uppercase.

---

## 2. Cyclomatic Complexity

**Collected by:** `lib/ast_analysis.py` — `_calculate_function_cc()`

**Technology:** Manual calculation via AST walking

Cyclomatic complexity (CC) measures the number of independent execution paths through a function. Higher CC means more branching logic and harder-to-understand code.

### What is collected

| Metric | Description |
|--------|-------------|
| **CC per function** | Complexity score for each function |
| **Total CC per file** | Sum of all function CCs in a file |
| **Hotspots** | Functions with CC above a threshold (default: >3) |
| **Average CC** | Mean complexity across the codebase |

### How it is calculated

Starting with a base score of 1, the calculator walks the function's AST and increments for each decision point:

| Decision point | Increment |
|----------------|-----------|
| `if`, `while`, `for`, `async for` | +1 each |
| `except` handler | +1 each |
| Boolean operators (`and` / `or`) | +1 per additional operand |
| Comprehension conditions (`if` inside list/set/dict comps or generators) | +1 per condition |

---

## 3. Type Coverage

**Collected by:** `lib/ast_analysis.py` — within `_extract_function_info()`

**Technology:** AST node inspection for type annotation presence

### What is collected

| Metric | Description |
|--------|-------------|
| **Typed functions** | Count of functions with at least one type annotation |
| **Total functions** | Count of all functions |
| **Type coverage %** | `(typed / total) × 100` |
| **Per-function flag** | `has_type_hints` boolean on each function |

### How it works

For each function node, the analyzer checks whether any argument has an `annotation` attribute set, or whether the function has a `returns` annotation. If either is present, the function is flagged as typed.

---

## 4. Async Patterns

**Collected by:** `lib/ast_analysis.py` — async pattern detection section

**Technology:** AST node type checking

### What is collected

| Metric | Description |
|--------|-------------|
| **Async functions** | Count of `async def` declarations |
| **Sync functions** | Count of regular `def` declarations |
| **Async for loops** | Count of `async for` statements |
| **Async context managers** | Count of `async with` statements |

### How it works

During the single-pass AST walk, nodes are checked against `AsyncFunctionDef`, `AsyncFor`, and `AsyncWith` AST types. Counts are accumulated per file and aggregated across the codebase.

---

## 5. Decorator Inventory

**Collected by:** `lib/ast_analysis.py` — decorator extraction within class/function analysis

**Technology:** AST `decorator_list` inspection

### What is collected

A histogram of all decorators used across the codebase with their occurrence counts (e.g., `@property: 15`, `@cached: 8`, `@app.route(): 3`).

### How it works

For every `ClassDef` and `FunctionDef` node, the `decorator_list` attribute is iterated. Decorator names are extracted from `Name`, `Attribute`, and `Call` AST nodes and accumulated into a global counter.

---

## 6. Side Effect Detection

**Collected by:** `lib/ast_analysis.py` — `_detect_side_effect()`

**Technology:** Pattern matching on AST call nodes + string-based heuristics

Side effects are function calls that mutate external state — databases, APIs, files, environment variables, or subprocesses. Detecting these helps developers understand which functions have observable impact beyond their return value.

### Categories detected

| Category | Trigger patterns |
|----------|-----------------|
| **DB** | `db.save`, `db.commit`, `session.commit`, `cursor.execute`, `insert(`, `update(`, `delete(`, `query(` |
| **API** | `requests.*`, `httpx.*`, `aiohttp.*`, `.post(`, `.put(`, `.patch(`, `fetch(`, `api.send` |
| **File** | `file.write`, `.write(`, `json.dump`, `pickle.dump`, `export(` |
| **Subprocess** | `subprocess.*`, `os.system`, `os.exec`, `Popen(` |
| **Environment** | `os.environ`, `setenv`, `putenv` |

### Safe patterns (excluded)

Certain patterns are whitelisted to avoid false positives: `.get(`, `ast.get_`, `isupper`, `islower`, `startswith`, `endswith`.

### Output

- **By category:** Aggregated call counts per side-effect type
- **By file:** Side effects listed per source file
- **Per call:** Call text, line number, category

---

## 7. Internal Call Graph

**Collected by:** `lib/ast_analysis.py` — internal call tracking section

**Technology:** AST call-site matching against defined functions in the same file

### What is collected

For each file, the analyzer records which locally-defined functions are called by other functions in the same file. This produces a file-scoped call graph that complements the cross-module analysis (see [section 9](#9-cross-module-call-analysis)).

---

## 8. Import Graph & Dependency Analysis

**Collected by:** `lib/import_analysis.py` — `build_import_graph()`, `analyze_imports()`

**Technology:** AST parsing of `import` / `from ... import` statements + BFS graph traversal

### What is collected

| Metric | Description |
|--------|-------------|
| **Import graph** | Directed graph of module → imported modules |
| **Reverse imports** | Who imports each module (importers list) |
| **Import aliases** | Map of aliases to fully-qualified module names |
| **Circular dependencies** | Bidirectional import pairs (A→B and B→A) |
| **Orphan files** | Modules with zero importers (dead code candidates) |
| **Hub modules** | Most-connected modules (potential god objects) |
| **Dependency distance** | Shortest path between any two modules (BFS) |
| **External dependencies** | Third-party packages used |

### Architectural layer classification

Based on import/imported-by ratios, modules are classified into three layers:

| Layer | Characteristics |
|-------|----------------|
| **Orchestration** | High imports, low importers — top-level coordination |
| **Core** | Balanced import/imported-by — business logic |
| **Foundation** | High importers, low imports — utilities and base libraries |

### How it works

Every `Import` and `ImportFrom` AST node is parsed. Relative imports are resolved against the package structure. A directed graph is built where edges represent import relationships. BFS is used to compute shortest paths for dependency distance. Circular dependencies are detected by checking for bidirectional edges.

---

## 9. Cross-Module Call Analysis

**Collected by:** `lib/call_analysis.py` — `analyze_calls()`, `CallVisitor` class

**Technology:** Custom AST visitor (`CallVisitor`) that walks every file and matches call sites against the function index from AST analysis

### What is collected

| Metric | Description |
|--------|-------------|
| **Most-called functions** | Functions called from the most distinct modules |
| **Call sites** | Count and location of cross-module calls per function |
| **Isolated functions** | Functions with zero cross-module callers |
| **Data flow direction** | Push-based (orchestration→foundation) vs. pull-based vs. bidirectional |

### How it works

The `CallVisitor` AST visitor extracts all function calls from each file, tracking the calling function/class context. These are then cross-referenced with the function index built during AST analysis. A call is "cross-module" when the callee is defined in a different file than the caller.

---

## 10. Git History Signals

**Collected by:** `lib/git_analysis.py` — `analyze_risk()`, `analyze_coupling()`, `analyze_freshness()`, `analyze_commit_sizes()`

**Technology:** `git log` subprocess calls + text parsing

Git analysis runs `git log` commands via subprocess and parses the output to extract historical signals about code evolution.

### 10a. Risk Scoring

**Function:** `analyze_risk()`

| Component | Weight | Normalization |
|-----------|--------|---------------|
| **Churn** (commit count in past 6 months) | 40% | Divided by max churn across all files |
| **Hotfix density** (commits matching fix/bug/urgent/revert/hotfix/patch/emergency) | 40% | `min(hotfixes, 3) / 3.0` |
| **Author entropy** (unique authors) | 20% | `min(authors, 5) / 5.0` |

**Risk formula:** `(churn_norm × 0.4) + (hotfix_score × 0.4) + (author_score × 0.2)`

Files with risk > 0.1 are included in the results.

### 10b. Co-Modification Coupling

**Function:** `analyze_coupling()`

Detects "hidden coupling" — files that frequently change together in commits even without import relationships.

- Parses the last 200 commits (configurable)
- Builds a co-occurrence matrix of Python files per commit
- Filters out bulk refactors (commits touching >20 files)
- Returns pairs with ≥3 co-occurrences (configurable)

### 10c. Freshness Tracking

**Function:** `analyze_freshness()`

Categorizes files by last modification timestamp:

| Category | Days since last modification |
|----------|------------------------------|
| **Active** | < 30 days |
| **Aging** | 30–90 days |
| **Stale** | 90–180 days |
| **Dormant** | > 180 days |

### 10d. Commit Sizes

**Function:** `analyze_commit_sizes()`

Records the distribution of commit sizes (number of files changed) per file, providing insight into whether changes tend to be focused or sprawling.

---

## 11. Test Coverage Estimation

**Collected by:** `lib/test_analysis.py` — `analyze_tests()`, `count_test_functions()`, `extract_fixtures()`

**Technology:** File pattern matching (regex) + AST/regex-based function detection

### What is collected

| Metric | Description |
|--------|-------------|
| **Test files** | Files matching `test_*.py`, `*_test.py`, or `tests.py` |
| **Test directories** | Directories named `tests/`, `test/`, `testing/` |
| **Test functions per file** | Functions matching `def test_*` pattern |
| **Async tests** | Functions matching `async def test_*` |
| **Fixtures** | Functions decorated with `@pytest.fixture` (including from conftest.py) |
| **Tested modules** | Source modules with corresponding test files |
| **Untested modules** | Source modules without any test coverage |

### How it works

Test files are identified by matching filenames against regex patterns. Test function counts are obtained by scanning file content for `def test_` patterns. Fixtures are extracted by detecting `@pytest.fixture` decorators. Coverage estimation maps test files to source modules by name correspondence (e.g., `test_utils.py` → `utils.py`).

---

## 12. Technical Debt Markers

**Collected by:** `lib/tech_debt_analysis.py` — `analyze_tech_debt()`

**Technology:** Line-by-line regex scanning of source files

### Marker types detected

| Marker | Meaning |
|--------|---------|
| **TODO** | Planned future improvements |
| **FIXME** | Known bugs that need fixing |
| **HACK** | Temporary workarounds |
| **XXX** | General warnings |
| **BUG** | Explicitly flagged bugs |
| **OPTIMIZE** | Performance improvement opportunities |

### Regex pattern

```
#\s*(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE)\b[:\s]*(.*)$
```

### Output

- **By type:** List of markers per category
- **By file:** Markers grouped by source file
- **Summary:** Total count and per-type counts

---

## 13. Priority Scoring & Ranking

**Collected by:** `lib/gap_features.py` — `calculate_priority_scores()`, `get_architectural_pillars()`, `get_maintenance_hotspots()`

**Technology:** Composite weighted formula with min-max normalization

### Composite priority score

Ranks files by importance for developer understanding. The formula is:

```
score = (CC × 0.25) + (ImportWeight × 0.20) + (GitRisk × 0.30) + (Freshness × 0.15) + (Untested × 0.10)
```

| Factor | Weight | Source | Rationale |
|--------|--------|--------|-----------|
| Cyclomatic Complexity | 25% | AST analysis | Complex code needs more attention |
| Import Weight | 20% | Import graph (count of importers) | Foundational modules affect more code |
| Git Risk | 30% | Git history (churn + hotfixes + authors) | Volatile files need understanding most |
| Freshness | 15% | Git timestamps | Active files are more relevant |
| Untested | 10% | Test analysis | Untested code is riskier |

All factors are normalized to 0–1 using min-max normalization. The top 20 files are returned with their scores and explanatory reasons.

### Architectural pillars

Ranks files by import weight (how many other modules depend on them). These are the foundational modules a new developer should learn first.

### Maintenance hotspots

Ranks files by git risk score. These are the volatile files that change frequently, often in the context of bugfixes.

---

## 14. Architecture Visualization

**Collected by:** `lib/gap_features.py` — `generate_mermaid_diagram()`

**Technology:** Mermaid diagram generation from import graph data

### What is generated

A Mermaid `graph TD` diagram showing:
- **Subgraphs** for ORCHESTRATION, CORE, and FOUNDATION layers
- **Edges** representing import relationships between modules
- **Data flow annotations** (optional): push, pull, or bidirectional

Maximum of 30 nodes (configurable) to keep diagrams readable.

---

## 15. Data Model Extraction

**Collected by:** `lib/gap_features.py` — `extract_data_models()`, `_extract_field_constraints()`, `_extract_validators()`

**Technology:** AST parsing with base class detection

### Model types detected

| Type | Detection method |
|------|-----------------|
| **Pydantic models** | Classes inheriting from `BaseModel` |
| **Dataclasses** | Classes decorated with `@dataclass` or `@attrs.define` / `@attr.s` |
| **TypedDict** | Classes inheriting from `TypedDict` |

### What is extracted

- **Fields:** Name, type annotation, default value, aliases
- **Constraints (Pydantic):** `gt`, `ge`, `lt`, `le`, `min_length`, `max_length`, `regex`, etc.
- **Validators:** Methods decorated with `@validator` or `@field_validator`
- **Domain classification:** Models categorized as Agents, API, Config, Models, Workflows, or Other

---

## 16. Entry Point Detection

**Collected by:** `lib/gap_features.py` — `detect_entry_points()`

**Technology:** Filename matching + AST function/block detection

### Detection methods

| Method | Patterns |
|--------|----------|
| **Filename** | `main.py`, `cli.py`, `__main__.py`, `app.py`, `run.py`, `server.py` |
| **Function name** | Module-level `main()`, `cli()`, `run()`, `app()`, `serve()` |
| **Code block** | `if __name__ == "__main__":` blocks (detected via AST) |

Each entry point includes the file path and a suggested invocation command.

---

## 17. CLI Arguments Extraction

**Collected by:** `lib/gap_features.py` — `extract_cli_arguments()`, `_extract_argparse_args()`, `_extract_click_args()`, `_extract_typer_args()`

**Technology:** AST call-site detection for three argument parsing libraries

### Supported libraries

| Library | Detection method |
|---------|-----------------|
| **argparse** | `ArgumentParser.add_argument()` call analysis |
| **Click** | `@click.command()`, `@click.option()`, `@click.argument()` decorator analysis |
| **Typer** | `typer.Argument()`, `typer.Option()` parameter analysis |

### Per-argument output

- Name, type (if specified), help text, default value, required flag

---

## 18. Environment Variables

**Collected by:** `lib/gap_features.py` — `get_environment_variables()`, `_extract_env_vars_from_file_ast()`

**Technology:** AST call-site detection for `os.getenv` / `os.environ` patterns

### Patterns detected

| Pattern | Required? |
|---------|-----------|
| `os.getenv("VAR", default)` | No (has default) |
| `os.environ.get("VAR", default)` | No (has default) |
| `os.environ["VAR"]` | Yes (no default) |

### Output per variable

Variable name, default value (if any), required flag, file location, line number.

---

## 19. Hazard File Detection

**Collected by:** `lib/gap_features.py` — `detect_hazards()`, `get_directory_hazards()`

**Technology:** Token counting (estimated ~4 tokens per line) + filename pattern matching

### Hazard types

| Hazard | Trigger | Recommendation |
|--------|---------|----------------|
| **Large files** | >10,000 tokens (configurable) | "Use skeleton view" |
| **Generated code** | Filenames matching `**/generated_*.py` | "Skip — auto-generated" |
| **Migrations** | Migration-related filenames | "Skip" |
| **Test fixtures** | Large test data files | "Skip unless debugging" |

Files exceeding ~50K tokens are flagged with "Never read directly."

---

## 20. Logic Maps

**Collected by:** `lib/gap_features.py` — `generate_logic_maps()`, `LogicMapGenerator` class

**Technology:** AST walking with control flow interpretation

Logic maps are generated for complex functions (CC > 15) to provide a human-readable summary of control flow without reading the full implementation.

### Map notation

| Symbol | Meaning |
|--------|---------|
| `→` | Sequential flow |
| `?` | Conditional branch |
| `*` | Loop |
| `{attr = value}` | State mutation |
| `[category: call]` | Side effect |

### What is captured

- Docstring and parameters
- Conditional branches and their conditions
- Loop structures
- Side effects (I/O, API, DB operations)
- Function calls along each path
- Return statements

---

## 21. State Mutation Tracking

**Collected by:** `lib/gap_features.py` — `extract_state_mutations()`

**Technology:** AST detection of `self.X = Y` assignments

### What is collected

For complex functions (hotspots with CC > 15), all instance attribute assignments (`self.attribute = value`) are recorded. Output is grouped by `filename:method_name` with a list of mutated attribute names.

---

## 22. Linter Rules Configuration

**Collected by:** `lib/gap_features.py` — `extract_linter_rules()`

**Technology:** TOML parsing (`tomllib` on Python 3.11+, simple regex fallback)

### Supported linters

| Linter | Config source |
|--------|--------------|
| **ruff** | `pyproject.toml` or `ruff.toml` |
| **black** | `pyproject.toml` (line length, target version) |
| **isort** | `pyproject.toml` (profile) |
| **flake8** | `.flake8` file |

### What is extracted

Line length, enabled/disabled rule codes (`select`/`ignore`), Python target version, pyupgrade flags, and banned import patterns (e.g., `print()` banned via T20x rules).

---

## 23. GitHub Repository Metadata

**Collected by:** `lib/gap_features.py` — `get_github_about()`, `_parse_git_remote_url()`

**Technology:** `gh` CLI (subprocess) with fallback to GitHub REST API (`urllib`)

### What is collected

- **Description:** Repository description from the About section
- **Topics:** Tags/keywords for the project

### How it works

First attempts to use the `gh` CLI (which handles authentication for private repos). Falls back to the public GitHub API via `urllib` if `gh` is unavailable. The remote URL is parsed from `.git/config` to extract the `owner/repo` pair.

---

## Technology Summary

| Technology | Modules Using It | Purpose |
|------------|-----------------|---------|
| Python `ast` module | ast_analysis, import_analysis, call_analysis, gap_features | Parse source code into ASTs for structural analysis |
| Regex | tech_debt_analysis, test_analysis | Pattern matching on raw source text |
| `git log` (subprocess) | git_analysis | Extract historical commit data |
| BFS graph traversal | import_analysis | Compute dependency distances and detect cycles |
| `gh` CLI (subprocess) | gap_features | Fetch GitHub repository metadata |
| `urllib` | gap_features | Fallback GitHub API access |
| TOML parsing | gap_features | Read linter configuration files |
| Mermaid syntax | gap_features | Generate architecture diagrams |

All AST-based signals are computed in a **single pass** through each file for efficiency.

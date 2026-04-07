# CLAUDE.md

Read INTENT.md before starting any task. It explains why this project exists and the design decisions behind it. Violating those decisions — even to "improve" things — is a bug.

## What This Is

A deterministic codebase analyzer for Python and TypeScript/JavaScript projects. Produces compressed intelligence for AI coding assistants. Single entry point: `python xray.py /path/to/project`. The Python scanner has zero external dependencies (stdlib only). The TypeScript scanner requires Node.js and is a self-contained npm project in `ts-scanner/`.

## How to Run

```bash
python xray.py .                              # Full analysis, stdout
python xray.py . --output both --out ./out    # Both formats to files
python xray.py . --preset minimal             # ~2K token output
python xray.py . --verbose                    # Progress to stderr
```

Tests: `python -m pytest tests/ -x -q`

## Architecture

```
xray.py                        Entry point + orchestration (detect language → run scanner → format → output)
  ├── lib/                       Python scanner modules
  │   ├── file_discovery.py    Find Python files, apply ignore patterns
  │   ├── ast_analysis.py      Single-pass AST: skeletons, complexity, types, side effects, security, silent failures, async violations, SQL, deprecations
  │   ├── import_analysis.py   Dependency graph, layers, circular deps, distance
  │   ├── call_analysis.py     Cross-module call sites, reverse lookup, fan-in
  │   ├── git_analysis.py      Risk scores, co-modification coupling, freshness
  │   ├── gap_features.py      Logic maps, hazards, data models, entry points, mermaid diagrams
  │   ├── test_analysis.py     Test file detection, pattern extraction
  │   └── tech_debt_analysis.py  TODO/FIXME markers
  ├── ts-scanner/                TypeScript/JavaScript scanner (self-contained npm project)
  │   ├── src/                   20 modules (~5,700 lines): AST analysis, imports, calls, detectors, etc.
  │   ├── test/                  8 test files + fixtures
  │   ├── package.json           Own deps (typescript only)
  │   └── tsconfig.json          Own build config
  ├── formatters/
  │   ├── markdown_formatter.py  Curated human/AI-readable output (~8-15K tokens), language-aware
  │   └── json_formatter.py      Complete structured output (~30-50K tokens)
  ├── configs/
  │   ├── presets.json           Analysis presets (minimal, standard, full)
  │   └── default_config.json    Section-level config
  └── .claude/
      ├── agents/                Agent definitions for Claude Code
      └── skills/                Skill definitions for Claude Code
```

## Critical Path

`xray.py:main()` → parse args → `config_loader.load_config()` → `run_analysis()` → `gap_features` processing → formatter → output

For Python projects, `run_analysis()` pipeline is:
1. `file_discovery.discover_python_files()` — find files, apply ignores
2. `ast_analysis.analyze_codebase()` — single-pass AST extraction (everything structural)
3. `import_analysis.analyze_imports()` — dependency graph from import statements
4. `call_analysis.analyze_calls()` — cross-module call graph (depends on ast_results)
5. `git_analysis.*` — risk, coupling, freshness from git log
6. `test_analysis` + `tech_debt_analysis` — supplementary signals

For TypeScript/JavaScript projects, `xray.py` detects the language via `detect_language()`, invokes `ts-scanner/` via subprocess (`node ts-scanner/dist/index.js`), then augments the results with language-agnostic git analysis and investigation targets. The TS scanner produces the same `XRayResults` JSON schema as the Python pipeline.

After `run_analysis()`, gap features are computed separately via `config_to_gap_features()` and passed to the markdown formatter. This separation exists because gap features need the combined results from multiple analyses.

## Things to Know

`gap_features.py` is 2900+ lines. It accumulated multiple unrelated concerns (logic maps, hazards, data models, entry points, mermaid diagrams, state mutations, CLI extraction) because they all share one trait: they need combined results from multiple analysis modules. If you're adding a new analysis that combines results, create a new file in `lib/` following the pattern of `call_analysis.py` (takes combined results as input, returns a dict). Don't add to `gap_features.py`. Test against `tests/test_gap_features.py` if modifying existing gap features.

`markdown_formatter.py` is 50K (the largest file). It assembles the final markdown output from analysis results and gap features. Section ordering and token budget management happen here. If you're changing what appears in the output, this is where it lands.

All `lib/` modules are imported by `xray.py` using `sys.path` manipulation (`sys.path.insert(0, str(SCRIPT_DIR / "lib"))`). Imports between lib modules use bare names (`from ast_analysis import ...`), not package-relative imports. Follow this pattern.

`ast_analysis.py` parses each file exactly once. Multiple analysis types (skeleton, complexity, types, decorators, side effects) are extracted from the same AST walk. If you need new AST-derived data, add it to the existing visitor rather than parsing files again.

The Python scanner has zero external dependencies by design. Do not add `pip install` requirements. If you need functionality from an external library, implement it using stdlib. The TypeScript scanner is a separate npm project in `ts-scanner/` with its own `package.json` (typescript is the only dependency). It communicates with `xray.py` via subprocess + JSON — it does not import from or depend on the Python codebase.

## Conventions

Functions that analyze files take a list of file paths and return a dict. The dict keys become the JSON output keys. Follow existing patterns in the `lib/` modules.

Error handling: analysis functions catch exceptions per-file and continue. A single unparseable file should never crash the whole scan. See `ast_analysis.py:analyze_file()` for the pattern.

Output goes to stderr for progress, stdout for results. Never mix progress messages into the analysis output.

Config-driven sections: each section in the markdown output can be enabled/disabled via `.xray.json` or `--no-{section}` flags. If you add a new section, add its config entry to `configs/default_config.json` and wire it through `config_loader.py`.

## Agents and Skills

The `.claude/` directory contains Claude Code agent and skill definitions. The `repo_xray` agent uses xray output to investigate codebases and produce onboarding documents. The `repo_retrospective` agent QAs those documents. These are markdown files that instruct Claude Code — they don't contain executable code. If you modify the scanner's output format, check whether agent or skill instructions reference the changed fields.

## Don't

- Don't add external dependencies
- Don't make the scanner non-deterministic (no LLM calls, no network requests during analysis)
- Don't parse files more than once — extend the existing AST visitor
- Don't put analysis logic in the formatters — formatters only format
- Don't change the JSON output schema without updating the markdown formatter to match
- Don't read `archive/` for current architecture — those are historical planning docs that may be outdated

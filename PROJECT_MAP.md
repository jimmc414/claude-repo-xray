# PROJECT MAP: repo-xray

> For AI agents. Read this document to understand every component of this project, why it exists, how the pieces connect, and what the design constraints are. After reading this, you should be able to modify any part of the system without violating its architecture.

---

## What This Project Does

repo-xray solves the cold start problem for AI coding assistants. When a fresh AI lands in an unfamiliar codebase, it either reads files at random (wasting context) or guesses (producing wrong suggestions). Both fail because the AI lacks a map.

This project produces that map in two phases:

**Phase 1 (X-Ray Scanner)** — A deterministic scanner that parses every source file via AST (Python's `ast` module for `.py` files, TypeScript compiler API for `.ts`/`.js` files), mines git history, builds dependency graphs, and produces a ~15K token structural map. Runs in 5 seconds. Same input, same output, every time.

**Phase 2 (Deep Crawl)** — An optional LLM-powered investigation that uses the scanner output as a map, then spawns parallel agents to read actual source code, trace request paths, discover gotchas, and produce a comprehensive onboarding document (~60K words, every claim backed by `file:line` evidence). Runs in 30-70 minutes. Non-deterministic. The generation cost is amortized across every future AI session that reads the document.

Most users only need Phase 1. Phase 2 pays for itself on codebases where many AI sessions will work over time.

---

## Why It's Built This Way

Read `INTENT.md` for the full rationale. The key decisions:

1. **Determinism in Phase 1.** The scanner runs in CI, before every session, on every commit. It cannot be flaky, slow, or expensive. Intelligence lives in Phase 2.

2. **Minimal dependencies.** Python scanner: zero dependencies, Python 3.8+ stdlib only. TypeScript scanner: Node.js + npm (typescript is the only package dependency). No `pip install` on the Python side.

3. **Output is for AI, not humans.** Dense, structured, token-efficient. A human can read code directly; an AI's effectiveness is bottlenecked by what fits in context.

4. **Single AST parse per file.** Every signal (skeletons, complexity, side effects, security, types) is extracted from one `ast.parse()` call (Python) or one `ts.createSourceFile()` call (TypeScript). Adding a new signal means extending the existing visitor, never parsing again.

5. **Investigation targets in the scanner.** The scanner cheaply computes "this function is probably confusing" from name genericity and type coverage, saving the expensive crawl agent from deciding what to investigate.

6. **Unlimited budget for deep crawl.** The document is read hundreds of times. Optimizing for cheap generation at the expense of quality is a false economy. Depth over brevity.

7. **CLAUDE.md delivery.** The onboarding document auto-loads in every AI session via prompt caching. An agent that has to know to look for it sometimes won't.

---

## Entry Point and Pipeline

```
python xray.py /path/to/project [--output both] [--preset minimal] [--repo-name NAME]
```

`xray.py:main()` orchestrates everything:

```
CLI args → config_loader.load_config() → run_analysis() → gap_features → formatter → output
```

`xray.py` first calls `detect_language()` to determine the project language (Python vs TypeScript/JavaScript) based on file extensions.

**For Python projects**, `run_analysis()` runs 10 stages sequentially:

| Stage | Module | Input | Output | Depends On |
|-------|--------|-------|--------|------------|
| 1 | `file_discovery.py` | Target directory | List of .py file paths | Nothing |
| 2 | `ast_analysis.py` | File paths | Per-file AST data (structure, complexity, types, side effects, security, async, SQL, deprecations) | Stage 1 |
| 3 | `import_analysis.py` | File paths + AST data | Dependency graph, layers, hubs, orphans, circular deps | Stage 1 |
| 4 | `call_analysis.py` | File paths + AST data | Cross-module call graph, reverse lookup, fan-in | Stages 1-2 |
| 5 | `git_analysis.py` | File paths | Risk scores, coupling, freshness, churn, velocity, author expertise | Stage 1 |
| 6 | `test_analysis.py` | File paths | Test file index, fixture list, coverage estimate | Stage 1 |
| 7 | `tech_debt_analysis.py` | File paths | TODO/FIXME markers, deprecation markers | Stage 1 |
| 8 | `investigation_targets.py` | All prior results | Prioritized signals: ambiguous interfaces, coupling anomalies, high-uncertainty modules, domain entities | Stages 1-7 |

**For TypeScript/JavaScript projects**, `xray.py` invokes `ts-scanner/` via subprocess (`node ts-scanner/dist/index.js`). The TS scanner performs its own file discovery, AST analysis, import analysis, call analysis, and produces the same `XRayResults` JSON schema. `xray.py` then augments the results with language-agnostic git analysis (`_augment_with_git()`) and investigation targets (`compute_investigation_targets()`).

After `run_analysis()`, gap features are computed separately (`gap_features.py`) because they need combined results from multiple stages. Then formatters produce output.

---

## File-by-File Component Map

### Core Scanner

| File | Lines | Role | Key Insight |
|------|-------|------|-------------|
| `xray.py` | ~900 | Orchestrator, CLI, pipeline | `run_analysis()` is the critical path. `detect_language()` determines Python vs TS. `invoke_ts_scanner()` delegates to TS scanner via subprocess. `_augment_with_git()` adds git analysis to TS results. `config_to_gap_features()` bridges config flags to formatter. |
| `lib/file_discovery.py` | ~320 | Find .py files, apply ignores | `discover_python_files()` uses `os.walk` with in-place directory filtering. Token estimate = file_size // 4. |
| `lib/ast_analysis.py` | ~850 | Single-pass AST extraction | `analyze_file()` parses once, extracts everything: skeletons, complexity (base=1, +1 per branch), types, side effects, security (exec/eval/compile), silent failures (bare except), async violations, SQL strings, deprecations. Per-file error handling — one bad file never crashes the scan. |
| `lib/import_analysis.py` | ~450 | Dependency graph | Builds module→imports/imported_by graph. Layer classification (FOUNDATION/CORE/ORCHESTRATION by keyword). Hub ranking by connection count. BFS for dependency distance. Handles relative imports. |
| `lib/call_analysis.py` | ~250 | Cross-module call graph | `CallVisitor` AST walk tracks caller context. Matches call sites to function definitions. Reverse lookup = "who calls this function?" High-fan-in = most-called functions. |
| `lib/git_analysis.py` | ~350 | Git history mining | Risk = 40% churn + 40% hotfixes + 20% author entropy. Coupling via frequent itemset mining on commit co-occurrence. Function-level churn. Velocity trend detection. Graceful degradation when no git. |
| `lib/test_analysis.py` | ~180 | Test detection | Matches test_*.py and *_test.py. Counts `def test_` functions. Extracts @pytest.fixture from conftest.py. |
| `lib/tech_debt_analysis.py` | ~120 | Debt markers | Finds TODO/FIXME/HACK/XXX/BUG/OPTIMIZE comments. Scans for @deprecated decorators and DeprecationWarning. |
| `lib/investigation_targets.py` | ~800 | Prioritized crawl signals | Ambiguity score = (caller_count * cc) / type_coverage. 49 hardcoded generic names (process, handle, run...). Entry-to-side-effect path tracing. Coupling anomaly = high co-modification without import relationship. |
| `lib/gap_features.py` | ~2900 | Multi-module synthesis | The largest lib file. Combines results from all stages to produce: priority scores, mermaid diagrams, hazard detection, data model extraction, logic maps, entry points, architecture prose, state mutations, CLI arguments, Pydantic validators, linter rules, security summaries, env var defaults. If you're adding a new combined-results analysis, create a new file — don't add to this one. |
| `lib/config_loader.py` | ~340 | Configuration | Load order: --config flag > .xray.json in target > defaults. Presets (minimal/standard/full) override sections. CLI --no-{section} flags override everything. `is_section_enabled()` handles both bool and {enabled: true} dict formats. |

### TypeScript/JavaScript Scanner

Self-contained npm project in `ts-scanner/`. Communicates with `xray.py` via subprocess + JSON. Produces the same `XRayResults` JSON schema as the Python pipeline.

| File | Lines | Role | Key Insight |
|------|-------|------|-------------|
| `ts-scanner/src/index.ts` | ~370 | Entry point + orchestration | CLI parsing, file discovery, scanner pipeline, JSON output to stdout. Mirror of `xray.py:run_analysis()`. |
| `ts-scanner/src/ast-analysis.ts` | ~860 | Single-pass TS AST extraction | Uses `ts.createSourceFile()`. Extracts skeletons, complexity, types, side effects, security, decorators, async patterns. |
| `ts-scanner/src/import-analysis.ts` | ~640 | Dependency graph | Import/export resolution, barrel files, layer classification, hub detection, circular deps. |
| `ts-scanner/src/call-analysis.ts` | ~260 | Cross-module call graph | Call site tracking, reverse lookup, fan-in computation. |
| `ts-scanner/src/detectors.ts` | ~490 | Behavioral detectors | Security concerns, silent failures, SQL patterns, resource leaks, unsafe deserialization, deprecation markers. |
| `ts-scanner/src/investigation-targets.ts` | ~460 | Prioritized crawl signals | Ambiguity scoring, entry-to-side-effect tracing, coupling anomalies. |
| `ts-scanner/src/git-analysis.ts` | ~500 | Git history mining | Risk scores, coupling, freshness, churn — same algorithms as Python `git_analysis.py`. |
| `ts-scanner/src/logic-maps.ts` | ~390 | Logic map generation | Symbolic control flow for complex functions (CC > threshold). |
| `ts-scanner/src/types.ts` | ~670 | Type definitions | `XRayResults` interface — the shared output contract between scanners. |
| `ts-scanner/src/cli-analysis.ts` | ~270 | CLI extraction | Commander/yargs/minimist argument detection. |
| `ts-scanner/src/config-analysis.ts` | ~150 | Config detection | Environment variables, config file patterns. |
| `ts-scanner/src/route-analysis.ts` | ~120 | HTTP route detection | Express/Fastify/Koa route extraction. |
| `ts-scanner/src/blast-analysis.ts` | ~160 | Blast radius | Transitive impact via BFS over import+call graph. |
| `ts-scanner/src/tech-debt.ts` | ~90 | Debt markers | TODO/FIXME/HACK comment scanning. |
| `ts-scanner/src/test-analysis.ts` | ~70 | Test detection | Jest/Vitest/Mocha test file and function detection. |
| `ts-scanner/src/import-time-effects.ts` | ~75 | Import-time side effects | Top-level calls, global mutations at module scope. |
| `ts-scanner/src/file-discovery.ts` | ~100 | File discovery | Find .ts/.tsx/.js/.jsx files, apply ignore patterns. |
| `ts-scanner/src/utils.ts` | ~50 | Shared utilities | Path manipulation, relative path computation. |

Tests: `cd ts-scanner && npm test` — 8 test files with Vitest.

### Formatters

| File | Lines | Role | Key Insight |
|------|-------|------|-------------|
| `formatters/markdown_formatter.py` | ~1500 | Markdown output | The largest file in the project (~50K bytes). Assembles all sections with tables, Mermaid diagrams, code blocks. Each section gated by config flag. Language-aware: switches syntax markers (`#` vs `//`, `def` vs `function`) based on `code_lang` parameter. |
| `formatters/json_formatter.py` | ~100 | JSON output | Complete structured dump. 30-50K tokens (vs 8-15K markdown). Used by deep crawl agents for programmatic lookups. |

### Configuration

| File | Role |
|------|------|
| `configs/default_config.json` | All 34 sections enabled. Three blocks: `analysis` (12 booleans), `sections` (29+ flags, some with params), `output` (format, relative_paths). |
| `configs/presets.json` | minimal (~2K tokens), standard (~8K), full/default (~15K). Controls which analysis passes run and skeleton detail level. |
| `configs/ignore_patterns.json` | Directories (`__pycache__`, `.git`, `.venv`), extensions (`.pyc`, `.db`), files (`.DS_Store`) to skip during discovery. |

### Tests

| File | Tests | What It Covers |
|------|-------|---------------|
| `tests/test_gap_features.py` | ~50 | Priority scores, mermaid diagrams, hazards, data models, pillars, hotspots, state mutations, entry points |
| `tests/test_investigation_targets.py` | ~50 | Ambiguous interfaces, entry paths, coupling anomalies, convention deviations, shared state, uncertainty |
| `tests/test_scanner_enhancements.py` | ~30 | v3.2: security concerns (exec not cursor.execute), silent failures (bare except), async violations (blocking in async), SQL detection, deprecation markers |

Run: `python -m pytest tests/ -x -q` — currently 137 tests, all passing.

### Tools

| File | Role |
|------|------|
| `tools/enrich_onboard.py` | Post-hoc: inject git risk/churn/velocity annotations into DEEP_ONBOARD.md as blockquotes. Idempotent. Not integrated into main pipeline. |

---

## Phase 2: The Deep Crawl Ecosystem

Phase 2 is entirely defined in `.claude/` — markdown files that instruct Claude Code, not executable Python.

### Agents (4)

| Agent | File | Model | Role |
|-------|------|-------|------|
| `repo_xray` | `.claude/agents/repo_xray.md` | Sonnet | Quick onboarding from X-Ray signals. Four phases: ORIENT → INVESTIGATE → SYNTHESIZE → VALIDATE. Produces lighter ONBOARD.md with [VERIFIED]/[INFERRED]/[X-RAY SIGNAL] confidence tags. |
| `deep_crawl` | `.claude/agents/deep_crawl.md` | Opus | Sequential fallback when parallel sub-agents are unavailable. Same pipeline as the skill, executed in one context. |
| `deep_onboard_validator` | `.claude/agents/deep_onboard_validator.md` | Sonnet | Independent QA. 7-check protocol: completeness, accuracy, pattern verification, coverage, redundancy, adversarial simulation, structural navigability. |
| `repo_retrospective` | `.claude/agents/repo_retrospective.md` | Sonnet | Documentation audit. Five phases: INVENTORY → COVERAGE → VERIFICATION → ACTIONABILITY → RECOMMENDATIONS. |

### Skills (3)

**deep-crawl** (`.claude/skills/deep-crawl/`) — The primary Phase 2 skill. 1,667 lines of orchestrator instructions.

| Command | Mode | What It Does |
|---------|------|--------------|
| `/deep-crawl full` | Parallel sub-agents | Full 7-phase pipeline, maximum quality |
| `@deep_crawl full` | Sequential fallback | Same pipeline, single agent |
| `@deep_crawl plan` | Sequential | Generate investigation plan only |
| `@deep_crawl resume` | Sequential | Continue from checkpoint |
| `@deep_crawl validate` | Sequential | QA an existing document |
| `@deep_crawl refresh` | Sequential | Incremental update for code changes |
| `@deep_crawl focus ./path` | Sequential | Deep crawl a specific subsystem |

**Seven-Phase Pipeline:**

```
Phase 0   SETUP         Create .deep_crawl/ dirs, verify xray exists
Phase 0b  PRE-FLIGHT    Git freshness check, file count, framework detection
Phase 1   PLAN          Build crawl agenda from investigation_targets, detect domain facets
Phase 1b  CALIBRATE     3 exemplar investigations (trace, module, cross-cutting) set quality bar
Phase 2   CRAWL         Parallel sub-agents execute 6 investigation protocols in 6 batches
Phase 3   ASSEMBLE      7 assembly sub-agents (S1-S6) produce sections from findings
Phase 4   CROSS-REF     Additive only — link sections, verify completeness (12 standard questions)
Phase 5   VALIDATE      Independent validator: 12 questions, 10 spot-checks, adversarial simulation
Phase 6   DELIVER       Copy to docs/, update CLAUDE.md, report metrics
```

**Six Investigation Protocols:**

| Protocol | Focus | Output Dir | Batching |
|----------|-------|-----------|----------|
| A | Request traces — follow entry→side effect end-to-end | `findings/traces/` | Batch 1 (parallel, max 5 agents) |
| B | Module deep reads — behavioral detail, public API, test coverage | `findings/modules/` | Batch 2 (one agent per module, parallel) |
| C | Cross-cutting concerns — error handling, config, shared state, async boundaries | `findings/cross_cutting/` | Batch 3 (parallel, max 6 agents) |
| D | Convention documentation — patterns, testing, coding style | `findings/conventions/` | Batch 4 (waits for 1-3) |
| E | Reverse dependency & change impact — hub modules, blast radii | `findings/impact/` | Batch 5 (waits for 1-4) |
| F | Change scenario walkthroughs — step-by-step playbooks | `findings/playbooks/` | Batch 6 (waits for 1-5) |

**Evidence Standards (non-negotiable):**

| Tag | Meaning | Required For |
|-----|---------|-------------|
| `[FACT]` | Read specific code, cite file:line | Every gotcha, every critical claim |
| `[PATTERN]` | Observed in >= 3 examples, state N/M count | Conventions, recurring behavior |
| `[ABSENCE]` | Searched (grep), confirmed non-existence | "No X exists" claims |

Citation density is mechanically enforced at every stage — findings (5.0/100w), calibration (6.0/100w), assembly sections (tiered: 3.0 high-evidence, 2.0 medium, 1.0 narrative).

**Quality Gates (from `configs/quality_gates.json`):**
- Investigation findings: 200 words, 5 [FACT] minimum per file
- Batch 2 (modules): elevated to 400 words, 10 [FACT]
- Calibration: 400 words, 10 [FACT], 6.0 density
- Playbooks: 800 words, 30 [FACT], 8 common mistakes each
- Assembly retention: >= 80% of input findings word count
- Fact-level completeness: every file:line citation in findings must survive to final document
- Document size floor: scaled to codebase (small: 4.6K words, medium: 7.7K, large: 10K)

**Domain Facet Detection (from `configs/domain_profiles.json`):**

The crawl adapts its investigation based on detected frameworks. A repo can match multiple facets.

| Facet | Detection | Extra Investigation |
|-------|-----------|-------------------|
| web_api | FastAPI, Flask, Django | Auth middleware, CORS, request lifecycle, rate limiting |
| cli_tool | argparse, Click, Typer | Command hierarchy, exit codes, output formatting |
| ml_pipeline | torch, tensorflow | Training loops, checkpoints, data loading |
| data_pipeline | airflow, dagster | DAG structure, idempotency, backfill strategy |
| async_service | asyncio, aiohttp | Event loops, sync/async boundaries, cancellation |
| scientific_computation | numpy, scipy | Numerical stability, data shapes, reproducibility |
| infrastructure_automation | subprocess, boto3 | Idempotency, rollback, credential handling |
| plugin_system | pluggy, stevedore | Discovery, lifecycle, isolation |

**Output Document (DEEP_ONBOARD.md) — 17 sections:**

1. Identity (what is this, what's the stack)
2. Critical Paths (traced end-to-end with code citations)
3. Module Behavioral Index (every investigated module's behavior, blast radius, gotchas)
4. Change Impact Index (hub modules, what breaks if you change them)
5. Key Interfaces (public APIs with usage patterns)
6. Data Contracts (Pydantic models, cross-boundary flows, schema risks)
7. Error Handling Strategy (dominant patterns, recovery, exception taxonomy)
8. Shared State (globals, caches, singletons, thread safety)
9. Domain Glossary (codebase-specific terminology)
10. Configuration Surface (env vars, config files, feature flags)
11. Conventions (coding patterns stated as directives with evidence counts)
12. Gotchas (clustered by subsystem, severity-tagged, each with file:line)
13. Hazards — Do Not Read (files that waste context)
14. Extension Points (where to add new functionality)
15. Change Playbooks (step-by-step modification guides with validation commands)
16. Reading Order (suggested file sequence for manual exploration)
17. Environment Bootstrap (setup instructions)

Stable sections go first (caching-friendly). Volatile sections at the bottom.

**Other deep-crawl config files:**

| File | Purpose |
|------|---------|
| `configs/exemplar_templates.md` | Structural examples showing expected format for impact tables, playbooks, data contracts |
| `configs/generic_names.json` | Hardcoded lists of generic function/module names (for reference) |
| `configs/compression_targets.json` | Min token floors per section (prevents assembly from dropping content) |
| `templates/DEEP_ONBOARD.md.template` | Section skeleton with placeholder markers |
| `templates/CRAWL_PLAN.md.template` | Investigation plan skeleton (P1-P7 priority groups) |
| `templates/VALIDATION_REPORT.md.template` | QA report skeleton |
| `templates/onboard_change_tracking_rule.md` | Instructions for CLAUDE.md change logging (incremental updates) |

**repo-xray skill** (`.claude/skills/repo-xray/`) — Lighter Phase 2 option. Uses `repo_xray` agent for quick investigation with [VERIFIED]/[INFERRED] confidence levels.

**repo-retrospective skill** (`.claude/skills/repo-retrospective/`) — QA for existing ONBOARD documents. Five-phase audit comparing claims against X-Ray data and actual code.

---

## Context Management Architecture

The deep crawl's key architectural decision: **all intermediate state lives on disk, not in conversation context.**

```
.deep_crawl/
  findings/
    traces/          # Protocol A output (one .md per trace)
    modules/         # Protocol B output (one .md per module)
    cross_cutting/   # Protocol C output (one .md per concern)
    conventions/     # Protocol D output
    impact/          # Protocol E output
    playbooks/       # Protocol F output
    calibration/     # Phase 1b exemplar output
  batch_status/      # Sentinel files (touch X.done) for completion tracking
  sections/          # Assembly output (one .md per document section)
  CRAWL_PLAN.md      # Investigation agenda with [x] completion marks
  SYNTHESIS_INPUT.md  # Concatenated findings (pre-assembly)
  DRAFT_ONBOARD.md   # Pre-cross-reference assembly
  DEEP_ONBOARD.md    # Final document
  VALIDATION_REPORT.md
  REFINE_LOG.md
```

The orchestrator never reads finding content between batches — only sentinel files. Findings are consumed in Phase 3 by assembly sub-agents. This prevents context window exhaustion during long crawls.

---

## The v3.2 Scanner Enhancements

Six new detection categories added to `ast_analysis.py`, all extracted during the single AST pass:

| Category | What It Detects | JSON Key | Markdown Section |
|----------|----------------|----------|-----------------|
| Security concerns | `exec()`, `eval()`, `compile()` calls (not `cursor.execute()`) | `security_concerns` | `## Security Concerns` |
| Silent failures | bare `except:`, `except: pass`, `except Exception: pass` | `silent_failures` | `## Silent Failures` |
| Async violations | Blocking calls (`time.sleep`, `requests.*`) inside `async def` | `async_patterns.violations` | `### Async/Sync Violations` |
| SQL strings | Raw SQL keywords in string literals | `sql_strings` | `## Database Queries (String Literals)` |
| DB side effects | ORM patterns (`.filter`, `.objects.get`, `.execute`) | `side_effects.by_type.db` | (in Side Effects section) |
| Deprecation markers | `@deprecated` decorators, `# DEPRECATED:` comments | `deprecation_markers` | `## Deprecated APIs` |

Each has a config toggle in `configs/default_config.json` (all default to true) and CLI `--no-{section}` flag support.

---

## What the Output Directory Contains

`output/` holds per-repo analysis output. Each analyzed repo gets one folder with final deliverables at the top and intermediate data underneath:

```
output/<repo-name>/
  xray.md              ← Curated markdown summary
  deep_onboard.md      ← Full onboarding document (from deep crawl)
  data/
    xray.json          ← Complete structured output
    <crawl artifacts>  ← Plans, findings, sections, validation reports
```

Current contents:

| Directory | Significance |
|-----------|-------------|
| `output/kosmos/` | Kosmos analysis (802 files, 2.4M tokens). Full deep crawl. 12/12 questions, 10/10 spot checks, adversarial PASS 5/5. 57K words, 777 [FACT] citations. |
- `VALIDATION_REPORT.md` — QA results (23KB)
- `CRAWL_PLAN.md` — Investigation plan (5.2KB)

---

## Documentation

| File | Purpose | Read When |
|------|---------|-----------|
| `INTENT.md` | Why this project exists and the design constraints. **Read before any modification.** | Before changing anything |
| `CLAUDE.md` | How to run, architecture, conventions, don'ts | Before working on scanner code |
| `README.md` | User guide, quick start, examples | Understanding the product |
| `PROJECT_MAP.md` | Complete project reference for AI agents (this file) | First-time onboarding |
| `docs/METHODOLOGY.md` | Technical reference for pipeline algorithms (updated for v3.2) | Understanding scanner internals |
| `docs/TECHNICAL_METRICS.md` | Thresholds and formulas (29 sections, updated for v3.2) | Tuning quality gates |
| `docs/PLAN_INCREMENTAL_CRAWL.md` | Design for `@deep_crawl refresh` (not yet implemented) | Working on incremental updates |
| `MULTI_LANGUAGE_RESEARCH.md` | Research on extending scanner beyond Python (historical — TypeScript now implemented) | Planning additional language support |

**Examples** (`examples/`):

| File | Content |
|------|---------|
| `examples/KOSMOS_XRAY.md` | X-Ray markdown output for Kosmos (802 files) |
| `examples/KOSMOS_DEEP_ONBOARD.md` | Deep crawl R14 onboarding document for Kosmos (~58K words) |
| `output_validation/KOSMOS_DEEP_ONBOARD_VALIDATION.md` | Validation report for the Kosmos deep crawl |

**Archived** (`archive/`):

| File | What It Was |
|------|------------|
| `archive/plans/deep-crawl-spec-v1.md` | Original deep crawl specification (superseded by SKILL.md) |
| `archive/plans/deep-crawl-spec-v2.md` | Revised specification (superseded by SKILL.md) |
| `archive/plans/kickoff-prompt.md` | Implementation kickoff prompt |
| `archive/command_reference.md` | Duplicate of deep-crawl COMMANDS.md |

---

## Critical Rules

These are load-bearing constraints. Violating them, even to "improve" things, is a bug:

1. **No external dependencies on the Python side.** Python 3.8+ stdlib only. If you need library functionality, implement it. The TypeScript scanner is a separate npm project with its own `package.json` (typescript only).

2. **No re-parsing files.** Extend the existing AST visitor in `ast_analysis.py`. One parse per file.

3. **No analysis logic in formatters.** Formatters only format. Analysis belongs in `lib/`.

4. **No non-determinism in the scanner.** No LLM calls, no network requests, no randomness. Same input → same output.

5. **No JSON schema changes without updating the markdown formatter.** They must stay in sync.

6. **Errors are per-file, never per-codebase.** One unparseable file must not crash the scan. See the try/except pattern in `ast_analysis.py:analyze_file()`.

7. **Progress to stderr, results to stdout.** Never mix them.

8. **If adding a new combined-results analysis**, create a new file in `lib/` following the `call_analysis.py` pattern (takes combined results, returns dict). Don't add to `gap_features.py`.

9. **If changing scanner output format**, check whether agent/skill instructions reference the changed fields.

---

## How to Add Things

**New AST-derived signal:** Add detection logic to the `_analyze_tree()` method in `ast_analysis.py`. Add the result key to the returned dict. Wire through `xray.py:run_analysis()`, add config toggle in `default_config.json` and `config_loader.py`, add formatting in both `markdown_formatter.py` and `json_formatter.py`. Add tests.

**New combined-results analysis:** Create `lib/new_analysis.py` with a function taking combined results dict, returning a new dict. Add it as a new stage in `xray.py:run_analysis()`. Wire through formatters and config.

**New deep crawl investigation protocol:** Add to SKILL.md Phase 2 with a new letter (G, H...). Define the protocol instructions. Add it to the batch table. Create a new findings subdirectory. Update the assembly plan to include the new findings.

**New domain facet:** Add entry to `configs/domain_profiles.json` with indicators, additional_investigation, grep_patterns, and primary_entity.

**New quality gate threshold:** Edit `configs/quality_gates.json`. The bash scripts in SKILL.md read these values.

---

## Dependency Graph

```
<<<<<<< HEAD
xray.py ─── detect_language() → Python or TypeScript path
  │
  ├── [Python path]
  │   ├── lib/config_loader.py
  │   ├── lib/file_discovery.py
  │   ├── lib/ast_analysis.py ──────────────────┐
  │   ├── lib/import_analysis.py                │
  │   ├── lib/call_analysis.py ──── needs ──────┤ ast results
  │   ├── lib/git_analysis.py                   │
  │   ├── lib/test_analysis.py                  │
  │   ├── lib/tech_debt_analysis.py             │
  │   ├── lib/blast_analysis.py ──── needs ──────┤ import + call results
  │   ├── lib/route_analysis.py ──── needs ──────┤ ast results
  │   ├── lib/investigation_targets.py ◄────────┘ needs all above
  │   ├── lib/gap_features.py ◄── combines all results
  │   ├── formatters/markdown_formatter.py ◄── uses gap features
  │   └── formatters/json_formatter.py
  │
  └── [TypeScript path]
      ├── ts-scanner/ ◄── invoked via subprocess (node dist/index.js)
      │   └── produces XRayResults JSON (same schema as Python pipeline)
      ├── lib/git_analysis.py ◄── augments TS results (_augment_with_git)
      ├── lib/investigation_targets.py ◄── computes targets from TS results
      ├── lib/gap_features.py ◄── entry points, data models
      ├── formatters/markdown_formatter.py ◄── language-aware formatting
      └── formatters/json_formatter.py

.claude/skills/deep-crawl/SKILL.md
  ├── Reads: output/$REPO_NAME/data/xray.json (Phase 1 output)
  ├── Spawns: investigation sub-agents (Phase 2)
  ├── Spawns: assembly sub-agents (Phase 3, S1-S6)
  ├── Spawns: cross-reference sub-agent (Phase 4)
  ├── Spawns: validator sub-agent (Phase 5)
  ├── References: configs/domain_profiles.json
  ├── References: configs/quality_gates.json
  ├── References: configs/exemplar_templates.md
  └── Uses templates: DEEP_ONBOARD.md.template, CRAWL_PLAN.md.template

tests/
  ├── test_gap_features.py ──► lib/gap_features.py
  ├── test_investigation_targets.py ──► lib/investigation_targets.py
  └── test_scanner_enhancements.py ──► lib/ast_analysis.py
```

---

## Current State

- **Branch:** `master`
- **Languages:** Python, TypeScript/JavaScript
- **Tests:** 137/137 passing (Python side); 8 test files (TypeScript side)
- **Latest validation run (R14):** 12/12 standard questions YES, 10/10 spot checks CONFIRMED, adversarial PASS (5/5)
- **Python scanner signals:** 49+ (original 37 + 5 v3.2 categories + 7 extended signals: blast radius, routes, decorator details, resource leaks, unsafe deserialization, magic methods, import-time side effects)
- **TypeScript scanner:** 20 modules, ~5,700 lines, produces same XRayResults JSON schema as Python scanner
- **Shared output contract:** Both scanners produce identical JSON shape — the JSON schema IS the abstraction layer, not a code-level interface
- **Deep crawl pipeline:** 7 phases, 6 investigation protocols, 6 batches, up to 27 parallel sub-agents

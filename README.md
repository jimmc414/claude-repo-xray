# repo-xray

Solve the cold start problem for AI coding assistants. Two phases: a fast deterministic scan, then an optional LLM-powered deep investigation.

```
Phase 1 — X-Ray:     python xray.py /path/to/project     # 5 sec, ~15K tokens, Python or TypeScript/JS
Phase 2 — Deep Crawl: /deep-crawl full                    # 30-70 min, ~60K words, every claim cited
```

**Phase 1 (X-Ray)** runs in seconds with no API calls or inference tokens expended. It produces a lean, deterministic map of the codebase — skeletons, dependency graph, complexity hotspots, git risk, side effects — that fits in a single context window. Same input, same output, every time. This is enough for most tasks: the AI knows where to look and what to be careful about.

**Phase 2 (Deep Crawl)** is the optional second stage for when you want comprehensive understanding. It uses the X-Ray output as its map, then spawns parallel LLM agents that read actual source code, trace request paths, verify signals, and document everything they find with `file:line` evidence citations. The result is a complete onboarding document that auto-loads in every future AI session. Run it once, benefit for months.

Most users only need Phase 1. Phase 2 pays for itself on codebases where multiple AI sessions will work over time — the generation cost is amortized across every future session that reads the document.

### Example: Kosmos (802 files, ~2.4M tokens)

[Kosmos](https://github.com/jimmc414/Kosmos) is an AI Scientist platform — 802 Python files totaling over 2.4 million tokens. Far too large for any AI context window. Here's what each phase produces:

- **Phase 1 output**: [X-Ray scan](examples/KOSMOS_XRAY.md) — deterministic map in ~15K tokens. Skeletons, dependency graph, complexity hotspots, git risk, side effects, security concerns, silent failures. Produced in seconds.
- **Phase 2 output**: [Deep Crawl onboarding document](examples/KOSMOS_DEEP_ONBOARD.md) — ~58K words of verified behavioral documentation with 444 `[FACT]` citations. Critical paths, module analysis, gotchas, change playbooks, error handling — everything a fresh AI session needs to work confidently in the codebase. Validation: 12/12 standard questions, 10/10 spot checks, adversarial PASS.

### Using the Output

Once generated, attach the output files to your AI session prompt. For Kosmos, that would be [KOSMOS_XRAY.md](examples/KOSMOS_XRAY.md) and [KOSMOS_DEEP_ONBOARD.md](examples/KOSMOS_DEEP_ONBOARD.md). Here's what that looks like:

```
I'm providing two reference documents for the Kosmos codebase:

1. KOSMOS_XRAY.md — A deterministic structural scan (architecture, dependencies,
   complexity hotspots, risk signals)
2. KOSMOS_DEEP_ONBOARD.md — A comprehensive onboarding document with verified
   code citations covering critical paths, module behavior, error handling,
   gotchas, and change playbooks

Use these documents to orient yourself before reading or modifying any code.
When the documents reference specific files and line numbers, trust those as
your starting points but verify current state since code may have changed
since generation.

The codebase is located at: /path/to/Kosmos

My task: [describe what you want the AI to do]
```

If you only ran Phase 1, the X-Ray scan alone is enough for most targeted tasks. Phase 2 adds the most value for open-ended work, complex modifications, or when multiple AI sessions will work on the same codebase over time. A reusable [sample prompt](examples/sample_prompt.md) is included in the examples folder.

## The Problem

When a fresh AI agent lands in an unfamiliar codebase, it does one of two things: reads files at random and wastes context on implementation details, or reads nothing and guesses. Both produce confident, plausible, wrong suggestions.

The cost isn't the bad suggestion itself -- it's the compounding effect. A wrong mental model early in a session infects every subsequent decision. An agent that misidentifies the architectural style will write code that technically works but fights the existing design. An agent that doesn't know about a shared cache will introduce a concurrency bug. An agent that doesn't know which files are generated will burn half its context reading code no human wrote.

A codebase might span 2 million tokens. A context window holds 200K. The agent cannot read everything, but must understand the architecture to know what to read. This is the cold start problem.

## Two Phases

**Phase 1: X-Ray** (deterministic scanner)

| | |
|---|---|
| Speed | 5 seconds on 500 files |
| Output | ~15K tokens (configurable: 2K-15K) |
| Dependencies | Python scanner: Python 3.8+ stdlib only. TypeScript scanner: Node.js + npm. |
| Determinism | Same input produces identical output every time |
| What it extracts | 49+ signals: AST skeletons, import layers, complexity, git risk, side effects, call graph, hub modules, security concerns, silent failures, async violations, SQL patterns, deprecation markers, blast radius, HTTP routes, decorator details, resource leaks, unsafe deserialization, magic methods, import-time side effects |
| What it can't do | Read code semantically. It knows a function has CC=25 and 8 callers. It doesn't know why. |

**Phase 2: Deep Crawl** (LLM-powered investigation, optional)

| | |
|---|---|
| Speed | 30-70 minutes (parallel sub-agents) |
| Output | ~60K words, 17 sections, every claim backed by `file:line` citations |
| Dependencies | Claude Code with sub-agent support (Opus/Sonnet) |
| Determinism | Non-deterministic. Two runs produce different documents. The value is in the investigation. |
| What it does | Traces request paths end-to-end, reads module source, documents error handling, discovers gotchas, builds change playbooks |
| Prerequisite | X-Ray output (Phase 1 must run first) |

The scanner tells you a function has cyclomatic complexity 25 and is called from 8 modules. It cannot tell you that the function silently swallows timeout errors, or that changing its return type will break an undocumented integration three modules away. Only reading the code can tell you that. The deep crawl reads the code.

---

## Quick Start

```bash
git clone https://github.com/jimmc414/claude-repo-xray.git
cd claude-repo-xray

# Scan any Python project (zero dependencies)
python xray.py /path/to/python-project                          # Full analysis to stdout
python xray.py /path/to/python-project --output both             # Markdown + JSON to output/<repo>/
python xray.py /path/to/python-project --preset minimal          # ~2K tokens, quick survey

# Scan any TypeScript/JavaScript project (requires Node.js)
cd claude-repo-xray/ts-scanner && npm install && npm run build && cd ..
python xray.py /path/to/ts-project                              # Auto-detects language

# Layer 2: Deep crawl (requires Claude Code)
cd /path/to/project
python /path/to/xray.py . --output both   # Scanner first (writes to output/<repo>/)
/deep-crawl full                           # Then exhaustive investigation
```

Requirements: Python 3.8+. No `pip install` for Python scanning. TypeScript scanning requires Node.js (run `npm install && npm run build` in `ts-scanner/` once). Layer 2 requires [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview).

---

## Layer 1: The Scanner

### What It Extracts

| Dimension | Signals |
|-----------|---------|
| **Structure** | Skeletons, tokens, files, interfaces, class hierarchies |
| **Architecture** | Import layers, dependency distance, circular deps, hub modules, orphans |
| **Complexity** | Cyclomatic complexity per function, hotspots, async patterns |
| **Behavior** | Side effects (DB, API, file, subprocess), cross-module call graph |
| **History** | Risk scores, co-modification coupling, freshness, author expertise |
| **Context** | CLI arguments, environment variables, Pydantic validators, linter rules |
| **Safety** | Security concerns (exec/eval/compile), unsafe deserialization (pickle/yaml/marshal), silent failures (bare except, except-pass), resource leaks (open without with), hazard files |
| **Quality** | Async/sync violations, SQL string literals, deprecation markers, env var fallbacks |
| **Impact** | Blast radius (transitive dependency impact per module), HTTP route detection (method, path, handler, side effects) |
| **Detail** | Decorator arguments (positional + keyword), magic methods (is_dunder flag), import-time side effects |

A 10K-token source file typically produces a 500-token skeleton. That's a 95% reduction while preserving every public interface and type annotation.

### Presets

| Preset | Tokens | Signals | Use Case |
|--------|--------|---------|----------|
| `minimal` | ~2K | Skeleton + imports | Quick reconnaissance |
| `standard` | ~8K | 8 analysis passes | Balanced coverage |
| (default) | ~15K | All 17 passes | Comprehensive map |

### Configuration

Three ways to control output:

```bash
# CLI flags
python xray.py . --no-logic-maps --no-test-example --no-prose

# Project config (auto-detected)
echo '{"sections": {"logic_maps": false}}' > .xray.json
python xray.py .

# Generate full config template
python xray.py --init-config > .xray.json
```

### Output Formats

**Markdown** -- Human/AI-readable with tables, Mermaid diagrams, code blocks. Renders in GitHub, VS Code, Obsidian.

**JSON** -- Complete structured data for programmatic consumption. Agents use JSON for specific lookups and markdown for orientation.

```bash
python xray.py . --output both
# Creates: analysis.md, analysis.json
```

### Selected Analysis Examples

**Skeleton extraction** -- Classes stripped to signatures:
```python
class OrderEngine:  # L45
    def __init__(self, provider: PaymentProvider): ...
    def process(self, order: Order) -> Result: ...  # CC=25
    def validate(self, order: Order) -> bool: ...
```

**Logic maps** -- Symbolic control flow for complex functions (CC > 15):
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

**Co-modification coupling** -- Files that change together without import relationships, found via frequent itemset mining on commit history:
```
api/router.py <-> tests/test_api.py     (87% co-change, 23 commits)
models/order.py <-> migrations/0047.py  (71% co-change, 14 commits)
```

**Investigation targets** -- Prioritized signals for the crawl agent: ambiguous interfaces, coupling anomalies, high-uncertainty modules, shared mutable state. The scanner cheaply computes "this function is probably confusing" from name genericity and type coverage, saving the expensive crawl agent from deciding what to investigate.

---

## Layer 2: The Deep Crawl

The scanner produces a map. The deep crawl produces understanding.

It spawns parallel investigation agents that systematically read source code across six protocols, then assembles findings into a comprehensive onboarding document. Every claim is backed by evidence. The document is delivered via CLAUDE.md so every future agent session receives it automatically.

### Six-Phase Pipeline

```
Phase 0  SETUP        Working directory, context management, calibration
Phase 1  PLANNING     Investigation strategy from X-Ray signals
Phase 2  CRAWL        Parallel sub-agents execute six investigation protocols
Phase 3  ASSEMBLY     Curate findings into structured document
Phase 4  CROSS-REF    Link sections, verify consistency
Phase 5  VALIDATE     Independent QA (12 questions, 10 spot-checks, adversarial test)
Phase 6  DELIVER      Copy to docs/, update CLAUDE.md, report metrics
```

### Investigation Protocols

| Protocol | Focus | Output |
|----------|-------|--------|
| **A** | Request traces -- follow critical paths end-to-end | `findings/traces/` |
| **B** | Module deep reads -- behavioral detail per module | `findings/modules/` |
| **C** | Cross-cutting concerns -- error handling, config, shared state | `findings/cross_cutting/` |
| **D** | Convention documentation -- patterns, testing, coding style | `findings/conventions/` |
| **E** | Reverse dependency & change impact -- hub modules, blast radii | `findings/impact/` |
| **F** | Change scenario walkthroughs -- step-by-step playbooks | `findings/playbooks/` |

Batches 1-3 run in parallel. Batch 4 waits for 1-3 (conventions benefit from earlier findings). Batch 5 (impact analysis) waits for 1-4 (reads module findings). Batch 6 (playbooks) waits for 1-5 (references impact data).

### Evidence Standards

No inferences or unverified signals in the output document.

| Tag | Standard | Example |
|-----|----------|---------|
| `[FACT]` | Read specific code, cite `file:line` | "3x retry with backoff [FACT] (stripe.py:89)" |
| `[PATTERN]` | Observed in >= 3 examples, state count | "DI via `__init__` [PATTERN: 12/14 services]" |
| `[ABSENCE]` | Searched and confirmed non-existence | "No rate limiting [ABSENCE: grep -- 0 hits]" |

Citation density is mechanically enforced: >= 5.0 `[FACT]` per 100 words in investigation findings, tiered floors in assembled sections (3.0 for high-evidence, 2.0 for medium, 1.0 for narrative). Every citation from findings is verified to survive into the final document.

### Domain Detection

The crawl adapts its investigation based on detected frameworks:

| Domain | Detection | Additional Investigation |
|--------|-----------|------------------------|
| Web API | FastAPI, Flask, Django | Routes, auth middleware, CORS, request lifecycle |
| CLI Tool | argparse, click, typer | Command structure, argument parsing, output formats |
| ML Pipeline | torch, tensorflow, keras | Training loops, data loading, model serialization |
| Data Pipeline | airflow, dagster, prefect | DAG structure, idempotency, stage dependencies |
| Async Service | asyncio, aiohttp, trio | Event loops, sync/async boundaries, cancellation |
| Infrastructure | subprocess, boto3, ansible | Idempotency, rollback, credential handling |

Detection uses import analysis + directory patterns. Domain-specific investigation prompts and grep patterns are defined in `configs/domain_profiles.json`.

### What the Deep Crawl Produces

**DEEP_ONBOARD.md** -- Comprehensive onboarding document with 17 sections:

- Identity & tech stack
- Critical paths (traced end-to-end with code citations)
- Module behavioral index (every investigated module)
- Change impact index (hub modules, blast radii)
- Key interfaces (public APIs with usage patterns)
- Data contracts (cross-boundary flows, schema evolution risks)
- Error handling strategy (patterns, recovery mechanisms)
- Shared state (globals, caches, singletons)
- Domain glossary (codebase-specific terminology)
- Configuration surface (env vars, config files, feature flags)
- Conventions (coding patterns, testing approach)
- Gotchas (clustered by subsystem, severity-tagged, each with `file:line` evidence)
- Hazards (files to avoid reading)
- Extension points (where to add new functionality)
- Change playbooks (step-by-step modification guides with validation commands)
- Reading order (suggested file sequence for manual exploration)
- Environment bootstrap (setup instructions)

The document is auto-loaded via CLAUDE.md. Prompt caching reduces subsequent read cost by ~90%.

### Commands

| Command | Mode | What It Does |
|---------|------|--------------|
| `/deep-crawl full` | Parallel sub-agents | Full pipeline, maximum quality |
| `@deep_crawl full` | Sequential fallback | Same pipeline, single agent |
| `@deep_crawl plan` | Sequential | Generate investigation plan only |
| `@deep_crawl resume` | Sequential | Continue from last checkpoint |
| `@deep_crawl validate` | Sequential | QA an existing document |
| `@deep_crawl refresh` | Sequential | Incremental update for code changes |
| `@deep_crawl focus ./path` | Sequential | Deep crawl a specific subsystem |

### Validation Pipeline

Phase 5 spawns an independent validator with no access to findings or X-Ray output -- it can only see the final document and the actual source code. The validator:

1. Answers 12 standard questions from the document alone (can it guide a new developer?)
2. Spot-checks 10 random `[FACT]` claims against actual source files (9/10 must verify)
3. Runs an adversarial test: 5 deliberately tricky scenarios to find gaps
4. Checks structural navigability (section count, gotcha clusters, module coverage)
5. Verifies document size meets floors scaled to codebase size

---

## The Agent Ecosystem

Four agents, three layers of verification:

| Agent | Role | Approach |
|-------|------|----------|
| **repo_xray** | Quick onboarding from X-Ray signals | Four-phase: orient, investigate, synthesize, validate |
| **deep_crawl** | Exhaustive investigation | Six-phase pipeline with parallel sub-agents |
| **deep_onboard_validator** | Independent QA | 7-check protocol (completeness, accuracy, coverage, adversarial) |
| **repo_retrospective** | Documentation audit | Five-phase: inventory, coverage, verification, actionability, recommendations |

`repo_xray` is the lightweight path -- it uses X-Ray output as a map and adds judgment via targeted file reads. Output is tagged with `[VERIFIED]`, `[INFERRED]`, and `[X-RAY SIGNAL]` confidence levels.

`deep_crawl` is the exhaustive path -- it reads everything worth reading and produces a document where every claim is `[FACT]`-cited. It costs more but the output is read by many future sessions. Generation cost is amortized.

---

## Incremental Updates

Code changes but documentation stays the same until someone re-runs the pipeline. A full deep crawl is expensive. The incremental system (designed, not yet implemented) uses three mechanisms:

**Dependency-scoped re-investigation** -- `git diff` identifies changed files. The import graph computes 1-hop and 2-hop dependents. Only affected modules are re-investigated. A typical 5-file PR touches ~15 modules instead of the full codebase.

**Change log** -- A rule in the target repo's CLAUDE.md instructs models to append to `docs/.onboard_changes.log` when they modify code affecting documented claims:

```
2026-04-01T14:23:00Z | executor.py:617 | Gotchas / Process Management | Changed timeout mechanism
2026-04-01T14:30:00Z | api_router.py:45 | Critical Paths / API Request | Added rate limiting
```

The section reference tells the diff crawl exactly where in the document to look, not just which source file changed. Advisory, not authoritative -- the dependency analysis still runs.

**Finding merge** -- Previous findings are preserved on disk. New findings overwrite only the affected entries. Assembly reads the merged directory and doesn't know or care whether files are fresh or reused.

---

## How It Works

### Scanner Internals

**Python scanner:** Single-pass AST traversal using Python's `ast` module. Each file is parsed once; multiple analyzers extract different signals from the same tree.

| Technique | Used For |
|-----------|----------|
| `ast.walk()` | Flat traversal (complexity counting, side effect detection) |
| `ast.NodeVisitor` | Stateful traversal (call graph, skeleton extraction) |
| `collections.Counter` | Frequency analysis (pattern detection) |
| `collections.deque` | BFS (dependency distance computation) |
| Git log parsing | Risk scores, coupling, freshness |

**TypeScript scanner:** Uses the TypeScript compiler API (`ts.createSourceFile`) for AST parsing. Self-contained npm project in `ts-scanner/` with 20 modules. Produces the same `XRayResults` JSON schema as the Python scanner. `xray.py` detects the project language, invokes the appropriate scanner, then augments results with language-agnostic git analysis.

### Performance

For a 500-file codebase:
- AST analysis: ~2 seconds (Python), ~3 seconds (TypeScript)
- Git analysis: ~1 second
- Total: ~5 seconds

Python scanner: no external dependencies, Python 3.8+ stdlib only. TypeScript scanner: requires Node.js.

### Deep Crawl Internals

All intermediate state lives on disk (`.deep_crawl/`), not in conversation context. Sub-agents write findings to individual markdown files. The orchestrator never reads finding content until assembly -- it only checks sentinel files for completion.

Findings are quality-gated between batches. If a finding has fewer than 200 words or 5 `[FACT]` citations, the sub-agent is re-spawned with corrective instructions. Batch 2 (module deep reads) uses elevated thresholds: 400 words and 10 citations.

Calibration runs before the main crawl: three exemplar investigations (one trace, one module, one cross-cutting concern) establish quality baselines. All subsequent sub-agent prompts reference these exemplars.

---

## Design Decisions

**Why AST-only for the scanner.** We considered pytest tracing, coverage integration, and runtime type capture. Each would produce more accurate data. We rejected them because they add dependencies, require a working test suite, take minutes instead of seconds, and produce non-deterministic output. The scanner's value is that it works on any codebase with zero setup (Python) or minimal setup (TypeScript).

**Why the output is for AI, not humans.** Early versions served both audiences. The result was too verbose for AI (wasting context on prose) and too structured for humans (tables and compact notation). We chose the AI audience because that's where the leverage is -- a human can read code directly, but an AI's effectiveness is bottlenecked by what fits in context.

**Why investigation targets in the scanner.** The scanner was originally pure observation. We added investigation targets (ambiguous interfaces, coupling anomalies, high-uncertainty modules) because without them, the crawl agent wastes significant time deciding what to investigate. The scanner cheaply computes "this is probably confusing" from name genericity and type coverage. Surfacing that as a prioritized list makes the crawl agent 2-3x more efficient.

**Why delivered via CLAUDE.md, not read on demand.** An agent that has to know to look for the onboarding document sometimes won't. An agent that receives it automatically in system context always has it. The token cost of auto-loading is less than the cost of a single session where the agent works without orientation. Prompt caching makes the ongoing cost negligible.

**Why unlimited generation budget for deep crawl.** The document is read by many future sessions. Optimizing for cheap generation at the expense of output quality is a false economy when the output is read hundreds of times. We removed token budget ceilings and let content determine size.

---

## Limitations

- **Python and TypeScript/JavaScript only.** Other languages are not yet supported. The agent layer and document format are language-agnostic -- adding a new scanner means producing the same JSON schema.
- **Git history required** for risk, coupling, and freshness signals. Works without git, just with fewer signals.
- **Side effect detection is heuristic.** Pattern matching on function names (`session.commit`, `requests.post`). Has a whitelist to reduce false positives, but won't catch novel patterns. SQL string detection may flag docstrings containing SQL-like keywords.
- **Documents go stale.** Code changes but the document stays the same until refresh. A slightly stale onboarding document is better than none.
- **Deep crawl output is non-deterministic.** Two runs on the same codebase produce different documents. The value comes from investigation and synthesis, not reproducibility. The scanner provides the reproducible foundation.

---

## File Structure

```
repo-xray/
├── xray.py                          Entry point + orchestration (language detection, scanner dispatch)
├── lib/                             Python scanner modules
│   ├── ast_analysis.py              Single-pass AST extraction
│   ├── import_analysis.py           Dependency graph, layers, hub detection
│   ├── call_analysis.py             Cross-module call sites, reverse lookup
│   ├── git_analysis.py              Risk scores, coupling, freshness
│   ├── gap_features.py              Logic maps, hazards, data models, mermaid
│   ├── investigation_targets.py     Prioritized signals for crawl agents
│   ├── blast_analysis.py            Transitive impact via BFS over import+call graph
│   ├── route_analysis.py            HTTP route detection (method, path, handler, side effects)
│   ├── file_discovery.py            Python file discovery, ignore patterns
│   ├── test_analysis.py             Test file detection, pattern extraction
│   ├── tech_debt_analysis.py        TODO/FIXME markers
│   └── config_loader.py             Config file loading, validation
├── ts-scanner/                      TypeScript/JavaScript scanner (self-contained npm project)
│   ├── src/                         20 modules: AST analysis, imports, calls, detectors, etc.
│   ├── test/                        8 test files + fixtures
│   ├── package.json                 Own deps (typescript only)
│   └── tsconfig.json                Own build config
├── formatters/
│   ├── markdown_formatter.py        Human/AI-readable output (language-aware)
│   └── json_formatter.py            Structured output
├── configs/
│   ├── default_config.json          All sections enabled
│   └── presets.json                 Preset definitions
├── tools/
│   └── enrich_onboard.py           Inject git signals into DEEP_ONBOARD.md
├── tests/
│   ├── test_gap_features.py         Gap analysis tests
│   ├── test_investigation_targets.py Signal computation tests
│   └── test_scanner_enhancements.py v3.2 detection category tests
├── docs/
│   └── PLAN_INCREMENTAL_CRAWL.md    Incremental refresh design
└── .claude/
    ├── agents/
    │   ├── repo_xray.md             Investigation agent
    │   ├── deep_crawl.md            Sequential fallback agent
    │   ├── deep_onboard_validator.md Independent QA agent
    │   └── repo_retrospective.md    Documentation audit agent
    └── skills/
        └── deep-crawl/
            ├── SKILL.md             Orchestrator instructions (1,600 lines)
            ├── configs/
            │   ├── domain_profiles.json   Framework detection + investigation prompts
            │   ├── quality_gates.json     Citation density, word count floors
            │   └── compression_targets.json Section size targets
            └── templates/
                ├── DEEP_ONBOARD.md.template
                ├── CRAWL_PLAN.md.template
                └── VALIDATION_REPORT.md.template
```

---

## Installation

```bash
git clone https://github.com/jimmc414/claude-repo-xray.git
cd claude-repo-xray
python xray.py /path/to/your/project          # Python projects work immediately

# For TypeScript/JavaScript projects (one-time setup):
cd ts-scanner && npm install && npm run build && cd ..
python xray.py /path/to/your/ts-project       # Auto-detects language
```

Requirements: Python 3.8+ (no external dependencies for Python scanning). Node.js for TypeScript scanning.

To install the deep crawl skill globally in Claude Code:
```bash
./setup_deep_crawl.sh
```

This creates a symlink so `/deep-crawl full` is available in any project directory.

## License

MIT

# Deep Crawl Specification for repo-xray

> **Version:** 1.0
> **Status:** Specification
> **Audience:** Developers implementing and using the deep crawl addon
> **Dependencies:** repo-xray (existing), Claude Code agent/skill framework

---

## 1. Problem Statement

repo-xray solves the cold start problem by producing a deterministic, fast, zero-dependency map of a Python codebase. This map is good — but it's a map, not understanding. A 5-million-token codebase compressed to 15K tokens of xray output still leaves a downstream agent guessing about behavioral semantics, hidden coupling, error handling strategy, and the meaning of generic abstractions.

The current `repo_xray` agent partially addresses this through its INVESTIGATE phase, but it operates under token budget constraints designed for a single interactive session. It reads selectively, summarizes quickly, and delivers within minutes. This is appropriate for developer-facing workflows but leaves significant value on the table.

**Deep Crawl** removes the budget constraint on generation. It assumes the onboarding document will be read by hundreds of agent sessions, so spending 20M tokens to produce a 15K-token document is justified if that document maximally reduces uncertainty for every downstream agent that reads it.

### The Core Metric

**File-reads saved per onboarding token.** Every token in the onboarding document should reduce the number of files a downstream agent needs to open before it can confidently make changes. A raw skeleton saves ~0.5 file reads (the agent usually still opens the file). An LLM-generated behavioral summary with gotchas saves ~1.0. A verified request trace through 5 modules saves 5. Deep Crawl optimizes for this ratio.

---

## 2. Design Principles

**2.1. xray stays deterministic.** The scanner remains fast, zero-dependency, reproducible. Deep Crawl builds on top of xray output, never replaces it.

**2.2. Generation cost is irrelevant; access cost is everything.** The crawl can run for hours and consume millions of tokens. The output document must be small enough to fit in a downstream agent's context alongside the task it's working on.

**2.3. Every output token must resolve uncertainty.** No filler, no redundancy with information the downstream agent can derive from file names or signatures alone. If a fact is obvious from the code structure, don't include it. If it's surprising, counterintuitive, or requires reading multiple files to understand, include it.

**2.4. The document is for AI agents, not humans.** Optimize for machine consumption. Structured, unambiguous, directly actionable. No motivational prose, no "this is a well-designed system" commentary. State facts, flag dangers, provide coordinates.

**2.5. Leverage the Anthropic ecosystem fully.** Extended thinking for synthesis, Claude Code tools for investigation, prompt caching for efficient multi-pass analysis. Design for how Claude Code actually works, not for a generic LLM.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GENERATION PIPELINE                         │
│                  (runs once, cost amortized)                        │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │  xray.py │───▶│ investigation│───▶│     deep_crawl agent     │  │
│  │ (scanner)│    │   _targets   │    │  (LLM-powered analysis)  │  │
│  │          │    │  (new JSON   │    │                          │  │
│  │ Layer 1  │    │   section)   │    │  Phase 1: Plan           │  │
│  │ signals  │    │              │    │  Phase 2: Crawl          │  │
│  └──────────┘    └──────────────┘    │  Phase 3: Synthesize     │  │
│                                      │  Phase 4: Compress        │  │
│                                      │  Phase 5: Validate        │  │
│                                      └────────────┬─────────────┘  │
│                                                    │                │
│                                                    ▼                │
│                                      ┌──────────────────────────┐  │
│                                      │  DEEP_ONBOARD.md         │  │
│                                      │  (~8-20K tokens)         │  │
│                                      │  Optimized for agent     │  │
│                                      │  consumption             │  │
│                                      └──────────────────────────┘  │
│                                                    │                │
└────────────────────────────────────────────────────┼────────────────┘
                                                     │
                        ┌────────────────────────────┼──────────┐
                        │     CONSUMPTION (every session)       │
                        │                                       │
                        │   Fresh Claude instance reads         │
                        │   DEEP_ONBOARD.md (~15K tokens)       │
                        │   + task instructions                 │
                        │   = productive immediately            │
                        │                                       │
                        └───────────────────────────────────────┘
```

### Component Roles

| Component | Role | Cost Model |
|-----------|------|------------|
| `xray.py` | Deterministic signal extraction | ~5 seconds, zero API cost |
| `investigation_targets` | Prioritized crawl agenda (new xray output section) | Part of xray scan, zero additional cost |
| `deep_crawl` agent | LLM-powered investigation and synthesis | 5-20M tokens (one-time generation) |
| `deep_onboard_validator` agent | QA pass on the output document | 1-3M tokens (one-time) |
| `DEEP_ONBOARD.md` | Compressed onboarding document | 8-20K tokens (read every session) |

---

## 4. Modifications to xray.py

### 4.1. New Output Section: `investigation_targets`

Add a new section to both the JSON and markdown outputs. This section is deterministically computed from existing xray signals and serves as the crawl agenda for the deep_crawl agent.

#### JSON Schema

```json
{
  "investigation_targets": {
    "ambiguous_interfaces": [
      {
        "function": "process",
        "file": "core/engine.py",
        "line": 45,
        "reason": "generic_name",
        "type_coverage": 0.3,
        "cc": 25,
        "cross_module_callers": 8
      }
    ],
    "entry_to_side_effect_paths": [
      {
        "entry_point": "api/routes.py:create_order",
        "entry_type": "fastapi_route",
        "reachable_side_effects": [
          {"type": "db", "location": "repositories/order.py:34", "pattern": "session.commit"},
          {"type": "api", "location": "providers/stripe.py:67", "pattern": "requests.post"}
        ],
        "estimated_hop_count": 4
      }
    ],
    "coupling_anomalies": [
      {
        "files": ["payments.py", "notifications.py"],
        "co_modification_score": 0.85,
        "has_import_relationship": false,
        "reason": "co_modified_without_imports"
      }
    ],
    "convention_deviations": [
      {
        "convention": "service_classes_take_config_init",
        "conforming_count": 12,
        "violating": [
          {"class": "LegacyOrderService", "file": "services/legacy.py", "line": 15}
        ]
      }
    ],
    "shared_mutable_state": [
      {
        "variable": "_cache",
        "file": "lib/cache.py",
        "line": 8,
        "scope": "module",
        "mutated_by": ["cache.py:set", "cache.py:clear", "config.py:reload"],
        "risk": "concurrent_modification"
      }
    ],
    "high_uncertainty_modules": [
      {
        "module": "core/resolver.py",
        "reasons": ["generic_name", "low_type_coverage", "high_fan_in", "no_docstrings"],
        "uncertainty_score": 0.92
      }
    ],
    "domain_entities": [
      {
        "name": "Order",
        "type": "pydantic_model",
        "file": "models/order.py",
        "line": 12,
        "referenced_in": ["services/order.py", "api/routes.py", "repositories/order.py"]
      }
    ]
  }
}
```

#### Implementation Details

Each sub-section is computed from existing xray data with minimal new analysis:

**`ambiguous_interfaces`** — Filter functions from the skeleton where: (a) the name is in a generic-name list (`process`, `handle`, `run`, `execute`, `resolve`, `validate`, `transform`, `convert`, `dispatch`, `apply`, `update`, `get`, `set`, `do`, `perform`, `manage`, `build`, `create`, `make`), OR (b) type annotation coverage < 50% AND the function has cross-module callers ≥ 2. Score by `(cross_module_callers * cc) / type_coverage`. This identifies functions where reading the signature alone won't tell you what they do.

**`entry_to_side_effect_paths`** — For each detected entry point, walk the call graph (already built by `call_analysis.py`) and collect all reachable side effects (already detected by `ast_analysis.py`). Store the entry point, the terminal side effects, and an estimated hop count. This gives the deep_crawl agent a roadmap of "trace from here to here" without the agent needing to discover the path itself.

**`coupling_anomalies`** — Already computed by `git_analysis.py` (co-modification coupling). Cross-reference with `import_analysis.py` graph. Flag pairs where co-modification score > 0.7 but no direct or transitive import relationship exists within 2 hops.

**`convention_deviations`** — New analysis pass over existing skeleton data. For each detected pattern (class `__init__` signatures, decorator usage, module naming, return type annotations), compute the majority convention and flag outliers. Implementation: group classes by structural similarity (same base class, same decorators, same method names), find the dominant signature pattern in each group, flag members that deviate.

**`shared_mutable_state`** — New AST pass (or extend existing `ast_analysis.py` visitor). Find module-level assignments where the target is subsequently mutated via augmented assignment (`+=`, `.append`, `.update`, `[key] =`, `.clear()`, etc.) anywhere in the module or by any cross-module caller. Also flag singleton patterns (`_instance = None` with a `get_instance()` function).

**`high_uncertainty_modules`** — Composite score from: generic filename (1 point), low type coverage (1 point), high fan-in from call analysis (1 point), no module or class docstrings (1 point), high CC but not already a hotspot (1 point), contains `**kwargs` in public functions (1 point). Modules scoring ≥ 3 are flagged. These are modules where the deep_crawl agent should spend its reading budget.

**`domain_entities`** — Already partially extracted via `extract_data_models()` in `gap_features.py`. Extend to include non-Pydantic classes that are referenced in type annotations across 3+ modules, which identifies domain objects that may not use a formal modeling library.

#### New File: `lib/investigation_targets.py`

Single new module, ~300-500 lines. Imports from existing analysis results, computes the above sections, returns a dict. Called from `xray.py` main function after all other analyses complete.

#### Markdown Output

Add a compact section to the markdown output:

```markdown
## Investigation Targets (for Deep Crawl)

**High-uncertainty modules (6):** core/resolver.py (0.92), lib/dispatcher.py (0.85), ...
**Ambiguous interfaces (14):** process() in 3 modules, handle() in 5 modules, ...
**Traced entry→side-effect paths (5):** POST /orders → 4 hops → db.commit + stripe.post, ...
**Coupling anomalies (2):** payments.py ↔ notifications.py (no imports, 85% co-modified), ...
**Shared mutable state (3):** _cache in lib/cache.py, _config in settings.py, ...
**Convention deviations (4):** LegacyOrderService skips config init, ...
**Domain entities (8):** Order, OrderItem, Payment, User, ...
```

---

## 5. Deep Crawl Agent Specification

### 5.1. Agent Definition

```markdown
---
name: deep_crawl
description: Exhaustive LLM-powered codebase investigator. Uses X-Ray signals as a map to systematically crawl a codebase and produce a maximally compressed onboarding document optimized for AI agent consumption. Designed to run without token budget constraints — spends whatever is needed to produce the optimal output.
tools: Read, Grep, Glob, Bash
model: opus
skills: deep-crawl
---
```

**Model selection: Opus.** This agent's entire purpose is deep reasoning and synthesis. It runs once, amortized over many downstream sessions. Using the most capable model maximizes the quality of every output token, and cost is explicitly not a constraint.

### 5.2. Five-Phase Workflow

#### Phase 1: PLAN (Build the Crawl Agenda)

**Input:** xray JSON output (full preset), including `investigation_targets`.

**Process:**
1. Read the full xray markdown for orientation
2. Read the `investigation_targets` section from JSON
3. Detect the project domain (web API, CLI tool, ML pipeline, data pipeline, library)
4. Produce a prioritized crawl plan — an ordered list of investigation tasks

**Crawl Plan Structure:**

```markdown
## Crawl Plan

### Priority 1: Request Traces (entry → side effect)
- [ ] Trace POST /orders → db.commit (estimated 4 hops)
- [ ] Trace CLI main → file.write (estimated 3 hops)
- [ ] Trace webhook handler → api.post (estimated 5 hops)

### Priority 2: High-Uncertainty Module Deep Reads
- [ ] core/resolver.py — generic name, 0 docstrings, 8 callers
- [ ] lib/dispatcher.py — low type coverage, high fan-in

### Priority 3: Behavioral Summaries for Pillar Modules
- [ ] core/engine.py (pillar #1) — full read, behavioral summary
- [ ] services/order.py (pillar #2) — full read, behavioral summary
- [ ] ...

### Priority 4: Cross-Cutting Concerns
- [ ] Error handling strategy — grep for except/raise patterns, identify strategy
- [ ] Configuration surface — find all config reads, map to modules
- [ ] Shared mutable state — verify 3 flagged globals, assess risk
- [ ] Domain glossary — extract from models + type annotations

### Priority 5: Convention and Pattern Documentation
- [ ] Identify the dominant coding patterns
- [ ] Document the 4 flagged convention deviations
- [ ] Verify 2 coupling anomalies

### Priority 6: Gap Investigation
- [ ] What does xray NOT tell us that an agent would need?
- [ ] Are there implicit initialization sequences?
- [ ] Are there undocumented environment dependencies?
```

**Prioritization logic:**

The ordering reflects information density — what saves the most downstream file-reads per token of output. Request traces are first because a single trace replaces 3-5 file reads for any agent working on that pathway. High-uncertainty modules are second because they're the modules where reading the name and signature tells you nothing. Cross-cutting concerns are fourth because they're "learn once, apply everywhere" — a single paragraph about error handling strategy applies to every modification the downstream agent makes.

**Output:** A markdown crawl plan saved to `/tmp/deep_crawl/CRAWL_PLAN.md`. The agent checks off items as it completes them, enabling resumability.

---

#### Phase 2: CRAWL (Systematic Investigation)

**Process:** Execute the crawl plan in priority order. For each investigation task, use a specific investigation protocol based on the task type.

##### Protocol: Request Trace

```
1. Read the entry point function (full source)
2. Identify the first call it makes to another module
3. Read that function (full source)
4. Repeat until you reach a terminal side effect or 8 hops
5. Record the trace as a compact chain:
   entry_function (file:line)
     → called_function (file:line) — what it does in 1 sentence
     → next_function (file:line) — what it does in 1 sentence
     → [SIDE EFFECT: db.commit] (file:line)
6. Note any branching (error paths, conditional logic) at each hop
7. Note any transformations (data shape changes between hops)
```

##### Protocol: Module Deep Read

```
1. Read the entire module (or first 500 lines if larger)
2. Produce a behavioral summary:
   - What this module does (1-2 sentences)
   - What's non-obvious about it (gotchas, implicit assumptions)
   - What breaks if you change it (blast radius)
   - What it depends on (not imports — runtime dependencies)
   - What depends on it (from call analysis cross-referencing)
3. For each public function/method:
   - 1-sentence behavioral description (not the signature — what it DOES)
   - Preconditions (what must be true before calling)
   - Side effects (what changes after calling)
   - Error behavior (what happens on failure)
```

##### Protocol: Cross-Cutting Concern

```
1. Grep for the relevant patterns across the entire codebase
2. Categorize the results (how many files, which modules, what patterns)
3. Identify the dominant strategy
4. Flag deviations from the dominant strategy
5. Produce a 2-3 sentence summary of the strategy + list of deviations
```

##### Protocol: Convention Documentation

```
1. Read 3-5 examples of the convention in practice
2. State the convention in 1-2 sentences
3. List the deviations flagged by xray
4. Read each deviation and determine: intentional variation or bug?
```

**State management:** After each investigation task completes, the agent appends its findings to `/tmp/deep_crawl/FINDINGS.md`. This serves as the raw material for Phase 3 and enables resumability if the crawl is interrupted.

**Checkpointing:** After every 5 completed tasks, the agent updates the crawl plan to mark completed items. If the conversation is interrupted and restarted, the agent reads the crawl plan and findings file to resume from the last checkpoint.

---

#### Phase 3: SYNTHESIZE (Produce Raw Onboarding Document)

**Input:** Accumulated findings from Phase 2.

**Process:**
1. Review all findings holistically — identify themes, patterns, and connections between findings
2. Use extended thinking to reason about what a downstream agent MOST needs
3. Draft the onboarding document following the `DEEP_ONBOARD.md.template`
4. For each section, select the findings that maximize information density
5. Discard findings that are obvious from code structure or duplicate other findings

**Key synthesis questions (evaluate with extended thinking):**

- "If an agent reads only this document and then tries to fix a bug in module X, what would it get wrong?"
- "What implicit knowledge does a developer accumulate over a week that I can encode in a sentence?"
- "Which of my findings are redundant with what the agent could infer from just seeing the file tree?"
- "What's the minimum set of facts that, if known, would let the agent make safe changes anywhere in the codebase?"

**Output:** First draft of `DEEP_ONBOARD.md`, likely 20-30K tokens (intentionally over budget for next phase).

---

#### Phase 4: COMPRESS (Optimize for Token Budget)

**Input:** First draft from Phase 3.

**Process:**
1. Measure the current document size in tokens
2. Set target: 8-20K tokens depending on codebase size (see sizing table below)
3. For each section, evaluate: "does this save more file-reads than it costs in tokens?"
4. Cut the lowest-value content first:
   - Remove behavioral summaries for modules that are self-explanatory from their names and signatures
   - Merge similar gotchas into categories
   - Compress request traces that share common sub-paths
   - Replace verbose explanations with structured tables
   - Eliminate any sentence that restates what the code structure already implies
5. Re-evaluate: "can an agent still answer the 10 standard questions from this compressed version?"
6. If not, restore the minimum content needed to answer each question

**Target document sizes:**

| Codebase Size | Files | Target Onboarding Size | Rationale |
|---------------|-------|------------------------|-----------|
| Small | <100 | 8-10K tokens | Minimal overhead needed |
| Medium | 100-500 | 12-15K tokens | Standard coverage |
| Large | 500-2000 | 15-18K tokens | More modules = more traces |
| Very Large | >2000 | 18-20K tokens | Hard ceiling — diminishing returns beyond this |

**Output:** Final draft of `DEEP_ONBOARD.md`.

---

#### Phase 5: VALIDATE (Quality Assurance)

**Input:** Final `DEEP_ONBOARD.md` + codebase access.

**Process:**

##### 5a. Standard Questions Test

The agent attempts to answer these 10 questions using ONLY the onboarding document (no file reads). Each question must be answerable, or the document is deficient.

```
1. What does this codebase do? (purpose and scope)
2. Where does a request/command enter the system? (entry points)
3. What's the critical path from input to output? (main flow)
4. What files should I never read? (hazards)
5. What happens when the main operation fails? (error handling)
6. What external systems does this talk to? (side effects/integrations)
7. What shared state exists that could cause bugs? (mutable globals, singletons)
8. What are the testing conventions? (how to write a test that fits)
9. What are the 3 most counterintuitive things about this codebase? (gotchas)
10. If I need to add a new [primary entity], where do I start? (extension points)
```

##### 5b. Spot-Check Verification

Select 5 [VERIFIED] claims at random from the document. Read the actual code and confirm they're accurate. If any fail, flag and correct.

##### 5c. Redundancy Check

For each section, ask: "Would an agent who can see the file tree and read function signatures already know this?" If yes, the section is wasting tokens. Cut it.

##### 5d. Compression Ratio Report

```
| Metric | Value |
|--------|-------|
| Codebase size (tokens) | X |
| Onboarding document size (tokens) | Y |
| Compression ratio | X:Y |
| Crawl budget consumed (tokens) | Z |
| ROI (if read by N sessions) | Z / (N * file-reads-saved) |
| Standard questions answerable | M/10 |
| Verified claims spot-checked | P/5 passed |
| Investigation tasks completed | Q/R |
```

**Output:** Validated `DEEP_ONBOARD.md` + validation report.

---

## 6. Deep Crawl Skill Specification

### 6.1. File Structure

```
.claude/skills/deep-crawl/
├── SKILL.md                          # Skill reference
├── COMMANDS.md                       # Quick command reference
├── configs/
│   ├── generic_names.json            # List of ambiguous function names
│   ├── domain_profiles.json          # Domain-specific investigation priorities
│   └── compression_targets.json      # Token budget targets by codebase size
└── templates/
    ├── DEEP_ONBOARD.md.template      # Output document template
    ├── CRAWL_PLAN.md.template        # Investigation plan template
    └── VALIDATION_REPORT.md.template # QA report template
```

### 6.2. Commands

```
@deep_crawl full                 # Full pipeline: plan → crawl → synthesize → compress → validate
@deep_crawl plan                 # Generate crawl plan only (review before committing to full crawl)
@deep_crawl resume               # Resume from last checkpoint
@deep_crawl validate <path>      # Validate an existing DEEP_ONBOARD.md
@deep_crawl refresh              # Re-run crawl with updated xray output, preserve valid findings
@deep_crawl focus <path>         # Deep crawl a specific subsystem only
```

### 6.3. Interaction with Existing Agents

```
Workflow:
  1. User runs: python xray.py . --output both --out /tmp/xray
  2. User runs: @deep_crawl full
  3. (Optional) User runs: @deep_onboard_validator full
  4. Output: DEEP_ONBOARD.md in project root

The deep_crawl agent REPLACES the repo_xray agent for this workflow.
It does NOT call the repo_xray agent. It reads xray.py output directly.

The repo_xray agent remains available for quick, interactive analysis.
The deep_crawl agent is for thorough, non-interactive generation.
```

---

## 7. Output Document Template

### 7.1. `DEEP_ONBOARD.md.template`

The output document is structured for machine parsing. Each section has a consistent format that a downstream agent can scan efficiently.

```markdown
# {PROJECT_NAME}: Agent Onboarding

> Codebase: {FILE_COUNT} files, ~{TOTAL_TOKENS} tokens
> This document: ~{DOC_TOKENS} tokens
> Generated: {TIMESTAMP} from commit {GIT_HASH}
> Crawl depth: {TASKS_COMPLETED}/{TASKS_PLANNED} investigation tasks

---

## Identity

{1-3 sentences: what this is, what it does, what stack it uses}

## Critical Paths

{For each major entry point, a compact trace showing the
chain from entry to terminal side effect, with 1-sentence
behavioral descriptions at each hop}

### {PATH_NAME}
```
{ENTRY} ({file}:{line})
  → {FUNC_1} ({file}:{line}) — {what it does}
    → {FUNC_2} ({file}:{line}) — {what it does}
      → [{SIDE_EFFECT}] ({file}:{line})
  ✗ on failure: {what happens}
```

## Module Behavioral Index

{For each architecturally significant module: 1-sentence
behavioral summary, preconditions, gotchas. NOT the
skeleton — the skeleton is in xray output. This is what
the skeleton doesn't tell you.}

| Module | Does | Depends On | Danger |
|--------|------|------------|--------|
| {path} | {1-sentence behavior} | {runtime deps} | {gotcha or "none"} |

## Error Handling Strategy

{2-3 sentences describing the dominant error handling pattern.
Then a table of deviations.}

Dominant pattern: {description}

Deviations:
| Module | Pattern | Risk |
|--------|---------|------|
| {path} | {how it differs} | {what could go wrong} |

## Shared State

{Every module-level mutable variable, singleton, cache,
or global registry. These are the things that cause
action-at-a-distance bugs.}

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| {name} | {file}:{line} | {functions} | {description} |

## Domain Glossary

{Map of domain-specific terms to their meaning in THIS
codebase. Only include terms that are ambiguous or
overloaded — skip obvious ones like "User" or "Database".}

| Term | Means | Defined In |
|------|-------|------------|
| {term} | {meaning in this codebase} | {file} |

## Configuration Surface

{Every config knob that changes behavior: env vars,
config file keys, feature flags, CLI args.}

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| {name} | {env/file/flag} | {what behavior changes} | {value} |

## Conventions

{The implicit rules a developer learns over a week.
Write these as directives: "do X", "never Y", "always Z".}

1. {Convention — 1 sentence}
2. {Convention — 1 sentence}
...

## Gotchas

{Counterintuitive behaviors, ordered by likelihood of
causing a bug. Each must be [VERIFIED] with file:line evidence.}

1. **{title}** — {description} (`{file}:{line}`)
2. ...

## Hazards — Do Not Read

{Files that waste context. Include glob patterns.}

| Pattern | Size | Why |
|---------|------|-----|
| {glob} | {tokens} | {reason} |

## Extension Points

{Where to start for common modification tasks. Only include
tasks that are non-obvious — skip "add a test" → tests/.}

| Task | Start Here | Touch These | Watch Out |
|------|------------|-------------|-----------|
| {task} | {file} | {other files} | {gotcha} |

## Reading Order

{If the agent needs to go deeper, read in this order.
Ranked by information-per-token, not by importance.}

1. `{file}` — {why read this first, what you learn}
2. `{file}` — {why}
3. `{file}` — {why}

## Gaps

{What this document doesn't cover. Be specific so the
agent knows when it needs to investigate further.}

- {gap description}
```

### 7.2. Key Differences from ONBOARD.md.template

| Aspect | ONBOARD.md (repo_xray) | DEEP_ONBOARD.md (deep_crawl) |
|--------|------------------------|------------------------------|
| Audience | Humans and AI | AI agents only |
| Skeletons | Included in Critical Components | Omitted (available in xray output) |
| Behavioral summaries | Brief, for top pillars | Comprehensive, for all significant modules |
| Request traces | Suggested, agent may skip | Mandatory, verified by reading code |
| Error handling | Optional investigation | Mandatory section |
| Domain glossary | Not present | Mandatory section |
| Shared state | Not systematically covered | Mandatory section |
| Configuration | Env vars listed | Full config surface mapped |
| Conventions | Implicit in patterns shown | Explicit directives |
| Token investment | ~45-55K agent consumption | 5-20M agent consumption |
| Confidence tags | [VERIFIED], [INFERRED], [X-RAY SIGNAL] | Everything is [VERIFIED] — if it's not verified, it's not included |

---

## 8. Crawl Strategy Details

### 8.1. Budget Allocation

Given unlimited generation budget, the question is how to allocate investigation time across task types for maximum output quality.

**Recommended allocation (by investigation time):**

| Task Type | Budget Share | Rationale |
|-----------|-------------|-----------|
| Request traces | 30% | Highest file-reads-saved-per-output-token |
| Module deep reads | 25% | Required for behavioral index |
| Cross-cutting concerns | 20% | "Learn once, apply everywhere" |
| Convention/pattern docs | 10% | Prevents style violations |
| Gap investigation | 10% | Catches what xray missed entirely |
| Validation | 5% | Ensures output quality |

### 8.2. Crawl Ordering Within Task Types

**Request traces:** Order by estimated hop count descending. Longer traces save more downstream file-reads. Also prioritize traces that pass through high-uncertainty modules, since those traces force the agent to read and understand them.

**Module deep reads:** Order by uncertainty score from `investigation_targets`. Read the most ambiguous modules first. Skip modules where the name, signature, and docstring already tell the full story.

**Cross-cutting concerns:** Fixed order:
1. Error handling (affects every modification)
2. Configuration (affects deployment and behavior)
3. Shared state (affects concurrency and testing)
4. Authentication/authorization (if detected — affects security)
5. Logging/observability (affects debugging)

### 8.3. When to Stop Crawling

The crawl is complete when:
1. All Priority 1 (request traces) tasks are done
2. All Priority 2 (high-uncertainty modules) tasks are done
3. All Priority 4 cross-cutting concerns have been investigated
4. The raw findings are sufficient to answer all 10 standard questions
5. Diminishing returns: the last 3 investigation tasks did not surface new gotchas or change the behavioral summary of any module

### 8.4. Handling Very Large Codebases (>2000 files)

For very large codebases, the crawl plan itself becomes a significant document. Strategy:

1. Run xray with `--preset full` to get complete signals
2. During PLAN phase, identify 3-5 subsystems from the architectural layers
3. Execute a focused deep crawl on each subsystem independently
4. In SYNTHESIZE, produce a top-level document that covers cross-subsystem interactions, plus subsystem-specific appendix sections
5. The top-level document stays within 20K tokens; subsystem appendices are referenced by file path for agents working in specific areas

```markdown
## Subsystem Deep Dives

For focused work in a specific area, read the relevant subsystem document:

| Subsystem | Document | Scope |
|-----------|----------|-------|
| API Layer | `docs/deep_onboard_api.md` | Routes, middleware, auth |
| Core Engine | `docs/deep_onboard_core.md` | Business logic, workflows |
| Data Layer | `docs/deep_onboard_data.md` | Models, repositories, migrations |
```

---

## 9. Claude Code Integration

### 9.1. Tool Usage Patterns

The deep_crawl agent should use Claude Code tools in specific patterns:

**Read** — Primary investigation tool. Use for:
- Full module reads during deep read protocol
- Targeted reads during request trace protocol (read only the function being traced)
- Convention verification (read 3-5 examples)

**Grep** — Discovery tool. Use for:
- Error handling strategy (`grep -r "except\|raise" --include="*.py"`)
- Configuration reads (`grep -r "os.getenv\|os.environ\|config\[" --include="*.py"`)
- Pattern detection (`grep -r "@retry\|@cached\|@singleton" --include="*.py"`)
- Shared state mutations (`grep -r "^[A-Z_].*=" --include="*.py" | grep -v "^#\|def \|class "`)

**Glob** — Structure discovery. Use for:
- Finding test files for convention analysis
- Locating config files
- Mapping module organization

**Bash** — Running xray and utility operations:
```bash
# Run xray scan
python xray.py . --output both --out /tmp/xray

# Count tokens in draft
wc -w /tmp/deep_crawl/DEEP_ONBOARD.md | awk '{print int($1 * 1.3)}'

# Check for findings file (resumability)
test -f /tmp/deep_crawl/FINDINGS.md && echo "RESUME" || echo "FRESH"
```

### 9.2. Extended Thinking Usage

The agent should use extended thinking at these specific points:

1. **End of Phase 1 (PLAN):** Reason about investigation priorities given the specific codebase characteristics. Which xray signals are most surprising? What domain-specific patterns should be investigated?

2. **During Phase 2 (CRAWL) — after each request trace:** Reason about what the trace reveals about the system's design. Are there implicit contracts between modules? Is the error handling consistent across the trace?

3. **Beginning of Phase 3 (SYNTHESIZE):** Reason about all findings holistically. What are the 3-5 most important things a downstream agent needs to know? What's the minimum viable onboarding document?

4. **During Phase 4 (COMPRESS):** Reason about each section: "If I remove this, what mistake would the downstream agent make?" Keep sections that prevent mistakes. Cut sections that merely inform.

### 9.3. Prompt Caching Strategy

The deep crawl involves reading many files, some of which will be referenced multiple times. To minimize redundant token usage:

1. Read xray JSON once at the start and refer to it in system prompt context throughout
2. When a module deep read surfaces imports from another module, batch the reads — don't re-read modules
3. Store findings incrementally so they serve as context for later investigation tasks

### 9.4. File Management

```
/tmp/deep_crawl/
├── CRAWL_PLAN.md          # Investigation plan (updated during crawl)
├── FINDINGS.md            # Raw findings (appended during crawl)
├── DRAFT_ONBOARD.md       # First draft (Phase 3 output)
├── DEEP_ONBOARD.md        # Final output (Phase 4 output)
└── VALIDATION_REPORT.md   # QA report (Phase 5 output)

Final deliverable:
{project_root}/DEEP_ONBOARD.md     # Copied here at end
```

---

## 10. Domain-Specific Profiles

The crawl agent should adjust its investigation strategy based on detected domain. Stored in `configs/domain_profiles.json`.

### 10.1. Web API (FastAPI, Flask, Django)

**Additional investigation targets:**
- Authentication/authorization middleware chain
- Request validation pipeline
- Rate limiting implementation
- CORS configuration
- Middleware execution order

**Additional onboarding sections:**
- API endpoint index (route → handler → service mapping)
- Auth flow trace
- Middleware chain documentation

### 10.2. CLI Tool (argparse, Click, Typer)

**Additional investigation targets:**
- Command hierarchy and subcommand structure
- Argument parsing and validation
- Output formatting strategy (JSON, table, plain text)
- Exit code conventions

**Additional onboarding sections:**
- Command tree with argument signatures
- Output format documentation

### 10.3. ML/AI Pipeline (torch, tensorflow, transformers)

**Additional investigation targets:**
- Training loop structure
- Model architecture definition location
- Data loading and preprocessing pipeline
- Checkpoint/save/load conventions
- Evaluation metrics implementation

**Additional onboarding sections:**
- Training pipeline trace
- Model configuration surface
- Data flow from raw input to model input

### 10.4. Data Pipeline (airflow, dagster, ETL)

**Additional investigation targets:**
- DAG structure and dependencies
- Idempotency guarantees
- Failure recovery and retry strategy
- Data validation between stages
- Scheduling configuration

**Additional onboarding sections:**
- DAG visualization or description
- Stage-by-stage data transformation documentation

### 10.5. Library/SDK

**Additional investigation targets:**
- Public API surface (what's exported)
- Backward compatibility constraints
- Extension/plugin mechanisms
- Thread safety guarantees

**Additional onboarding sections:**
- Public API index with behavioral descriptions
- Extension point documentation

---

## 11. Validation Agent Specification

A separate, lighter-weight agent provides independent QA on the deep crawl output. This is a modified version of the existing `repo_retrospective` agent, adapted for the DEEP_ONBOARD format.

### 11.1. Agent Definition

```markdown
---
name: deep_onboard_validator
description: Quality assurance agent for DEEP_ONBOARD documents. Verifies claims against actual code, tests completeness against standard questions, identifies redundancy and wasted tokens. Run after deep_crawl completes.
tools: Read, Grep, Glob, Bash
model: sonnet
skills: deep-crawl
---
```

**Model selection: Sonnet.** Validation is structured and protocol-driven. It doesn't require Opus-level reasoning. Sonnet is sufficient and cheaper.

### 11.2. Validation Protocol

```
1. COMPLETENESS: Answer all 10 standard questions from the document alone
2. ACCURACY: Spot-check 10 [VERIFIED] claims (not 5 — higher bar than repo_xray)
3. REDUNDANCY: For each section, check if content is inferable from file tree + signatures
4. FRESHNESS: Verify 3 file:line references still point to the claimed code
5. ADVERSARIAL: Simulate "agent tries to add a new [primary entity]" using
   only the onboarding doc — does it make a mistake?
6. REPORT: Produce validation report with pass/fail and specific deficiencies
```

---

## 12. Implementation Plan

### Phase 1: xray Modifications (1-2 days)

1. Create `lib/investigation_targets.py`
   - `compute_ambiguous_interfaces(ast_results, call_results)` — filter by generic names + low type coverage
   - `compute_entry_side_effect_paths(entry_points, call_results, side_effects)` — walk call graph from entries
   - `compute_coupling_anomalies(git_results, import_results)` — cross-reference co-modification with imports
   - `compute_convention_deviations(ast_results)` — statistical pattern detection
   - `compute_shared_mutable_state(ast_results)` — module-level mutation detection
   - `compute_high_uncertainty_modules(ast_results, call_results)` — composite scoring
   - `compute_domain_entities(ast_results, call_results)` — extended data model extraction
   - `compute_investigation_targets(all_results)` — master function that calls all above

2. Integrate into `xray.py` main pipeline
   - Call `compute_investigation_targets()` after all existing analyses
   - Pass results to formatters

3. Update `formatters/markdown_formatter.py` — add compact investigation targets section
4. Update `formatters/json_formatter.py` — add full investigation targets to JSON output

### Phase 2: Agent and Skill Creation (1-2 days)

1. Create `.claude/agents/deep_crawl.md` — agent definition with five-phase workflow
2. Create `.claude/agents/deep_onboard_validator.md` — validation agent
3. Create `.claude/skills/deep-crawl/SKILL.md` — skill reference
4. Create `.claude/skills/deep-crawl/COMMANDS.md` — command reference
5. Create template files:
   - `DEEP_ONBOARD.md.template`
   - `CRAWL_PLAN.md.template`
   - `VALIDATION_REPORT.md.template`
6. Create config files:
   - `generic_names.json`
   - `domain_profiles.json`
   - `compression_targets.json`

### Phase 3: Testing (1-2 days)

1. Run `investigation_targets.py` against 3-5 real codebases of varying size
2. Verify the crawl agent produces usable crawl plans from xray output
3. Run the full pipeline end-to-end on a medium codebase (~200 files)
4. Verify the validator catches intentionally introduced errors
5. Measure: can a fresh Claude instance answer the 10 standard questions from the output?

### Phase 4: Iteration (ongoing)

1. Collect feedback from downstream agents using DEEP_ONBOARD documents
2. Track which onboarding sections are most referenced / most useful
3. Adjust investigation priorities and compression strategy based on data
4. Add domain profiles for additional project types

---

## 13. Open Questions

**13.1. Should the deep crawl agent produce the xray scan itself or require it as input?**
Recommendation: Require it as input. Keeps the separation clean and lets users inspect xray output before committing to a potentially expensive crawl. The agent should fail fast with a clear message if xray output is missing or stale.

**13.2. Should the output document include xray skeleton data or reference it?**
Recommendation: Reference it. The DEEP_ONBOARD document should say "for class signatures, see xray output" and focus exclusively on behavioral information that can't be derived from the skeleton. This avoids duplication and keeps the document within budget.

**13.3. How should staleness be handled?**
Recommendation: Store the git commit hash in the DEEP_ONBOARD header. The deep_crawl agent's `refresh` command diffs the current commit against the stored one, identifies changed files, re-investigates only those files and their dependents, and updates the relevant sections. Full re-crawl only when >30% of files have changed.

**13.4. Should the document be a single file or a directory of files?**
Recommendation: Single file for codebases <2000 files. Directory with a top-level index for larger codebases (see Section 8.4). A single file maximizes the chance that a downstream agent reads the whole thing — if it's split across files, agents will skip subsystem documents they think are irrelevant and miss cross-cutting gotchas.

**13.5. How should the deep crawl handle codebases in languages other than Python?**
Outside current scope. xray itself is Python-only. A future version could accept a language-agnostic xray-equivalent as input, but the deep_crawl agent's investigation protocols would need language-specific adaptations. The DEEP_ONBOARD template and compression strategy are language-agnostic.

---

## Appendix A: Generic Function Name List

Used for `ambiguous_interfaces` detection. Functions with these names AND low type coverage AND cross-module callers are flagged for deep investigation.

```json
{
  "generic_names": [
    "process", "handle", "run", "execute", "resolve",
    "validate", "transform", "convert", "dispatch", "apply",
    "update", "get", "set", "do", "perform",
    "manage", "build", "create", "make", "generate",
    "parse", "format", "load", "save", "send",
    "check", "verify", "compute", "calculate", "evaluate",
    "init", "setup", "configure", "prepare", "cleanup",
    "start", "stop", "reset", "refresh", "sync",
    "call", "invoke", "emit", "notify", "trigger",
    "wrap", "decorate", "inject", "register", "connect"
  ]
}
```

## Appendix B: Standard Questions

The 10 questions every DEEP_ONBOARD document must answer. Used in Phase 5 validation.

```
Q1.  PURPOSE:    What does this codebase do?
Q2.  ENTRY:      Where does a request/command enter the system?
Q3.  FLOW:       What's the critical path from input to output?
Q4.  HAZARDS:    What files should I never read?
Q5.  ERRORS:     What happens when the main operation fails?
Q6.  EXTERNAL:   What external systems does this talk to?
Q7.  STATE:      What shared state exists that could cause bugs?
Q8.  TESTING:    What are the testing conventions?
Q9.  GOTCHAS:    What are the 3 most counterintuitive things?
Q10. EXTENSION:  If I need to add a new [primary entity], where do I start?
```

## Appendix C: Uncertainty Scoring Formula

Used to compute `high_uncertainty_modules` in investigation targets.

```
uncertainty_score = (
    (1.0 if name_is_generic else 0) +
    (1.0 if type_coverage < 0.3 else 0.5 if type_coverage < 0.6 else 0) +
    (1.0 if fan_in >= 5 else 0.5 if fan_in >= 3 else 0) +
    (1.0 if no_docstrings else 0) +
    (1.0 if max_cc > 15 and not_already_hotspot else 0) +
    (0.5 if has_kwargs_in_public_functions else 0) +
    (0.5 if no_type_annotations_on_returns else 0)
) / 6.0
```

Modules with uncertainty_score >= 0.5 are flagged for deep investigation.
```

---

# Part 2: Implementable Artifacts

Everything below is ready to drop into the repo-xray project structure. Each section is a complete file with its target path noted.

---

## 14. Agent Definitions

### 14.1. `deep_crawl` Agent

**Target path:** `.claude/agents/deep_crawl.md`

````markdown
---
name: deep_crawl
description: Exhaustive LLM-powered codebase investigator. Uses X-Ray signals to systematically crawl a codebase and produce a maximally compressed onboarding document optimized for AI agent consumption. Designed to run without token budget constraints. Use this instead of repo_xray when generation cost is not a concern and output quality is paramount.
tools: Read, Grep, Glob, Bash
model: opus
skills: deep-crawl
---

# Deep Crawl Agent

You are producing the single most important document a future AI coding agent will read before working in this codebase. Every token you include in the output saves or wastes context for hundreds of future agent sessions. Every fact you verify prevents or permits a class of bugs. Treat this as the most consequential technical writing you will do.

## Your Mission

Produce `DEEP_ONBOARD.md` — a compressed, verified, behaviorally-focused onboarding document that enables a fresh Claude instance to work safely and effectively in a codebase it has never seen.

**Constraint:** The output document must be 8-20K tokens. The generation process has no token budget. Spend whatever is necessary to produce the optimal output.

**Standard:** Every claim in the output must be verified by reading actual code. If you haven't read it, don't include it. No [INFERRED] or [X-RAY SIGNAL] tags — everything is [VERIFIED] or it's not in the document.

---

## Prerequisites

Before starting, verify:

1. X-Ray output exists:
```bash
test -f /tmp/xray/xray.json && echo "READY" || echo "Run: python xray.py . --output both --out /tmp/xray"
```

2. Check for existing crawl state (resumability):
```bash
test -f /tmp/deep_crawl/CRAWL_PLAN.md && echo "RESUME AVAILABLE" || echo "FRESH CRAWL"
```

If resuming, read the crawl plan and findings file first. Continue from the last unchecked task.

---

## Phase 1: PLAN

**Goal:** Build a prioritized investigation agenda from X-Ray signals.

### Steps

1. Read the X-Ray markdown summary:
```bash
cat /tmp/xray/xray.md
```

2. Read investigation targets from JSON:
```bash
python3 -c "import json; d=json.load(open('/tmp/xray/xray.json')); print(json.dumps(d.get('investigation_targets', {}), indent=2))"
```

3. Detect the project domain from X-Ray signals:
   - Check entry points, decorators, dependencies
   - Classify as: web_api | cli_tool | ml_pipeline | data_pipeline | library | other

4. Build the crawl plan. Use extended thinking to reason about priorities:
   - Which modules have the highest uncertainty?
   - Which request traces cover the most code?
   - What cross-cutting concerns are most likely to cause bugs?

5. Write the crawl plan:
```bash
mkdir -p /tmp/deep_crawl
```

Write to `/tmp/deep_crawl/CRAWL_PLAN.md` using this structure:

```markdown
# Deep Crawl Plan: {project_name}

## Domain: {detected_domain}
## Codebase: {file_count} files, ~{token_count} tokens
## Generated: {timestamp}

### Priority 1: Request Traces
- [ ] {trace_description} (est. {N} hops)
...

### Priority 2: High-Uncertainty Module Deep Reads
- [ ] {module} — {reasons}
...

### Priority 3: Pillar Behavioral Summaries
- [ ] {module} — pillar #{rank}
...

### Priority 4: Cross-Cutting Concerns
- [ ] Error handling strategy
- [ ] Configuration surface
- [ ] Shared mutable state
- [ ] {domain-specific concerns}

### Priority 5: Conventions and Patterns
- [ ] Dominant coding patterns
- [ ] Convention deviations ({count} flagged)
- [ ] Coupling anomalies ({count} flagged)

### Priority 6: Gap Investigation
- [ ] Implicit initialization sequences
- [ ] Undocumented environment dependencies
- [ ] Hidden coupling not in imports
```

---

## Phase 2: CRAWL

**Goal:** Execute the crawl plan systematically. Append findings to `/tmp/deep_crawl/FINDINGS.md`.

### Investigation Protocols

For each task type, follow the specific protocol below. After completing each task, append findings and mark the task as complete in the crawl plan.

#### Protocol A: Request Trace

```
1. Read the entry point function in full
2. Identify the first cross-module call
3. Read that function in full
4. Continue until you reach a terminal side effect OR 8 hops
5. At each hop, record:
   - Function name and file:line
   - What it does (1 sentence — behavior, not structure)
   - What data it transforms (input shape → output shape)
   - What can go wrong (error path)
6. Record the complete trace in FINDINGS.md
```

**Output format in FINDINGS.md:**

```markdown
### Trace: {name}
```
{entry_function} ({file}:{line})
  → {func} ({file}:{line}) — {behavior}
    → {func} ({file}:{line}) — {behavior}
      → [{SIDE_EFFECT}: {detail}] ({file}:{line})
  ✗ on failure: {error_behavior}
  ⚠ gotcha: {if any}
```
```

#### Protocol B: Module Deep Read

```
1. Read the module (full, or first 500 lines if >500)
2. For the module overall:
   - What does it do? (1-2 sentences of BEHAVIOR, not structure)
   - What's its single responsibility?
   - What would break if you deleted it?
3. For each public function/class:
   - 1-sentence behavioral description
   - Preconditions (what must be true before calling)
   - Side effects (what changes after calling)
   - Error behavior (what happens on failure)
4. Identify gotchas:
   - Implicit assumptions not in the signature
   - Non-obvious side effects
   - Order dependencies
   - Thread safety issues
5. Record in FINDINGS.md
```

**Output format in FINDINGS.md:**

```markdown
### Module: {path}

**Does:** {1-2 sentence behavioral summary}
**Breaks if removed:** {blast radius}

| Public Interface | Behavior | Preconditions | Side Effects | On Failure |
|-----------------|----------|---------------|--------------|------------|
| {name} | {desc} | {pre} | {effects} | {error} |

**Gotchas:**
- {gotcha with file:line evidence}
```

#### Protocol C: Cross-Cutting Concern

```
1. Grep for relevant patterns across the entire codebase
2. Categorize results by module and pattern
3. Identify the dominant strategy
4. Read 2-3 representative examples in full
5. Flag deviations from the dominant strategy
6. Record in FINDINGS.md
```

**For error handling specifically:**
```bash
# Find the error handling patterns
grep -rn "except " --include="*.py" | head -40
grep -rn "raise " --include="*.py" | head -30
grep -rn "try:" --include="*.py" | wc -l
grep -rn "except.*pass" --include="*.py"  # swallowed exceptions
grep -rn "retry\|backoff\|fallback" --include="*.py"
```

**For configuration surface:**
```bash
grep -rn "os.getenv\|os.environ\|\.env\." --include="*.py"
grep -rn "config\[" --include="*.py"
grep -rn "settings\." --include="*.py"
find . -name "*.yaml" -o -name "*.toml" -o -name "*.ini" -o -name "*.cfg" | head -10
```

**For shared mutable state:**
```bash
# Module-level assignments that aren't constants
grep -rn "^[a-z_].*= " --include="*.py" | grep -v "def \|class \|#\|import " | head -30
grep -rn "_instance\|_cache\|_registry\|_pool" --include="*.py"
grep -rn "global " --include="*.py"
```

#### Protocol D: Convention Documentation

```
1. Read 3-5 examples of the pattern (from xray pillar/hotspot list)
2. Identify the common structure
3. State the convention as a directive ("always X", "never Y")
4. Read each flagged deviation
5. Assess: intentional variation or oversight?
6. Record in FINDINGS.md
```

### Checkpoint Discipline

After every 5 completed tasks:
1. Update CRAWL_PLAN.md — mark completed items with [x]
2. Count remaining tasks
3. If all Priority 1-4 tasks are complete, evaluate:
   - Can you answer all 10 standard questions from current findings?
   - If yes, proceed to Phase 3
   - If no, identify which questions can't be answered and investigate specifically

### When to Stop Crawling

Stop when ALL of the following are true:
- All Priority 1 (request traces) tasks are complete
- All Priority 2 (high-uncertainty modules) are read
- All Priority 4 (cross-cutting concerns) are investigated
- Current findings can answer all 10 standard questions
- The last 3 tasks did not surface new gotchas

---

## Phase 3: SYNTHESIZE

**Goal:** Transform raw findings into a structured onboarding document.

### Steps

1. Read ALL findings:
```bash
cat /tmp/deep_crawl/FINDINGS.md
```

2. **Use extended thinking** to reason holistically:
   - What are the 3-5 most important things a downstream agent needs?
   - What themes emerge across findings?
   - What's the minimum set of facts for safe modifications anywhere?
   - What did I find that surprised me? (That's a gotcha.)

3. Draft `DEEP_ONBOARD.md` following the template at:
   `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

4. Key synthesis rules:
   - **Don't copy findings verbatim** — synthesize across modules
   - **Don't include skeletons** — those are in xray output, reference them
   - **Don't explain obvious things** — if the file name tells the story, skip it
   - **DO include surprises** — anything non-obvious gets priority space
   - **DO include cross-module interactions** — how modules affect each other
   - **DO write conventions as directives** — "Always X", "Never Y"

5. Write first draft to `/tmp/deep_crawl/DRAFT_ONBOARD.md`

---

## Phase 4: COMPRESS

**Goal:** Reduce the draft to target token budget while preserving maximum value.

### Target Sizes

| Codebase Files | Target Tokens |
|----------------|---------------|
| <100 | 8-10K |
| 100-500 | 12-15K |
| 500-2000 | 15-18K |
| >2000 | 18-20K |

### Compression Protocol

1. Estimate current size:
```bash
wc -w /tmp/deep_crawl/DRAFT_ONBOARD.md | awk '{printf "~%d tokens\n", $1 * 1.3}'
```

2. For each section, ask: **"If I remove this, what specific mistake would a downstream agent make?"**
   - If you can name the mistake → keep the section
   - If you can't → cut it

3. Compression techniques (apply in order):
   a. **Merge similar gotchas** — "Functions A, B, C all swallow exceptions" not three separate entries
   b. **Compress traces that share sub-paths** — show the shared path once, branch points as bullets
   c. **Convert prose to tables** — tables are denser than paragraphs for structured information
   d. **Drop self-evident module summaries** — if `email_sender.py` sends emails, don't say so
   e. **Replace verbose error descriptions with patterns** — "All services use try/except/log/reraise" not per-service descriptions
   f. **Reference xray output** — "For class signatures, see xray output" saves hundreds of tokens

4. After compression, verify the 10 standard questions are still answerable

5. Write final version to `/tmp/deep_crawl/DEEP_ONBOARD.md`

---

## Phase 5: VALIDATE

**Goal:** Ensure the document actually works.

### 5a. Standard Questions Test

For each of the 10 standard questions (see Appendix B in skill docs), attempt to answer using ONLY the DEEP_ONBOARD.md content. Do NOT look at any source files.

```
For each question:
- Can you answer it? YES / NO / PARTIAL
- If NO or PARTIAL: what's missing?
- Fix any gaps by adding minimal content
```

### 5b. Spot-Check Verification

Select 10 factual claims from the document at random. For each:
1. Read the referenced file:line
2. Verify the claim is accurate
3. If inaccurate, correct it

### 5c. Redundancy Audit

For each section, ask: "Would an agent who can see the file tree and run `grep` figure this out in under 30 seconds?"
- If yes → the section is wasting tokens, cut it
- If no → keep it

### 5d. Adversarial Test

Simulate: "An agent reads this document, then tries to add a new instance of the primary entity (new API endpoint, new CLI command, new model, etc.)."
- Walk through the steps the agent would take
- Would it make a mistake that the document should have prevented?
- If yes, add the missing information

### 5e. Deliver

1. Copy to project root:
```bash
cp /tmp/deep_crawl/DEEP_ONBOARD.md ./DEEP_ONBOARD.md
```

2. Generate validation report at `/tmp/deep_crawl/VALIDATION_REPORT.md`

3. Report summary to user:
```
Deep Crawl Complete
═══════════════════
Codebase: {files} files, ~{tokens} tokens
Document: ~{doc_tokens} tokens ({compression_ratio}:1 compression)
Crawl: {tasks_completed}/{tasks_planned} tasks
Questions answerable: {score}/10
Claims verified: {verified}/10
Gotchas documented: {count}
Request traces: {count}
```

---

## Constraints

1. **Every claim must be verified by reading code** — no inferences, no assumptions
2. **No skeletons in output** — reference xray output for structural information
3. **No filler** — every sentence must either prevent a mistake or direct attention
4. **Tables over prose** — for structured information, always use tables
5. **Directives over descriptions** — "Never call X before Y" not "X depends on Y being initialized"
6. **Gotchas are gold** — a single gotcha can save hours; invest space in them
7. **Name the blast radius** — for every critical module, state what breaks if it changes
8. **Checkpoint regularly** — enable resumability for long crawls
9. **Compress ruthlessly** — a 12K token document read 100 times consumes 1.2M tokens; every wasted token multiplies

---

## Handling Edge Cases

### Codebase has no tests
- Skip testing conventions section
- Note in Gaps: "No test suite found — conventions unknown"
- Increase Priority 4 investigation depth (no test-based verification available)

### Codebase has no git history
- Skip co-modification coupling analysis
- Note in Gaps: "No git history — coupling anomalies not detectable"
- Increase convention deviation investigation (can't use churn data)

### Codebase is a monorepo with multiple services
- During PLAN, identify service boundaries
- Produce one DEEP_ONBOARD.md per service + one cross-service index
- Cross-service index documents: shared libraries, communication patterns, deployment dependencies

### Codebase uses non-standard patterns
- If xray can't classify architecture into layers, the crawl is MORE valuable, not less
- Spend extra budget on Module Deep Reads for every module with fan-in >= 3
- Document the actual architecture in plain terms, don't force a layered model

### xray output is missing investigation_targets
- Fall back to manual investigation planning
- Use xray's existing signals (pillars, hotspots, side effects) as the crawl agenda
- The crawl will be less efficient but the output quality should be equivalent

### Crawl is interrupted mid-execution
- On restart, read CRAWL_PLAN.md and FINDINGS.md
- Verify findings are still valid (git hash matches)
- Continue from last unchecked task
- If git hash has changed, re-run xray and re-plan

---

## Files

- **Agent:** `.claude/agents/deep_crawl.md` (this file)
- **Skill:** `.claude/skills/deep-crawl/SKILL.md`
- **Commands:** `.claude/skills/deep-crawl/COMMANDS.md`
- **Template:** `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`
- **Scanner:** `xray.py` (prerequisite — run first)
- **Investigation targets:** `lib/investigation_targets.py` (xray addon)

*This agent is designed to produce the highest-quality codebase onboarding document possible, without regard for generation cost. The investment pays off across every downstream agent session that reads the output.*
````

---

### 14.2. `deep_onboard_validator` Agent

**Target path:** `.claude/agents/deep_onboard_validator.md`

````markdown
---
name: deep_onboard_validator
description: Independent QA agent for DEEP_ONBOARD documents. Verifies claims against actual code, tests completeness, identifies redundancy. Run after deep_crawl completes or when validating an existing onboarding document.
tools: Read, Grep, Glob, Bash
model: sonnet
skills: deep-crawl
---

# Deep Onboard Validator Agent

You are an independent quality auditor. Your job is to find deficiencies in a DEEP_ONBOARD.md document before it becomes the foundation for hundreds of agent sessions. Every error you miss will be multiplied across every session that reads the document.

## Inputs

1. **DEEP_ONBOARD.md** — the document to validate (project root or specified path)
2. **X-Ray output** — `/tmp/xray/xray.json` and `/tmp/xray/xray.md`
3. **Codebase** — full source access

## Validation Protocol

Execute all 6 checks in order. Do not skip any check.

### Check 1: Completeness (Standard Questions)

Using ONLY the DEEP_ONBOARD.md content (do NOT read any source files), attempt to answer each question:

```
Q1.  PURPOSE:    What does this codebase do?
Q2.  ENTRY:      Where does a request/command enter the system?
Q3.  FLOW:       What's the critical path from input to output?
Q4.  HAZARDS:    What files should I never read?
Q5.  ERRORS:     What happens when the main operation fails?
Q6.  EXTERNAL:   What external systems does this talk to?
Q7.  STATE:      What shared state exists that could cause bugs?
Q8.  TESTING:    What are the testing conventions?
Q9.  GOTCHAS:    What are the 3 most counterintuitive things?
Q10. EXTENSION:  If I need to add a new [primary entity], where do I start?
```

For each: rate as PASS (fully answerable), PARTIAL (some info missing), or FAIL (can't answer).

### Check 2: Accuracy (Spot-Check 10 Claims)

Select 10 specific factual claims from the document. For each:

1. Read the referenced file and line
2. Verify the claim is accurate
3. Rate as: CONFIRMED, INACCURATE, or STALE (code has changed)

Priority: check claims in Gotchas and Critical Paths first — errors there cause the most damage.

### Check 3: Coverage (X-Ray Cross-Reference)

Compare the document against xray output:

1. Read xray JSON: extract the top 10 pillars, top 5 hotspots, all entry points
2. For each pillar: is it mentioned in the Module Behavioral Index? If not, why?
3. For each entry point: is there a Critical Path trace that starts from it? If not, why?
4. For each side effect type (DB, API, file): are they documented? If not, why?

Not every xray signal needs to be in the document — but omissions should be justified (module is self-explanatory, trace is trivial, etc.).

### Check 4: Redundancy (Token Waste)

For each section in the document:

1. Read the section
2. Ask: "Would an agent who can see the file tree, read function signatures, and run grep figure this out in under 30 seconds?"
3. If yes: flag as REDUNDANT — these tokens could be better used
4. Estimate wasted tokens per redundant section

### Check 5: Adversarial Simulation

Simulate a real task using only the document:

1. Pick the most common modification type for this codebase domain:
   - Web API → "Add a new endpoint"
   - CLI → "Add a new command"
   - Library → "Add a new public function"
   - Pipeline → "Add a new stage"

2. Using ONLY DEEP_ONBOARD.md, plan the modification:
   - Which files to create/modify
   - What conventions to follow
   - What to watch out for

3. Then READ the actual code to check if you would have made a mistake
4. If yes: the document has a gap. Describe what's missing.

### Check 6: Freshness

1. Read the git hash from the document header
2. Compare against current HEAD:
```bash
git log --oneline -1
```
3. If different, list changed files:
```bash
git diff --name-only {doc_hash} HEAD
```
4. For each changed file mentioned in the document, flag as POTENTIALLY STALE

---

## Output: Validation Report

Write to `/tmp/deep_crawl/VALIDATION_REPORT.md`:

```markdown
# DEEP_ONBOARD Validation Report

## Document: {path}
## Validated: {timestamp}
## Codebase HEAD: {git_hash}
## Document built from: {doc_git_hash}

---

## Verdict: {PASS | NEEDS FIXES | NEEDS REWORK}

---

## Check 1: Completeness ({score}/10)

| Question | Result | Detail |
|----------|--------|--------|
| Q1 Purpose | {PASS/PARTIAL/FAIL} | {detail if not PASS} |
| Q2 Entry | ... | ... |
...

## Check 2: Accuracy ({confirmed}/{total})

| Claim | Location | Result | Detail |
|-------|----------|--------|--------|
| {claim} | {file:line} | {CONFIRMED/INACCURATE/STALE} | {detail} |
...

## Check 3: Coverage

### Missing from document:
- {pillar/entry/side_effect not covered} — {justified/unjustified}

### Justifiable omissions:
- {item} — {reason it's OK to skip}

## Check 4: Redundancy

| Section | Tokens | Redundant? | Reason |
|---------|--------|------------|--------|
| {section} | ~{N} | {YES/NO} | {reason} |

**Estimated wasted tokens:** ~{total}

## Check 5: Adversarial Simulation

**Task:** {simulated task}
**Would agent succeed?** {YES/NO/PARTIAL}
**Gap found:** {description of missing info, if any}

## Check 6: Freshness

**Document hash:** {hash}
**Current HEAD:** {hash}
**Stale sections:** {count}
**Files changed since document:** {list}

---

## Recommended Fixes

Priority order:
1. {fix — prevents incorrect agent behavior}
2. {fix — fills completeness gap}
3. {fix — removes redundancy}
...

## Metrics

| Metric | Value |
|--------|-------|
| Completeness score | {N}/10 |
| Accuracy score | {N}/10 |
| Coverage (pillars) | {N}% |
| Coverage (entry points) | {N}% |
| Redundant tokens | ~{N} |
| Adversarial test | {PASS/FAIL} |
| Freshness | {CURRENT/STALE} |
```

### Verdict Criteria

| Verdict | Criteria |
|---------|----------|
| **PASS** | Completeness ≥ 9/10, Accuracy ≥ 9/10, Adversarial PASS |
| **NEEDS FIXES** | Completeness ≥ 7/10, Accuracy ≥ 7/10, specific fixable gaps |
| **NEEDS REWORK** | Completeness < 7/10, OR Accuracy < 7/10, OR critical gaps in Gotchas/Critical Paths |

---

## Constraints

1. **Be adversarial, not collegial** — your job is to find problems, not confirm quality
2. **Check claims against actual code** — don't trust the document's file:line references without reading them
3. **Measure token waste** — every redundant token in the document costs across all future sessions
4. **Test with a real task** — the adversarial simulation is the most important check
5. **Distinguish "nice to have" from "causes bugs"** — prioritize fixes that prevent incorrect agent behavior
````

---

## 15. Skill Definition

### 15.1. `SKILL.md`

**Target path:** `.claude/skills/deep-crawl/SKILL.md`

````markdown
---
name: deep-crawl
description: Exhaustive LLM-powered codebase investigation for optimal AI onboarding. Use when generation cost is not a constraint and you need the highest-quality onboarding document possible. Builds on X-Ray deterministic signals with unlimited LLM-powered investigation.
---

# deep-crawl

Systematic codebase investigation that produces a maximally compressed onboarding document optimized for AI agent consumption. Designed to complement repo-xray: xray provides the map, deep-crawl provides the understanding.

## When to Use

- **Use deep-crawl** when you have a large codebase, many future agent sessions will use the onboarding document, and you don't care about generation cost
- **Use repo_xray** when you need quick interactive analysis, or generation cost matters
- **Use both**: run xray first (always required), then deep_crawl for the premium onboarding document

## Prerequisites

```bash
# X-Ray scan must exist before deep crawl
python xray.py . --output both --out /tmp/xray

# Verify
test -f /tmp/xray/xray.json && echo "READY"
```

## Commands

```bash
@deep_crawl full          # Full 5-phase pipeline
@deep_crawl plan          # Generate crawl plan only (review before committing)
@deep_crawl resume        # Resume interrupted crawl from checkpoint
@deep_crawl validate      # Validate an existing DEEP_ONBOARD.md
@deep_crawl refresh       # Update document for code changes
@deep_crawl focus ./path  # Deep crawl a specific subsystem
```

## Pipeline Overview

```
Phase 1: PLAN        Read xray → build prioritized investigation agenda
Phase 2: CRAWL       Execute agenda → read code → record verified findings
Phase 3: SYNTHESIZE  Transform findings → draft onboarding document
Phase 4: COMPRESS    Reduce to token budget → maximize info density
Phase 5: VALIDATE    Standard questions test → spot-check → adversarial sim
```

## Output

```
DEEP_ONBOARD.md          Final onboarding document (8-20K tokens)
/tmp/deep_crawl/
├── CRAWL_PLAN.md         Investigation agenda with completion tracking
├── FINDINGS.md           Raw verified findings from crawl
├── DRAFT_ONBOARD.md      Pre-compression draft
└── VALIDATION_REPORT.md  QA results
```

## Output Document Sections

| Section | Purpose | Token Density |
|---------|---------|---------------|
| Identity | What this codebase is (1-3 sentences) | High |
| Critical Paths | Entry → side effect traces | Highest |
| Module Behavioral Index | What each module DOES (not its structure) | High |
| Error Handling Strategy | Dominant pattern + deviations | Medium-High |
| Shared State | Mutable globals, singletons, caches | High |
| Domain Glossary | Ambiguous terms → meaning here | Medium |
| Configuration Surface | Every knob that changes behavior | Medium |
| Conventions | Implicit rules as directives | High |
| Gotchas | Counterintuitive behaviors with evidence | Highest |
| Hazards | Files to never read | Medium |
| Extension Points | Where to start for common tasks | High |
| Reading Order | Priority file reading sequence | Medium |
| Gaps | What the document doesn't cover | Low but essential |

## Key Principles

1. **Everything verified** — if you didn't read the code, don't include it
2. **Behavior over structure** — skeletons are in xray output; this doc covers WHAT code does, not HOW it's structured
3. **Gotchas are gold** — a single gotcha can save hours of debugging
4. **Tables over prose** — structured information compresses better
5. **Directives over descriptions** — "Never X" is more actionable than "X is configured to..."
6. **Blast radius for everything** — for every important module, state what breaks if it changes

## Investigation Protocols

The crawl uses 4 specific protocols depending on task type:

### Protocol A: Request Trace
Follow calls from entry point to terminal side effect. Record each hop with behavioral description and error path.

### Protocol B: Module Deep Read
Full read of high-uncertainty module. Produce behavioral summary, preconditions, side effects, and gotchas for every public interface.

### Protocol C: Cross-Cutting Concern
Grep for patterns, categorize, identify dominant strategy, read representative examples, flag deviations.

### Protocol D: Convention Documentation
Read 3-5 examples, state the convention as a directive, assess flagged deviations.

## Crawl Priority Order

1. **Request traces** — highest file-reads saved per output token
2. **High-uncertainty module deep reads** — resolves the most ambiguity
3. **Pillar behavioral summaries** — covers the most important code
4. **Cross-cutting concerns** — "learn once, apply everywhere"
5. **Conventions** — prevents style violations
6. **Gap investigation** — catches what xray missed

## Token Budget Targets

| Codebase Size | Target |
|---------------|--------|
| <100 files | 8-10K tokens |
| 100-500 files | 12-15K tokens |
| 500-2000 files | 15-18K tokens |
| >2000 files | 18-20K tokens |

## Domain Profiles

The crawl adjusts investigation strategy based on detected domain:

| Domain | Extra Investigation | Extra Output |
|--------|--------------------|-|
| Web API | Auth chain, middleware order, rate limiting | Endpoint index, auth trace |
| CLI Tool | Command hierarchy, exit codes, output formats | Command tree |
| ML/AI | Training loop, model loading, data pipeline | Training trace, config surface |
| Data Pipeline | DAG structure, idempotency, failure recovery | Stage documentation |
| Library | Public API surface, extension points, thread safety | API index |

## Resumability

The crawl is checkpointed every 5 tasks. If interrupted:

```bash
@deep_crawl resume
```

This reads CRAWL_PLAN.md (with completion marks) and FINDINGS.md, verifies the git hash hasn't changed, and continues from the last unchecked task.

## Validation

After generating DEEP_ONBOARD.md:

```bash
@deep_onboard_validator full
```

Or the deep_crawl agent runs validation as Phase 5 automatically.

### Quality Bar

| Metric | Target |
|--------|--------|
| Standard questions answerable | ≥9/10 |
| Claims verified accurate | ≥9/10 |
| Adversarial simulation | PASS |
| Redundant tokens | <10% of document |

## Files

```
.claude/
├── agents/
│   ├── deep_crawl.md              # Crawl agent (Opus)
│   └── deep_onboard_validator.md  # Validation agent (Sonnet)
└── skills/
    └── deep-crawl/
        ├── SKILL.md               # This file
        ├── COMMANDS.md            # Quick reference
        ├── configs/
        │   ├── generic_names.json
        │   ├── domain_profiles.json
        │   └── compression_targets.json
        └── templates/
            ├── DEEP_ONBOARD.md.template
            ├── CRAWL_PLAN.md.template
            └── VALIDATION_REPORT.md.template
```

## Relationship to Other Components

```
xray.py (deterministic scan)
   │
   ├── repo_xray agent (quick, interactive, human+AI audience)
   │     └── produces ONBOARD.md
   │
   ├── deep_crawl agent (exhaustive, non-interactive, AI-only audience)
   │     └── produces DEEP_ONBOARD.md
   │
   └── repo_retrospective agent (QA for ONBOARD.md)
         deep_onboard_validator agent (QA for DEEP_ONBOARD.md)
```
````

---

### 15.2. `COMMANDS.md`

**Target path:** `.claude/skills/deep-crawl/COMMANDS.md`

````markdown
# Deep Crawl Commands

## Quick Reference

| Command | What It Does | Duration |
|---------|-------------|----------|
| `@deep_crawl full` | Complete pipeline: plan → crawl → synthesize → compress → validate | 30-120 min |
| `@deep_crawl plan` | Generate investigation plan only | 2-5 min |
| `@deep_crawl resume` | Continue from last checkpoint | Varies |
| `@deep_crawl validate` | QA an existing DEEP_ONBOARD.md | 10-20 min |
| `@deep_crawl refresh` | Update for code changes | 10-60 min |
| `@deep_crawl focus ./path` | Deep crawl a subsystem | 15-45 min |

## Prerequisites

```bash
# Always required: X-Ray scan
python xray.py . --output both --out /tmp/xray
```

## Typical Workflow

```bash
# 1. Scan
python xray.py . --output both --out /tmp/xray

# 2. (Optional) Preview the plan
@deep_crawl plan

# 3. Full crawl
@deep_crawl full

# 4. (Optional) Independent QA
@deep_onboard_validator full

# 5. Output is at ./DEEP_ONBOARD.md
```

## After Code Changes

```bash
# Re-scan
python xray.py . --output both --out /tmp/xray

# Incremental update
@deep_crawl refresh
```
````

---

## 16. Configuration Files

### 16.1. `generic_names.json`

**Target path:** `.claude/skills/deep-crawl/configs/generic_names.json`

```json
{
  "description": "Function names that are ambiguous without context. Functions with these names AND low type coverage AND cross-module callers are flagged for deep investigation.",
  "generic_names": [
    "process", "handle", "run", "execute", "resolve",
    "validate", "transform", "convert", "dispatch", "apply",
    "update", "get", "set", "do", "perform",
    "manage", "build", "create", "make", "generate",
    "parse", "format", "load", "save", "send",
    "check", "verify", "compute", "calculate", "evaluate",
    "init", "setup", "configure", "prepare", "cleanup",
    "start", "stop", "reset", "refresh", "sync",
    "call", "invoke", "emit", "notify", "trigger",
    "wrap", "decorate", "inject", "register", "connect",
    "fetch", "pull", "push", "merge", "split",
    "filter", "map", "reduce", "aggregate", "collect",
    "render", "display", "show", "output", "log"
  ],
  "generic_module_names": [
    "utils", "helpers", "common", "base", "core",
    "misc", "tools", "lib", "shared", "general",
    "service", "handler", "manager", "processor", "worker",
    "engine", "runner", "executor", "dispatcher", "resolver",
    "controller", "adapter", "wrapper", "proxy", "factory"
  ]
}
```

### 16.2. `domain_profiles.json`

**Target path:** `.claude/skills/deep-crawl/configs/domain_profiles.json`

```json
{
  "web_api": {
    "indicators": {
      "frameworks": ["fastapi", "flask", "django", "starlette", "sanic", "tornado"],
      "patterns": ["@app.route", "@router.", "APIRouter", "Blueprint"],
      "directories": ["routes/", "api/", "views/", "endpoints/"]
    },
    "additional_investigation": [
      "Authentication and authorization middleware chain",
      "Request validation pipeline (Pydantic, marshmallow, etc.)",
      "Rate limiting implementation",
      "CORS configuration",
      "Middleware execution order",
      "Database session lifecycle (per-request? connection pool?)",
      "Background task handling (Celery, ARQ, etc.)"
    ],
    "additional_output_sections": [
      "API endpoint index (route → handler → service)",
      "Auth flow trace",
      "Middleware chain with execution order"
    ],
    "primary_entity": "API endpoint",
    "grep_patterns": {
      "auth": "authenticate\\|authorize\\|@login_required\\|Depends.*auth\\|Bearer\\|JWT",
      "middleware": "middleware\\|@app.before\\|@app.after\\|Depends(",
      "rate_limit": "rate_limit\\|throttle\\|RateLimit\\|slowapi"
    }
  },
  "cli_tool": {
    "indicators": {
      "frameworks": ["argparse", "click", "typer", "fire", "cement"],
      "patterns": ["@click.command", "@app.command", "add_argument", "ArgumentParser"],
      "directories": ["commands/", "cli/"]
    },
    "additional_investigation": [
      "Command hierarchy and subcommand structure",
      "Argument parsing and validation",
      "Output formatting strategy (JSON, table, plain text)",
      "Exit code conventions",
      "Interactive vs non-interactive mode handling",
      "Progress reporting for long operations"
    ],
    "additional_output_sections": [
      "Command tree with argument signatures",
      "Output format documentation",
      "Exit code table"
    ],
    "primary_entity": "CLI command",
    "grep_patterns": {
      "commands": "@click\\.command\\|@app\\.command\\|add_subparsers",
      "output": "click\\.echo\\|print(\\|rich\\.print\\|console\\.print",
      "exit_codes": "sys\\.exit\\|exit(\\|raise SystemExit"
    }
  },
  "ml_pipeline": {
    "indicators": {
      "frameworks": ["torch", "tensorflow", "keras", "transformers", "sklearn", "lightning"],
      "patterns": ["nn.Module", "tf.keras.Model", "model.fit", "model.train"],
      "directories": ["models/", "training/", "data/", "experiments/"]
    },
    "additional_investigation": [
      "Training loop structure and hooks",
      "Model architecture definition location",
      "Data loading and preprocessing pipeline",
      "Checkpoint save/load conventions",
      "Evaluation metrics implementation",
      "Hyperparameter configuration surface",
      "GPU/device management",
      "Experiment tracking integration"
    ],
    "additional_output_sections": [
      "Training pipeline trace (data → preprocessing → model → loss → optimizer)",
      "Model configuration surface",
      "Data flow from raw input to model input"
    ],
    "primary_entity": "model or training experiment",
    "grep_patterns": {
      "training": "def train\\|model\\.train\\|trainer\\.fit",
      "data": "DataLoader\\|Dataset\\|dataloader\\|batch_size",
      "checkpoint": "save_checkpoint\\|load_checkpoint\\|torch\\.save\\|torch\\.load"
    }
  },
  "data_pipeline": {
    "indicators": {
      "frameworks": ["airflow", "dagster", "prefect", "luigi", "dbt", "beam"],
      "patterns": ["@dag", "@task", "PythonOperator", "@op", "@asset"],
      "directories": ["dags/", "pipelines/", "etl/", "jobs/"]
    },
    "additional_investigation": [
      "DAG structure and stage dependencies",
      "Idempotency guarantees (can re-run safely?)",
      "Failure recovery and retry strategy",
      "Data validation between stages",
      "Scheduling configuration",
      "Backfill strategy",
      "Data partitioning approach"
    ],
    "additional_output_sections": [
      "DAG/pipeline stage documentation",
      "Stage-by-stage data transformation description",
      "Failure recovery procedures"
    ],
    "primary_entity": "pipeline stage or DAG",
    "grep_patterns": {
      "stages": "@task\\|@op\\|PythonOperator\\|@asset",
      "retry": "retries\\|retry_delay\\|on_failure",
      "scheduling": "schedule_interval\\|cron\\|schedule("
    }
  },
  "library": {
    "indicators": {
      "frameworks": [],
      "patterns": ["__all__", "setup.py", "pyproject.toml"],
      "directories": ["src/", "lib/"]
    },
    "additional_investigation": [
      "Public API surface (what's exported via __all__ or top-level imports)",
      "Backward compatibility constraints",
      "Extension/plugin mechanisms",
      "Thread safety guarantees",
      "Performance-critical code paths",
      "Deprecation patterns"
    ],
    "additional_output_sections": [
      "Public API index with behavioral descriptions",
      "Extension point documentation",
      "Thread safety annotations"
    ],
    "primary_entity": "public API function or class",
    "grep_patterns": {
      "public_api": "__all__\\|from.*import.*\\*",
      "deprecation": "deprecated\\|DeprecationWarning\\|warnings\\.warn",
      "thread_safety": "Lock\\|RLock\\|threading\\|asyncio\\.Lock"
    }
  }
}
```

### 16.3. `compression_targets.json`

**Target path:** `.claude/skills/deep-crawl/configs/compression_targets.json`

```json
{
  "description": "Token budget targets for DEEP_ONBOARD.md by codebase size. The document should be within the target range. Exceeding the max is a compression failure.",
  "targets": [
    {
      "max_files": 100,
      "label": "small",
      "min_tokens": 6000,
      "target_tokens": 8000,
      "max_tokens": 10000
    },
    {
      "max_files": 500,
      "label": "medium",
      "min_tokens": 10000,
      "target_tokens": 13000,
      "max_tokens": 15000
    },
    {
      "max_files": 2000,
      "label": "large",
      "min_tokens": 13000,
      "target_tokens": 16000,
      "max_tokens": 18000
    },
    {
      "max_files": 999999,
      "label": "very_large",
      "min_tokens": 15000,
      "target_tokens": 18000,
      "max_tokens": 20000
    }
  ],
  "section_budgets": {
    "identity": { "max_tokens": 200, "priority": "required" },
    "critical_paths": { "max_tokens": 3000, "priority": "required" },
    "module_behavioral_index": { "max_tokens": 4000, "priority": "required" },
    "error_handling": { "max_tokens": 1000, "priority": "required" },
    "shared_state": { "max_tokens": 800, "priority": "required" },
    "domain_glossary": { "max_tokens": 600, "priority": "recommended" },
    "config_surface": { "max_tokens": 1000, "priority": "required" },
    "conventions": { "max_tokens": 800, "priority": "required" },
    "gotchas": { "max_tokens": 1500, "priority": "required" },
    "hazards": { "max_tokens": 500, "priority": "required" },
    "extension_points": { "max_tokens": 800, "priority": "recommended" },
    "reading_order": { "max_tokens": 400, "priority": "recommended" },
    "gaps": { "max_tokens": 300, "priority": "required" }
  }
}
```

---

## 17. Templates

### 17.1. `DEEP_ONBOARD.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

````markdown
# {PROJECT_NAME}: Agent Onboarding

> Codebase: {FILE_COUNT} files, ~{TOTAL_TOKENS} tokens
> This document: ~{DOC_TOKENS} tokens
> Generated: {TIMESTAMP} from commit `{GIT_HASH}`
> Crawl: {TASKS_COMPLETED}/{TASKS_PLANNED} tasks, {MODULES_READ} modules read
> For class signatures and skeletons, see: xray output at `/tmp/xray/xray.md`

---

## Identity

<!-- AGENT: 1-3 sentences. What is this, what does it do, what's the stack. No filler. -->

{IDENTITY}

---

## Critical Paths

<!-- AGENT: For each major entry point, show the verified call chain from entry
to terminal side effect. Include behavioral description at each hop and error path.
This section has the highest file-reads-saved-per-token ratio.
Budget: ~3000 tokens. Prioritize the 3-5 most important paths. -->

### {PATH_1_NAME}

```
{ENTRY} ({file}:{line})
  → {FUNC} ({file}:{line}) — {what it does}
    → {FUNC} ({file}:{line}) — {what it does}
      → [{SIDE_EFFECT}] ({file}:{line})
  ✗ on failure: {what happens}
```

<!-- Repeat for 3-5 critical paths -->

---

## Module Behavioral Index

<!-- AGENT: For every architecturally significant module, provide a behavioral summary.
NOT the signature — that's in xray output. This is WHAT it does, what depends on it,
and what's dangerous about it. Use a table for density.
Budget: ~4000 tokens. -->

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `{path}` | {1-sentence behavior} | {what it needs at runtime} | {gotcha or "—"} |

<!-- Include 15-30 modules for medium codebases, 30-50 for large -->

---

## Error Handling Strategy

<!-- AGENT: Identify the dominant error handling pattern and flag deviations.
This applies to every modification the downstream agent makes.
Budget: ~1000 tokens. -->

**Dominant pattern:** {description — e.g., "try/except at service boundaries, log + reraise as domain exceptions, swallow at API layer and return error response"}

**Retry strategy:** {description or "none detected"}

**Deviations:**

| Module | Pattern | Risk |
|--------|---------|------|
| `{path}` | {how it differs} | {what could go wrong} |

---

## Shared State

<!-- AGENT: Every module-level mutable, singleton, cache, or registry.
These cause action-at-a-distance bugs. Miss one and the downstream agent
will introduce a concurrency bug.
Budget: ~800 tokens. -->

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `{name}` | `{file}:{line}` | `{functions}` | {description} |

---

## Domain Glossary

<!-- AGENT: Map of terms that mean something specific in THIS codebase.
Only include terms that are ambiguous or overloaded. Skip "User", "Database", etc.
Budget: ~600 tokens. -->

| Term | Means Here | Defined In |
|------|------------|------------|
| {term} | {codebase-specific meaning} | `{file}` |

---

## Configuration Surface

<!-- AGENT: Every knob that changes runtime behavior.
Downstream agents need this to understand why code behaves differently in different environments.
Budget: ~1000 tokens. -->

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `{name}` | {env/file/flag} | {what behavior changes} | `{value}` |

---

## Conventions

<!-- AGENT: The implicit rules. Write as directives: "Always X", "Never Y".
These prevent the downstream agent from writing code that works but violates project norms.
Budget: ~800 tokens. -->

1. {Convention as directive — 1 sentence}
2. {Convention as directive — 1 sentence}

---

## Gotchas

<!-- AGENT: Counterintuitive behaviors. Ordered by likelihood of causing a bug.
Every gotcha must cite file:line evidence.
This section has the highest value per token alongside Critical Paths.
Budget: ~1500 tokens. -->

1. **{title}** — {description} (`{file}:{line}`)
2. **{title}** — {description} (`{file}:{line}`)

---

## Hazards — Do Not Read

<!-- AGENT: Files that waste context. Include glob patterns for easy exclusion.
Budget: ~500 tokens. -->

| Pattern | Tokens | Why |
|---------|--------|-----|
| `{glob}` | ~{N}K | {reason} |

---

## Extension Points

<!-- AGENT: Where to start for common modification tasks.
Only include tasks that are non-obvious.
Budget: ~800 tokens. -->

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| {common task} | `{file}` | `{files}` | {gotcha} |

---

## Reading Order

<!-- AGENT: If the downstream agent needs to go deeper, read in this order.
Ranked by information-per-token, not by importance.
Budget: ~400 tokens. -->

1. `{file}` — {what you learn by reading this}
2. `{file}` — {what you learn}
3. `{file}` — {what you learn}

**Skip:** `{file}` ({why}), `{file}` ({why})

---

## Gaps

<!-- AGENT: What this document doesn't cover. Be specific.
The downstream agent needs to know when to investigate further.
Budget: ~300 tokens. -->

- {specific gap — e.g., "Migration strategy unclear — Alembic exists but rollback procedures not investigated"}
- {specific gap}

---

*Generated by deep_crawl agent. {TASKS_COMPLETED} investigation tasks,
{MODULES_READ} modules read, {TRACES_VERIFIED} traces verified.
Compression: {TOTAL_TOKENS} → {DOC_TOKENS} tokens ({COMPRESSION_RATIO}:1).*
````

### 17.2. `CRAWL_PLAN.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template`

````markdown
# Deep Crawl Plan: {PROJECT_NAME}

> Domain: {DETECTED_DOMAIN}
> Codebase: {FILE_COUNT} files, ~{TOTAL_TOKENS} tokens
> X-Ray scan: {XRAY_TIMESTAMP}
> Plan generated: {TIMESTAMP}
> Git commit: {GIT_HASH}

---

## Priority 1: Request Traces ({COUNT} tasks)

<!-- Trace from each entry point to terminal side effects.
Highest value: each trace saves 3-5 downstream file reads. -->

- [ ] {ENTRY_POINT} → {TERMINAL_SIDE_EFFECTS} (est. {HOP_COUNT} hops)

## Priority 2: High-Uncertainty Module Deep Reads ({COUNT} tasks)

<!-- Modules where name + signature don't tell the story.
Ordered by uncertainty score descending. -->

- [ ] `{MODULE_PATH}` — uncertainty {SCORE}: {REASONS}

## Priority 3: Pillar Behavioral Summaries ({COUNT} tasks)

<!-- Top architectural pillars from xray.
Read and produce behavioral summary for each. -->

- [ ] `{MODULE_PATH}` — pillar #{RANK}, {CALLERS} cross-module callers

## Priority 4: Cross-Cutting Concerns ({COUNT} tasks)

<!-- These apply to every modification. Investigate exhaustively. -->

- [ ] Error handling strategy
- [ ] Configuration surface
- [ ] Shared mutable state verification

<!-- Domain-specific additions: -->
{DOMAIN_SPECIFIC_TASKS}

## Priority 5: Conventions and Patterns ({COUNT} tasks)

- [ ] Identify dominant coding conventions (3-5 examples each)
- [ ] Assess {DEVIATION_COUNT} flagged convention deviations
- [ ] Investigate {COUPLING_COUNT} coupling anomalies

## Priority 6: Gap Investigation ({COUNT} tasks)

- [ ] Implicit initialization sequences
- [ ] Undocumented environment dependencies
- [ ] Hidden coupling not captured by import analysis
- [ ] {DOMAIN_SPECIFIC_GAPS}

---

## Completion Criteria

Stop crawling when ALL are true:
- [x] All Priority 1 tasks complete
- [x] All Priority 2 tasks complete
- [x] All Priority 4 tasks complete
- [x] Can answer all 10 standard questions from findings
- [x] Last 3 tasks surfaced no new gotchas

## Progress

| Priority | Total | Done | Remaining |
|----------|-------|------|-----------|
| 1: Traces | {N} | {N} | {N} |
| 2: Uncertainty | {N} | {N} | {N} |
| 3: Pillars | {N} | {N} | {N} |
| 4: Cross-cutting | {N} | {N} | {N} |
| 5: Conventions | {N} | {N} | {N} |
| 6: Gaps | {N} | {N} | {N} |
| **Total** | **{N}** | **{N}** | **{N}** |

Last checkpoint: {TIMESTAMP}
````

### 17.3. `VALIDATION_REPORT.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/VALIDATION_REPORT.md.template`

````markdown
# DEEP_ONBOARD Validation Report

> Document: {DOCUMENT_PATH}
> Validated: {TIMESTAMP}
> Codebase HEAD: {CURRENT_GIT_HASH}
> Document from: {DOC_GIT_HASH}

---

## Verdict: {PASS | NEEDS FIXES | NEEDS REWORK}

---

## Check 1: Completeness ({SCORE}/10)

| # | Question | Result | Detail |
|---|----------|--------|--------|
| Q1 | What does this codebase do? | {PASS/PARTIAL/FAIL} | {detail} |
| Q2 | Where does a request enter? | {PASS/PARTIAL/FAIL} | {detail} |
| Q3 | Critical path input → output? | {PASS/PARTIAL/FAIL} | {detail} |
| Q4 | Files to never read? | {PASS/PARTIAL/FAIL} | {detail} |
| Q5 | What happens on failure? | {PASS/PARTIAL/FAIL} | {detail} |
| Q6 | External systems? | {PASS/PARTIAL/FAIL} | {detail} |
| Q7 | Shared state risks? | {PASS/PARTIAL/FAIL} | {detail} |
| Q8 | Testing conventions? | {PASS/PARTIAL/FAIL} | {detail} |
| Q9 | Top 3 counterintuitive things? | {PASS/PARTIAL/FAIL} | {detail} |
| Q10 | Where to start adding new entity? | {PASS/PARTIAL/FAIL} | {detail} |

## Check 2: Accuracy ({CONFIRMED}/{TOTAL} confirmed)

| # | Claim | Referenced Location | Result | Detail |
|---|-------|-------------------|--------|--------|
| 1 | {claim} | `{file}:{line}` | {CONFIRMED/INACCURATE/STALE} | {detail} |

## Check 3: Coverage

**X-Ray pillars covered:** {N}/{TOTAL} ({PERCENT}%)
**Entry points with traces:** {N}/{TOTAL} ({PERCENT}%)
**Side effect types documented:** {N}/{TOTAL}

### Notable Omissions
{OMISSIONS_OR_NONE}

## Check 4: Redundancy

| Section | ~Tokens | Redundant? | Reason |
|---------|---------|------------|--------|
| {section} | {N} | {YES/NO} | {reason} |

**Estimated wasted tokens:** ~{TOTAL}

## Check 5: Adversarial Simulation

**Task:** {SIMULATED_TASK}
**Using only the document, agent would:**
1. {step}
2. {step}

**Would agent succeed?** {YES / NO / PARTIAL}
**Gap found:** {DESCRIPTION_OR_NONE}

## Check 6: Freshness

| Metric | Value |
|--------|-------|
| Document commit | `{DOC_HASH}` |
| Current HEAD | `{CURRENT_HASH}` |
| Commits behind | {N} |
| Changed files mentioned in doc | {N} |

{FRESHNESS_DETAIL}

---

## Recommended Fixes

<!-- Ordered by impact: fixes that prevent incorrect agent behavior first -->

1. **{PRIORITY}** — {fix description}
2. **{PRIORITY}** — {fix description}

---

## Summary Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Completeness | {N}/10 | ≥9 | {PASS/FAIL} |
| Accuracy | {N}/10 | ≥9 | {PASS/FAIL} |
| Pillar coverage | {N}% | ≥80% | {PASS/FAIL} |
| Entry point coverage | {N}% | ≥80% | {PASS/FAIL} |
| Redundant tokens | ~{N} | <10% | {PASS/FAIL} |
| Adversarial test | {RESULT} | PASS | {PASS/FAIL} |
| Freshness | {STATUS} | CURRENT | {PASS/FAIL} |
````

---

## 18. Implementation Skeleton: `investigation_targets.py`

**Target path:** `lib/investigation_targets.py`

This is the implementation skeleton for the new xray module. Each function takes existing analysis results and computes investigation signals.

```python
"""
Repo X-Ray: Investigation Targets

Computes prioritized investigation signals for the deep_crawl agent.
All analysis is deterministic and derived from existing xray results.

Usage:
    from investigation_targets import compute_investigation_targets

    targets = compute_investigation_targets(
        ast_results=ast_results,
        import_results=import_results,
        call_results=call_results,
        git_results=git_results,
        gap_results=gap_results,
        root_dir="."
    )
"""

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# Configuration
# =============================================================================

# Load generic names from config if available, else use defaults
_DEFAULT_GENERIC_NAMES = {
    "process", "handle", "run", "execute", "resolve",
    "validate", "transform", "convert", "dispatch", "apply",
    "update", "get", "set", "do", "perform",
    "manage", "build", "create", "make", "generate",
    "parse", "format", "load", "save", "send",
    "check", "verify", "compute", "calculate", "evaluate",
    "init", "setup", "configure", "prepare", "cleanup",
    "start", "stop", "reset", "refresh", "sync",
    "call", "invoke", "emit", "notify", "trigger",
    "wrap", "decorate", "inject", "register", "connect",
    "fetch", "pull", "push", "merge", "split",
    "filter", "map", "reduce", "aggregate", "collect",
}

_DEFAULT_GENERIC_MODULE_NAMES = {
    "utils", "helpers", "common", "base", "core",
    "misc", "tools", "lib", "shared", "general",
    "service", "handler", "manager", "processor", "worker",
    "engine", "runner", "executor", "dispatcher", "resolver",
}


def _load_generic_names(config_dir: str = "configs") -> Tuple[Set[str], Set[str]]:
    """Load generic name lists from config file or use defaults."""
    config_path = os.path.join(config_dir, "generic_names.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                set(data.get("generic_names", _DEFAULT_GENERIC_NAMES)),
                set(data.get("generic_module_names", _DEFAULT_GENERIC_MODULE_NAMES)),
            )
        except (json.JSONDecodeError, IOError):
            pass
    return _DEFAULT_GENERIC_NAMES, _DEFAULT_GENERIC_MODULE_NAMES


# =============================================================================
# Ambiguous Interfaces
# =============================================================================

def compute_ambiguous_interfaces(
    ast_results: Dict[str, Any],
    call_results: Dict[str, Any],
    generic_names: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Find functions whose names are generic and whose signatures lack
    sufficient type information for a downstream agent to understand
    their behavior without reading the source.

    Scoring: (cross_module_callers * cc) / max(type_coverage, 0.1)
    Higher score = more ambiguous = higher investigation priority.
    """
    if generic_names is None:
        generic_names, _ = _load_generic_names()

    ambiguous = []
    files = ast_results.get("files", {})
    cross_module = call_results.get("cross_module", {})

    for filepath, file_data in files.items():
        # Check top-level functions
        for func in file_data.get("functions", []):
            _assess_function_ambiguity(
                func, filepath, file_data, cross_module, generic_names, ambiguous
            )

        # Check class methods
        for cls in file_data.get("classes", []):
            for method in cls.get("methods", []):
                _assess_function_ambiguity(
                    method, filepath, file_data, cross_module, generic_names, ambiguous,
                    class_name=cls.get("name")
                )

    # Sort by ambiguity score descending
    ambiguous.sort(key=lambda x: x.get("ambiguity_score", 0), reverse=True)
    return ambiguous[:30]  # Top 30


def _assess_function_ambiguity(
    func: Dict, filepath: str, file_data: Dict,
    cross_module: Dict, generic_names: Set[str],
    results: List, class_name: Optional[str] = None
) -> None:
    """Assess a single function for ambiguity and append to results if flagged."""
    name = func.get("name", "")
    base_name = name.split(".")[-1] if "." in name else name

    # Skip private/dunder methods
    if base_name.startswith("_"):
        return

    is_generic = base_name.lower() in generic_names

    # Calculate type coverage for this function
    params = func.get("params", [])
    typed_params = sum(1 for p in params if p.get("type") and p.get("type") != "...")
    total_params = max(len(params), 1)
    has_return_type = bool(func.get("return_type")) and func.get("return_type") != "..."
    type_coverage = (typed_params + (1 if has_return_type else 0)) / (total_params + 1)

    # Count cross-module callers
    module_name = Path(filepath).stem
    qualified_names = [
        f"{module_name}.{name}",
        name,
    ]
    if class_name:
        qualified_names.append(f"{class_name}.{name}")
        qualified_names.append(f"{module_name}.{class_name}.{name}")

    caller_count = 0
    for qname in qualified_names:
        if qname in cross_module:
            caller_count = max(caller_count, cross_module[qname].get("call_count", 0))

    # Only flag if: generic name OR (low type coverage AND has cross-module callers)
    if not is_generic and (type_coverage >= 0.5 or caller_count < 2):
        return

    cc = func.get("complexity", func.get("cc", 1))
    ambiguity_score = (max(caller_count, 1) * max(cc, 1)) / max(type_coverage, 0.1)

    results.append({
        "function": name,
        "class": class_name,
        "file": filepath,
        "line": func.get("start_line", 0),
        "reason": "generic_name" if is_generic else "low_type_coverage",
        "type_coverage": round(type_coverage, 2),
        "cc": cc,
        "cross_module_callers": caller_count,
        "ambiguity_score": round(ambiguity_score, 1),
    })


# =============================================================================
# Entry-to-Side-Effect Paths
# =============================================================================

def compute_entry_side_effect_paths(
    ast_results: Dict[str, Any],
    call_results: Dict[str, Any],
    gap_results: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    For each detected entry point, walk the call graph to find reachable
    side effects. Returns a list of paths with estimated hop counts.

    This gives the deep_crawl agent a roadmap: "trace from here to here."
    """
    entry_points = gap_results.get("entry_points", [])
    cross_module = call_results.get("cross_module", {})
    files = ast_results.get("files", {})

    # Collect all side effects by file
    side_effects_by_file = defaultdict(list)
    for filepath, file_data in files.items():
        for se in file_data.get("side_effects", []):
            side_effects_by_file[filepath].append(se)

    # Build a simplified call graph: caller_module -> set of callee_modules
    call_graph = defaultdict(set)
    for func_name, data in cross_module.items():
        for site in data.get("call_sites", []):
            caller_module = Path(site.get("file", "")).stem
            callee_module = Path(func_name.split(".")[0]).stem if "." in func_name else func_name
            if caller_module != callee_module:
                call_graph[caller_module].add(callee_module)

    paths = []
    for ep in entry_points:
        ep_file = ep.get("file", "")
        ep_module = Path(ep_file).stem

        # BFS to find reachable side effects
        visited = set()
        queue = [(ep_module, 0)]
        reachable_effects = []
        max_hops = 0

        while queue:
            module, hops = queue.pop(0)
            if module in visited or hops > 8:
                continue
            visited.add(module)
            max_hops = max(max_hops, hops)

            # Check for side effects in this module
            for filepath, effects in side_effects_by_file.items():
                if Path(filepath).stem == module:
                    for se in effects:
                        reachable_effects.append({
                            "type": se.get("type", "unknown"),
                            "location": f"{filepath}:{se.get('line', 0)}",
                            "pattern": se.get("pattern", se.get("call", "")),
                            "hops_from_entry": hops,
                        })

            # Follow call graph edges
            for callee in call_graph.get(module, set()):
                if callee not in visited:
                    queue.append((callee, hops + 1))

        if reachable_effects:
            paths.append({
                "entry_point": f"{ep_file}:{ep.get('entry_point', '')}",
                "entry_type": ep.get("type", "unknown"),
                "reachable_side_effects": reachable_effects[:10],
                "estimated_hop_count": max_hops,
                "modules_traversed": len(visited),
            })

    # Sort by hop count descending (longer traces = more value)
    paths.sort(key=lambda x: x["estimated_hop_count"], reverse=True)
    return paths[:10]


# =============================================================================
# Coupling Anomalies
# =============================================================================

def compute_coupling_anomalies(
    git_results: Dict[str, Any],
    import_results: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Find file pairs that are frequently co-modified but have no import
    relationship. These represent hidden coupling.
    """
    coupling = git_results.get("coupling", [])
    import_graph = import_results.get("graph", {})

    anomalies = []
    for pair in coupling:
        file_a = pair.get("file_a", pair.get("files", ["", ""])[0] if isinstance(pair.get("files"), list) else "")
        file_b = pair.get("file_b", pair.get("files", ["", ""])[1] if isinstance(pair.get("files"), list) else "")
        score = pair.get("score", pair.get("confidence", 0))

        if not file_a or not file_b or score < 0.7:
            continue

        # Check import relationship
        mod_a = Path(file_a).stem
        mod_b = Path(file_b).stem
        a_imports = set(import_graph.get(mod_a, {}).get("imports", []))
        b_imports = set(import_graph.get(mod_b, {}).get("imports", []))

        has_import = mod_b in a_imports or mod_a in b_imports

        if not has_import:
            anomalies.append({
                "files": [file_a, file_b],
                "co_modification_score": round(score, 2),
                "has_import_relationship": False,
                "reason": "co_modified_without_imports",
            })

    anomalies.sort(key=lambda x: x["co_modification_score"], reverse=True)
    return anomalies[:10]


# =============================================================================
# Convention Deviations
# =============================================================================

def compute_convention_deviations(
    ast_results: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Detect dominant coding patterns and flag outliers.

    Checks:
    - Class __init__ signature patterns (config injection, no-arg, etc.)
    - Decorator usage consistency
    - Module-level structure patterns
    """
    files = ast_results.get("files", {})
    deviations = []

    # Analyze class __init__ patterns
    init_patterns = defaultdict(list)  # pattern -> [class_info]

    for filepath, file_data in files.items():
        for cls in file_data.get("classes", []):
            init_method = None
            for method in cls.get("methods", []):
                if method.get("name") == "__init__":
                    init_method = method
                    break

            if init_method:
                params = init_method.get("params", [])
                # Classify the pattern
                non_self_params = [p for p in params if p.get("name") != "self"]
                has_typed_params = any(p.get("type") for p in non_self_params)

                if len(non_self_params) == 0:
                    pattern = "no_args"
                elif has_typed_params:
                    pattern = "typed_injection"
                else:
                    pattern = "untyped_args"

                init_patterns[pattern].append({
                    "class": cls["name"],
                    "file": filepath,
                    "line": cls.get("start_line", 0),
                    "param_count": len(non_self_params),
                })

    # Find the dominant pattern and flag deviations
    if init_patterns:
        dominant = max(init_patterns.items(), key=lambda x: len(x[1]))
        dominant_pattern = dominant[0]
        dominant_count = len(dominant[1])

        for pattern, classes in init_patterns.items():
            if pattern != dominant_pattern and len(classes) <= dominant_count * 0.3:
                deviations.append({
                    "convention": f"class_init_{dominant_pattern}",
                    "conforming_count": dominant_count,
                    "violating": [
                        {
                            "class": c["class"],
                            "file": c["file"],
                            "line": c["line"],
                            "actual_pattern": pattern,
                        }
                        for c in classes
                    ],
                })

    return deviations[:10]


# =============================================================================
# Shared Mutable State
# =============================================================================

def compute_shared_mutable_state(
    ast_results: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Find module-level variables that are mutated at runtime.

    Detects:
    - Module-level assignments that are later mutated
    - Singleton patterns (_instance = None with get_instance)
    - Global registries (module-level dicts/lists that get appended to)
    """
    import ast as ast_module

    files = ast_results.get("files", {})
    shared_state = []

    for filepath, file_data in files.items():
        # We need to re-parse for this analysis since ast_results
        # doesn't capture module-level mutation patterns
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast_module.parse(source)
        except (IOError, SyntaxError):
            continue

        # Find module-level assignments (not inside functions/classes)
        module_vars = {}
        for node in ast_module.iter_child_nodes(tree):
            if isinstance(node, ast_module.Assign):
                for target in node.targets:
                    if isinstance(target, ast_module.Name):
                        name = target.id
                        # Skip constants (ALL_CAPS) and private imports
                        if name.isupper() or name.startswith("__"):
                            continue
                        module_vars[name] = {
                            "name": name,
                            "line": node.lineno,
                            "file": filepath,
                        }

        if not module_vars:
            continue

        # Check if any module var is mutated inside functions
        for node in ast_module.walk(tree):
            if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
                for child in ast_module.walk(node):
                    # Check for augmented assignment: var += X
                    if isinstance(child, ast_module.AugAssign):
                        if isinstance(child.target, ast_module.Name):
                            if child.target.id in module_vars:
                                var = module_vars[child.target.id]
                                var["mutated"] = True
                                var.setdefault("mutated_by", []).append(
                                    f"{filepath}:{node.name}"
                                )

                    # Check for method calls on var: var.append(), var.update(), etc.
                    if isinstance(child, ast_module.Call):
                        if isinstance(child.func, ast_module.Attribute):
                            if isinstance(child.func.value, ast_module.Name):
                                if child.func.value.id in module_vars:
                                    method = child.func.attr
                                    if method in {"append", "extend", "update", "clear",
                                                   "pop", "remove", "add", "discard",
                                                   "insert", "setdefault"}:
                                        var = module_vars[child.func.value.id]
                                        var["mutated"] = True
                                        var.setdefault("mutated_by", []).append(
                                            f"{filepath}:{node.name}"
                                        )

                    # Check for subscript assignment: var[key] = X
                    if isinstance(child, ast_module.Assign):
                        for target in child.targets:
                            if isinstance(target, ast_module.Subscript):
                                if isinstance(target.value, ast_module.Name):
                                    if target.value.id in module_vars:
                                        var = module_vars[target.value.id]
                                        var["mutated"] = True
                                        var.setdefault("mutated_by", []).append(
                                            f"{filepath}:{node.name}"
                                        )

        # Collect mutated vars
        for name, var in module_vars.items():
            if var.get("mutated"):
                mutated_by = list(set(var.get("mutated_by", [])))
                shared_state.append({
                    "variable": name,
                    "file": filepath,
                    "line": var["line"],
                    "scope": "module",
                    "mutated_by": mutated_by[:5],
                    "risk": "concurrent_modification" if len(mutated_by) > 1 else "hidden_state",
                })

    shared_state.sort(key=lambda x: len(x.get("mutated_by", [])), reverse=True)
    return shared_state[:20]


# =============================================================================
# High Uncertainty Modules
# =============================================================================

def compute_high_uncertainty_modules(
    ast_results: Dict[str, Any],
    call_results: Dict[str, Any],
    generic_module_names: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Compute composite uncertainty score for each module.

    Modules with high uncertainty are where the deep_crawl agent should
    spend its reading budget — the name and signature alone don't tell
    the story.
    """
    if generic_module_names is None:
        _, generic_module_names = _load_generic_names()

    files = ast_results.get("files", {})
    cross_module = call_results.get("cross_module", {})

    # Compute fan-in per module
    fan_in = defaultdict(int)
    for func_name, data in cross_module.items():
        module = func_name.split(".")[0] if "." in func_name else ""
        fan_in[module] += data.get("call_count", 0)

    results = []
    for filepath, file_data in files.items():
        module_name = Path(filepath).stem
        reasons = []
        score = 0.0

        # Generic name check
        if module_name.lower() in generic_module_names:
            reasons.append("generic_name")
            score += 1.0

        # Type coverage check
        type_data = file_data.get("type_coverage", {})
        coverage = type_data.get("coverage_percent", 0) / 100.0
        if coverage < 0.3:
            reasons.append("low_type_coverage")
            score += 1.0
        elif coverage < 0.6:
            reasons.append("moderate_type_coverage")
            score += 0.5

        # Fan-in check
        module_fan_in = fan_in.get(module_name, 0)
        if module_fan_in >= 5:
            reasons.append("high_fan_in")
            score += 1.0
        elif module_fan_in >= 3:
            reasons.append("moderate_fan_in")
            score += 0.5

        # Docstring check (approximate: check if classes/functions have docstrings)
        has_docstrings = False
        for cls in file_data.get("classes", []):
            if cls.get("docstring"):
                has_docstrings = True
                break
        for func in file_data.get("functions", []):
            if func.get("docstring"):
                has_docstrings = True
                break
        if not has_docstrings:
            reasons.append("no_docstrings")
            score += 1.0

        # High complexity check
        hotspots = file_data.get("complexity", {}).get("hotspots", {})
        max_cc = max(hotspots.values()) if hotspots else 0
        if max_cc > 15:
            reasons.append("high_complexity")
            score += 1.0

        # kwargs check
        has_kwargs = False
        for func in file_data.get("functions", []):
            if not func.get("name", "").startswith("_"):
                for param in func.get("params", []):
                    if param.get("name") == "**kwargs" or param.get("name", "").startswith("**"):
                        has_kwargs = True
                        break
        if has_kwargs:
            reasons.append("has_kwargs")
            score += 0.5

        # Normalize
        normalized_score = score / 6.0

        if normalized_score >= 0.3 and reasons:
            results.append({
                "module": filepath,
                "reasons": reasons,
                "uncertainty_score": round(normalized_score, 2),
                "fan_in": module_fan_in,
                "type_coverage": round(coverage, 2),
                "max_cc": max_cc,
            })

    results.sort(key=lambda x: x["uncertainty_score"], reverse=True)
    return results[:20]


# =============================================================================
# Domain Entities
# =============================================================================

def compute_domain_entities(
    ast_results: Dict[str, Any],
    gap_results: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract domain-specific entities: Pydantic models, dataclasses,
    TypedDicts, and classes referenced in type annotations across 3+ modules.
    """
    # Start with data models already extracted by gap_features
    data_models = gap_results.get("data_models", [])

    entities = []
    seen = set()

    for model in data_models:
        name = model.get("name", "")
        if name and name not in seen:
            seen.add(name)
            entities.append({
                "name": name,
                "type": model.get("type", "class"),
                "file": model.get("file", ""),
                "line": model.get("line", 0),
                "fields": model.get("fields", [])[:5],  # Top 5 fields
            })

    # Also find classes used in type annotations across 3+ files
    files = ast_results.get("files", {})
    type_references = defaultdict(set)  # class_name -> set of files

    for filepath, file_data in files.items():
        for func in file_data.get("functions", []):
            for param in func.get("params", []):
                type_name = param.get("type", "")
                if type_name and type_name not in {"str", "int", "float", "bool",
                                                     "list", "dict", "set", "tuple",
                                                     "None", "Any", "Optional", "..."}:
                    # Extract base type name (strip Optional[], List[], etc.)
                    base = type_name.split("[")[0].split(".")[-1]
                    if base and base[0].isupper():
                        type_references[base].add(filepath)

            ret_type = func.get("return_type", "")
            if ret_type:
                base = ret_type.split("[")[0].split(".")[-1]
                if base and base[0].isupper() and base not in {"Optional", "List", "Dict", "Set", "Tuple"}:
                    type_references[base].add(filepath)

    for name, referenced_in in type_references.items():
        if len(referenced_in) >= 3 and name not in seen:
            seen.add(name)
            entities.append({
                "name": name,
                "type": "type_annotation_entity",
                "file": "",  # Would need a separate lookup to find definition
                "line": 0,
                "referenced_in": sorted(list(referenced_in))[:5],
            })

    entities.sort(key=lambda x: len(x.get("referenced_in", x.get("fields", []))), reverse=True)
    return entities[:20]


# =============================================================================
# Master Function
# =============================================================================

def compute_investigation_targets(
    ast_results: Dict[str, Any],
    import_results: Dict[str, Any],
    call_results: Dict[str, Any],
    git_results: Dict[str, Any],
    gap_results: Dict[str, Any],
    root_dir: str = ".",
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Compute all investigation targets from existing xray analysis results.

    Returns a dict suitable for inclusion in xray JSON output.
    """
    import sys

    if verbose:
        print("Computing investigation targets...", file=sys.stderr)

    targets = {}

    if verbose:
        print("  Ambiguous interfaces...", file=sys.stderr)
    targets["ambiguous_interfaces"] = compute_ambiguous_interfaces(ast_results, call_results)

    if verbose:
        print("  Entry-to-side-effect paths...", file=sys.stderr)
    targets["entry_to_side_effect_paths"] = compute_entry_side_effect_paths(
        ast_results, call_results, gap_results
    )

    if verbose:
        print("  Coupling anomalies...", file=sys.stderr)
    targets["coupling_anomalies"] = compute_coupling_anomalies(git_results, import_results)

    if verbose:
        print("  Convention deviations...", file=sys.stderr)
    targets["convention_deviations"] = compute_convention_deviations(ast_results)

    if verbose:
        print("  Shared mutable state...", file=sys.stderr)
    targets["shared_mutable_state"] = compute_shared_mutable_state(ast_results)

    if verbose:
        print("  High uncertainty modules...", file=sys.stderr)
    targets["high_uncertainty_modules"] = compute_high_uncertainty_modules(
        ast_results, call_results
    )

    if verbose:
        print("  Domain entities...", file=sys.stderr)
    targets["domain_entities"] = compute_domain_entities(ast_results, gap_results)

    # Summary stats
    targets["summary"] = {
        "ambiguous_interfaces": len(targets["ambiguous_interfaces"]),
        "entry_paths": len(targets["entry_to_side_effect_paths"]),
        "coupling_anomalies": len(targets["coupling_anomalies"]),
        "convention_deviations": sum(
            len(d.get("violating", []))
            for d in targets["convention_deviations"]
        ),
        "shared_mutable_state": len(targets["shared_mutable_state"]),
        "high_uncertainty_modules": len(targets["high_uncertainty_modules"]),
        "domain_entities": len(targets["domain_entities"]),
    }

    if verbose:
        print(f"  Investigation targets computed: {targets['summary']}", file=sys.stderr)

    return targets
```

---

## 19. Integration Points in `xray.py`

The changes to `xray.py` are minimal. Add the following after all existing analyses complete:

```python
# In the main analysis pipeline, after existing analyses:

from lib.investigation_targets import compute_investigation_targets

# ... existing code that produces ast_results, import_results, call_results, etc.

# NEW: Compute investigation targets for deep_crawl agent
if verbose:
    print("Computing investigation targets...", file=sys.stderr)

investigation_targets = compute_investigation_targets(
    ast_results=ast_results,
    import_results=import_results,
    call_results=call_results,
    git_results=git_results,
    gap_results=gap_results,
    root_dir=target_dir,
    verbose=verbose,
)

# Add to results dict
results["investigation_targets"] = investigation_targets
```

The formatters need corresponding updates to include the new section in both markdown and JSON output. The JSON formatter simply includes the dict. The markdown formatter should produce a compact summary (see Section 4, Markdown Output).

---

## 20. End-to-End Example

To illustrate how all components work together, here's a complete walkthrough for a hypothetical 300-file FastAPI codebase:

```
STEP 1: User runs xray
────────────────────────
$ python xray.py . --output both --out /tmp/xray
[5 seconds]
→ /tmp/xray/xray.md (12K tokens)
→ /tmp/xray/xray.json (40K tokens, now includes investigation_targets)

  investigation_targets summary:
    ambiguous_interfaces: 14
    entry_paths: 5
    coupling_anomalies: 2
    convention_deviations: 4
    shared_mutable_state: 3
    high_uncertainty_modules: 6
    domain_entities: 8


STEP 2: User starts deep crawl
────────────────────────────────
$ @deep_crawl full

  Phase 1: PLAN (3 minutes)
  ─────────────────────────
  Reading xray output... detected domain: web_api
  Building crawl plan:
    Priority 1: 5 request traces
    Priority 2: 6 high-uncertainty modules
    Priority 3: 8 pillar summaries
    Priority 4: 5 cross-cutting concerns (error, config, state, auth, middleware)
    Priority 5: 4 convention deviations + 2 coupling anomalies
    Priority 6: 3 gap investigations
  Total: 33 investigation tasks
  Plan saved to /tmp/deep_crawl/CRAWL_PLAN.md

  Phase 2: CRAWL (60-90 minutes)
  ──────────────────────────────
  [P1] Tracing POST /api/orders → order_service → payment → db.commit (5 hops)
       Found gotcha: payment retry silently changes order status
  [P1] Tracing POST /api/auth/login → auth_service → jwt → session (3 hops)
       Clean path, no surprises
  [P1] Tracing GET /api/reports → report_engine → cache → db (4 hops)
       Found gotcha: cache TTL is hardcoded, not configurable
  ... (2 more traces)

  [P2] Deep reading core/resolver.py (uncertainty 0.92)
       Behavioral summary: dispatches incoming requests to appropriate service
       based on a type registry populated at import time
       Gotcha: registry order depends on import order in __init__.py
  ... (5 more modules)

  [P4] Error handling: dominant pattern is try/except at service boundary,
       log with structlog, reraise as HTTPException.
       Deviation: payment_service catches and swallows TimeoutError
  [P4] Auth: JWT with refresh tokens, middleware checks on all /api routes
       except /api/health and /api/auth/*
  ... (3 more concerns)

  Checkpoint: 28/33 tasks complete, 7 gotchas found
  All Priority 1-4 complete. Standard questions: 10/10 answerable.
  Stopping crawl.

  Phase 3: SYNTHESIZE (5 minutes)
  ────────────────────────────────
  Drafting DEEP_ONBOARD.md from 28 investigation findings...
  First draft: ~22K tokens

  Phase 4: COMPRESS (3 minutes)
  ─────────────────────────────
  Target: 12-15K tokens (300 files = medium codebase)
  Cuts:
    - Removed 3 module summaries (self-evident from filename)
    - Merged 2 similar gotchas
    - Compressed 2 traces sharing common auth middleware sub-path
    - Converted error handling prose to table
  Final: ~14K tokens ✓

  Phase 5: VALIDATE (5 minutes)
  ─────────────────────────────
  Standard questions: 10/10 ✓
  Spot-check: 10/10 accurate ✓
  Adversarial (add new endpoint): PASS — doc covers route, service, schema conventions
  Redundancy: 1 section flagged (~200 tokens), acceptable

  ════════════════════════════════
  Deep Crawl Complete
  ════════════════════════════════
  Codebase: 300 files, ~1.2M tokens
  Document: ~14K tokens (86:1 compression)
  Crawl: 28/33 tasks (5 Priority 5-6 skipped, criteria met)
  Modules read: 19
  Traces verified: 5
  Gotchas found: 7
  Standard questions: 10/10
  Output: ./DEEP_ONBOARD.md


STEP 3 (optional): Independent validation
──────────────────────────────────────────
$ @deep_onboard_validator full

  Verdict: PASS
  Completeness: 10/10
  Accuracy: 10/10
  Adversarial: PASS
  Redundancy: ~200 tokens (1.4%)


STEP 4: Future agent sessions
──────────────────────────────
Every new Claude Code session reads DEEP_ONBOARD.md (14K tokens)
and can immediately:
  - Navigate to the right file for any task
  - Avoid 7 documented gotchas
  - Follow established conventions
  - Understand error handling without investigation
  - Know the blast radius of changes to any critical module
```

---

## 21. Changelog and Version Strategy

This spec is version 1.0. Future iterations should track:

| Version | Focus |
|---------|-------|
| 1.0 | Core pipeline: plan → crawl → synthesize → compress → validate |
| 1.1 | Refinement based on real-world testing on 5+ codebases |
| 1.2 | Multi-language support (JS/TS via tree-sitter xray equivalent) |
| 1.3 | Incremental refresh optimization (minimize re-crawl on changes) |
| 2.0 | Self-improving: track which onboarding sections downstream agents reference most, auto-adjust section budgets |

---

*End of specification.*

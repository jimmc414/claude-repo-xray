# Deep Crawl Specification for repo-xray

> **Version:** 2.0
> **Status:** Specification
> **Audience:** Developers implementing and using the deep crawl addon
> **Dependencies:** repo-xray (existing), Claude Code agent/skill framework
> **Supersedes:** v1.0 — incorporates delivery mechanism, context management, prompt caching strategy, compression algorithm, feedback loop, and evidence standard refinements

---

## 1. Problem Statement

repo-xray solves the cold start problem by producing a deterministic, fast, zero-dependency map of a Python codebase. This map is good — but it's a map, not understanding. A 5-million-token codebase compressed to 15K tokens of xray output still leaves a downstream agent guessing about behavioral semantics, hidden coupling, error handling strategy, and the meaning of generic abstractions.

The current `repo_xray` agent partially addresses this through its INVESTIGATE phase, but it operates under token budget constraints designed for a single interactive session. It reads selectively, summarizes quickly, and delivers within minutes. This is appropriate for developer-facing workflows but leaves significant value on the table.

**Deep Crawl** removes the budget constraint on generation. It assumes the onboarding document will be read by hundreds of agent sessions, so spending 20M tokens to produce a 15K-token document is justified if that document maximally reduces uncertainty for every downstream agent that reads it.

### The Core Metric

**File-reads saved per onboarding token.** Every token in the onboarding document should reduce the number of files a downstream agent needs to open before it can confidently make changes. A raw skeleton saves ~0.5 file reads (the agent usually still opens the file). An LLM-generated behavioral summary with gotchas saves ~1.0. A verified request trace through 5 modules saves 5. Deep Crawl optimizes for this ratio.

### The Economics of Access

The onboarding document is read at the start of every agent session. If 200 sessions read a 15K-token document, that's 3M tokens of access cost. But with prompt caching (see Section 6), cached reads cost ~90% less — so the effective access cost drops to ~300K tokens. The generation cost of 20M tokens pays for itself after ~7 uncached reads or ~67 cached reads. This makes even expensive generation overwhelmingly cost-effective, provided the delivery mechanism ensures caching actually occurs.

---

## 2. Design Principles

**2.1. xray stays deterministic.** The scanner remains fast, zero-dependency, reproducible. Deep Crawl builds on top of xray output, never replaces it.

**2.2. Generation cost is irrelevant; access cost is everything.** The crawl can run for hours and consume millions of tokens. The output document must be small enough to fit in a downstream agent's context alongside the task it's working on.

**2.3. Every output token must resolve uncertainty.** No filler, no redundancy with information the downstream agent can derive from file names or signatures alone. If a fact is obvious from the code structure, don't include it. If it's surprising, counterintuitive, or requires reading multiple files to understand, include it.

**2.4. The document is for AI agents, not humans.** Optimize for machine consumption. Structured, unambiguous, directly actionable. No motivational prose, no "this is a well-designed system" commentary. State facts, flag dangers, provide coordinates.

**2.5. Leverage the Anthropic ecosystem fully.** Extended thinking for synthesis, Claude Code tools for investigation, prompt caching for efficient multi-pass analysis. Design for how Claude Code actually works, not for a generic LLM.

**2.6. Design for prompt caching from the start.** The onboarding document must be delivered through a mechanism that enables prompt caching (CLAUDE.md inclusion). Stable content goes at the top of the document; content that changes with each refresh goes at the bottom. This maximizes cache hit rates across sessions.

**2.7. The document must be self-contained for its scope.** A downstream agent should NOT need to open a second reference document (like xray output) for information it needs frequently. Occasionally-needed structural details (full skeletons, complete import graphs) can be referenced externally, but behavioral information, gotchas, conventions, and critical paths must all be in DEEP_ONBOARD.md itself. The cost of including a few hundred extra tokens is less than the cost of a downstream agent context-switching to load a second file.

**2.8. Evidence standards must match claim types.** Not all knowledge is verifiable the same way. A function's behavior can be verified by reading the code. A coding convention is verified by observing it across multiple examples. Both belong in the document, but the evidence standard differs (see Section 5.3).

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
│                                      └──────────────────────────┘  │
│                                                    │                │
└────────────────────────────────────────────────────┼────────────────┘
                                                     │
                                    ┌────────────────┼──────────┐
                                    │   DELIVERY (automatic)    │
                                    │                           │
                                    │  CLAUDE.md includes:      │
                                    │  @docs/DEEP_ONBOARD.md    │
                                    │                           │
                                    │  → Loaded into system     │
                                    │    context automatically  │
                                    │  → Prompt caching active  │
                                    │  → Every session gets it  │
                                    │    for ~free after first   │
                                    └───────────┬───────────────┘
                                                │
                        ┌───────────────────────┼──────────────┐
                        │     CONSUMPTION (every session)       │
                        │                                       │
                        │   Fresh Claude instance has            │
                        │   DEEP_ONBOARD.md pre-loaded          │
                        │   via CLAUDE.md → prompt cache         │
                        │   + task instructions                  │
                        │   = productive immediately             │
                        │                                       │
                        │   Agent logs section references        │
                        │   → feedback for next refresh          │
                        └───────────────────────────────────────┘
```

### Component Roles

| Component | Role | Cost Model |
|-----------|------|------------|
| `xray.py` | Deterministic signal extraction | ~5 seconds, zero API cost |
| `investigation_targets` | Prioritized crawl agenda (new xray output section) | Part of xray scan, zero additional cost |
| `deep_crawl` agent | LLM-powered investigation and synthesis | 5-20M tokens (one-time generation) |
| `deep_onboard_validator` agent | QA pass on the output document | 1-3M tokens (one-time) |
| `DEEP_ONBOARD.md` | Compressed onboarding document | 8-20K tokens (read every session, cached) |
| `CLAUDE.md` integration | Automatic delivery to every agent session | Zero additional cost |
| Feedback annotations | Track which sections downstream agents use | Negligible per session |

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
        "estimated_hop_count": 4,
        "granularity": "module_level"
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

**`entry_to_side_effect_paths`** — For each detected entry point, walk the call graph (already built by `call_analysis.py`) and collect all reachable side effects (already detected by `ast_analysis.py`). Store the entry point, the terminal side effects, and an estimated hop count. **Important limitation:** this computation operates at module-level granularity, not function-level. The BFS walks module-to-module via the cross-module call graph. This means the estimated hop count represents module transitions, not function call depth — a 4-module-hop path might be 2 or 8 function calls. The deep_crawl agent should treat hop counts as rough priority signals, not accurate measurements. The agent will trace the actual function-level path during Phase 2.

**`coupling_anomalies`** — Already computed by `git_analysis.py` (co-modification coupling). Cross-reference with `import_analysis.py` graph. Flag pairs where co-modification score > 0.7 but no direct or transitive import relationship exists within 2 hops.

**`convention_deviations`** — New analysis pass over existing skeleton data. For each detected pattern (class `__init__` signatures, decorator usage, module naming, return type annotations), compute the majority convention and flag outliers. Implementation: group classes by structural similarity (same base class, same decorators, same method names), find the dominant signature pattern in each group, flag members that deviate.

**`shared_mutable_state`** — New AST pass (or extend existing `ast_analysis.py` visitor). Find module-level assignments where the target is subsequently mutated via augmented assignment (`+=`, `.append`, `.update`, `[key] =`, `.clear()`, etc.) anywhere in the module or by any cross-module caller. Also flag singleton patterns (`_instance = None` with a `get_instance()` function).

**`high_uncertainty_modules`** — Composite score from: generic filename (1 point), low type coverage (1 point), high fan-in from call analysis (1 point), no module or class docstrings (1 point), high CC but not already a hotspot (1 point), contains `**kwargs` in public functions (0.5 points). Modules scoring ≥ 0.3 normalized are flagged. These are modules where the deep_crawl agent should spend its reading budget.

**`domain_entities`** — Already partially extracted via `extract_data_models()` in `gap_features.py`. Extend to include non-Pydantic classes that are referenced in type annotations across 3+ modules, which identifies domain objects that may not use a formal modeling library.

#### 4.2. Data Structure Verification Requirement

**Before releasing the `investigation_targets.py` module, run this verification:**

```bash
# Run xray on its own codebase and dump JSON
python xray.py . --output json --out /tmp/xray_self_test

# Run verification script
python -c "
import json

with open('/tmp/xray_self_test.json') as f:
    data = json.load(f)

# Verify key paths exist
files = data.get('structure', {}).get('files', {})
first_file = next(iter(files.values()), {})

# Check ast_results shape
assert 'functions' in first_file, 'Missing: files[].functions'
assert 'classes' in first_file, 'Missing: files[].classes'

funcs = first_file.get('functions', [{}])
if funcs:
    f = funcs[0]
    print(f'Function keys: {list(f.keys())}')
    params = f.get('params', f.get('parameters', []))
    if params:
        print(f'Param keys: {list(params[0].keys())}')
        # Verify the key name for type annotations
        p = params[0]
        type_key = 'type' if 'type' in p else 'annotation' if 'annotation' in p else 'MISSING'
        print(f'Type annotation key: {type_key}')

# Check call_results shape
calls = data.get('calls', data.get('call_analysis', {}))
print(f'Call results keys: {list(calls.keys())}')
cross = calls.get('cross_module', calls.get('cross_module_calls', {}))
print(f'Cross-module format: {type(cross).__name__}, sample keys: {list(cross.keys())[:3]}')

# Check git results shape
git = data.get('git', {})
print(f'Git results keys: {list(git.keys())}')
coupling = git.get('coupling', git.get('co_modification', []))
if coupling:
    print(f'Coupling entry keys: {list(coupling[0].keys())}')

# Check import results shape
imports = data.get('imports', {})
print(f'Import results keys: {list(imports.keys())}')

print('\\nAll checks passed. Use these key names in investigation_targets.py')
"
```

This verification must pass before the module ships. The `investigation_targets.py` implementation must use the actual key names discovered by this verification, not assumed ones. The implementation skeleton in Section 18 uses the most likely key names based on code review, but several are ambiguous (e.g., `params` vs `parameters`, `type` vs `annotation`, `cross_module` vs `cross_module_calls`). The verification script resolves these ambiguities against real data.

#### Markdown Output

Add a compact section to the markdown output:

```markdown
## Investigation Targets (for Deep Crawl)

**High-uncertainty modules (6):** core/resolver.py (0.92), lib/dispatcher.py (0.85), ...
**Ambiguous interfaces (14):** process() in 3 modules, handle() in 5 modules, ...
**Traced entry→side-effect paths (5):** POST /orders → 4 module hops → db.commit + stripe.post, ...
  *(Note: hop counts are module-level estimates; actual function call depth may differ)*
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

### 5.2. Six-Phase Workflow

The workflow has six phases, not five. Phase 0 (Context Management Setup) is added to address the reality that long crawls will exceed conversation context limits.

---

#### Phase 0: SETUP (Context Management)

**Goal:** Establish the working environment and context management strategy.

**The problem:** A thorough crawl of a 500-file codebase involves reading 50+ modules, recording findings for each, maintaining the crawl plan, and synthesizing results. This easily exceeds a single conversation's context window. The agent must manage context proactively.

**Strategy: Disk as extended memory.**

All intermediate state lives on disk, not in conversation context. The agent reads findings from disk when needed for synthesis, not from earlier conversation turns.

```
/tmp/deep_crawl/
├── CRAWL_PLAN.md              # Investigation agenda, updated with completion marks
├── findings/
│   ├── traces/                # One file per request trace
│   │   ├── 01_post_orders.md
│   │   ├── 02_get_reports.md
│   │   └── ...
│   ├── modules/               # One file per deep-read module
│   │   ├── core_engine.md
│   │   ├── core_resolver.md
│   │   └── ...
│   ├── cross_cutting/         # One file per concern
│   │   ├── error_handling.md
│   │   ├── configuration.md
│   │   ├── shared_state.md
│   │   └── ...
│   └── conventions/
│       └── patterns.md
├── SYNTHESIS_INPUT.md         # Concatenated findings for Phase 3
├── DRAFT_ONBOARD.md           # First draft (Phase 3 output)
├── DEEP_ONBOARD.md            # Final output (Phase 4 output)
└── VALIDATION_REPORT.md       # QA report (Phase 5 output)
```

**Context management rules:**

1. **Write findings to disk immediately** after each investigation task. Do not rely on them being in conversation history.
2. **Read only what's needed** for the current task. Don't re-read all findings before each task.
3. **Batch related reads.** When tracing a request path, read all modules in the path in sequence before recording the trace — don't interleave traces.
4. **Clear mental context between task types.** After completing all request traces, the agent can "forget" the detailed code it read. The trace findings on disk preserve what matters.
5. **Before Phase 3 (SYNTHESIZE),** concatenate all findings into a single `SYNTHESIS_INPUT.md` file and read it fresh. This gives the agent a clean, complete view of all findings without the noise of intermediate investigation steps.

**If the conversation reaches context pressure** (the agent notices responses becoming less coherent or it's losing track of the crawl plan):

1. Write current state to disk (checkpoint)
2. Inform the user: "Context is getting full. I've checkpointed progress. Run `@deep_crawl resume` to continue in a fresh conversation."
3. The resume command reads the crawl plan (with completion marks) and findings directory to reconstruct state

**Setup steps:**

```bash
# Create working directory structure
mkdir -p /tmp/deep_crawl/findings/{traces,modules,cross_cutting,conventions}

# Verify xray output exists
test -f /tmp/xray/xray.json && echo "READY" || echo "Run: python xray.py . --output both --out /tmp/xray"

# Check for existing crawl state
if [ -f /tmp/deep_crawl/CRAWL_PLAN.md ]; then
    echo "PREVIOUS CRAWL FOUND"
    # Check if git hash matches
    head -5 /tmp/deep_crawl/CRAWL_PLAN.md
    git log --oneline -1
    echo "If hashes match, run @deep_crawl resume"
    echo "If not, this is a stale crawl — starting fresh"
fi
```

---

#### Phase 1: PLAN (Build the Crawl Agenda)

**Input:** xray JSON output (full preset), including `investigation_targets`.

**Process:**
1. Read the full xray markdown for orientation
2. Read the `investigation_targets` section from JSON
3. Detect the project domain (web API, CLI tool, ML pipeline, data pipeline, library)
4. Produce a prioritized crawl plan — an ordered list of investigation tasks
5. Estimate total tasks and expected duration

**Crawl Plan Structure:**

```markdown
# Deep Crawl Plan: {project_name}

## Domain: {detected_domain}
## Codebase: {file_count} files, ~{token_count} tokens
## X-Ray scan: {xray_timestamp}
## Plan generated: {timestamp}
## Git commit: {git_hash}

### Priority 1: Request Traces ({count} tasks)
- [ ] {trace_description} (est. {N} module hops — actual function depth may differ)
...

### Priority 2: High-Uncertainty Module Deep Reads ({count} tasks)
- [ ] {module} — {reasons}
...

### Priority 3: Pillar Behavioral Summaries ({count} tasks)
- [ ] {module} — pillar #{rank}
...

### Priority 4: Cross-Cutting Concerns ({count} tasks)
- [ ] Error handling strategy
- [ ] Configuration surface
- [ ] Shared mutable state
- [ ] {domain-specific concerns}

### Priority 5: Conventions and Patterns ({count} tasks)
- [ ] Dominant coding patterns
- [ ] Convention deviations ({count} flagged)
- [ ] Coupling anomalies ({count} flagged)

### Priority 6: Gap Investigation ({count} tasks)
- [ ] Implicit initialization sequences
- [ ] Undocumented environment dependencies
- [ ] Hidden coupling not in imports
```

**Prioritization logic:**

The ordering reflects information density — what saves the most downstream file-reads per token of output. Request traces are first because a single trace replaces 3-5 file reads for any agent working on that pathway. High-uncertainty modules are second because they're the modules where reading the name and signature tells you nothing. Cross-cutting concerns are fourth because they're "learn once, apply everywhere" — a single paragraph about error handling strategy applies to every modification the downstream agent makes.

**Output:** A markdown crawl plan saved to `/tmp/deep_crawl/CRAWL_PLAN.md`. The agent checks off items as it completes them, enabling resumability.

---

#### Phase 2: CRAWL (Systematic Investigation)

**Process:** Execute the crawl plan in priority order. For each investigation task, use a specific investigation protocol based on the task type. Write findings to the appropriate file in `/tmp/deep_crawl/findings/`.

##### Protocol A: Request Trace

```
1. Read the entry point function (full source)
2. Identify the first call it makes to another module
3. Read that function (full source)
4. Repeat until you reach a terminal side effect or 8 hops
5. Record the trace in /tmp/deep_crawl/findings/traces/{NN}_{name}.md:
   entry_function (file:line)
     → called_function (file:line) — what it does in 1 sentence
     → next_function (file:line) — what it does in 1 sentence
     → [SIDE EFFECT: db.commit] (file:line)
6. Note any branching (error paths, conditional logic) at each hop
7. Note any data transformations (shape changes between hops)
8. Note any gotchas discovered during tracing
```

##### Protocol B: Module Deep Read

```
1. Read the entire module (or first 500 lines if larger)
2. Write findings to /tmp/deep_crawl/findings/modules/{module_name}.md:
   - What this module does (1-2 sentences of BEHAVIOR)
   - What's non-obvious about it
   - What breaks if you change it (blast radius)
   - What it depends on at runtime (not just imports)
   - For each public function/method:
     - 1-sentence behavioral description
     - Preconditions
     - Side effects
     - Error behavior
3. Record any gotchas
```

##### Protocol C: Cross-Cutting Concern

```
1. Grep for the relevant patterns across the entire codebase
2. Categorize the results
3. Read 2-3 representative examples in full
4. Identify the dominant strategy
5. Flag deviations from the dominant strategy
6. Write findings to /tmp/deep_crawl/findings/cross_cutting/{concern_name}.md
```

**Specific grep patterns for each concern:**

```bash
# Error handling
grep -rn "except " --include="*.py" | head -40
grep -rn "raise " --include="*.py" | head -30
grep -rn "except.*pass" --include="*.py"  # swallowed exceptions — high value
grep -rn "retry\|backoff\|fallback" --include="*.py"

# Configuration
grep -rn "os.getenv\|os.environ" --include="*.py"
grep -rn "config\[" --include="*.py"
grep -rn "settings\." --include="*.py"
find . -name "*.yaml" -o -name "*.toml" -o -name "*.ini" -o -name "*.cfg" | head -10

# Shared mutable state
grep -rn "^[a-z_].*= " --include="*.py" | grep -v "def \|class \|#\|import " | head -30
grep -rn "_instance\|_cache\|_registry\|_pool" --include="*.py"
grep -rn "global " --include="*.py"
```

##### Protocol D: Convention Documentation

```
1. Read 3-5 examples of the pattern (from xray pillar/hotspot list)
2. Identify the common structure
3. State the convention as a directive ("always X", "never Y")
4. Read each flagged deviation
5. Assess: intentional variation or oversight?
6. Write findings to /tmp/deep_crawl/findings/conventions/patterns.md
```

**Checkpoint discipline:** After every 5 completed tasks, update CRAWL_PLAN.md to mark completed items with `[x]`. If the agent senses context pressure, checkpoint immediately and suggest resuming.

**When to stop crawling:**

Stop when ALL of the following are true:
1. All Priority 1 (request traces) tasks are complete
2. All Priority 2 (high-uncertainty modules) are read
3. All Priority 4 (cross-cutting concerns) are investigated
4. Current findings can answer all 10 standard questions (see Appendix B)
5. The last 3 tasks did not surface new gotchas

---

### 5.3. Evidence Standards

Not all claims in the onboarding document have the same epistemological status. The v1 spec required everything to be [VERIFIED], which is too strict for pattern-based observations and too ambiguous about what "verified" means for different claim types.

**Three evidence levels, each with a clear standard:**

| Level | Tag | Standard | Example |
|-------|-----|----------|---------|
| **Verified Fact** | `[FACT]` | Agent read the specific code and confirmed the claim is accurate at the cited file:line | "payment_service retries 3 times with exponential backoff (providers/stripe.py:89)" |
| **Verified Pattern** | `[PATTERN]` | Agent observed the pattern in ≥3 independent examples and states the count | "All service classes use dependency injection via __init__ (observed in 12/14 services)" |
| **Verified Absence** | `[ABSENCE]` | Agent searched for something expected and confirmed it does not exist | "No rate limiting implementation found (grepped for rate_limit, throttle, slowapi — zero hits)" |

**What is NOT included:** Inferences, assumptions, and unverified xray signals. If the agent didn't read the code or run the grep, the claim doesn't go in the document. The evidence tags tell the downstream agent how much to trust each claim and how to re-verify if needed.

**Rule for Conventions section:** Conventions are [PATTERN] claims. They must cite the example count. "Always inject config via __init__ [PATTERN: 12/14 services]" — this tells the downstream agent both the convention and its strength.

**Rule for Gotchas section:** Gotchas must be [FACT] claims with file:line evidence. A gotcha based on pattern observation ("this codebase probably has race conditions") is not actionable. A gotcha with a specific location ("check-then-act without locking at inventory.py:178") is.

---

#### Phase 3: SYNTHESIZE (Produce Raw Onboarding Document)

**Input:** Accumulated findings from Phase 2.

**Process:**

1. Concatenate all findings into a single input:
```bash
cat /tmp/deep_crawl/findings/traces/*.md \
    /tmp/deep_crawl/findings/modules/*.md \
    /tmp/deep_crawl/findings/cross_cutting/*.md \
    /tmp/deep_crawl/findings/conventions/*.md \
    > /tmp/deep_crawl/SYNTHESIS_INPUT.md
```

2. Read `SYNTHESIS_INPUT.md` fresh — this gives a clean, complete view of all findings

3. **Use extended thinking** to reason holistically about:
   - What are the 3-5 most important things a downstream agent needs?
   - What themes emerge across findings?
   - What's the minimum set of facts for safe modifications anywhere?
   - Which findings are redundant with what an agent could infer from file names?
   - What surprised me during the crawl? (Those are gotchas.)

4. Draft `DEEP_ONBOARD.md` following the template at `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

5. Key synthesis rules:
   - **Don't copy findings verbatim** — synthesize across modules
   - **Include the key structural facts an agent needs frequently** — the most important class signatures, the primary data types. Don't force the agent to open xray output for information it needs on every task.
   - **Don't include structural information that's rarely needed** — full import graphs, complete decorator inventories, etc. Reference xray output for these.
   - **DO include every surprise** — anything non-obvious gets priority space
   - **DO include cross-module interactions** — how modules affect each other
   - **DO write conventions as directives** — "Always X", "Never Y"
   - **Stable content first, volatile content last** — this maximizes prompt cache hit rates when the document is refreshed (see Section 6)

6. Write first draft to `/tmp/deep_crawl/DRAFT_ONBOARD.md`

---

#### Phase 4: COMPRESS (Optimize for Token Budget)

**Input:** First draft from Phase 3.

**Target sizes:**

| Codebase Files | Target Tokens | Hard Max |
|----------------|---------------|----------|
| <100 | 8-10K | 12K |
| 100-500 | 12-15K | 17K |
| 500-2000 | 15-18K | 20K |
| >2000 | 18-20K | 22K |

**Compression algorithm — execute in this exact order:**

**Step 1: Measure.**
```bash
wc -w /tmp/deep_crawl/DRAFT_ONBOARD.md | awk '{printf "~%d tokens\n", $1 * 1.3}'
```
If already within target, skip to Step 7.

**Step 2: Cut self-evident module summaries.**
Read the Module Behavioral Index. For each row, ask: "Does the module name + its position in the architecture already tell an agent what it does?" Examples:
- `email_sender.py` — "Sends emails" → CUT (self-evident)
- `resolver.py` — "Dispatches requests via type registry" → KEEP (not self-evident)
- `models/order.py` — "Order data model" → CUT (self-evident from path)

Re-measure. If within target, skip to Step 7.

**Step 3: Merge similar gotchas.**
Group gotchas by category. If 3 functions all swallow exceptions, merge into one entry: "Functions A, B, C swallow exceptions — see file:line, file:line, file:line." If two gotchas are about the same root cause, merge.

Re-measure.

**Step 4: Compress traces with shared sub-paths.**
If traces A and B both pass through the same auth middleware, show the middleware once with a note "shared by traces A, B." Don't repeat the same 3-hop sub-path.

Re-measure.

**Step 5: Convert prose to tables.**
Any paragraph that describes structured information (list of configs, list of error patterns, list of conventions) should be a table. Tables are 30-50% denser than equivalent prose.

Re-measure.

**Step 6: Trim low-priority sections.**
Cut from the bottom of the priority list:
1. Reading Order (agents can derive this from Critical Paths)
2. Extension Points (keep only if non-obvious)
3. Domain Glossary (keep only genuinely ambiguous terms)
4. Gaps (keep to 3-5 bullets max)

Re-measure. If still over budget, escalate: inform the user that the codebase is too complex for the target budget and recommend the next higher tier, or accept the overage.

**Step 7: Verify completeness.**
Attempt to answer all 10 standard questions (Appendix B) from the compressed document. If any question becomes unanswerable due to compression, restore the minimum content needed.

**Step 8: Verify structure for caching.**
Confirm that the document follows the stable-first ordering:
- Sections 1-8 (Identity through Conventions) are stable across refreshes
- Sections 9-12 (Gotchas through Gaps) may change more frequently
- The header metadata (commit hash, timestamps) is at the very top but changes every refresh — this is unavoidable

Write final version to `/tmp/deep_crawl/DEEP_ONBOARD.md`.

---

#### Phase 5: VALIDATE (Quality Assurance)

**Input:** Final `DEEP_ONBOARD.md` + codebase access.

##### 5a. Standard Questions Test

For each of the 10 standard questions (Appendix B), attempt to answer using ONLY the DEEP_ONBOARD.md content. Do NOT read any source files.

```
For each question:
- Can you answer it? YES / NO / PARTIAL
- If NO or PARTIAL: what's missing?
- Fix any gaps by adding minimal content
```

##### 5b. Spot-Check Verification

Select 10 [FACT] claims at random from the document. For each:
1. Read the referenced file:line
2. Verify the claim is accurate
3. If inaccurate, correct it

Priority: check claims in Gotchas and Critical Paths first — errors there cause the most downstream damage.

##### 5c. Redundancy Check

For each section, ask: "Would an agent who can see the file tree and run `grep` figure this out in under 30 seconds?"
- If yes → the section is wasting tokens, cut it
- If no → keep it

##### 5d. Adversarial Simulation

This is the highest-value validation check. Execute it rigorously:

**Step 1:** Determine the most common modification task for this codebase's domain:
- Web API → "Add a new API endpoint with request validation"
- CLI → "Add a new subcommand with argument parsing"
- Library → "Add a new public function to the API"
- Pipeline → "Add a new pipeline stage between existing stages"
- Other → "Add a new module that integrates with the core workflow"

**Step 2:** Using ONLY DEEP_ONBOARD.md, write a concrete 5-step implementation plan:
```
1. Create file at: {path}
2. Define class/function: {name} following convention: {convention from doc}
3. Register/connect it in: {integration point from doc}
4. Add test in: {test location from doc} following pattern: {pattern from doc}
5. Watch out for: {gotcha from doc}
```

**Step 3:** Read the actual codebase to evaluate each step:
- Would the agent create the file in the right place?
- Would the code follow the project's actual conventions?
- Would the integration point be correct?
- Would the test match actual test patterns?
- Did the gotcha warning prevent a real mistake?

**Step 4:** Score and report:
- **PASS:** All 5 steps would produce correct, convention-following code
- **PARTIAL:** 3-4 steps correct; document has a specific addressable gap
- **FAIL:** ≤2 steps correct; document fails its core purpose

If PARTIAL or FAIL, identify exactly what's missing and add it.

##### 5e. Caching Structure Verification

Confirm the document is structured for prompt cache efficiency:
1. The top of the document (Identity, Critical Paths, Module Index) is content that rarely changes between refreshes
2. The bottom of the document (Gotchas, Gaps) is content that changes more frequently
3. No section in the stable zone references volatile data (commit hashes, line numbers that shift frequently)

Note: some line numbers in [FACT] citations will shift between refreshes. This is acceptable — the important thing is that the behavioral descriptions remain accurate even if the line numbers drift by a few lines.

---

#### Phase 6: DELIVER (Package and Configure)

**Goal:** Place the document where downstream agents will actually receive it.

**Step 1:** Copy to project docs:
```bash
mkdir -p docs
cp /tmp/deep_crawl/DEEP_ONBOARD.md docs/DEEP_ONBOARD.md
```

**Step 2:** Configure automatic delivery via CLAUDE.md:

Check if CLAUDE.md exists:
```bash
test -f CLAUDE.md && echo "EXISTS" || echo "CREATE"
```

If CLAUDE.md exists, append the include (if not already present):
```bash
grep -q "DEEP_ONBOARD" CLAUDE.md || echo -e "\n# Codebase Onboarding\nRead docs/DEEP_ONBOARD.md before starting any task. It contains verified behavioral documentation, critical paths, gotchas, and conventions for this codebase." >> CLAUDE.md
```

If CLAUDE.md doesn't exist, create it:
```markdown
# Project Instructions

## Codebase Onboarding
Read docs/DEEP_ONBOARD.md before starting any task. It contains verified behavioral documentation, critical paths, gotchas, and conventions for this codebase.
```

**Why CLAUDE.md:** In Claude Code, the contents of CLAUDE.md are loaded into the system context at the start of every conversation. This means:
1. Every agent session automatically receives the onboarding document
2. The content is eligible for prompt caching — after the first session, subsequent sessions read it from cache at ~90% reduced cost
3. The agent doesn't need to know to look for the document — it's already in context

**Step 3:** Generate validation report:
```bash
cp /tmp/deep_crawl/VALIDATION_REPORT.md docs/DEEP_ONBOARD_VALIDATION.md
```

**Step 4:** Report to user:
```
Deep Crawl Complete
═══════════════════
Codebase: {files} files, ~{tokens} tokens
Document: ~{doc_tokens} tokens ({compression_ratio}:1 compression)
Crawl: {tasks_completed}/{tasks_planned} tasks
Questions answerable: {score}/10
Claims verified: {verified}/10
Adversarial test: {PASS/PARTIAL/FAIL}
Gotchas documented: {count}
Request traces: {count}

Delivered to: docs/DEEP_ONBOARD.md
CLAUDE.md: {UPDATED/CREATED} — document will auto-load in all sessions
Prompt caching: Active — subsequent sessions read at ~90% reduced cost
```

---

## 6. Delivery and Caching Strategy

This section addresses how the onboarding document gets into downstream agent contexts and how to minimize the access cost across hundreds of sessions.

### 6.1. The Delivery Problem

Creating a perfect onboarding document is worthless if downstream agents don't read it. There are several ways an agent could access the document:

| Method | Auto-loads? | Cached? | Requires agent action? |
|--------|-------------|---------|----------------------|
| CLAUDE.md include | Yes | Yes | No |
| Agent reads file explicitly | No | No | Yes (must know to look) |
| Custom system prompt | Yes | Yes | Requires user config |
| Skill/agent reference | Partial | Partial | Depends on trigger |

**CLAUDE.md is the correct delivery mechanism.** It's the only method that is both automatic (no agent action required) and cache-eligible (system context is cached across sessions).

### 6.2. Prompt Caching Mechanics

When content is part of the system context (loaded via CLAUDE.md), Anthropic's prompt caching stores it after the first session. Subsequent sessions that include the same content get a cache hit, reducing the token cost of reading that content by approximately 90%.

**Key constraint:** Caching is invalidated when the content changes. If the onboarding document is refreshed, the first session after the refresh pays the full cost, and subsequent sessions get the new cached version.

**Implication for document structure:** Arrange the document so that the most stable content is at the beginning and the most volatile content is at the end. Prompt caching works on prefixes — if the first 80% of the document is unchanged, the cache can serve that prefix even if the last 20% changed.

**Stable sections (put first):**
1. Identity (rarely changes)
2. Critical Paths (changes only when architecture changes)
3. Module Behavioral Index (changes only when modules change)
4. Error Handling Strategy (changes rarely)
5. Shared State (changes rarely)
6. Domain Glossary (changes rarely)
7. Configuration Surface (changes when config is added)
8. Conventions (changes rarely)

**Volatile sections (put last):**
9. Gotchas (may grow as new issues are found)
10. Hazards (changes when large files are added/removed)
11. Extension Points (may shift as architecture evolves)
12. Reading Order (may shift)
13. Gaps (shrinks as gaps are filled)
14. Metadata footer (changes every refresh)

### 6.3. Multi-File Context Budget

A downstream agent's context must hold:
1. DEEP_ONBOARD.md (8-20K tokens)
2. CLAUDE.md itself and any other project instructions (~1-2K tokens)
3. The current task instructions from the user (~1-5K tokens)
4. Files the agent reads during the task (variable, typically 10-50K tokens)
5. The agent's own responses (variable)

**Total context budget typically available:** ~180-190K tokens (in a 200K context window).

**Design constraint:** The onboarding document must leave enough room for the agent to actually work. A 20K-token onboarding document consumes ~10% of context — acceptable. A 40K-token document would consume ~20% and start crowding out working space.

**Decision on xray output co-loading:** The DEEP_ONBOARD.md document should NOT rely on xray output being simultaneously loaded. xray output (30-50K tokens for JSON) would consume too much context alongside the onboarding document. Instead:

- **Frequently-needed structural info** (key class signatures for the 5-10 most important classes, primary data model shapes) should be included directly in DEEP_ONBOARD.md. The token cost of ~500-1000 tokens for this is less than the cost of a downstream agent opening xray output.
- **Rarely-needed structural info** (complete skeletons, full import graphs, complete decorator inventories) should reference xray output with a path: "For complete class signatures, see `/tmp/xray/xray.md`." The downstream agent can open this on-demand when needed for specific tasks.
- **Investigation targets** are generation-time data only. They are never referenced by downstream agents.

### 6.4. Refresh Strategy

When the codebase changes and the onboarding document needs updating:

```bash
# Re-scan
python xray.py . --output both --out /tmp/xray

# Refresh (incremental update)
@deep_crawl refresh
```

The refresh command:
1. Reads the existing DEEP_ONBOARD.md
2. Reads the commit hash from the document header
3. Diffs against current HEAD:
```bash
git diff --name-only {doc_hash} HEAD
```
4. For each changed file mentioned in the document:
   - Re-reads the file
   - Updates the relevant findings
   - Re-verifies affected [FACT] claims
5. For files changed that are NOT in the document: checks if they're now significant enough to warrant inclusion
6. Re-runs Phase 4 (compress) and Phase 5 (validate) on the updated document
7. Preserves the stable-first section ordering for cache efficiency

**Full re-crawl trigger:** If >30% of files have changed, or if the architectural layer structure has changed (new directories, removed modules), do a full re-crawl instead of refresh.

---

## 7. Output Document Template

### 7.1. `DEEP_ONBOARD.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

```markdown
# {PROJECT_NAME}: Agent Onboarding

> Codebase: {FILE_COUNT} files, ~{TOTAL_TOKENS} tokens
> This document: ~{DOC_TOKENS} tokens
> Generated: {TIMESTAMP} from commit `{GIT_HASH}`
> Crawl: {TASKS_COMPLETED}/{TASKS_PLANNED} tasks, {MODULES_READ} modules read
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---

## Identity

<!-- 1-3 sentences. What is this, what does it do, what's the stack. No filler. -->

{IDENTITY}

---

## Critical Paths

<!-- For each major entry point, show the verified call chain from entry
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

---

## Module Behavioral Index

<!-- For every architecturally significant module: behavioral summary.
This is WHAT it does and what's dangerous, not its structure.
Budget: ~4000 tokens. -->

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `{path}` | {1-sentence behavior} | {what it needs at runtime} | {gotcha or "—"} |

---

## Key Interfaces

<!-- The 5-10 most important class/function signatures that downstream
agents will need on nearly every task. Include these directly rather than
forcing agents to open xray output. Budget: ~1000 tokens. -->

```python
# {file}
class {Name}:
    def {method}(self, {params}) -> {return}: ...  # {1-sentence behavior}
```

---

## Error Handling Strategy

<!-- Dominant pattern + deviations.
Budget: ~1000 tokens. -->

**Dominant pattern:** {description} [PATTERN: observed in N/M modules]

**Retry strategy:** {description or "none detected"}

**Deviations:**

| Module | Pattern | Risk |
|--------|---------|------|
| `{path}` | {how it differs} | {what could go wrong} |

---

## Shared State

<!-- Every module-level mutable, singleton, cache, or registry.
Budget: ~800 tokens. -->

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `{name}` | `{file}:{line}` | `{functions}` | {description} |

---

## Domain Glossary

<!-- Terms that mean something specific in THIS codebase.
Only genuinely ambiguous or overloaded terms.
Budget: ~600 tokens. -->

| Term | Means Here | Defined In |
|------|------------|------------|
| {term} | {codebase-specific meaning} | `{file}` |

---

## Configuration Surface

<!-- Every knob that changes runtime behavior.
Budget: ~1000 tokens. -->

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `{name}` | {env/file/flag} | {what behavior changes} | `{value}` |

---

## Conventions

<!-- Implicit rules as directives. Each cites evidence count.
Budget: ~800 tokens. -->

1. {Convention} [PATTERN: N/M examples]
2. {Convention} [PATTERN: N/M examples]

---

## Gotchas

<!-- Counterintuitive behaviors with file:line evidence.
Ordered by bug-likelihood. All must be [FACT].
Budget: ~1500 tokens. -->

1. **{title}** — {description} [FACT] (`{file}:{line}`)
2. **{title}** — {description} [FACT] (`{file}:{line}`)

---

## Hazards — Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `{glob}` | ~{N}K | {reason} |

---

## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| {task} | `{file}` | `{files}` | {gotcha} |

---

## Reading Order

1. `{file}` — {what you learn}
2. `{file}` — {what you learn}

**Skip:** `{file}` ({why})

---

## Gaps

- {specific gap}
- {specific gap}

---

*Generated by deep_crawl agent. {TASKS_COMPLETED} tasks,
{MODULES_READ} modules read, {TRACES_VERIFIED} traces verified.
Compression: {TOTAL_TOKENS} → {DOC_TOKENS} tokens ({COMPRESSION_RATIO}:1).
Evidence: {FACT_COUNT} [FACT], {PATTERN_COUNT} [PATTERN], {ABSENCE_COUNT} [ABSENCE].*
```

### 7.2. Key Differences from v1 Template

| Change | Rationale |
|--------|-----------|
| Added "Key Interfaces" section | Addresses multi-file context problem (#10) — include frequently-needed signatures directly instead of forcing agents to open xray output |
| Evidence tags changed from [VERIFIED] to [FACT]/[PATTERN]/[ABSENCE] | Addresses evidence standard issue (#5) — different claim types have different verification standards |
| Stable-first section ordering | Addresses prompt caching (#1) — maximizes cache prefix hits on refresh |
| Removed "For class signatures, see xray output" as blanket statement | Replaced with selective inclusion of key interfaces + targeted reference for complete data |
| Added evidence summary to footer | Lets downstream agents gauge document quality at a glance |

---

## 8. Feedback Mechanism

### 8.1. The Problem

The deep crawl produces a document based on the generator's judgment about what's valuable. But the real test is which sections downstream agents actually use. Without feedback, the document can't improve across refreshes.

### 8.2. Lightweight Feedback via Usage Annotations

The recommended approach is minimal and non-intrusive: downstream agents append a usage log to a feedback file when they reference specific sections of the onboarding document.

**Add to CLAUDE.md (alongside the onboarding include):**

```markdown
## Onboarding Feedback
When you reference a specific section of docs/DEEP_ONBOARD.md to make a decision, append a one-line log to docs/.onboard_feedback.log:
```
{ISO_TIMESTAMP} | {SECTION_NAME} | {TASK_SUMMARY}
```
Example:
```
2026-03-15T14:23:00Z | Gotchas | Avoided race condition in inventory check
2026-03-15T14:25:00Z | Critical Paths | Traced order flow to find payment integration point
2026-03-15T14:30:00Z | Conventions | Followed DI pattern for new service class
```
This helps improve the onboarding document over time. Keep entries to one line.
```

**Constraints on the feedback mechanism:**
- Must not add more than 1-2 tokens of overhead per downstream session
- Must not require the downstream agent to change its workflow
- Must not depend on external services
- Must be readable by the deep_crawl agent during refresh

### 8.3. Using Feedback During Refresh

When `@deep_crawl refresh` runs, it reads the feedback log:

```bash
if [ -f docs/.onboard_feedback.log ]; then
    echo "=== Section Usage Frequency ==="
    cat docs/.onboard_feedback.log | awk -F'|' '{gsub(/^ +| +$/, "", $2); print $2}' | sort | uniq -c | sort -rn
fi
```

This produces output like:
```
   47 Critical Paths
   31 Gotchas
   23 Conventions
   18 Module Behavioral Index
    8 Error Handling Strategy
    3 Domain Glossary
    1 Reading Order
    0 Extension Points
```

**Refresh adjustments based on feedback:**
- Sections with high usage get more token budget (they're earning their space)
- Sections with zero usage get cut or compressed (they're wasting space)
- Sections that are frequently referenced alongside each other might benefit from being closer together or cross-referenced

### 8.4. What Feedback Cannot Tell You

Feedback tracks what sections agents use, not what's missing. If no agent ever references "Shared State" it might mean:
- (a) The section is useless and should be cut, OR
- (b) The section is so well-written that agents internalize it on first read and never need to re-reference it, OR
- (c) No task in the sample required thinking about shared state

The deep_crawl agent should use feedback as one signal among many, not as the sole arbiter of section value. The adversarial simulation in Phase 5 is a better test of section necessity.

---

## 9. Crawl Strategy Details

### 9.1. Budget Allocation

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

### 9.2. Crawl Ordering Within Task Types

**Request traces:** Order by estimated hop count descending (remembering that these are module-level estimates). Longer traces save more downstream file-reads. Also prioritize traces that pass through high-uncertainty modules, since those traces force the agent to read and understand them.

**Module deep reads:** Order by uncertainty score from `investigation_targets`. Read the most ambiguous modules first. Skip modules where the name, signature, and docstring already tell the full story.

**Cross-cutting concerns:** Fixed order:
1. Error handling (affects every modification)
2. Configuration (affects deployment and behavior)
3. Shared state (affects concurrency and testing)
4. Authentication/authorization (if detected — affects security)
5. Logging/observability (affects debugging)

### 9.3. Handling Very Large Codebases (>2000 files)

For very large codebases, the crawl plan itself becomes a significant document. Strategy:

1. Run xray with `--preset full` to get complete signals
2. During PLAN phase, identify 3-5 subsystems from the architectural layers
3. Execute a focused deep crawl on each subsystem independently
4. In SYNTHESIZE, produce a top-level document that covers cross-subsystem interactions, plus subsystem-specific appendix documents
5. The top-level document stays within 20K tokens; subsystem appendices are referenced by file path for agents working in specific areas
6. CLAUDE.md includes only the top-level document. Subsystem docs are loaded on-demand.

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

## 10. Claude Code Integration

### 10.1. Tool Usage Patterns

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

**Bash** — Running xray, file management, and utility operations:
```bash
# Run xray scan
python xray.py . --output both --out /tmp/xray

# Token count estimate
wc -w /tmp/deep_crawl/DEEP_ONBOARD.md | awk '{printf "~%d tokens\n", $1 * 1.3}'

# Check for findings (resumability)
ls /tmp/deep_crawl/findings/traces/ 2>/dev/null | wc -l
```

### 10.2. Context Window Management in Practice

**The core problem:** A thorough crawl involves reading 50+ files. At ~200 lines average, that's 10K+ lines of code passing through context. Add findings, the crawl plan, and xray output, and the agent easily exceeds its working context.

**Practical rules:**

1. **Never hold more than 3 source files in "working memory" simultaneously.** Read a file, extract what you need, write findings to disk, move to the next file.

2. **Batch by investigation task, not by file.** Don't read all files and then write findings. Read the files for one trace, write that trace's findings, then start the next trace.

3. **Treat disk writes as memory commits.** Once findings are written to `/tmp/deep_crawl/findings/`, the agent can "forget" the details. The SYNTHESIS phase will re-read them.

4. **Monitor your own coherence.** If you notice yourself losing track of the crawl plan, re-read it from disk. If your responses are becoming repetitive or confused, checkpoint and recommend `@deep_crawl resume`.

5. **Phase 3 (SYNTHESIZE) is a fresh start.** By concatenating all findings into SYNTHESIS_INPUT.md and reading it as a single document, the agent gets a clean, comprehensive view without the noise of intermediate investigation steps.

### 10.3. Extended Thinking Usage

The agent should use extended thinking at these specific points:

1. **End of Phase 1 (PLAN):** Reason about investigation priorities given the specific codebase characteristics. Which xray signals are most surprising? What domain-specific patterns should be investigated?

2. **During Phase 2 (CRAWL) — after each request trace:** Reason about what the trace reveals about the system's design. Are there implicit contracts between modules? Is the error handling consistent across the trace?

3. **Beginning of Phase 3 (SYNTHESIZE):** Reason about all findings holistically. What are the 3-5 most important things a downstream agent needs to know? What's the minimum viable onboarding document?

4. **During Phase 4 (COMPRESS) — at Step 2:** Reason about each module summary: "Is this self-evident? Would an agent that knows nothing about this codebase guess this from the filename?"

5. **During Phase 5 (VALIDATE) — adversarial simulation:** Reason step-by-step through the simulated task, checking each decision against the document.

### 10.4. File Management Summary

```
GENERATION ARTIFACTS (temporary):
/tmp/xray/
├── xray.md                    # X-Ray markdown output
└── xray.json                  # X-Ray JSON output

/tmp/deep_crawl/
├── CRAWL_PLAN.md              # Investigation plan with completion tracking
├── findings/                  # Raw findings (one file per task)
│   ├── traces/*.md
│   ├── modules/*.md
│   ├── cross_cutting/*.md
│   └── conventions/*.md
├── SYNTHESIS_INPUT.md         # Concatenated findings for Phase 3
├── DRAFT_ONBOARD.md           # Pre-compression draft
├── DEEP_ONBOARD.md            # Final validated output
└── VALIDATION_REPORT.md       # QA results

DELIVERED ARTIFACTS (permanent, committed to repo):
{project_root}/
├── docs/
│   ├── DEEP_ONBOARD.md        # The onboarding document
│   ├── DEEP_ONBOARD_VALIDATION.md  # Validation report
│   └── .onboard_feedback.log  # Usage feedback (grows over time)
└── CLAUDE.md                  # Updated to include onboarding doc
```

---

## 11. Domain-Specific Profiles

The crawl agent should adjust its investigation strategy based on detected domain. Stored in `configs/domain_profiles.json`.

### 11.1. Web API (FastAPI, Flask, Django)

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

### 11.2. CLI Tool (argparse, Click, Typer)

**Additional investigation targets:**
- Command hierarchy and subcommand structure
- Argument parsing and validation
- Output formatting strategy (JSON, table, plain text)
- Exit code conventions

**Additional onboarding sections:**
- Command tree with argument signatures
- Output format documentation

### 11.3. ML/AI Pipeline (torch, tensorflow, transformers)

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

### 11.4. Data Pipeline (airflow, dagster, ETL)

**Additional investigation targets:**
- DAG structure and dependencies
- Idempotency guarantees
- Failure recovery and retry strategy
- Data validation between stages
- Scheduling configuration

**Additional onboarding sections:**
- DAG visualization or description
- Stage-by-stage data transformation documentation

### 11.5. Library/SDK

**Additional investigation targets:**
- Public API surface (what's exported)
- Backward compatibility constraints
- Extension/plugin mechanisms
- Thread safety guarantees

**Additional onboarding sections:**
- Public API index with behavioral descriptions
- Extension point documentation

---

## 12. Validation Agent Specification

### 12.1. Agent Definition

```markdown
---
name: deep_onboard_validator
description: Independent QA agent for DEEP_ONBOARD documents. Verifies claims against actual code, tests completeness, runs adversarial simulation. Run after deep_crawl completes.
tools: Read, Grep, Glob, Bash
model: sonnet
skills: deep-crawl
---
```

**Model selection: Sonnet.** Validation is structured and protocol-driven. It doesn't require Opus-level reasoning. Sonnet is sufficient and cheaper.

### 12.2. Validation Protocol

Execute all 7 checks in order:

**Check 1: Completeness** — Answer all 10 standard questions from document alone.

**Check 2: Accuracy** — Spot-check 10 [FACT] claims by reading the referenced code.

**Check 3: Pattern Verification** — For 3 [PATTERN] claims, verify the stated example count is accurate (e.g., "12/14 services use DI" — actually count them).

**Check 4: Coverage** — Cross-reference against xray pillars. Are top 10 pillars represented?

**Check 5: Redundancy** — Flag sections an agent could figure out in <30 seconds with grep.

**Check 6: Adversarial Simulation** — Execute the detailed simulation protocol from Phase 5d:
1. Pick the domain-appropriate modification task
2. Write a concrete 5-step implementation plan using ONLY the document
3. Verify each step against actual code
4. Score PASS/PARTIAL/FAIL with specific gap identification

**Check 7: Freshness and Caching Structure** — Verify git hash, check stable-first ordering.

### 12.3. Verdict Criteria

| Verdict | Criteria |
|---------|----------|
| **PASS** | Completeness ≥ 9/10, Accuracy ≥ 9/10, Adversarial PASS |
| **NEEDS FIXES** | Completeness ≥ 7/10, Accuracy ≥ 7/10, specific fixable gaps |
| **NEEDS REWORK** | Completeness < 7/10, OR Accuracy < 7/10, OR Adversarial FAIL |

---

## 13. Implementation Plan

### Phase 1: xray Modifications (1-2 days)

1. **Run the data structure verification script** (Section 4.2) against xray's own codebase to determine actual key names
2. Create `lib/investigation_targets.py` using verified key names
3. Integrate into `xray.py` main pipeline
4. Update `formatters/markdown_formatter.py` — add compact investigation targets section
5. Update `formatters/json_formatter.py` — add full investigation targets to JSON output
6. **Verify**: Run xray on its own codebase, confirm `investigation_targets` section is populated with non-empty results for each sub-section

### Phase 2: Agent and Skill Creation (1-2 days)

1. Create `.claude/agents/deep_crawl.md`
2. Create `.claude/agents/deep_onboard_validator.md`
3. Create `.claude/skills/deep-crawl/SKILL.md`
4. Create `.claude/skills/deep-crawl/COMMANDS.md`
5. Create template files (DEEP_ONBOARD, CRAWL_PLAN, VALIDATION_REPORT)
6. Create config files (generic_names, domain_profiles, compression_targets)

### Phase 3: Testing (1-2 days)

1. Run `investigation_targets.py` against 3-5 real codebases of varying size
2. Verify non-empty output for each sub-section on each codebase
3. Run the full pipeline end-to-end on a medium codebase (~200 files):
   - Verify crawl plan is reasonable
   - Verify findings are written to disk correctly
   - Verify synthesis produces a coherent document
   - Verify compression hits the target budget
   - Verify the 10 standard questions are answerable
   - Verify the adversarial simulation passes
4. Test the CLAUDE.md delivery mechanism:
   - Start a new Claude Code session in the test project
   - Verify the onboarding document is in the agent's context
   - Ask the agent a question that requires onboarding knowledge
   - Confirm it answers correctly without reading additional files
5. Test resumability:
   - Start a crawl, interrupt it at Phase 2
   - Run `@deep_crawl resume`
   - Verify it picks up from the last checkpoint

### Phase 4: Iteration (ongoing)

1. Collect feedback from downstream agents via `.onboard_feedback.log`
2. Track which sections are most/least referenced
3. Adjust compression targets and section budgets based on data
4. Add domain profiles for additional project types

---

## 14. Open Questions (Resolved)

These questions were open in v1. Here are the v2 resolutions:

| Question | v1 Status | v2 Resolution |
|----------|-----------|---------------|
| Should the deep crawl produce the xray scan itself? | Open | **No.** Require xray as input. Fail fast with a clear message if missing. |
| Should output include xray skeleton data? | Open | **Selectively.** Include the 5-10 most important signatures directly (Key Interfaces section). Reference xray for complete data. |
| How should staleness be handled? | Open | **Git hash comparison + 30% threshold for full re-crawl.** See Section 6.4. |
| Single file or directory? | Open | **Single file for <2000 files, directory for larger.** See Section 9.3. |
| Non-Python codebases? | Open | **Out of scope for v1.** Deep crawl's investigation protocols and output template are language-agnostic; only xray itself is Python-specific. |
| How does prompt caching work? | Not addressed | **CLAUDE.md inclusion.** See Section 6. |
| How does the document reach agents? | Not addressed | **CLAUDE.md delivery.** See Section 6. |
| How to handle context limits during crawl? | Not addressed | **Disk as extended memory, batch-by-task, checkpoint on pressure.** See Phase 0 and Section 10.2. |
| What evidence standard for conventions? | Not addressed | **[PATTERN] with example count.** See Section 5.3. |
| How to get feedback from downstream agents? | Not addressed | **Usage log in .onboard_feedback.log.** See Section 8. |
| How to handle multi-file context? | Not addressed | **Include key interfaces directly, reference xray for complete data.** See Section 6.3. |
| Module-level vs function-level path estimation? | Not addressed | **Document the limitation. Treat as rough priority signal.** See Section 4.1. |

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

## Appendix B: Standard Questions

The 10 questions every DEEP_ONBOARD document must answer. Used in Phase 5 validation and by the validator agent.

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

Modules with uncertainty_score >= 0.3 are flagged for deep investigation. The threshold is lower than v1 (which used 0.5) because under-investigation is more costly than over-investigation when generation budget is unlimited.

## Appendix D: Adversarial Simulation Protocol (Detailed)

Used in Phase 5d and by the validator agent in Check 6.

**Input:** DEEP_ONBOARD.md only (no source code access).

**Step 1 — Select task by domain:**

| Domain | Task |
|--------|------|
| Web API | Add a new API endpoint with request validation and DB persistence |
| CLI | Add a new subcommand with argument parsing and output formatting |
| Library | Add a new public function with tests and documentation |
| Pipeline | Add a new pipeline stage between two existing stages |
| Other | Add a new module that integrates with the core workflow |

**Step 2 — Write implementation plan:**

Using ONLY the onboarding document, produce:

```
File to create:      {path} (based on Extension Points or Conventions)
Class/function:      {name} (following naming Convention)
Interface to impl:   {base class or protocol} (from Key Interfaces)
Registration point:  {where to wire it in} (from Critical Paths or Extension Points)
Test file:           {path} (from Testing conventions)
Test pattern:        {fixture/mock strategy} (from Testing conventions)
Risks to watch:      {gotcha 1}, {gotcha 2} (from Gotchas)
```

**Step 3 — Verify against code:**

Now read the actual codebase. For each element of the plan:

| Element | Check | Score |
|---------|-------|-------|
| File location | Does it match actual project structure? | 0 or 1 |
| Naming | Does it match actual conventions? | 0 or 1 |
| Interface | Does the base class/protocol actually exist and work as described? | 0 or 1 |
| Registration | Would wiring it in at the stated point actually work? | 0 or 1 |
| Test approach | Does it match how tests are actually written? | 0 or 1 |

**Step 4 — Score:**

| Score | Verdict |
|-------|---------|
| 5/5 | PASS |
| 3-4/5 | PARTIAL — identify the gap |
| 0-2/5 | FAIL — document needs rework |

## Appendix E: Compression Algorithm Quick Reference

Execute in order. Stop when within target budget.

```
1. MEASURE current token count
2. CUT self-evident module summaries (name tells the story)
3. MERGE similar gotchas into grouped entries
4. COMPRESS traces with shared sub-paths (show shared part once)
5. CONVERT prose to tables (30-50% denser)
6. TRIM low-priority sections (Reading Order → Extension Points → Glossary → Gaps)
7. VERIFY completeness (10 standard questions still answerable)
8. VERIFY caching structure (stable sections first)
```

## Appendix F: Evidence Tag Reference

| Tag | Meaning | Required Evidence | Example |
|-----|---------|-------------------|---------|
| `[FACT]` | Verified by reading specific code | file:line citation | "Retries 3x with backoff [FACT] (stripe.py:89)" |
| `[PATTERN]` | Observed across multiple examples | N/M count | "Services use DI [PATTERN: 12/14]" |
| `[ABSENCE]` | Confirmed non-existence via search | Search description | "No rate limiting [ABSENCE: grep throttle\|rate_limit — 0 hits]" |

---

## Appendix G: Change Log from v1 to v2

| Section | Change | Addresses Problem # |
|---------|--------|-------------------|
| §2 Design Principles | Added 2.6 (caching), 2.7 (self-contained), 2.8 (evidence standards) | #1, #10, #5 |
| §3 Architecture | Added delivery mechanism and CLAUDE.md to diagram | #2 |
| §4 xray Modifications | Added data structure verification requirement; noted module-level granularity limitation | #4, #9 |
| §5 Agent Specification | Added Phase 0 (context management), Phase 6 (deliver); replaced 5-phase with 6-phase; added Section 5.3 (evidence standards); rewrote Phase 4 with concrete compression algorithm; rewrote Phase 5d with detailed adversarial protocol | #6, #5, #3, #7 |
| §6 Delivery and Caching | New section — CLAUDE.md integration, prompt caching strategy, multi-file context budget, refresh strategy | #1, #2, #10 |
| §7 Output Template | Added Key Interfaces section; changed evidence tags; stable-first ordering | #10, #5, #1 |
| §8 Feedback Mechanism | New section — usage logging, feedback during refresh, limitations of feedback data | #8 |
| §10 Claude Code Integration | Expanded context management rules; added practical guidance for long crawls | #6 |
| §12 Validation Agent | Added Check 3 (pattern verification), upgraded Check 6 (adversarial) with detailed protocol | #5, #7 |
| §13 Implementation Plan | Added data structure verification as Step 1; added CLAUDE.md delivery test | #4, #2 |
| §14 Open Questions | All resolved with specific decisions | All |
| Appendix D | New — detailed adversarial simulation protocol | #7 |
| Appendix E | New — compression algorithm quick reference | #3 |
| Appendix F | New — evidence tag reference | #5 |
| Appendix G | New — change log | Documentation |

---

---

# Part 2: Implementable Artifacts

Everything below is ready to drop into the repo-xray project structure. Each section notes the target file path. All artifacts reflect v2 changes (Phase 0/6, evidence tags, CLAUDE.md delivery, context management, feedback mechanism).

---

## 15. Agent Definition: `deep_crawl`

**Target path:** `.claude/agents/deep_crawl.md`

The complete agent definition is embedded in Section 5 of this spec. To create the agent file, extract Sections 5.2 through 5.3 (the six-phase workflow and evidence standards) and wrap them in the agent frontmatter:

```yaml
---
name: deep_crawl
description: Exhaustive LLM-powered codebase investigator. Uses X-Ray signals to systematically crawl a codebase and produce a maximally compressed onboarding document optimized for AI agent consumption. Designed to run without token budget constraints.
tools: Read, Grep, Glob, Bash
model: opus
skills: deep-crawl
---
```

The agent body should include:
- Phase 0: SETUP (context management, directory structure, resumability check)
- Phase 1: PLAN (crawl plan generation from xray signals)
- Phase 2: CRAWL (investigation protocols A-D, checkpoint discipline, stop criteria)
- Phase 3: SYNTHESIZE (findings concatenation, extended thinking, synthesis rules)
- Phase 4: COMPRESS (8-step algorithm from Section 5.2)
- Phase 5: VALIDATE (5 checks: standard questions, spot-check, redundancy, adversarial simulation, caching structure)
- Phase 6: DELIVER (copy to docs/, update CLAUDE.md, report)
- Evidence standards (Section 5.3: [FACT], [PATTERN], [ABSENCE])
- Edge case handling (no tests, no git, monorepo, interrupted crawl, missing investigation_targets)
- Constraints and quality checklist

---

## 16. Agent Definition: `deep_onboard_validator`

**Target path:** `.claude/agents/deep_onboard_validator.md`

```yaml
---
name: deep_onboard_validator
description: Independent QA for DEEP_ONBOARD documents. 7-check protocol: completeness, accuracy, pattern verification, coverage, redundancy, adversarial simulation, freshness. Run after deep_crawl.
tools: Read, Grep, Glob, Bash
model: sonnet
skills: deep-crawl
---
```

The agent body should include the 7-check protocol from Section 12.2, the detailed adversarial simulation protocol from Appendix D, the verdict criteria from Section 12.3, and the validation report template from Section 19.3.

---

## 17. Skill Files

### 17.1. `SKILL.md`

**Target path:** `.claude/skills/deep-crawl/SKILL.md`

````markdown
---
name: deep-crawl
description: Exhaustive LLM-powered codebase investigation for optimal AI agent onboarding. Builds on X-Ray signals with unlimited investigation budget to produce the highest-quality onboarding document possible.
---

# deep-crawl

Systematic codebase investigation producing maximally compressed onboarding
documents optimized for AI agent consumption via CLAUDE.md delivery with
prompt caching.

## When to Use

- **Use deep-crawl** when generation cost is not a constraint and you want
  the highest-quality onboarding document for many future agent sessions
- **Use repo_xray** for quick interactive analysis where cost matters
- **Always run xray first** — deep_crawl requires xray output as input

## Commands

| Command | Duration | Purpose |
|---------|----------|---------|
| `@deep_crawl full` | 30-120 min | Complete 6-phase pipeline |
| `@deep_crawl plan` | 2-5 min | Generate crawl plan for review |
| `@deep_crawl resume` | Varies | Continue from checkpoint |
| `@deep_crawl validate` | 10-20 min | QA existing DEEP_ONBOARD.md |
| `@deep_crawl refresh` | 10-60 min | Incremental update for code changes |
| `@deep_crawl focus ./path` | 15-45 min | Deep crawl a subsystem |

## Pipeline

```
Phase 0: SETUP       Create workspace, check prerequisites, plan context mgmt
Phase 1: PLAN        Read xray → build prioritized investigation agenda
Phase 2: CRAWL       Execute agenda → read code → write verified findings to disk
Phase 3: SYNTHESIZE  Concatenate findings → draft onboarding document
Phase 4: COMPRESS    8-step algorithm → reduce to token budget
Phase 5: VALIDATE    Questions test → spot-check → adversarial sim → cache check
Phase 6: DELIVER     Copy to docs/ → update CLAUDE.md → enable prompt caching
```

## Evidence Standards

| Tag | Standard | Example |
|-----|----------|---------|
| [FACT] | Read specific code, cite file:line | "3x retry with backoff [FACT] (stripe.py:89)" |
| [PATTERN] | Observed in ≥3 examples, state count | "DI via __init__ [PATTERN: 12/14 services]" |
| [ABSENCE] | Searched and confirmed non-existence | "No rate limiting [ABSENCE: grep — 0 hits]" |

No inferences or unverified signals in the output document.

## Output

| File | Purpose | Location |
|------|---------|----------|
| DEEP_ONBOARD.md | Onboarding document (8-20K tokens) | docs/ |
| CLAUDE.md update | Auto-delivery to all sessions | project root |
| .onboard_feedback.log | Usage tracking from downstream agents | docs/ |
| VALIDATION_REPORT.md | QA results | docs/ |

## Context Management

The crawl uses disk as extended memory to handle codebases larger than
conversation context:

- Findings written to `/tmp/deep_crawl/findings/` immediately after each task
- Never hold >3 source files in working memory simultaneously
- Batch by investigation task, not by file
- Checkpoint every 5 tasks for resumability
- Phase 3 reads all findings fresh from a concatenated file

## Delivery

DEEP_ONBOARD.md is included in CLAUDE.md so that:
1. Every agent session receives it automatically
2. Prompt caching reduces read cost by ~90% after first session
3. Downstream agents don't need to know to look for it

## Token Budget Targets

| Codebase | Target | Hard Max |
|----------|--------|----------|
| <100 files | 8-10K | 12K |
| 100-500 files | 12-15K | 17K |
| 500-2000 files | 15-18K | 20K |
| >2000 files | 18-20K | 22K |

## Feedback

Downstream agents log section references to docs/.onboard_feedback.log.
During refresh, this data informs section budget allocation.

## Files

```
.claude/
├── agents/
│   ├── deep_crawl.md
│   └── deep_onboard_validator.md
└── skills/
    └── deep-crawl/
        ├── SKILL.md
        ├── COMMANDS.md
        ├── configs/
        │   ├── generic_names.json
        │   ├── domain_profiles.json
        │   └── compression_targets.json
        └── templates/
            ├── DEEP_ONBOARD.md.template
            ├── CRAWL_PLAN.md.template
            └── VALIDATION_REPORT.md.template
```
````

### 17.2. `COMMANDS.md`

**Target path:** `.claude/skills/deep-crawl/COMMANDS.md`

````markdown
# Deep Crawl Commands

## Prerequisites

```bash
python xray.py . --output both --out /tmp/xray
```

## Commands

| Command | What It Does |
|---------|-------------|
| `@deep_crawl full` | Plan → Crawl → Synthesize → Compress → Validate → Deliver |
| `@deep_crawl plan` | Generate investigation plan only |
| `@deep_crawl resume` | Continue from last checkpoint |
| `@deep_crawl validate` | QA an existing DEEP_ONBOARD.md |
| `@deep_crawl refresh` | Update for code changes (reads .onboard_feedback.log) |
| `@deep_crawl focus ./path` | Deep crawl a specific subsystem |

## Typical Workflow

```bash
python xray.py . --output both --out /tmp/xray   # 1. Scan
@deep_crawl full                                   # 2. Crawl + deliver
@deep_onboard_validator full                       # 3. Optional independent QA
# Output: docs/DEEP_ONBOARD.md, CLAUDE.md updated
```

## After Code Changes

```bash
python xray.py . --output both --out /tmp/xray
@deep_crawl refresh
```
````

---

## 18. Configuration Files

### 18.1. `generic_names.json`

**Target path:** `.claude/skills/deep-crawl/configs/generic_names.json`

*(Same as v1 — see Appendix A for the full list. No changes needed.)*

### 18.2. `domain_profiles.json`

**Target path:** `.claude/skills/deep-crawl/configs/domain_profiles.json`

*(Same as v1 — contains web_api, cli_tool, ml_pipeline, data_pipeline, and library profiles with indicators, additional_investigation targets, additional_output_sections, primary_entity, and grep_patterns for each.)*

### 18.3. `compression_targets.json`

**Target path:** `.claude/skills/deep-crawl/configs/compression_targets.json`

```json
{
  "description": "Token budget targets for DEEP_ONBOARD.md by codebase size.",
  "targets": [
    {"max_files": 100, "label": "small", "min_tokens": 6000, "target_tokens": 8000, "max_tokens": 12000},
    {"max_files": 500, "label": "medium", "min_tokens": 10000, "target_tokens": 13000, "max_tokens": 17000},
    {"max_files": 2000, "label": "large", "min_tokens": 13000, "target_tokens": 16000, "max_tokens": 20000},
    {"max_files": 999999, "label": "very_large", "min_tokens": 15000, "target_tokens": 18000, "max_tokens": 22000}
  ],
  "section_budgets": {
    "identity": {"max_tokens": 200, "priority": "required", "stability": "high"},
    "critical_paths": {"max_tokens": 3000, "priority": "required", "stability": "high"},
    "module_behavioral_index": {"max_tokens": 4000, "priority": "required", "stability": "high"},
    "key_interfaces": {"max_tokens": 1000, "priority": "required", "stability": "high"},
    "error_handling": {"max_tokens": 1000, "priority": "required", "stability": "high"},
    "shared_state": {"max_tokens": 800, "priority": "required", "stability": "high"},
    "domain_glossary": {"max_tokens": 600, "priority": "recommended", "stability": "medium"},
    "config_surface": {"max_tokens": 1000, "priority": "required", "stability": "medium"},
    "conventions": {"max_tokens": 800, "priority": "required", "stability": "high"},
    "gotchas": {"max_tokens": 1500, "priority": "required", "stability": "low"},
    "hazards": {"max_tokens": 500, "priority": "required", "stability": "low"},
    "extension_points": {"max_tokens": 800, "priority": "recommended", "stability": "low"},
    "reading_order": {"max_tokens": 400, "priority": "recommended", "stability": "low"},
    "gaps": {"max_tokens": 300, "priority": "required", "stability": "low"}
  },
  "note": "Sections ordered by stability (high first) to maximize prompt cache prefix hits."
}
```

---

## 19. Templates

### 19.1. `DEEP_ONBOARD.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

*(Defined in Section 7.1 of this spec. Copy directly.)*

### 19.2. `CRAWL_PLAN.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template`

````markdown
# Deep Crawl Plan: {PROJECT_NAME}

> Domain: {DETECTED_DOMAIN}
> Codebase: {FILE_COUNT} files, ~{TOTAL_TOKENS} tokens
> X-Ray scan: {XRAY_TIMESTAMP}
> Plan generated: {TIMESTAMP}
> Git commit: {GIT_HASH}

### Priority 1: Request Traces ({COUNT} tasks)
<!-- Note: hop counts are module-level estimates from xray.
The crawl agent traces at function level; actual depth may differ. -->
- [ ] {ENTRY_POINT} → {TERMINAL_EFFECTS} (est. {N} module hops)

### Priority 2: High-Uncertainty Module Deep Reads ({COUNT} tasks)
- [ ] `{MODULE}` — uncertainty {SCORE}: {REASONS}

### Priority 3: Pillar Behavioral Summaries ({COUNT} tasks)
- [ ] `{MODULE}` — pillar #{RANK}, {CALLERS} cross-module callers

### Priority 4: Cross-Cutting Concerns ({COUNT} tasks)
- [ ] Error handling strategy
- [ ] Configuration surface
- [ ] Shared mutable state verification
{DOMAIN_SPECIFIC_TASKS}

### Priority 5: Conventions and Patterns ({COUNT} tasks)
- [ ] Dominant coding conventions
- [ ] {DEVIATION_COUNT} convention deviations
- [ ] {COUPLING_COUNT} coupling anomalies

### Priority 6: Gap Investigation ({COUNT} tasks)
- [ ] Implicit initialization sequences
- [ ] Undocumented environment dependencies
- [ ] Hidden coupling not captured by imports

## Completion Criteria
All P1-P4 complete + 10/10 standard questions answerable + no new gotchas in last 3 tasks.

## Context Management
Write findings to /tmp/deep_crawl/findings/{type}/ after each task.
Checkpoint this file every 5 tasks.

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | {N} | 0 |
| 2 | {N} | 0 |
| 3 | {N} | 0 |
| 4 | {N} | 0 |
| 5 | {N} | 0 |
| 6 | {N} | 0 |

Last checkpoint: {TIMESTAMP}
````

### 19.3. `VALIDATION_REPORT.md.template`

**Target path:** `.claude/skills/deep-crawl/templates/VALIDATION_REPORT.md.template`

````markdown
# DEEP_ONBOARD Validation Report

> Document: {PATH}  |  Validated: {TIMESTAMP}
> HEAD: {CURRENT_HASH}  |  Document from: {DOC_HASH}

## Verdict: {PASS | NEEDS FIXES | NEEDS REWORK}

## Check 1: Completeness ({N}/10)
| Q# | Topic | Result | Gap |
|----|-------|--------|-----|
| 1 | Purpose | {P/F} | |
| 2 | Entry | {P/F} | |
| 3 | Flow | {P/F} | |
| 4 | Hazards | {P/F} | |
| 5 | Errors | {P/F} | |
| 6 | External | {P/F} | |
| 7 | State | {P/F} | |
| 8 | Testing | {P/F} | |
| 9 | Gotchas | {P/F} | |
| 10 | Extension | {P/F} | |

## Check 2: [FACT] Accuracy ({N}/10)
| Claim | Location | Result |
|-------|----------|--------|
| {claim} | {loc} | {result} |

## Check 3: [PATTERN] Verification ({N}/3)
| Claim | Stated | Actual | Result |
|-------|--------|--------|--------|
| {claim} | {N/M} | {actual} | {result} |

## Check 4: Coverage
Pillars: {N}/{T}  |  Entry points: {N}/{T}  |  Side effects: {N}/{T}

## Check 5: Redundancy (~{N} wasted tokens)
| Section | Tokens | Redundant? |
|---------|--------|------------|
| {section} | {N} | {Y/N} |

## Check 6: Adversarial ({SCORE}/5 — {VERDICT})
Task: {task}
| Step | Planned | Correct? |
|------|---------|----------|
| File | {path} | {Y/N} |
| Name | {name} | {Y/N} |
| Interface | {iface} | {Y/N} |
| Registration | {point} | {Y/N} |
| Test | {approach} | {Y/N} |
Gap: {description or none}

## Check 7: Freshness
Stable-first: {Y/N}  |  Stale sections: {N}

## Fixes (priority order)
1. {fix}
````

---

## 20. Implementation: `investigation_targets.py`

**Target path:** `lib/investigation_targets.py`

The v1 implementation skeleton (v1 spec Section 18) provides the complete code. Before using it:

1. Run the verification script from Section 4.2 to determine actual key names
2. Update all key references to match verified names
3. Add `"granularity": "module_level"` to `entry_to_side_effect_paths` output
4. Lower the uncertainty threshold from 0.5 to 0.3 (per Appendix C)

No other code changes are required from the v1 skeleton.

---

## 21. Integration in `xray.py`

Same as v1: import `compute_investigation_targets`, call after existing analyses, add to results dict. See Section 4 for the integration snippet.

---

## 22. End-to-End Example

```
STEP 1: xray scan (5 sec, zero API cost)
STEP 2: @deep_crawl full (60-90 min, ~15M tokens)
  Phase 0: Setup workspace
  Phase 1: Plan 33 tasks from xray signals
  Phase 2: Crawl — 28 tasks, 19 modules read, 7 gotchas found
  Phase 3: Synthesize from concatenated findings
  Phase 4: Compress 22K → 14K via 8-step algorithm
  Phase 5: Validate — 10/10 questions, 10/10 accuracy, adversarial PASS
  Phase 6: Deliver — docs/DEEP_ONBOARD.md + CLAUDE.md updated
STEP 3: Every future session auto-loads document via CLAUDE.md (cached)
STEP 4: After changes → @deep_crawl refresh (reads feedback log)
```

---

## 23. Traceability: Problems → Solutions

| # | Problem | Where Fixed |
|---|---------|-------------|
| 1 | No prompt caching | §2.6, §6.2, Phase 5e, Phase 6 |
| 2 | No delivery mechanism | §3, §6.1, Phase 6 |
| 3 | Compression lacks algorithm | Phase 4 (8 steps), Appendix E |
| 4 | Unverified data structures | §4.2 verification script, §20 key table |
| 5 | Evidence standard too strict | §2.8, §5.3, Appendix F |
| 6 | No context management | Phase 0, §10.2 |
| 7 | Adversarial underspecified | Phase 5d, §12.2 Check 6, Appendix D |
| 8 | No feedback loop | §8 (complete section) |
| 9 | Module-level granularity | §4.1, §20, crawl plan template |
| 10 | Multi-file context budget | §2.7, §6.3, Key Interfaces section |

---

*End of specification v2.0.*

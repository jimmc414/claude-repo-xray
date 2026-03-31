---
name: deep-crawl
description: Exhaustive LLM-powered codebase investigation for optimal AI agent onboarding. Builds on X-Ray signals with unlimited investigation budget to produce the highest-quality onboarding document possible.
---

# Deep Crawl

Systematic codebase investigation producing comprehensive onboarding
documents optimized for AI agent consumption via CLAUDE.md delivery with
prompt caching. Depth over brevity — include everything that saves a
downstream agent from opening files.

**Core metric:** File-reads saved per onboarding token. Every token in your output should reduce the number of files a downstream agent needs to open before it can confidently make changes.

## When to Use

- **Use `/deep-crawl full`** when generation cost is not a constraint and you want
  the highest-quality onboarding document for many future agent sessions
- **Use `@deep_crawl full`** as a sequential fallback if `/deep-crawl` is unavailable
- **Use repo_xray** for quick interactive analysis where cost matters
- **Always run xray first** — deep crawl requires xray output as input

## Commands

| Command | Mode | What It Does |
|---------|------|-------------|
| `/deep-crawl full` | **Orchestrated** (parallel sub-agents) | Plan + parallel investigation + assemble + cross-reference + validate + deliver |
| `@deep_crawl full` | Sequential (single-agent fallback) | Same pipeline, sequential investigation |
| `@deep_crawl plan` | Sequential | Generate investigation plan only |
| `@deep_crawl resume` | Sequential | Continue from last checkpoint |
| `@deep_crawl validate` | Sequential | QA an existing DEEP_ONBOARD.md |
| `@deep_crawl refresh` | Sequential | Update for code changes |
| `@deep_crawl focus ./path` | Sequential | Deep crawl a specific subsystem |

## Evidence Standards

| Tag | Standard | Example |
|-----|----------|---------|
| [FACT] | Read specific code, cite file:line | "3x retry with backoff [FACT] (stripe.py:89)" |
| [PATTERN] | Observed in >=3 examples, state count | "DI via __init__ [PATTERN: 12/14 services]" |
| [ABSENCE] | Searched and confirmed non-existence | "No rate limiting [ABSENCE: grep — 0 hits]" |

No inferences or unverified signals in the output document.

**Citation density floor:** Assembled sections must achieve >= 3.0 [FACT] citations
per 100 words. Playbooks must individually achieve >= 3.0 per 100 words.
Investigation findings (raw) should target >= 5.0 per 100 words.

## Output

| File | Purpose | Location |
|------|---------|----------|
| DEEP_ONBOARD.md | Onboarding document (unrestricted, value-driven) | docs/ |
| CLAUDE.md update | Auto-delivery to all sessions | project root |
| .onboard_feedback.log | Usage tracking from downstream agents | docs/ |
| VALIDATION_REPORT.md | QA results | docs/ |

## Prerequisites

Before starting, verify:
1. X-Ray output exists at `/tmp/xray/xray.json` and `/tmp/xray/xray.md`
2. If missing, tell the user: "Run `python xray.py . --output both --out /tmp/xray` first."

## Six-Phase Workflow

### Phase 0: SETUP (Context Management)

**Goal:** Establish working environment and context management strategy.

All intermediate state lives on disk, not in conversation context.

```bash
# Create working directory structure
mkdir -p /tmp/deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks} \
         /tmp/deep_crawl/batch_status \
         /tmp/deep_crawl/sections

# Verify xray output exists
test -f /tmp/xray/xray.json && echo "READY" || echo "Run: python xray.py . --output both --out /tmp/xray"

# Check for existing crawl state (resumability)
if [ -f /tmp/deep_crawl/CRAWL_PLAN.md ]; then
    echo "PREVIOUS CRAWL FOUND"
    head -5 /tmp/deep_crawl/CRAWL_PLAN.md
    git log --oneline -1
    echo "If hashes match, run @deep_crawl resume"
    echo "If not, this is a stale crawl — starting fresh"
fi
```

**Context management rules:**
1. Write findings to disk immediately after each investigation task
2. Read only what's needed for the current task
3. Batch related reads — trace an entire request path before moving on
4. Before Phase 3 (ASSEMBLE), concatenate all findings and read fresh
5. If context gets full, checkpoint and suggest `@deep_crawl resume`
6. Sub-agents write findings directly to disk; you never read findings content until Phase 3
7. Between batches, check only batch_status/ sentinel files, not findings content
8. In Phase 3, assembly sub-agents read findings and write section files to /tmp/deep_crawl/sections/.
   The orchestrator reads only sentinel files until assembly. Gotchas extracted via bash pre-step.

---

### Phase 1: PLAN (Build the Crawl Agenda)

**Input:** X-Ray JSON output including `investigation_targets`.

1. Read `/tmp/xray/xray.md` for orientation
2. Read `investigation_targets` from `/tmp/xray/xray.json`
3. Detect the project domain (web API, CLI tool, ML pipeline, data pipeline, library) using indicators from `.claude/skills/deep-crawl/configs/domain_profiles.json`
4. Produce a prioritized crawl plan using the template at `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template`
5. Save to `/tmp/deep_crawl/CRAWL_PLAN.md`

**Prioritization logic (by information density):**

| Priority | Task Type | Rationale |
|----------|-----------|-----------|
| 1 | Request traces | Highest file-reads-saved per output token |
| 2 | High-uncertainty module deep reads | Name and signature tell you nothing |
| 3 | Pillar behavioral summaries | Most-depended-on modules |
| 4 | Cross-cutting concerns | Learn once, apply everywhere |
| 5 | Conventions and patterns | Prevents style violations |
| 6 | Gap investigation | Catches what xray missed |

Within each priority level, order tasks by information density: request traces by estimated hop count descending (longer traces reveal more cross-module behavior). Module deep reads by uncertainty score descending (highest-uncertainty modules first).

Use extended thinking here to reason about investigation priorities for this specific codebase.

---

### Phase 2: CRAWL (Orchestrated Investigation)

Phase 2 uses parallel sub-agents to investigate the codebase. You act as the **orchestrator** — spawn investigation agents, monitor completion, and verify coverage. Do NOT perform investigation yourself (except as fallback).

#### Orchestration Procedure

**Step 1: Parse and batch.** Read CRAWL_PLAN.md. Group tasks into batches:

| Batch | Tasks | Protocol | Max Agents | Dependencies |
|-------|-------|----------|------------|--------------|
| 1 | All P1 (request traces) | A | 5 | None |
| 2 | All P2 + P3 + P7 (modules + pillars + impact) | B + E | 8 | None |
| 3 | All P4 (cross-cutting concerns incl. async boundaries) | C | 6 | None |
| 4 | All P5 + P6 (conventions + gaps) | D + mixed | 4 | Batches 1-3 |
| 5 | Coverage gaps (if any) | Mixed | 4 | Batch 4 |
| 6 | Change scenarios | F | 3 | Batches 1-4 |

Batches 1-3 are independent — launch them concurrently (all in a single message with multiple Agent tool calls). Batch 4 waits for 1-3 because convention detection and gap investigation benefit from earlier findings being on disk. Batches 5+6 run concurrently (both depend on 1-4, independent of each other).

If a batch has more tasks than its max agents, split into sequential sub-batches of max agents each. All sub-batches within a batch are independent.

**Step 2: Spawn sub-agents.** For each task in a batch, spawn a sub-agent using the Agent tool. Each sub-agent prompt must be **self-contained** with these sections:

```
You are investigating [CODEBASE] at [ROOT_PATH] for an onboarding document.

## Your Task
[Specific task from crawl plan — e.g., "Trace the CLI `kosmos run` path from entry to terminal side effect"]

## Investigation Protocol
[Full text of the relevant protocol (A, B, C, or D) copied verbatim from below]

## Evidence Standards
- [FACT]: Read specific code, cite file:line. Example: "retries 3x (stripe.py:89)"
- [PATTERN]: Observed in >=3 examples, state count. Example: "DI via __init__ (12/14 services)"
- [ABSENCE]: Searched and confirmed non-existence. Example: "No rate limiting (grep — 0 hits)"
- Gotchas must be [FACT] claims with file:line.
- Never include inferences or unverified signals.

## Output
Write findings to: [EXACT PATH — e.g., /tmp/deep_crawl/findings/traces/01_cli_run.md]
When done, write a sentinel: touch /tmp/deep_crawl/batch_status/[TASK_ID].done

## Constraints
- Read-only: never modify source code
- Do NOT spawn sub-agents yourself
- X-Ray output available at /tmp/xray/xray.json and /tmp/xray/xray.md for reference
```

Use `run_in_background: true` for all sub-agents within a batch to maximize parallelism. **Note:** If sub-agents run sequentially despite `run_in_background: true`, each sub-agent still gets a full context window for its investigation task, which is strictly better than sequential investigation in a single context.

**Step 3: Monitor completion.** After launching a batch, check for sentinel files:
```bash
ls /tmp/deep_crawl/batch_status/*.done 2>/dev/null | wc -l
```
When all expected sentinels exist, the batch is complete.

**Step 4: Checkpoint.** After each batch completes, update CRAWL_PLAN.md to mark completed tasks with `[x]`. Sub-agents never write to CRAWL_PLAN.md (concurrent writes would corrupt it).

**Step 5: Handle failures.** After a batch completes:
- Check which sentinel files are missing — those tasks failed
- Retry each failed task once (spawn a new sub-agent)
- If retry fails, log the task ID and continue — Phase 4's coverage check will catch gaps
- If ALL tasks in Batch 1 fail (Agent tool unavailable), switch to **sequential fallback** (see below)

**Step 6: Coverage check.** After all batches complete, verify the stopping criteria and coverage checks below. If coverage is insufficient, spawn Batch 5 with targeted gap-filling tasks.

#### Sequential Fallback

If the Agent tool is unavailable or all Batch 1 spawns fail, execute the crawl plan sequentially using the protocols below directly. This produces shallower results but ensures the pipeline completes. Log a warning: "Running in sequential fallback mode — investigation depth will be reduced."

#### Investigation Protocols

Sub-agents receive these protocol instructions verbatim:

#### Protocol A: Request Trace

```
1. Read the entry point function (full source)
2. Identify the first call to another module
3. Read that function (full source)
4. Repeat until terminal side effect (no hop limit — follow the full chain)
5. Record in /tmp/deep_crawl/findings/traces/{NN}_{name}.md:
   entry_function (file:line)
     → called_function (file:line) — what it does in 1 sentence
     → next_function (file:line) — what it does in 1 sentence
     → [SIDE EFFECT: db.commit] (file:line)
6. Note branching (error paths, conditional logic) at each hop
7. Note data transformations between hops
8. Note gotchas discovered during tracing
```

#### Protocol B: Module Deep Read

```
1. Read the entire module
2. Write to /tmp/deep_crawl/findings/modules/{module_name}.md:
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

#### Protocol C: Cross-Cutting Concern

```
1. Grep for relevant patterns across the entire codebase
2. Categorize the results
3. Read representative examples in full — at least max(3, result_count / 5) examples, sampling from different subsystems
4. Identify the dominant strategy
5. Flag deviations from the dominant strategy
6. Write to /tmp/deep_crawl/findings/cross_cutting/{concern_name}.md
```

**Grep patterns for common concerns:**

```bash
# Error handling
grep -rn "except " --include="*.py" | head -40
grep -rn "except.*pass" --include="*.py"  # swallowed exceptions — high value
grep -rn "retry\|backoff\|fallback" --include="*.py"

# Configuration
grep -rn "os.getenv\|os.environ" --include="*.py"
grep -rn "config\[" --include="*.py"

# Shared mutable state
grep -rn "^[a-z_].*= " --include="*.py" | grep -v "def \|class \|#\|import " | head -30
grep -rn "_instance\|_cache\|_registry\|_pool" --include="*.py"
grep -rn "global " --include="*.py"

# Async/sync boundaries
grep -rn "asyncio\.run\|loop\.run_until_complete\|run_coroutine_threadsafe" --include="*.py"
grep -rn "async def " --include="*.py" | wc -l
```

#### Protocol D: Convention Documentation

```
1. Read examples of the pattern from xray pillar/hotspot list — at least max(5, pillar_count / 3) examples, covering different architectural layers
2. Identify the common structure
3. State the convention as a directive ("always X", "never Y")
4. Read each flagged deviation
5. Assess: intentional variation or oversight?
6. Write to /tmp/deep_crawl/findings/conventions/patterns.md
```

#### Protocol E: Reverse Dependency & Change Impact

```
1. Read xray reverse dependency data for the assigned hub module cluster:
   - .imports.graph[module]["imported_by"] — list of importer modules
   - .imports.distances.hub_modules — sorted by connection count
   - .calls.reverse_lookup[function] — {callers, caller_count, module_count, impact_rating}
   - .calls.high_impact — pre-filtered high-impact functions
2. For each hub module in the cluster, read 2-3 representative callers (full source)
3. Identify:
   - Which callers depend on specific function signatures
   - Which callers depend on specific return value shapes
   - Which callers depend on specific side effects or state mutations
4. Classify changes as safe vs dangerous:
   - Safe: internal refactoring, adding optional parameters, performance changes
   - Dangerous: signature changes, return type changes, side effect changes, exception changes
5. Write to /tmp/deep_crawl/findings/impact/{cluster_name}.md:
   For each hub module:
   - Module name and importer count
   - High-impact functions with caller counts and impact ratings
   - Signature-change consequences (which callers break and how)
   - Behavior-change consequences (which callers produce wrong results)
   - Safe changes list
   - Dangerous changes list with specific blast radius
```

#### Protocol F: Change Scenario Walkthrough

```
1. Read Protocol E impact findings for context on hub modules and blast radii
2. Read Protocol B module findings for behavioral detail
3. Read conventions findings for coding patterns to follow
4. Derive scenarios from domain profile's primary_entity + Extension Points findings:
   - "Add new {primary_entity}" (always include this scenario)
   - "Modify {top hub module} behavior" (top 3 hub modules by connection count)
   - "Add new external dependency" (if >3 external deps detected)
5. For each scenario, build a step-by-step checklist:
   - Ordered steps with file:line targets
   - What to create/modify at each step
   - Validation commands (test commands, grep checks)
   - Common mistakes (derived from gotchas and impact analysis)
6. Write to /tmp/deep_crawl/findings/playbooks/{scenario_name}.md
```

**Checkpoint discipline:** After each batch completes, update CRAWL_PLAN.md to mark completed tasks. In sequential fallback mode, update after every 5 completed tasks.

**When to stop crawling — ALL must be true:**
1. All Priority 1 (request traces) tasks are complete
2. All Priority 2 (high-uncertainty modules) are read
3. All Priority 3 (pillar behavioral summaries) are complete
4. All Priority 4 (cross-cutting concerns) are investigated
5. All Priority 5 (conventions and patterns) are documented
6. All Priority 6 (gap investigation) tasks are attempted
7. All Priority 7 (change impact analysis) tasks are complete
8. Current findings can answer all 12 standard questions (see below)
9. Coverage check passes (see below)

**Coverage check — ALL must be true:**
- At least 50% of subsystems/top-level packages have at least one module deep-read
- Number of modules deep-read >= max(10, file_count / 40)
- Number of request traces >= number of entry points identified by xray
- Every cross-cutting concern has examples from at least 3 different subsystems
- At least one impact card exists for each hub module cluster
- At least one change playbook exists

---

### Phase 3: ASSEMBLE (Orchestrated Section Production)

Phase 3 delegates assembly to parallel sub-agents, each producing specific template sections from their assigned subset of findings. The orchestrator's role is: spawn agents, monitor sentinels, concatenate section files. Do NOT read findings content yourself.

#### Value Hierarchy (shared with all assembly sub-agents)

- **Tier 1 (MUST include, never cut):** Bugs, security issues, data loss risks, crashes, dead code, broken features
- **Tier 2 (MUST include, cut only if literally duplicated):** Behavioral gotchas, non-obvious side effects, error handling deviations, initialization order dependencies, state leakage risks
- **Tier 3 (include unless redundant with another finding):** Patterns with N/M counts, conventions, structural facts, configuration details
- **Tier 4 (include unless literally duplicated elsewhere in this document; reference xray for raw structural dumps only):** Class skeletons, import graphs, file listings

Phase 4 may merge Tier 3-4 entries that describe the same fact, but must not drop distinct findings. When in doubt, keep both. Phase 4 may NEVER cut Tier 1-2 content.

#### Step 0: Concatenate findings (word count reference for retention check)

```bash
cat /tmp/deep_crawl/findings/traces/*.md \
    /tmp/deep_crawl/findings/modules/*.md \
    /tmp/deep_crawl/findings/cross_cutting/*.md \
    /tmp/deep_crawl/findings/conventions/*.md \
    /tmp/deep_crawl/findings/impact/*.md \
    /tmp/deep_crawl/findings/playbooks/*.md \
    > /tmp/deep_crawl/SYNTHESIS_INPUT.md
wc -w /tmp/deep_crawl/SYNTHESIS_INPUT.md
```

Record the total word count — you will use it to verify retention in Step 8.

#### Step 1: Pre-extract gotchas via bash

No sub-agent needed. Extract formal gotcha sections from all findings so S5 has them consolidated:

```bash
for f in /tmp/deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks}/*.md; do
    gotcha_line=$(grep -n "^## Gotcha\|^### Gotcha" "$f" | head -1 | cut -d: -f1)
    if [ -n "$gotcha_line" ]; then
        echo "### From: $(basename "$f" .md)"
        tail -n +"$gotcha_line" "$f"
        echo ""
    fi
done > /tmp/deep_crawl/sections/gotcha_extracts.md
```

#### Step 1a: Extract state diagrams from trace findings

No sub-agent needed. Mechanically grep trace findings for state transition patterns and generate mermaid state diagrams if found:

```bash
# Look for state transition patterns in trace findings
STATE_PATTERNS=$(grep -rn "state\|status\|phase\|stage\|transition\|→.*→" \
    /tmp/deep_crawl/findings/traces/*.md 2>/dev/null | head -20)

if [ -n "$STATE_PATTERNS" ]; then
    echo "## State Diagrams" > /tmp/deep_crawl/sections/state_diagrams.md
    echo "" >> /tmp/deep_crawl/sections/state_diagrams.md
    echo "State transitions extracted from request traces:" >> /tmp/deep_crawl/sections/state_diagrams.md
    echo "" >> /tmp/deep_crawl/sections/state_diagrams.md
    echo '```mermaid' >> /tmp/deep_crawl/sections/state_diagrams.md
    echo "stateDiagram-v2" >> /tmp/deep_crawl/sections/state_diagrams.md
    # Assembly agent S1 will populate the actual transitions
    echo "    [*] --> TODO_POPULATE_FROM_TRACES" >> /tmp/deep_crawl/sections/state_diagrams.md
    echo '```' >> /tmp/deep_crawl/sections/state_diagrams.md
    echo "State patterns found — S1 assembly agent will include in Critical Paths section header."
else
    echo "No state transition patterns found in traces."
    touch /tmp/deep_crawl/sections/state_diagrams.md  # empty file
fi
```

If state_diagrams.md has content, assembly agent S1 includes it at the top of the Critical Paths section.

#### Step 1b: Temporarily remove CLAUDE.md compression contamination

Sub-agents spawn with fresh context and read CLAUDE.md files automatically. If the project's CLAUDE.md references "compressed intelligence" or similar framing, sub-agents absorb "my job is compression" before reading their task prompt. Temporarily rename CLAUDE.md files to prevent this:

```bash
# Rename project CLAUDE.md (and parent directory's if it exists)
ROOT_PATH=$(pwd)
[ -f "$ROOT_PATH/CLAUDE.md" ] && mv "$ROOT_PATH/CLAUDE.md" "$ROOT_PATH/CLAUDE.md.assembly_save"
PARENT_PATH=$(dirname "$ROOT_PATH")
[ -f "$PARENT_PATH/CLAUDE.md" ] && mv "$PARENT_PATH/CLAUDE.md" "$PARENT_PATH/CLAUDE.md.assembly_save"
```

**IMPORTANT:** Restore these files after all sub-agents complete (after Step 9). See Step 9 completion.

#### Step 2: Spawn S1–S4 in parallel

Launch 4 assembly sub-agents simultaneously (all with `run_in_background: true`):

| Agent | Sections | Input Files | Est. Input |
|-------|----------|-------------|-----------|
| **S1** | Critical Paths | `findings/traces/*.md` | ~11K words |
| **S2** | Module Behavioral Index, Domain Glossary | `findings/modules/*.md` | ~25K words |
| **S3** | Key Interfaces, Error Handling, Shared State | `findings/modules/{research_director,llm,executor,code_generator,code_validator}.md` + `findings/cross_cutting/{agent_communication,error_handling,initialization,database_storage}.md` | ~18K words |
| **S4** | Configuration Surface, Conventions | `findings/cross_cutting/{configuration,env_dependencies,llm_providers}.md` + `findings/modules/config.md` + `findings/conventions/*.md` | ~16K words |

**Note:** The file lists above are examples based on R5/Kosmos. Adjust filenames to match actual findings on disk. Use `ls /tmp/deep_crawl/findings/{category}/` to discover actual filenames before constructing prompts.

Each sub-agent prompt must be self-contained:

```
You are assembling investigation findings into onboarding document sections. Include every finding — do not summarize, condense, or compress.

## Your Task
Produce these template sections: [SECTION NAMES]

## Input
Read ONLY these files: [FILE PATHS]

## Template Format
[Copy the relevant section templates verbatim from .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template]

## Rules
- INCLUDE EVERY FINDING. The output context window is 1M tokens. Your section will consume less than 5% of available context. There is no reason to drop, summarize, or condense any finding.
- The ONLY reason to exclude a finding is if it is literally stated elsewhere in your section or is derivable from the module's file name alone.
- Place each finding at full fidelity with its original [FACT], [PATTERN], or [ABSENCE] tag and file:line citation.
- When multiple findings describe the same code from different angles, include ALL of them — each angle provides context the others miss.
- Write conventions as directives — "Always X", "Never Y".
- Your output should be 80-100% of your input word count. If you produce less than 80%, you have dropped findings. Re-read your input and find what you missed.

## Secondary Output
Collect every gotcha/warning/danger note encountered → write to:
/tmp/deep_crawl/sections/gotchas_from_S{N}.md

## Output
Write each section to its own file: /tmp/deep_crawl/sections/{section_name}.md
  (e.g., critical_paths.md, module_index.md, domain_glossary.md)
Sentinel: touch /tmp/deep_crawl/sections/S{N}.done

## Constraints
- Read-only: never modify source code
- Do NOT spawn sub-agents yourself
```

#### Step 3: Monitor S1–S4 completion

Check for sentinel files. All 4 must complete before proceeding:
```bash
ls /tmp/deep_crawl/sections/S{1,2,3,4}.done 2>/dev/null | wc -l
```

#### Step 4: Spawn S5 AND S6 in parallel (depend on S1–S4 gotcha outputs)

Launch S5 and S6 simultaneously (both with `run_in_background: true`):

| Agent | Sections | Input Files | Est. Input |
|-------|----------|-------------|-----------|
| **S5** | Gotchas, Hazards, Extension Points, Reading Order | `sections/gotcha_extracts.md` + `sections/gotchas_from_S{1,2,3,4}.md` + CRAWL_PLAN.md (for structure) | ~12K words |
| **S6** | Change Impact Index, Data Contracts, Change Playbooks | `findings/impact/*.md` + `findings/playbooks/*.md` + `findings/modules/*.md` (grep for Pydantic/dataclass) + `sections/state_diagrams.md` | ~15K words |

S5's prompt follows the same template as S1–S4. Its template sections are Gotchas, Hazards — Do Not Read, Extension Points, and Reading Order from DEEP_ONBOARD.md.template.

S6's prompt for **Data Contracts**: extract all Pydantic models, dataclasses, TypedDicts, and NamedTuples from module findings + xray `investigation_targets.domain_entities`. Format as table with Model, File, Type, Key Fields, Serialization, Gotcha.

S6's prompt for **Change Impact Index**: organize impact findings by hub module cluster. Each cluster gets a table showing importers, high-impact functions, signature-change consequences, behavior-change consequences, safe vs dangerous changes.

S6's prompt for **Change Playbooks**: organize playbook findings into step-by-step checklists with validation commands and common mistakes.

S6's prompt for **Change Playbooks** quality checks:
- Each playbook individually: >= 800 words, >= 30 [FACT] citations
- Each playbook must have: 8-10 common mistakes with behavioral explanations
- Citation density per playbook: >= 3.0 [FACT] per 100 words
- If a reference playbook exists (e.g., modify_llm_provider.md), use it as the quality bar

#### Step 5: Monitor S5+S6 completion

```bash
ls /tmp/deep_crawl/sections/S{5,6}.done 2>/dev/null | wc -l  # expect 2
```

#### Step 6: Orchestrator produces small sections

The orchestrator writes these directly (no sub-agent needed — they are small, <500 words total):

- **Identity** — from xray.md (already in context from Phase 1)
- **Gaps** — from Phase 2 coverage check results
- **Header metadata** — file count, token count, timestamp, git hash
- **Footer metadata** — task counts, coverage scope, evidence counts, hub module count, playbook count
- **Environment Bootstrap** — read assembled `config_surface.md` + cross-cutting findings for external systems. Produce short bootstrap checklist: required services, minimum env vars, setup commands, verify command. Write to `sections/environment_bootstrap.md`.

Write to `/tmp/deep_crawl/sections/header.md`, `/tmp/deep_crawl/sections/identity.md`, `/tmp/deep_crawl/sections/gaps.md`, `/tmp/deep_crawl/sections/environment_bootstrap.md`, `/tmp/deep_crawl/sections/footer.md`.

#### Step 7: Assemble DRAFT_ONBOARD.md

Concatenate all section files in template order:

```bash
cat /tmp/deep_crawl/sections/header.md \
    /tmp/deep_crawl/sections/identity.md \
    /tmp/deep_crawl/sections/critical_paths.md \
    /tmp/deep_crawl/sections/module_index.md \
    /tmp/deep_crawl/sections/change_impact_index.md \
    /tmp/deep_crawl/sections/key_interfaces.md \
    /tmp/deep_crawl/sections/data_contracts.md \
    /tmp/deep_crawl/sections/error_handling.md \
    /tmp/deep_crawl/sections/shared_state.md \
    /tmp/deep_crawl/sections/domain_glossary.md \
    /tmp/deep_crawl/sections/config_surface.md \
    /tmp/deep_crawl/sections/conventions.md \
    /tmp/deep_crawl/sections/gotchas.md \
    /tmp/deep_crawl/sections/hazards.md \
    /tmp/deep_crawl/sections/extension_points.md \
    /tmp/deep_crawl/sections/change_playbooks.md \
    /tmp/deep_crawl/sections/reading_order.md \
    /tmp/deep_crawl/sections/environment_bootstrap.md \
    /tmp/deep_crawl/sections/gaps.md \
    /tmp/deep_crawl/sections/footer.md \
    > /tmp/deep_crawl/DRAFT_ONBOARD.md
```

#### Step 8: Verify retention

```bash
wc -w /tmp/deep_crawl/SYNTHESIS_INPUT.md /tmp/deep_crawl/DRAFT_ONBOARD.md
```

If the draft is under 80% of SYNTHESIS_INPUT.md word count, an assembly agent dropped findings. Identify which section agent under-produced by comparing each section's word count against its input word count, and re-spawn that agent with: "Your previous output was N words from M words of input. Include every finding — you dropped content. The context window is 1M tokens and there is no reason to exclude findings."

#### Step 8b: Fact-level completeness check

This is a mechanical step — no LLM needed. Extract all file:line citations that appear with [FACT] tags in SYNTHESIS_INPUT.md and verify each appears in DRAFT_ONBOARD.md.

```bash
# Extract unique file:line citations from [FACT]-tagged lines in findings
grep '\[FACT' /tmp/deep_crawl/SYNTHESIS_INPUT.md \
  | grep -oP '[\w/]+\.py:\d+' | sort -u \
  > /tmp/deep_crawl/_synthesis_fact_citations.txt

# Extract unique file:line citations from assembled draft
grep -oP '[\w/]+\.py:\d+' /tmp/deep_crawl/DRAFT_ONBOARD.md \
  | sort -u > /tmp/deep_crawl/_draft_citations.txt

# Find dropped citations
comm -23 /tmp/deep_crawl/_synthesis_fact_citations.txt \
         /tmp/deep_crawl/_draft_citations.txt \
  > /tmp/deep_crawl/_dropped_citations.txt

TOTAL=$(wc -l < /tmp/deep_crawl/_synthesis_fact_citations.txt)
RETAINED=$(comm -12 /tmp/deep_crawl/_synthesis_fact_citations.txt /tmp/deep_crawl/_draft_citations.txt | wc -l)
DROPPED=$(wc -l < /tmp/deep_crawl/_dropped_citations.txt)

echo "Fact citations: $RETAINED/$TOTAL retained, $DROPPED dropped"
```

If DROPPED > 0, recover the dropped facts:

```bash
# For each dropped citation, extract the full [FACT] line from SYNTHESIS_INPUT.md
while IFS= read -r cite; do
    grep "$cite" /tmp/deep_crawl/SYNTHESIS_INPUT.md | grep '\[FACT'
done < /tmp/deep_crawl/_dropped_citations.txt > /tmp/deep_crawl/_dropped_facts.txt
```

Classify each dropped fact by the section it belongs to (using the finding file it came from):
- Facts from `findings/traces/` → append to Critical Paths section
- Facts from `findings/modules/` → append to Module Behavioral Index section
- Facts from `findings/cross_cutting/` → append to the corresponding section (Error Handling, Shared State, etc.)
- Facts from `findings/conventions/` → append to Conventions section

Append dropped facts to the appropriate section files in `/tmp/deep_crawl/sections/`, then re-concatenate DRAFT_ONBOARD.md using the Step 7 concatenation command.

Log: `Step 8b: {RETAINED}/{TOTAL} fact citations retained ({PCT}%). Recovered {N} dropped facts.`

If DROPPED == 0: `Step 8b: {TOTAL}/{TOTAL} fact citations retained (100%). No recovery needed.`

Log fact-level retention to `/tmp/deep_crawl/REFINE_LOG.md`:
```
## Fact-Level Retention
Citations in findings: {N}
Citations in draft: {M}
Retained: {R}/{N} ({PCT}%)
Dropped and recovered: {D}
```

#### Step 9: Delegate refinement and validation (sequential)

Phase 4 and Phase 5 are delegated to **separate** sub-agents to prevent self-validation bias. The cross-referencer never sees the validator's output, and the validator cannot see the raw findings — only the cross-referenced document and the codebase.

**Sub-agent 1: Cross-referencer**

Spawn a sub-agent for Phase 4 only:

```
You are cross-referencing a DEEP_ONBOARD.md draft for an AI agent onboarding document. This is an additive-only process — you may NOT delete, merge, summarize, or compress any content.

## Input Files
- /tmp/deep_crawl/DRAFT_ONBOARD.md — the assembled draft to cross-reference
- /tmp/deep_crawl/CRAWL_PLAN.md — the investigation plan (for coverage context)
- .claude/skills/deep-crawl/configs/compression_targets.json — for min_tokens floor check

## Your Task
Execute Phase 4 (CROSS-REFERENCE) — additive only, no deletions.
Write the cross-referenced document to /tmp/deep_crawl/DEEP_ONBOARD.md.
Write the log to /tmp/deep_crawl/REFINE_LOG.md.

When done: touch /tmp/deep_crawl/REFINE.done

[Copy Phase 4 instructions verbatim from SKILL.md]
```

Use `run_in_background: true`.

**Cross-referencer completion gate:** After REFINE.done appears, verify:
```bash
# Artifacts must exist
test -f /tmp/deep_crawl/DEEP_ONBOARD.md && test -f /tmp/deep_crawl/REFINE_LOG.md && echo "PASS" || echo "FAIL"

# Cross-referencing is strictly additive — final must be >= draft
wc -w /tmp/deep_crawl/DRAFT_ONBOARD.md /tmp/deep_crawl/DEEP_ONBOARD.md
# If DEEP_ONBOARD word count < DRAFT_ONBOARD, re-spawn with: "Your output lost words. Cross-referencing is additive only — you may NOT delete content. Re-execute all 4 steps."
```

**Sub-agent 2: Validator**

After the cross-referencer completes and passes its gate, spawn a **separate** sub-agent for Phase 5:

```
You are validating a DEEP_ONBOARD.md document for an AI agent onboarding document.

## Input Files
- /tmp/deep_crawl/DEEP_ONBOARD.md — the refined document to validate
- /tmp/deep_crawl/CRAWL_PLAN.md — the investigation plan (for coverage targets only)
- Codebase at {ROOT_PATH} — read source files to verify claims

## NOT Available to You
You do NOT have access to SYNTHESIS_INPUT.md, findings/, or xray.md.
You validate the document as a standalone artifact — if information is missing, it's a gap.

## Your Task
Execute Phase 5 (VALIDATE) from the deep-crawl skill instructions below. Phase 5 ONLY.
You may read codebase source files to verify claims and check coverage.
You may NOT modify DEEP_ONBOARD.md — report gaps in VALIDATION_REPORT.md only.
Write the validation report to /tmp/deep_crawl/VALIDATION_REPORT.md.

When done: touch /tmp/deep_crawl/VALIDATE.done

[Copy Phase 5 instructions verbatim from SKILL.md]
```

Use `run_in_background: true`.

**Validator completion gate:** After VALIDATE.done appears, verify:
```bash
# Report must exist with required sections
test -f /tmp/deep_crawl/VALIDATION_REPORT.md && echo "PASS" || echo "FAIL"
grep -c "^### Q[0-9]" /tmp/deep_crawl/VALIDATION_REPORT.md  # expect 12
grep -c "^### Spot Check" /tmp/deep_crawl/VALIDATION_REPORT.md  # expect 10
grep -c "Adversarial Simulation" /tmp/deep_crawl/VALIDATION_REPORT.md  # expect >= 1
```

**Orchestrator spot-check (before remediation):** The orchestrator reads 5 [FACT]
citations from DEEP_ONBOARD.md and verifies them by reading the actual source file.
Priority: new sections > modified sections > unchanged sections. Log:
```bash
# For each spot-check:
# Claim: "{quoted claim}" [FACT] ({file}:{line})
# Source: {what the actual file says}
# Verdict: CONFIRMED | WRONG_LINE | WRONG_CONTENT | FILE_MISSING
```
If >= 2/5 spot-checks fail, re-spawn S6 with corrective instructions before proceeding.

**Remediation loop:** After the validator completes, parse VALIDATION_REPORT.md for gaps:

```bash
# Check for NO or PARTIAL standard questions
grep -E "^\*\*Rating:\*\* (NO|PARTIAL)" /tmp/deep_crawl/VALIDATION_REPORT.md
```

If any standard question is NO or PARTIAL, or if the adversarial simulation is PARTIAL/FAIL:

**Step R1: Map gaps to investigation tasks.** For each gap, determine the investigation protocol and target:

| Gap Type | Protocol | Target | Finding Output |
|----------|----------|--------|----------------|
| Q1 PURPOSE unanswerable | B | Entry point modules | findings/modules/gap_purpose.md |
| Q2 ENTRY missing entry points | A | Untraced entry points | findings/traces/gap_entry.md |
| Q3 FLOW incomplete path | A | Untraceable critical paths | findings/traces/gap_flow.md |
| Q4 HAZARDS not documented | B | Large/generated files from xray | findings/modules/gap_hazards.md |
| Q5 ERRORS incomplete | C | Error handling patterns | findings/cross_cutting/gap_errors.md |
| Q6 EXTERNAL missing systems | C | External system patterns (grep: requests, httpx, boto, redis) | findings/cross_cutting/gap_external.md |
| Q7 STATE incomplete | C | Shared state patterns (grep: global, _instance, _cache) | findings/cross_cutting/gap_state.md |
| Q8 TESTING thin | D | Testing conventions (read conftest.py, sample test files) | findings/conventions/gap_testing.md |
| Q9 GOTCHAS insufficient | (review) | Re-scan existing findings for uncollected gotchas | findings/cross_cutting/gap_gotchas.md |
| Q10 EXTENSION missing | B | Primary entity base class + extension patterns | findings/modules/gap_extension.md |
| Q11 IMPACT missing | E | Hub modules from xray | findings/impact/gap_impact.md |
| Q12 BOOTSTRAP missing | C | Setup patterns (requirements.txt, Dockerfile, Makefile) | findings/cross_cutting/gap_bootstrap.md |
| Adversarial step N failed | B | Module referenced in failing step | findings/modules/gap_adversarial_{N}.md |

**Step R2: Spawn targeted investigation agents.** For each gap, spawn one sub-agent with the appropriate protocol. Use `run_in_background: true` for parallel execution. Sub-agent prompts follow the standard Phase 2 format:

```
You are investigating {CODEBASE} at {ROOT_PATH} to fill a specific gap in the onboarding document.

## Gap Being Filled
{Question text} was rated {NO/PARTIAL} because: {validator's explanation}

## Investigation Protocol
{Protocol A/B/C/D text, copied verbatim}

## Specific Target
{What to investigate — e.g., "Read conftest.py, 3 representative test files, pytest.ini. Document fixture patterns, mocking strategies, coverage configuration, marker usage."}

## Evidence Standards
- [FACT]: Read specific code, cite file:line. Example: "retries 3x (stripe.py:89)"
- [PATTERN]: Observed in >=3 examples, state count. Example: "DI via __init__ (12/14 services)"
- [ABSENCE]: Searched and confirmed non-existence. Example: "No rate limiting (grep — 0 hits)"

## Output
Write findings to: /tmp/deep_crawl/findings/{category}/gap_{name}.md
When done: touch /tmp/deep_crawl/batch_status/gap_{name}.done
```

**Step R3: Wait for completion.** Monitor sentinel files:
```bash
ls /tmp/deep_crawl/batch_status/gap_*.done 2>/dev/null | wc -l
```

**Step R4: Patch DEEP_ONBOARD.md.** For each new finding:
1. Read the finding file
2. Determine which section of DEEP_ONBOARD.md it belongs to
3. Append the content to the appropriate section (ADDITIVE ONLY — do not remove existing content)
4. Update the Gaps section to mark the gap as addressed

Log to REFINE_LOG.md: `Gap closure: Investigated {N} gaps, added {M} words to {K} sections`

**Step R5: Re-validate.** Re-spawn the validator to check ONLY the previously-failed questions:

```
You are re-validating specific questions that previously failed.

## Questions to Re-check
{List of previously NO/PARTIAL questions}

## Input
- /tmp/deep_crawl/DEEP_ONBOARD.md (updated with gap investigation results)
- Codebase at {ROOT_PATH}

Append results to /tmp/deep_crawl/VALIDATION_REPORT.md under "## Gap Closure Re-validation"
When done: touch /tmp/deep_crawl/REVALIDATE.done
```

**Step R6: Accept or deliver.** If all re-checked questions are now YES, proceed to delivery. If any remain NO/PARTIAL after one investigation cycle, note in Gaps section and deliver. **Maximum 1 gap-closure cycle** to prevent infinite loops.

### Partial Re-investigation Protocol

When re-investigating specific sections (rather than a full crawl), the same quality
standards apply. The orchestrator MUST NOT assemble or validate manually.

**Rules:**
1. **S6 assembly is mandatory.** Spawn a sub-agent to assemble replacement sections
   from findings. The orchestrator reads only sentinel files + word counts, never
   assembles section content itself.
2. **Independent validation is mandatory.** Spawn a separate validator agent.
   The validator receives ONLY the patched document + codebase, not findings.
3. **Orchestrator spot-checks 5 citations.** Before declaring quality gate passed,
   the orchestrator reads 5 [FACT] citations from the assembled sections and verifies
   each against actual source code. Log results.
4. **Quality gate checks are per-section, not aggregate.** Each re-investigated
   section must independently meet the citation density floor (see Evidence Standards).
5. **Findings-to-section retention floor.** S6 output for each section must retain
   >= 60% of the corresponding findings word count. If below 60%, the orchestrator
   must direct S6 to include more detail.

**Partial re-investigation follows this sequence:**
1. Spawn investigation agents (Protocol E/F) for the sections being re-done
2. Wait for all agents; verify findings files have `wc -w > 500`
3. Spawn S6 agent to assemble replacement sections from findings
4. Verify S6 output: citation density >= 3.0/100w per section, word count retention >= 60%
5. Patch the document (replace specific sections)
6. Spawn independent validator on the patched document
7. Run quality gate checks (per-section, not aggregate)
8. Update DECLARATION.md with actual metrics

**Step 10: Restore CLAUDE.md files.**

After all sub-agents (S1-S6, cross-referencer, validator) have completed:

```bash
ROOT_PATH=$(pwd)
[ -f "$ROOT_PATH/CLAUDE.md.assembly_save" ] && mv "$ROOT_PATH/CLAUDE.md.assembly_save" "$ROOT_PATH/CLAUDE.md"
PARENT_PATH=$(dirname "$ROOT_PATH")
[ -f "$PARENT_PATH/CLAUDE.md.assembly_save" ] && mv "$PARENT_PATH/CLAUDE.md.assembly_save" "$PARENT_PATH/CLAUDE.md"
```

If the Agent tool is unavailable, execute Phase 4 then Phase 5 inline (sequential fallback). Never interleave — complete Phase 4 fully before starting Phase 5.

#### Sequential Fallback

If the Agent tool is unavailable, process findings in category groups sequentially:
1. Read `findings/traces/*.md` → write critical_paths.md
2. Read `findings/modules/*.md` → write module_index.md + domain_glossary.md
3. Read key module + cross-cutting files → write key_interfaces.md + error_handling.md + shared_state.md
4. Read config + convention files → write config_surface.md + conventions.md
5. Read gotcha extracts → write gotchas.md + hazards.md + extension_points.md + reading_order.md

Write each section to disk before reading the next group. Do NOT read SYNTHESIS_INPUT.md monolithically — that is the failure mode this design prevents.

---

### Phase 4: CROSS-REFERENCE (Additive Only — No Deletions)

This phase adds cross-references between independently-assembled sections. It may NOT delete, merge, summarize, or compress any content. Every operation is strictly additive.

**Step 1: Measure.**
```bash
wc -w /tmp/deep_crawl/DRAFT_ONBOARD.md | awk '{printf "~%d tokens\n", $1 * 1.3}'
```
Read `min_tokens` from `.claude/skills/deep-crawl/configs/compression_targets.json`. If below floor, the assembly agents dropped findings — re-spawn the undersized section agents with explicit "include every finding" instructions. Do NOT proceed until the floor is met.

Log to `/tmp/deep_crawl/REFINE_LOG.md`:
```
## Phase 4 Cross-Reference Log
Step 1: PASS — draft is ~{N} tokens (floor: {min_tokens})
```

**Step 2: Add cross-references between sections.** The draft was assembled from 5 independent agents who couldn't reference each other's output. Add links:
1. Module Index entries mentioned in Critical Paths get `(see Module Index)`.
2. Gotchas relating to traced paths get `(see Critical Path N)`.
3. Critical Path hops that have Module Index entries get `(see Module Index: {module})`.
4. Error Handling deviations referenced in Gotchas get cross-links.
5. Change Impact entries get `(see Module Index)` links.
6. Change Playbook steps referencing gotchas get `(see Gotcha #N)` links.
7. Data Contracts in Critical Paths get `(see Data Contracts)` links.
8. Environment Bootstrap services get `(see Configuration Surface)` links.
9. Do NOT rewrite, merge, or remove any content. Only add parenthetical cross-references.

Log: `Step 2: Added {N} cross-references`

**Step 3: Verify completeness.** Two checks:
- **3a. Standard Questions:** Attempt to answer all 12 standard questions. If any is unanswerable, note in Gaps section (do NOT fabricate content — the assembly agents produced what the investigation found).
- **3b. Coverage Breadth:** Check subsystem coverage, pillar coverage, entry point traces, cross-cutting concerns. Note gaps in Gaps section.

Log: `Step 3: {N}/10 questions answerable, {gaps noted}`

**Step 4: Verify caching structure.** Confirm stable sections before volatile sections.

**Completion gate:** REFINE_LOG.md must have entries for Steps 1-3. Word count of DEEP_ONBOARD.md must be >= word count of DRAFT_ONBOARD.md (cross-references only add words, never remove).

Write final version to `/tmp/deep_crawl/DEEP_ONBOARD.md`.

```bash
wc -w /tmp/deep_crawl/DRAFT_ONBOARD.md /tmp/deep_crawl/DEEP_ONBOARD.md
# DEEP_ONBOARD >= DRAFT_ONBOARD (strictly additive)
```

---

### Phase 5: VALIDATE (Quality Assurance)

#### 5a. Standard Questions Test

For each of the 12 standard questions, attempt to answer using ONLY DEEP_ONBOARD.md.
Write each answer to VALIDATION_REPORT.md in this format:

```
### Q1. PURPOSE: What does this codebase do?
**Rating:** YES / NO / PARTIAL
**Answer:** [1-2 sentence answer derived from the document — proving you read it, not just grepped]
**Source section:** [which section answered this]
```

If rating is NO or PARTIAL, also include:
```
**Gap:** [1-sentence description of what's missing]
**Investigation needed:** [Protocol A/B/C/D] targeting [specific files or patterns]
**Expected output:** [what the investigation should produce]
```

Example:
```
### Q8. TESTING: What are the testing conventions?
**Rating:** PARTIAL
**Answer:** Conventions 14-20 cover test structure, organization, markers, fixtures, mocking, helpers, pytest config. But the document self-identifies testing as a gap.
**Source section:** Conventions sections 14-20, Gaps section
**Gap:** Fixture patterns and mocking strategies are surface-level only. No examples of how conftest.py layers fixtures or how tests mock LLM calls.
**Investigation needed:** Protocol D targeting conftest.py, tests/unit/agents/test_research_director.py, tests/unit/core/test_llm.py
**Expected output:** Detailed testing conventions with fixture hierarchy, LLM mocking patterns, database isolation strategies
```

The 12 standard questions:

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
Q11. IMPACT:     If I change the most-connected module, what files are affected?
Q12. BOOTSTRAP:  How do I set up a dev environment and run tests from scratch?

If any question is NO or PARTIAL, fix the gap in DEEP_ONBOARD.md before continuing.

#### 5a-bis. Coverage Breadth Test

| Metric | Target | Actual |
|--------|--------|--------|
| Subsystems with >= 1 documented module | 100% | {N}/{T} |
| Xray pillars in Module Index | 100% | {N}/{T} |
| Entry points with traces | 100% | {N}/{T} |
| Cross-cutting concerns from crawl plan | 100% | {N}/{T} |
| Module Index entries vs core files | >= 25% | {N}/{T} |

If any metric is below target, return to Phase 3 findings and add content.

#### 5b. Spot-Check Verification

Select 10 [FACT] claims from DEEP_ONBOARD.md. Priority: Gotchas first, then Critical Paths.
For each claim, read the referenced file:line in the actual codebase and verify accuracy.

Write each check to VALIDATION_REPORT.md:
```
### Spot Check {N}
**Claim:** "{quoted claim}" ({file}:{line})
**Actual code:** {what the code actually says}
**Verdict:** CONFIRMED / INACCURATE / STALE
**Action:** {none / corrected in document / noted as gap}
```

#### 5c. Redundancy Check

For each section: "Is this content literally duplicated from another section in this document?" If yes, cut the duplicate. Do NOT cut synthesized information just because the raw data is grepable — the synthesis (cross-module patterns, behavioral descriptions, contextual annotations) is the value.

WARNING: Do NOT flag content as "redundant" because it could be derived from source code. The purpose of this document is to save agents from reading source. Content is redundant ONLY if literally duplicated within this document.

#### 5d. Adversarial Simulation

**Step 1:** Determine the most common modification task for this domain:
- Agent-based system -> "Add a new agent type with custom behavior"

**Step 2:** Using ONLY DEEP_ONBOARD.md, write a concrete 5-step implementation plan.
Write the plan to VALIDATION_REPORT.md under `### Adversarial Simulation`.

**Step 3:** Read actual codebase files to verify each step would produce correct code.
For each step, note whether the document gave correct, incorrect, or missing guidance.
If incorrect or missing, include:
```
**Missing info:** [what the document should have said]
**Source module:** [which module contains the correct information]
**Investigation needed:** Protocol B targeting {module path}
```

**Step 4:** Score: PASS (5/5 correct), PARTIAL (3-4/5), FAIL (<=2/5).
If PARTIAL or FAIL, identify what's missing from DEEP_ONBOARD.md and add it.

#### 5e. Caching Structure Verification

Confirm stable sections (Identity, Critical Paths, Module Index) come before volatile sections (Gotchas, Gaps). This maximizes prompt cache prefix hits.

**Phase 5 completion gate:** VALIDATION_REPORT.md must contain all of:
- 12 standard question answers with ratings
- Coverage breadth table with actuals filled in
- 10 spot-check entries with verdicts
- Redundancy check results
- Adversarial simulation plan with score
- Caching structure verification result

```bash
# Verify report completeness
grep -c "^### Q[0-9]" /tmp/deep_crawl/VALIDATION_REPORT.md  # expect 12
grep -c "^### Spot Check" /tmp/deep_crawl/VALIDATION_REPORT.md  # expect 10
grep -c "Adversarial Simulation" /tmp/deep_crawl/VALIDATION_REPORT.md  # expect >= 1
```

Write validation results to `/tmp/deep_crawl/VALIDATION_REPORT.md`.

---

### Phase 6: DELIVER (Package and Configure)

**Step 1:** Copy to project:
```bash
mkdir -p docs
cp /tmp/deep_crawl/DEEP_ONBOARD.md docs/DEEP_ONBOARD.md
```

**Step 2:** Configure CLAUDE.md for automatic delivery:
```bash
if [ -f CLAUDE.md ]; then
    grep -q "DEEP_ONBOARD" CLAUDE.md || echo -e "\n# Codebase Onboarding\nRead docs/DEEP_ONBOARD.md before starting any task. It contains verified behavioral documentation, critical paths, gotchas, and conventions for this codebase." >> CLAUDE.md
else
    cat > CLAUDE.md << 'CLEOF'
# Project Instructions

## Codebase Onboarding
Read docs/DEEP_ONBOARD.md before starting any task. It contains verified behavioral documentation, critical paths, gotchas, and conventions for this codebase.
CLEOF
fi
```

**Step 3:** Copy validation report:
```bash
cp /tmp/deep_crawl/VALIDATION_REPORT.md docs/DEEP_ONBOARD_VALIDATION.md
```

**Step 4:** Report to user:
```
Deep Crawl Complete
===================
Codebase: {files} files, ~{tokens} tokens
Document: ~{doc_tokens} tokens covering {tokens} token codebase
Crawl: {tasks_completed}/{tasks_planned} tasks
Questions answerable: {score}/12
Claims verified: {verified}/10
Adversarial test: {PASS/PARTIAL/FAIL}
Gotchas documented: {count}
Request traces: {count}

Delivered to: docs/DEEP_ONBOARD.md
CLAUDE.md: {UPDATED/CREATED} — document will auto-load in all sessions
Prompt caching: Active — subsequent sessions read at ~90% reduced cost
```

---

## Evidence Standards (Detailed)

Not all claims have the same epistemological status. Use these tags:

| Level | Tag | Standard | Example |
|-------|-----|----------|---------|
| Verified Fact | `[FACT]` | Read the specific code, confirmed at cited file:line | "payment_service retries 3x with exponential backoff (providers/stripe.py:89)" |
| Verified Pattern | `[PATTERN]` | Observed in >=3 independent examples, state the count | "All service classes use DI via __init__ (observed in 12/14 services)" |
| Verified Absence | `[ABSENCE]` | Searched for something expected, confirmed it doesn't exist | "No rate limiting found (grepped for rate_limit, throttle, slowapi — zero hits)" |

**Rules:**
- Conventions are [PATTERN] claims. Must cite example count.
- Gotchas must be [FACT] claims with file:line evidence.
- Never include inferences, assumptions, or unverified xray signals.

---

## Edge Case Handling

**No tests in the codebase:**
- Skip testing conventions section
- Note in Gaps: "No test suite detected"

**No git history:**
- Skip git-dependent investigation targets (coupling anomalies, maintenance hotspots)
- Note in Gaps: "No git history available — coupling and churn data missing"

**Monorepo (>2000 files):**
- Identify 3-5 subsystems from architectural layers
- Execute focused crawl on each subsystem independently
- Produce top-level document + subsystem appendices
- Only top-level document goes in CLAUDE.md

**Interrupted crawl:**
- On resume, read CRAWL_PLAN.md for completion marks
- Read existing findings from disk
- Continue from the first incomplete task

**Missing investigation_targets in xray output:**
- The xray version may predate this feature
- Fall back to using xray pillars and hotspots for investigation planning
- Tell user: "Consider upgrading xray for better crawl planning"

**Sub-agent spawning fails:**
- If Agent tool returns an error, retry the spawn once
- If retry fails, add to sequential retry queue
- After batch, execute queued tasks sequentially using protocols directly
- If ALL spawns in Batch 1 fail, switch entirely to sequential fallback mode
- Log which tasks ran sequentially so Phase 5 can flag reduced investigation depth

**Assembly sub-agent produces undersized section:**
- After assembly, check each section's word count against its input word count
- If a section is under 80% of its input, the assembly agent dropped findings. Re-spawn with: "Your previous output was N words from M words of input. You dropped findings. Include every finding at full fidelity. The 1M context window means your section consumes less than 5% of available space."

---

## Constraints

- Never modify source code. This is a read-only investigation.
- Never include information that is literally duplicated elsewhere in this document or in xray output verbatim. DO include synthesized information even if the underlying raw data is grepable — the synthesis is the value.
- Every [FACT] claim must have a file:line citation.
- Every [PATTERN] claim must have an N/M count.
- The output document must be self-contained for frequently-needed information.
- Rarely-needed structural details reference xray output by path.
- Stable content goes at the top of the document, volatile content at the bottom.
- Sub-agents must not spawn further sub-agents. Only the orchestrator spawns agents.
- The orchestrator does not read findings content between batches — only sentinel files. Findings are consumed in Phase 3.

## Quality Checklist (before delivery)

- [ ] All 12 standard questions answerable from the document
- [ ] Change Impact Index covers all xray hub modules
- [ ] At least one change playbook exists
- [ ] Data Contracts lists high-usage domain entities
- [ ] All [FACT] claims have file:line citations
- [ ] All [PATTERN] claims have N/M counts
- [ ] Adversarial simulation passes
- [ ] Every section contains information not derivable from file names and signatures
- [ ] Stable-first section ordering maintained
- [ ] No literally duplicated content between sections or with xray output
- [ ] Every gotcha has specific file:line evidence
- [ ] CLAUDE.md updated for automatic delivery

## Delivery

DEEP_ONBOARD.md is included in CLAUDE.md so that:
1. Every agent session receives it automatically
2. Prompt caching reduces read cost by ~90% after first session
3. Downstream agents don't need to know to look for it

## Output Size Guidance

No token ceilings. Include everything that's not redundant with information
derivable from file names and signatures. Let the content determine the size.

## Feedback

Downstream agents log section references to docs/.onboard_feedback.log.
During refresh, this data informs section prioritization.

## Files

```
.claude/
├── agents/
│   ├── deep_crawl.md          (sequential fallback agent)
│   └── deep_onboard_validator.md
└── skills/
    └── deep-crawl/
        ├── SKILL.md            (this file — orchestrator instructions)
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

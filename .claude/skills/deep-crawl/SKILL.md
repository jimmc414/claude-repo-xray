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
| `/deep-crawl full <github-url>` | **Orchestrated** | Clone remote repo, auto-run xray, then full crawl pipeline |

## Remote Repository Support

When a GitHub URL (or `gh:owner/repo` shorthand) is passed as an argument to `/deep-crawl full`,
the skill clones the repository to a local temp directory and runs the full pipeline against it.

**Supported URL formats:**
- `https://github.com/owner/repo`
- `https://github.com/owner/repo.git`
- `gh:owner/repo`
- `git@github.com:owner/repo.git`

**Key differences from local crawl:**
- Repository is cloned with full history (for git log/blame) to `/tmp/deep_crawl/repo/`
- Xray is run automatically — no manual prerequisite step
- `DEEP_CRAWL_ROOT` points to the clone directory instead of `$(pwd)`
- Sub-agent `{ROOT_PATH}` is set to the clone directory
- Phase 6 delivers output to `/tmp/deep_crawl/output/` instead of the project's `docs/`
- CLAUDE.md in the clone is not modified (read-only analysis of external repo)
- Cleanup is manual: `rm -rf /tmp/deep_crawl/repo/` when done

**What stays the same:** All six phases, quality gates, investigation protocols,
evidence standards, and validation — the entire pipeline is identical.

## Evidence Standards

| Tag | Standard | Example |
|-----|----------|---------|
| [FACT] | Read specific code, cite file:line | "3x retry with backoff [FACT] (stripe.py:89)" |
| [PATTERN] | Observed in >=3 examples, state count | "DI via __init__ [PATTERN: 12/14 services]" |
| [ABSENCE] | Searched and confirmed non-existence | "No rate limiting [ABSENCE: grep — 0 hits]" |

No inferences or unverified signals in the output document.

**Citation density floor:** Assembled sections have tiered density requirements:
high-evidence sections (impact, gotchas, contracts) >= 3.0, medium (module index,
interfaces, playbooks, error handling) >= 2.0, narrative (critical paths, conventions) >= 1.0,
structural (glossary, reading order) >= 0. Playbooks individually >= 3.0 per 100 words.
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
# === REMOTE REPOSITORY DETECTION ===
# If the user passed a GitHub URL, clone it and set DEEP_CRAWL_ROOT.
# Otherwise, DEEP_CRAWL_ROOT defaults to the current working directory.
DEEP_CRAWL_REMOTE="${1:-}"  # first argument, if any
DEEP_CRAWL_ROOT="$(pwd)"

if [[ "$DEEP_CRAWL_REMOTE" =~ ^(https://github\.com/|git@github\.com:|gh:) ]]; then
    REPO_DIR="/tmp/deep_crawl/repo"

    # Clean previous clone
    [ -d "$REPO_DIR" ] && rm -rf "$REPO_DIR"

    # Normalize gh:owner/repo shorthand to full URL
    if [[ "$DEEP_CRAWL_REMOTE" == gh:* ]]; then
        DEEP_CRAWL_REMOTE="https://github.com/${DEEP_CRAWL_REMOTE#gh:}"
    fi

    echo "Cloning remote repository: $DEEP_CRAWL_REMOTE"
    gh repo clone "$DEEP_CRAWL_REMOTE" "$REPO_DIR" 2>/dev/null \
        || git clone "$DEEP_CRAWL_REMOTE" "$REPO_DIR"

    if [ ! -d "$REPO_DIR/.git" ]; then
        echo "HALT: Clone failed. Check the URL and your access permissions."
        exit 1
    fi

    DEEP_CRAWL_ROOT="$REPO_DIR"
    echo "Remote repo cloned to: $DEEP_CRAWL_ROOT"
    echo "DEEP_CRAWL_MODE=remote"

    # Auto-run xray on cloned repo
    # Locate xray.py: check skill source directory, then cwd, then PATH
    XRAY_PY=""
    SKILL_SOURCE=$(readlink -f ~/.claude/skills/deep-crawl 2>/dev/null || echo "")
    if [ -n "$SKILL_SOURCE" ] && [ -f "$(dirname "$SKILL_SOURCE")/../../xray.py" ]; then
        XRAY_PY="$(dirname "$SKILL_SOURCE")/../../xray.py"
    elif [ -f "xray.py" ]; then
        XRAY_PY="./xray.py"
    elif command -v xray.py >/dev/null 2>&1; then
        XRAY_PY="xray.py"
    fi

    if [ -n "$XRAY_PY" ]; then
        echo "Running xray: python $XRAY_PY $DEEP_CRAWL_ROOT --output both --out /tmp/xray"
        python "$XRAY_PY" "$DEEP_CRAWL_ROOT" --output both --out /tmp/xray
    else
        echo "HALT: Cannot find xray.py. Provide its path or run manually:"
        echo "  python /path/to/xray.py $DEEP_CRAWL_ROOT --output both --out /tmp/xray"
    fi
else
    echo "DEEP_CRAWL_MODE=local"
fi

# Create working directory structure
mkdir -p /tmp/deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks,calibration} \
         /tmp/deep_crawl/batch_status \
         /tmp/deep_crawl/sections

# Verify xray output exists
test -f /tmp/xray/xray.json && echo "READY" || echo "Run: python xray.py . --output both --out /tmp/xray"

# Check for existing crawl state (resumability)
if [ -f /tmp/deep_crawl/CRAWL_PLAN.md ]; then
    echo "PREVIOUS CRAWL FOUND"
    head -5 /tmp/deep_crawl/CRAWL_PLAN.md
    git -C "$DEEP_CRAWL_ROOT" log --oneline -1
    echo "If hashes match, run @deep_crawl resume"
    echo "If not, this is a stale crawl — starting fresh"
fi
```

**DEEP_CRAWL_ROOT usage:** All subsequent phases use `$DEEP_CRAWL_ROOT` wherever the codebase
root is referenced. For local crawls this equals `$(pwd)` (backward compatible). For remote
crawls it points to `/tmp/deep_crawl/repo/`. Sub-agent prompts must set `{ROOT_PATH}` to
the value of `$DEEP_CRAWL_ROOT`.

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

### Phase 0b: PRE-FLIGHT DIAGNOSTICS

**Goal:** Catch stale inputs and repo characteristics before investing tokens in investigation.

```bash
# === PRE-FLIGHT DIAGNOSTICS ===
echo "=== Pre-Flight ==="

# Xray freshness — robust hash comparison
XRAY_HASH=$(python3 -c "
import json
d = json.load(open('/tmp/xray/xray.json'))
print(d.get('git_commit', d.get('commit_hash', '?')))
" 2>/dev/null)
HEAD=$(git -C "$DEEP_CRAWL_ROOT" rev-parse HEAD 2>/dev/null || echo "no-git")

if [ "$XRAY_HASH" != "?" ] && [ "$HEAD" != "no-git" ]; then
    # Prefix match handles short-vs-full hash
    if [[ ! "$HEAD" == "$XRAY_HASH"* ]] && [[ ! "$XRAY_HASH" == "$HEAD"* ]]; then
        echo "HALT: Xray is stale (xray: ${XRAY_HASH:0:7}, HEAD: ${HEAD:0:7}). Re-run xray."
    else
        echo "Xray matches HEAD: ${HEAD:0:7}"
    fi
else
    [ "$XRAY_HASH" = "?" ] && echo "WARNING: Xray has no git_commit field. Proceeding without freshness check."
fi

# Repo characteristics
FILE_COUNT=$(find "$DEEP_CRAWL_ROOT" -name "*.py" -not -path "*/.git/*" | wc -l)
TEST_COUNT=$(find "$DEEP_CRAWL_ROOT" -name "test_*.py" -o -name "*_test.py" | wc -l)
echo "Python files: $FILE_COUNT | Test files: $TEST_COUNT"
[ "$FILE_COUNT" -gt 5000 ] && echo "WARNING: Very large repo. Consider focused crawl."
[ "$TEST_COUNT" -eq 0 ] && echo "WARNING: No test files. Testing section will be thin."

# Framework detection
for fw in fastapi flask django click typer torch tensorflow airflow dagster numpy scipy asyncio aiohttp paramiko boto3 pluggy stevedore; do
    grep -rl "$fw" --include="*.py" "$DEEP_CRAWL_ROOT" 2>/dev/null | head -1 >/dev/null 2>&1 && echo "Framework: $fw"
done
```

**Halt condition:** If xray hash doesn't match HEAD, stop and tell user to re-run xray. Other warnings are logged to `/tmp/deep_crawl/PREFLIGHT.md` for context during investigation planning.

Save all pre-flight output to `/tmp/deep_crawl/PREFLIGHT.md` for Phase 1 consumption.

---

### Phase 1: PLAN (Build the Crawl Agenda)

**Input:** X-Ray JSON output including `investigation_targets`.

1. Read `/tmp/xray/xray.md` for orientation
2. Read `investigation_targets` from `/tmp/xray/xray.json`
3. Read `git.function_churn` and `git.velocity` from `/tmp/xray/xray.json`. Files with accelerating velocity or high function-level churn should be prioritized for investigation.
4. Detect all applicable domain facets using indicators from `.claude/skills/deep-crawl/configs/domain_profiles.json`. A repo can match multiple facets (e.g., a Django app with Celery workers and a CLI gets `web_api` + `async_service` + `cli_tool`). Union their `additional_investigation` tasks into the crawl plan. If no facet matches, use `library` as default. Read `/tmp/deep_crawl/PREFLIGHT.md` for framework detection results to guide facet matching.

For each matched facet:
1. Add its `additional_investigation` tasks to the crawl plan at P4 priority (cross-cutting concerns)
2. Add its `additional_output_sections` to the assembly plan for the appropriate sub-agent (S3 or S4)
3. Add its `grep_patterns` to Protocol C investigation prompts for related cross-cutting agents
4. Record all matched facets in CRAWL_PLAN.md header: `Domain Facets: web_api, async_service, cli_tool`

If facet investigation tasks push any batch beyond its max agent limit, split into sub-batches.
Use the facet's `primary_entity` to determine the adversarial simulation scenario in Phase 5.
If multiple facets match, the adversarial simulation should use the primary facet's entity.
4. Produce a prioritized crawl plan using the template at `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template`
5. Save to `/tmp/deep_crawl/CRAWL_PLAN.md`
6. **Module coverage pre-check (mandatory).** After saving the plan, verify P2+P3 task count meets the coverage target:

```bash
# === MODULE COVERAGE PRE-CHECK ===
P23_COUNT=$(grep -c '^\- \[ \] P[23]\.' /tmp/deep_crawl/CRAWL_PLAN.md 2>/dev/null || echo 0)
TARGET=$(python3 -c "
import json
d = json.load(open('/tmp/xray/xray.json'))
file_count = len(d.get('files', d.get('file_list', [])))
print(max(10, file_count // 40))
" 2>/dev/null)
echo "P2+P3 tasks: $P23_COUNT, coverage target: $TARGET"
```

If P23_COUNT < TARGET:
   a. Read xray.json import graph: identify all modules with `imported_by` count >= 3 that are NOT already P2 or P3 tasks
   b. Sort by `imported_by` count descending
   c. Add the top `(TARGET - P23_COUNT)` modules as new P3 tasks to CRAWL_PLAN.md
   d. **Hop promotion:** Any module that appears as an intermediate hop in a P1 trace task description AND does not already have a P2/P3 task gets added as a P3 task (these are modules the traces pass through — they deserve deep-reads)
   e. Update the Progress table's P3 total
   f. Log: `Coverage pre-check: {P23_COUNT} tasks → {new_count} (added {added} modules, target {TARGET})`

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

### Phase 1b: CALIBRATE (Repo-Specific Exemplar Discovery)

**Goal:** Before bulk investigation, produce repo-specific quality exemplars by investigating a small number of high-value targets at elevated depth. Their output becomes the quality reference for all Phase 2 sub-agents, replacing static exemplars.

**Scope by repo size** (from Phase 0b FILE_COUNT):

| Files | Calibration |
|-------|-------------|
| <= 10 | Skip — use structural templates only |
| 11-30 | 1 target (CAL_B only) |
| >= 31 | Full 3 targets |

**Target selection (deterministic, no LLM judgment):**
- **CAL_A (Protocol A trace):** First P1 task from CRAWL_PLAN.md (longest trace)
- **CAL_B (Protocol B module):** First P2 task (highest uncertainty module), or first P3 if no P2
- **CAL_C (Protocol C cross-cutting):** First P4 task (error handling — universal)

**Elevated quality floor** (calibration must exceed normal investigation floor):
- 400 words (normal: 200), 10 [FACT] (normal: 5), density 6.0/100w (normal: 5.0)
- For traces: follow EVERY branch. For modules: document EVERY public method
- For cross-cutting: read >= 5 representative examples

Thresholds are defined in `.claude/skills/deep-crawl/configs/quality_gates.json` under `calibration_findings`.

**Procedure:**

1. Parse CRAWL_PLAN.md and select targets per the rules above.
2. Spawn calibration agents (1-3 depending on repo size). Each agent prompt follows the standard Phase 2 format with these modifications:
   - Quality floor references `calibration_findings` thresholds (400w, 10 FACT, 6.0/100w)
   - Format guidance references `.claude/skills/deep-crawl/configs/exemplar_templates.md` only (calibration findings don't exist yet)
   - Output path: `/tmp/deep_crawl/findings/calibration/cal_{a|b|c}.md`
   - Sentinel: `touch /tmp/deep_crawl/batch_status/cal_{a|b|c}.done`
3. Wait for all calibration sentinels.
4. Run calibration quality gate:

```bash
# === CALIBRATION QUALITY GATE ===
CAL_GATE=true
for f in /tmp/deep_crawl/findings/calibration/cal_*.md; do
    [ -f "$f" ] || continue
    WORDS=$(wc -w < "$f")
    FACTS=$(grep -c '\[FACT' "$f" 2>/dev/null || echo 0)
    [ "$WORDS" -eq 0 ] && continue
    DENSITY=$((FACTS * 100 / WORDS))
    if [ "$WORDS" -lt 400 ] || [ "$FACTS" -lt 10 ] || [ "$DENSITY" -lt 6 ]; then
        echo "CAL FAIL: $(basename $f) — ${WORDS}w, ${FACTS} FACT, ${DENSITY}/100w density"
        echo "  (elevated floor: 400w, 10 FACT, 6.0/100w)"
        CAL_GATE=false
    fi
done
```

**Failure handling:**
1. If calibration fails elevated gate: re-spawn once with corrective instructions
2. If re-spawn passes normal gate (200w, 5 FACT) but not elevated: accept with warning
3. If re-spawn fails normal gate: fall back to structural templates for that protocol

**Integration:**
- Copy calibration findings into standard finding dirs so they are included in assembly:
  ```bash
  [ -f /tmp/deep_crawl/findings/calibration/cal_a.md ] && \
      cp /tmp/deep_crawl/findings/calibration/cal_a.md /tmp/deep_crawl/findings/traces/00_calibration.md
  [ -f /tmp/deep_crawl/findings/calibration/cal_b.md ] && \
      cp /tmp/deep_crawl/findings/calibration/cal_b.md /tmp/deep_crawl/findings/modules/00_calibration.md
  [ -f /tmp/deep_crawl/findings/calibration/cal_c.md ] && \
      cp /tmp/deep_crawl/findings/calibration/cal_c.md /tmp/deep_crawl/findings/cross_cutting/00_calibration.md
  ```
- Mark calibration targets as `[x]` in CRAWL_PLAN.md so Phase 2 doesn't re-investigate them
- Phase 2 sub-agent prompts reference `/tmp/deep_crawl/findings/calibration/cal_{type}.md` as quality exemplars instead of static exemplars

---

### Phase 2: CRAWL (Orchestrated Investigation)

Phase 2 uses parallel sub-agents to investigate the codebase. You act as the **orchestrator** — spawn investigation agents, monitor completion, and verify coverage. Do NOT perform investigation yourself (except as fallback).

#### Orchestration Procedure

**Step 1: Parse and batch.** Read CRAWL_PLAN.md. Group tasks into batches:

| Batch | Tasks | Protocol | Max Agents | Dependencies |
|-------|-------|----------|------------|--------------|
| 1 | All P1 (request traces) | A | 5 | None |
| 2 | All P2 + P3 (modules + pillars) | B | one per task | None |
| 3 | All P4 (cross-cutting concerns incl. async boundaries) | C | 6 | None |
| 4 | All P5 + P6 (conventions + gaps) | D + mixed | 4 | Batches 1-3 |
| 5 | P7 (change impact) + Coverage gaps | E + Mixed | 8 | Batches 1-4 |
| 6 | Change scenarios | F | 3 | Batches 1-5 |

Batches 1-3 are independent — launch them concurrently (all in a single message with multiple Agent tool calls). Batch 4 waits for 1-3 because convention detection and gap investigation benefit from earlier findings being on disk. Batch 5 (P7 impact + coverage gaps) waits for Batches 1-4 because impact analysis reads module findings. Batch 6 (change scenarios) waits for Batches 1-5 because playbooks reference impact findings.

If a batch has more tasks than its max agents, split into sequential sub-batches of max agents each. All sub-batches within a batch are independent.

**Batch 2 unbatching rule:** Spawn one agent per P2/P3 task — never batch multiple modules into one agent. Each module gets its own investigation context for richer, more distinct findings that map cleanly to individual ### subsections during assembly. If total P2+P3 tasks exceed 15, use sequential sub-batches of 15.

**Batch 2 elevated quality floor:** Because each unbatched agent investigates a single module with full context, findings must be deeper than the default floor. Batch 2 sub-agent prompts MUST use these thresholds instead of the default:
- Minimum 400 words (not 200)
- Minimum 10 [FACT] citations (not 5)
- Target density: >= 5.0 [FACT] per 100 words
The findings quality gate (Step 3b) MUST also check Batch 2 files against these elevated thresholds. Use the file path to identify Batch 2 findings: any file in `findings/modules/` (excluding `00_calibration.md`) uses the elevated floor.

**P7 relocation rationale:** Change impact analysis (Protocol E) moved from Batch 2 to Batch 5 because impact analysis reads reverse dependency data enriched by module deep-reads. Running P7 after Batches 1-4 ensures impact agents have full module findings on disk.

**Multi-facet batch adjustment:** If domain facets added investigation tasks to P4,
Batch 3 may exceed its max of 6 agents. Split Batch 3 into sub-batches of 6 each.
Facet investigation tasks have no dependencies on Batch 1-2 and can run in any
Batch 3 sub-batch. The orchestrator must include the facet's grep_patterns in the
Protocol C prompt for facet-specific cross-cutting investigations.

**Step 2: Spawn sub-agents.** For each task in a batch, spawn a sub-agent using the Agent tool. Each sub-agent prompt must be **self-contained** with these sections:

```
You are investigating [CODEBASE] at [ROOT_PATH] for an onboarding document.

## Your Task
[Specific task from crawl plan — e.g., "Trace the primary CLI entry point from invocation to terminal side effect"]

## Investigation Protocol
[Full text of the relevant protocol (A, B, C, or D) copied verbatim from below]

## Evidence Standards
- [FACT]: Read specific code, cite file:line. Example: "retries 3x (stripe.py:89)"
- [PATTERN]: Observed in >=3 examples, state count. Example: "DI via __init__ (12/14 services)"
- [ABSENCE]: Searched and confirmed non-existence. Example: "No rate limiting (grep — 0 hits)"
- Gotchas must be [FACT] claims with file:line.
- Never include inferences or unverified signals.

## Quality Floor (mechanically checked after you finish)
- Minimum 200 words
- Minimum 5 [FACT] citations
- Target density: >= 5.0 [FACT] per 100 words
If your file fails the check, you will be re-spawned to investigate deeper.
For format guidance, see .claude/skills/deep-crawl/configs/exemplar_templates.md.
For quality reference from this repo, see /tmp/deep_crawl/findings/calibration/cal_{type}.md.

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

**Step 3a: SNAPSHOT (before spawning batch).** Record existing findings files so the quality gate only checks new ones:

```bash
# === FINDINGS SNAPSHOT (before spawning batch) ===
ls /tmp/deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks}/*.md \
    2>/dev/null | sort > /tmp/deep_crawl/_pre_batch_files.txt
```

**Step 3b: FINDINGS QUALITY GATE (batch-scoped, mandatory after each batch).** After confirming all sentinel files exist, check only files produced in this batch:

```bash
# === FINDINGS QUALITY GATE (batch-scoped) ===
ls /tmp/deep_crawl/findings/{traces,modules,cross_cutting,conventions,impact,playbooks}/*.md \
    2>/dev/null | sort > /tmp/deep_crawl/_post_batch_files.txt

GATE_PASS=true
while IFS= read -r f; do
    WORDS=$(wc -w < "$f")
    FACTS=$(grep -c '\[FACT' "$f" 2>/dev/null || echo 0)
    if [ "$WORDS" -lt 200 ] || [ "$FACTS" -lt 5 ]; then
        echo "FAIL: $(basename $f) — ${WORDS}w, ${FACTS} FACT (min: 200w, 5 FACT)"
        GATE_PASS=false
    fi
done < <(comm -13 /tmp/deep_crawl/_pre_batch_files.txt /tmp/deep_crawl/_post_batch_files.txt)
# If any file fails: re-spawn the failing sub-agent with corrective instructions.
# Do NOT proceed to next batch until all findings files pass.
```

Thresholds are defined in `.claude/skills/deep-crawl/configs/quality_gates.json` under `investigation_findings`. If a file fails, re-spawn the sub-agent with: "Your output had {WORDS}w and {FACTS} [FACT] citations. Minimum is 200w and 5 [FACT]. Investigate deeper — read more source files, trace more hops, grep for more patterns."

**Step 4: Checkpoint.** After each batch completes and passes the findings quality gate, update CRAWL_PLAN.md to mark completed tasks with `[x]`. Sub-agents never write to CRAWL_PLAN.md (concurrent writes would corrupt it).

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
2b. Check for corresponding test files:
    - Look for tests/test_{module_name}.py, tests/unit/**/test_{module_name}.py,
      tests/{module_name}_test.py, and any test file importing from this module
    - If found, scan test function names and docstrings
    - Note which public functions have test coverage and which don't
    - Add to findings:
      Test coverage: {tested_count}/{total_public} public functions tested.
      Tested: {list}. Untested: {list}.
      Test file: {path} ({N} test functions)
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

# Exception taxonomy (for exception_taxonomy investigations)
grep -rn "class.*Exception\|class.*Error" --include="*.py"  # custom exception classes
grep -rn "except.*pass\|except:$" --include="*.py"  # silent failures
grep -rn "except.*:\s*$\|except Exception" --include="*.py" | head -30  # bare/broad catches
grep -rn "raise " --include="*.py" | head -40  # raise sites
```

**Exception taxonomy investigations (Protocol C):**

When the crawl plan includes an exception taxonomy task, Protocol C agents should:
1. Find all classes inheriting from Exception or BaseException
2. Build inheritance tree (which exceptions derive from which)
3. For each custom exception: where it's raised, where it's caught, whether
   it crosses module boundaries
4. Identify uncaught exception paths (raise without corresponding catch in callers)
5. Identify silent failure patterns: `except: pass`, `except Exception: log`,
   bare except — these are high-value gotcha candidates
6. Write to findings/cross_cutting/exception_taxonomy.md

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
(Note: This check verifies the Phase 1 coverage pre-check was effective. If gaps remain, the pre-check heuristic needs improvement.)
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
cat /tmp/deep_crawl/findings/calibration/*.md \
    /tmp/deep_crawl/findings/traces/*.md \
    /tmp/deep_crawl/findings/modules/*.md \
    /tmp/deep_crawl/findings/cross_cutting/*.md \
    /tmp/deep_crawl/findings/conventions/*.md \
    /tmp/deep_crawl/findings/impact/*.md \
    /tmp/deep_crawl/findings/playbooks/*.md \
    > /tmp/deep_crawl/SYNTHESIS_INPUT.md 2>/dev/null
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
ROOT_PATH="${DEEP_CRAWL_ROOT:-$(pwd)}"
[ -f "$ROOT_PATH/CLAUDE.md" ] && mv "$ROOT_PATH/CLAUDE.md" "$ROOT_PATH/CLAUDE.md.assembly_save"
PARENT_PATH=$(dirname "$ROOT_PATH")
[ -f "$PARENT_PATH/CLAUDE.md" ] && mv "$PARENT_PATH/CLAUDE.md" "$PARENT_PATH/CLAUDE.md.assembly_save"
```

**IMPORTANT:** Restore these files after all sub-agents complete (after Step 9). See Step 9 completion.

#### Step 1c: Generate structural skeleton

Before spawning assembly agents, mechanically generate a skeleton of prescribed ### headers from investigation findings. This skeleton locks section structure — assembly agents fill content under prescribed headers but cannot merge or remove them.

```bash
# === STRUCTURAL SKELETON GENERATION ===
SKEL="/tmp/deep_crawl/sections/_skeleton.md"
echo "# Assembly Skeleton — Prescribed Section Structure" > $SKEL
echo "# Assembly agents MUST produce every ### listed below for their section." >> $SKEL
echo "" >> $SKEL

# S1: Critical Paths — one ### per trace finding
echo "## S1: Critical Paths" >> $SKEL
N=1
for f in /tmp/deep_crawl/findings/traces/*.md; do
    [ -f "$f" ] || continue
    [[ "$(basename "$f")" == "00_calibration.md" ]] && continue
    TITLE=$(head -1 "$f" | sed 's/^#* *//' | cut -c1-80)
    echo "### Path $N: $TITLE" >> $SKEL
    N=$((N+1))
done
echo "" >> $SKEL

# S2: Module Behavioral Index — one ### per module finding
echo "## S2: Module Behavioral Index" >> $SKEL
for f in /tmp/deep_crawl/findings/modules/*.md; do
    [ -f "$f" ] || continue
    [[ "$(basename "$f")" == "00_calibration.md" ]] && continue
    # Extract module path from first line or filename
    MOD=$(head -3 "$f" | grep -oP '`[^`]+\.py`' | head -1)
    [ -z "$MOD" ] && MOD="\`$(basename "$f" .md).py\`"
    echo "### $MOD -- Detailed Behavioral Analysis" >> $SKEL
done
echo "" >> $SKEL

# S3b: Error Handling — one ### per strategy/pattern in cross-cutting findings
echo "## S3b: Error Handling" >> $SKEL
if [ -f /tmp/deep_crawl/findings/cross_cutting/error_handling.md ]; then
    grep '^## \|^### ' /tmp/deep_crawl/findings/cross_cutting/error_handling.md \
        | sed 's/^## /### /' | sed 's/^### ### /### /' >> $SKEL
fi
echo "" >> $SKEL

# S5: Gotchas — domain cluster headers from module directory groupings
echo "## S5: Gotchas" >> $SKEL
ls /tmp/deep_crawl/findings/modules/*.md 2>/dev/null \
    | xargs -I{} head -3 {} \
    | grep -oP '`[^`/]+/' \
    | sort -u | tr -d '`' \
    | while read -r pkg; do
        # Convert package dir to readable cluster name
        CLUSTER=$(echo "$pkg" | sed 's|/$||' | sed 's|_| |g' | sed 's|\b\(.\)|\u\1|g')
        echo "### ${CLUSTER} Gotchas" >> $SKEL
    done
# Always include a cross-cutting cluster
echo "### Cross-Cutting Gotchas" >> $SKEL
echo "" >> $SKEL

echo "Skeleton generated: $(grep -c '^### ' $SKEL) subsections prescribed"
```

The skeleton is informational, not rigid for every section. S1 and S2 MUST follow it exactly (one ### per finding file). S3b and S5 use it as guidance — they may adjust ### headers based on content but should maintain similar granularity.

#### Step 2: Spawn S1, S2, S3a, S3b, S4 in parallel

Launch 5 assembly sub-agents simultaneously (all with `run_in_background: true`):

| Agent | Sections | Input Files | Est. Input |
|-------|----------|-------------|-----------|
| **S1** | Critical Paths | `findings/traces/*.md` | ~11K words |
| **S2** | Module Behavioral Index, Domain Glossary | `findings/modules/*.md` | ~25K words |
| **S3a** | Key Interfaces | `findings/modules/*.md` (public API extraction) + `findings/cross_cutting/agent_communication.md` | ~12K words |
| **S3b** | Error Handling, Shared State | `findings/cross_cutting/{error_handling,initialization,shared_state,database_storage,async_boundaries,exception_taxonomy}.md` + `findings/modules/*.md` (grep for error/exception/retry patterns) | ~16K words |
| **S4** | Configuration Surface, Conventions | `findings/cross_cutting/{configuration,env_dependencies,llm_providers}.md` + `findings/modules/config.md` + `findings/conventions/*.md` | ~16K words |

**Note:** The file lists above are illustrative examples. Adjust filenames to match actual findings on disk. Use `ls /tmp/deep_crawl/findings/{category}/` to discover actual filenames before constructing prompts.

Each sub-agent prompt must be self-contained:

```
You are assembling investigation findings into onboarding document sections. Include every finding — do not summarize, condense, or compress.

## Your Task
Produce these template sections: [SECTION NAMES]

## Input
Read ONLY these files: [FILE PATHS]

## Template Format
[Copy the relevant section templates verbatim from .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template]

## Structural Contract
Read /tmp/deep_crawl/sections/_skeleton.md for your section's prescribed ### headers.
- For Module Behavioral Index and Critical Paths: each prescribed ### MUST appear in your output exactly as listed. Each findings file maps to one ###. Do not merge.
- For Error Handling and Gotchas: use the skeleton's ### headers as guidance. Maintain similar granularity but adjust header wording based on actual content.
- For other sections: no skeleton constraint — derive structure from content.
- You MAY add additional ### subsections beyond the skeleton's prescriptions.

## Section Hierarchy Rule
Your output MUST use exactly one `## ` header per template section assigned to you (e.g., `## Error Handling Strategy`, `## Module Behavioral Index`). All subdivisions within a section MUST use `### ` or deeper. Never promote subsection content to `## ` level — a flat document with many `## ` headers destroys navigability. If your template section has subsections, they are `### `. If those subsections have further divisions, they are `#### `.

## S2 Historical Risk Annotation
If you are S2 (Module Behavioral Index): for each module ### being assembled, check if it appears in `git.risk`, `git.function_churn`, or `git.velocity` from `/tmp/xray/xray.json`. If it does, append a brief **Historical Risk** note at the end of that module's subsection with: risk score, most-volatile functions, and trend direction. Format: `> **Git risk:** 0.88 — volatile functions: load_config (8 commits, 2 hotfixes). Trend: stable.`

## S3b Depth Directive
If you are S3b (Error Handling, Shared State): the Error Handling Strategy section must document the dominant error pattern, per-subsystem deviations, retry strategies, exception hierarchies, and recovery paths. Target: >= 3,500 words for Error Handling alone. Read module findings for error/exception/retry patterns in addition to cross-cutting findings — every module's error handling deviations contribute to this section. If `findings/cross_cutting/exception_taxonomy.md` exists, include it as a subsection under Error Handling: inheritance tree of custom exceptions, raise/catch mapping, uncaught paths, and silent failure patterns (`except: pass`, bare except, log-and-swallow). Silent failures are high-value gotcha candidates — flag them in your gotchas output file.

## Rules
- INCLUDE EVERY FINDING. The output context window is 1M tokens. Your section will consume less than 5% of available context. There is no reason to drop, summarize, or condense any finding.
- The ONLY reason to exclude a finding is if it is literally stated elsewhere in your section or is derivable from the module's file name alone.
- Place each finding at full fidelity with its original [FACT], [PATTERN], or [ABSENCE] tag and file:line citation.
- When multiple findings describe the same code from different angles, include ALL of them — each angle provides context the others miss.
- Write conventions as directives — "Always X", "Never Y".
- Your output should be 80-100% of your input word count. If you produce less than 80%, you have dropped findings. Re-read your input and find what you missed.

## Quality Floor (mechanically checked after you finish)
- Citation density floor varies by section type — see quality_gates.json density_tiers.
  High-evidence sections (impact, gotchas, contracts): 3.0/100w.
  Medium (module index, interfaces, playbooks): 2.0/100w.
  Narrative (critical paths, conventions): 1.0/100w.
  Structural (glossary, reading order): no floor.
- Word count: >= 80% of your input findings word count
If your section fails, you will be re-spawned.
For format guidance, see .claude/skills/deep-crawl/configs/exemplar_templates.md.
For quality reference from this repo, see /tmp/deep_crawl/findings/calibration/cal_{type}.md.

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

Check for sentinel files. All 5 must complete before proceeding:
```bash
ls /tmp/deep_crawl/sections/S{1,2,3a,3b,4}.done 2>/dev/null | wc -l  # expect 5
```

#### Step 4: Spawn S5 AND S6 in parallel (depend on S1-S3a-S3b-S4 gotcha outputs)

Launch S5 and S6 simultaneously (both with `run_in_background: true`):

| Agent | Sections | Input Files | Est. Input |
|-------|----------|-------------|-----------|
| **S5** | Gotchas, Hazards, Extension Points, Reading Order | `sections/gotcha_extracts.md` + `sections/gotchas_from_S{1,2,3a,3b,4}.md` + CRAWL_PLAN.md (for structure) | ~14K words |
| **S6** | Change Impact Index, Data Contracts, Change Playbooks | `findings/impact/*.md` + `findings/playbooks/*.md` + `findings/modules/*.md` (grep for Pydantic/dataclass) + `sections/state_diagrams.md` | ~15K words |

S5's prompt follows the same template as S1-S4, with these additions for the **Gotchas** section:

Organize gotchas into domain-cluster ### subsections derived from the investigation's subsystem structure (e.g., "Agent System", "Data Models", "Execution Engine", "LLM Integration", "Configuration"). Derive cluster names from the module findings directory — group `findings/modules/*.md` by top-level package directory. Within each cluster, order entries by severity (critical first). Prefix each entry with severity tag: `[CRITICAL]`, `[HIGH]`, or `[MEDIUM]`. Target: one ### per 5-15 gotchas. Never put more than 15 gotchas under a single ### heading.

S5's template sections remain: Gotchas, Hazards — Do Not Read, Extension Points, and Reading Order from DEEP_ONBOARD.md.template.

S6's prompt for **Data Contracts**: extract all Pydantic models, dataclasses, TypedDicts, and NamedTuples from module findings + xray `investigation_targets.domain_entities`. Format as table with Model, File, Type, Key Fields, Serialization, Gotcha.

S6's prompt for **Change Impact Index**: organize impact findings by hub module cluster. Each cluster gets a table showing importers, high-impact functions, signature-change consequences, behavior-change consequences, safe vs dangerous changes. Also read `git.coupling_clusters` from `/tmp/xray/xray.json`. For each cluster, add a **Hidden Coupling** row to the relevant hub module's impact table. Format: `When modifying {file_a}, also verify {file_b} — {count} historical co-changes with no import relationship.`

S6's prompt for **Change Playbooks**: organize playbook findings into step-by-step checklists with validation commands and common mistakes.

S6's prompt must include this **Playbook Quality Floor (mechanically checked after you finish)**:
```
## Playbook Quality Floor (each playbook individually)
- Minimum 800 words
- Minimum 30 [FACT] citations
- Minimum 8 common mistakes with behavioral explanations
- Citation density: >= 3.0 [FACT] per 100 words
If any playbook fails, you will be re-spawned.
For format guidance, see .claude/skills/deep-crawl/configs/exemplar_templates.md.
For quality reference from this repo, see /tmp/deep_crawl/findings/calibration/cal_{type}.md.
```
Thresholds are defined in `.claude/skills/deep-crawl/configs/quality_gates.json` under `playbooks`.

S6's prompt for **Change Playbooks** quality checks:
- Each playbook individually: >= 800 words, >= 30 [FACT] citations
- Each playbook must have: 8-10 common mistakes with behavioral explanations
- Citation density per playbook: >= 3.0 [FACT] per 100 words
- If a reference playbook exists (e.g., modify_llm_provider.md), use it as the quality bar

#### Step 5: Monitor S5+S6 completion

```bash
ls /tmp/deep_crawl/sections/S{5,6}.done 2>/dev/null | wc -l  # expect 2
```

#### Step 5b: SECTION QUALITY GATE (mandatory before concatenation)

After all assembly sub-agents (S1-S6) complete, run this mechanical check. **The orchestrator MUST NOT write section content itself** — if a section is missing or below quality, re-spawn the appropriate assembly sub-agent. The only sections the orchestrator writes directly are the small metadata sections listed in Step 6.

```bash
# === SECTION QUALITY GATE (mandatory before concatenation) ===
# (a) Existence check
MISSING=""
for section in critical_paths module_index change_impact_index \
    key_interfaces data_contracts error_handling shared_state \
    config_surface conventions gotchas hazards extension_points; do
    [ -f "/tmp/deep_crawl/sections/${section}.md" ] || MISSING="$MISSING $section"
done
[ -n "$MISSING" ] && echo "GATE FAIL — missing sections:$MISSING"

# (b) Citation density check — tiered by section type
get_density_floor() {
    case "$1" in
        change_impact_index|gotchas|data_contracts) echo 3 ;;
        module_index|key_interfaces|shared_state|change_playbooks|error_handling|hazards) echo 2 ;;
        critical_paths|config_surface|conventions|extension_points) echo 1 ;;
        *) echo 0 ;;  # domain_glossary, reading_order, environment_bootstrap, etc.
    esac
}

for f in /tmp/deep_crawl/sections/*.md; do
    [ -f "$f" ] || continue
    SECTION=$(basename "$f" .md)
    WORDS=$(wc -w < "$f")
    FACTS=$(grep -c '\[FACT' "$f" 2>/dev/null || echo 0)
    [ "$WORDS" -eq 0 ] && continue
    FLOOR=$(get_density_floor "$SECTION")
    [ "$FLOOR" -eq 0 ] && continue  # no density requirement for structural sections
    DENSITY=$((FACTS * 100 / WORDS))
    [ "$DENSITY" -lt "$FLOOR" ] && echo "FAIL: $SECTION — density ${DENSITY}/100w (floor: ${FLOOR})"
done
```

Thresholds are defined in `.claude/skills/deep-crawl/configs/quality_gates.json` under `assembly_sections.density_tiers`.

If missing sections found: spawn the appropriate assembly sub-agent (S1-S6 based on which section is missing).

If density fails: re-spawn the section agent with "Your section has {DENSITY} [FACT]/100w. Floor for {TIER} sections is {FLOOR}. Re-assemble with more citations from your findings input."

```bash
# === PLAYBOOK QUALITY GATE (mandatory after S6 — per playbook, not aggregate) ===
if [ -f /tmp/deep_crawl/sections/change_playbooks.md ]; then
    # Split by ### headings into individual playbook files
    mkdir -p /tmp/deep_crawl/_pb_check
    csplit -z /tmp/deep_crawl/sections/change_playbooks.md \
        '/^### /' '{*}' \
        --prefix=/tmp/deep_crawl/_pb_check/pb_ \
        --suffix-format='%03d.md' 2>/dev/null

    PB_GATE=true
    for pb in /tmp/deep_crawl/_pb_check/pb_*.md; do
        [ -s "$pb" ] || continue
        TITLE=$(head -1 "$pb" | sed 's/^### //')
        WORDS=$(wc -w < "$pb")
        FACTS=$(grep -c '\[FACT' "$pb" 2>/dev/null || echo 0)
        MISTAKES=$(grep -ci 'common mistake\|^\*\*[0-9]' "$pb" 2>/dev/null || echo 0)
        if [ "$WORDS" -lt 800 ] || [ "$FACTS" -lt 30 ] || [ "$MISTAKES" -lt 8 ]; then
            echo "PLAYBOOK FAIL: '$TITLE' — ${WORDS}w, ${FACTS} FACT, ${MISTAKES} mistakes"
            echo "  (floor: 800w, 30 FACT, 8 mistakes)"
            PB_GATE=false
        fi
    done
    rm -rf /tmp/deep_crawl/_pb_check

    if [ "$PB_GATE" = false ]; then
        echo "Re-spawn S6 with corrective instructions for failing playbooks."
    fi
fi
```

Playbook thresholds are defined in `.claude/skills/deep-crawl/configs/quality_gates.json` under `playbooks`.

#### Step 5c: TRACEABILITY GATE (mandatory before orchestrator sections)

Mechanically verify every completed investigation task has content in at least one assembled section file:

```bash
# === TRACEABILITY GATE ===
TRACE_FAILS=0
while IFS= read -r task; do
    KEY=$(echo "$task" | grep -oP '`[^`]+`' | head -1 | tr -d '`')
    [ -z "$KEY" ] && continue
    if ! grep -ql "$KEY" /tmp/deep_crawl/sections/*.md 2>/dev/null; then
        echo "TRACE FAIL: $KEY not found in assembled sections"
        # Identify the source finding
        FINDING=$(grep -rl "$KEY" /tmp/deep_crawl/findings/*/*.md 2>/dev/null | head -1)
        [ -n "$FINDING" ] && echo "  Source: $FINDING"
        TRACE_FAILS=$((TRACE_FAILS + 1))
    fi
done < <(grep '^\- \[x\]' /tmp/deep_crawl/CRAWL_PLAN.md)

echo "Traceability: $TRACE_FAILS tasks missing from output"
```

If TRACE_FAILS > 0:
1. For each missing task, identify the findings file and responsible assembly agent:
   - `findings/traces/` → S1, `findings/modules/` → S2, `findings/cross_cutting/agent_communication*` → S3a, `findings/cross_cutting/{error,init,shared,database,async}*` → S3b, `findings/conventions/` or `findings/cross_cutting/{config,env,llm}*` → S4
2. Re-spawn that assembly agent with: "Your previous assembly missed content for {KEY}. Include findings from {FINDING_PATH} under the appropriate ### header."
3. Re-run traceability gate after re-assembly. **Maximum 1 remediation cycle.**

Log: `Step 5c: {total} tasks traced, {TRACE_FAILS} gaps, {recovered} recovered`

#### Step 6: Orchestrator produces small sections

The orchestrator writes these directly (no sub-agent needed — they are small, <500 words total):

- **Identity** — from xray.md and investigation findings. 1-3 sentences: what it is, what it does, what the stack is. Verify framework claims against investigation findings — only list a framework as part of the stack if the investigation confirmed it is actively used (mounted routes, configured endpoints), not merely imported. If a framework is imported but not wired up, note it as "library dependency, not deployed as service."
- **Gaps** — from Phase 2 coverage check results
- **Header metadata** — file count, token count, timestamp, git hash
- **Footer metadata** — task counts, coverage scope, evidence counts, hub module count, playbook count
- **Environment Bootstrap** — read assembled `config_surface.md` + cross-cutting findings for external systems. Produce bootstrap checklist with:
  - **Required services** — only list services that block core functionality. Services with graceful degradation (e.g., caches, optional databases) should be listed as "Optional (degrades gracefully to X)."
  - **Minimum env vars** — distinguish required vs optional with defaults.
  - **Setup commands** — include install, db init, and a basic run command.
  - **Verify command** — a command that proves the environment works (e.g., `pytest`, `make test`, or the project's health check).
  - **How to run** — the actual command to start the application (not just setup).
  Write to `sections/environment_bootstrap.md`.

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

**Step 5: Re-validate.** Re-spawn the validator to check ONLY the previously-failed questions:

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
4. Verify S6 output: citation density meets tiered floor per section (see density_tiers in quality_gates.json), word count retention >= 60%
5. Patch the document (replace specific sections)
6. Spawn independent validator on the patched document
7. Run quality gate checks (per-section, not aggregate)
8. Update DECLARATION.md with actual metrics

**Step 10: Restore CLAUDE.md files.**

After all sub-agents (S1-S6, cross-referencer, validator) have completed:

```bash
ROOT_PATH="${DEEP_CRAWL_ROOT:-$(pwd)}"
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
10. Gotchas sharing a root cause get cross-linked:
    - Identify gotchas that reference the same file, same function, or same pattern
    - Add "(related: Gotcha #N — same root cause)" to each member of a cluster
    - Group criteria: same file within 50 lines, or same function name, or
      description mentions the same concept (e.g., "exec()" security model)

Log: `Step 2: Added {N} cross-references ({M} gotcha clusters linked)`

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

**Identity verification (mandatory, not counted toward 10 spot checks):**
Read the Identity section. For each technology/framework mentioned in the stack description,
verify it is actively used (not just imported) by checking for: mounted routes (web frameworks),
registered commands (CLI frameworks), configured connections (databases), active service
endpoints. If a framework is mentioned but not actively used, flag as INACCURATE.

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

**Step 1:** Copy to output location (differs for local vs remote):
```bash
if [ "${DEEP_CRAWL_MODE:-local}" = "remote" ]; then
    # Remote repo: deliver to temp output directory (not inside the clone)
    OUTPUT_DIR="/tmp/deep_crawl/output"
    mkdir -p "$OUTPUT_DIR"
    cp /tmp/deep_crawl/DEEP_ONBOARD.md "$OUTPUT_DIR/DEEP_ONBOARD.md"
    cp /tmp/xray/xray.md "$OUTPUT_DIR/xray.md"
    cp /tmp/deep_crawl/VALIDATION_REPORT.md "$OUTPUT_DIR/DEEP_ONBOARD_VALIDATION.md"
    echo "Remote crawl output delivered to: $OUTPUT_DIR/"
    echo "  - DEEP_ONBOARD.md"
    echo "  - xray.md"
    echo "  - DEEP_ONBOARD_VALIDATION.md"
else
    # Local repo: deliver to project docs/
    mkdir -p docs
    cp /tmp/deep_crawl/DEEP_ONBOARD.md docs/DEEP_ONBOARD.md
    cp /tmp/xray/xray.md docs/xray.md
fi
```

**Step 2:** Configure CLAUDE.md for automatic delivery (**local repos only** — skip for remote):
```bash
if [ "${DEEP_CRAWL_MODE:-local}" = "remote" ]; then
    echo "Skipping CLAUDE.md update (remote repo — read-only analysis)"
else
    if [ -f CLAUDE.md ]; then
        grep -q "DEEP_ONBOARD" CLAUDE.md || cat >> CLAUDE.md << 'ONBOARD_EOF'

# Codebase Onboarding
Read docs/DEEP_ONBOARD.md before starting any task. It contains verified behavioral documentation, critical paths, gotchas, and conventions for this codebase.

## Onboarding Document Change Tracking

If you modify code that may affect claims in docs/DEEP_ONBOARD.md, append to docs/.onboard_changes.log:

    {ISO_TIMESTAMP} | {FILE:LINE} | {SECTION_PATH} | {BRIEF_DESCRIPTION}

Section path uses document headings: `{## Section}` or `{## Section} / {### Subsection}`.
Do not manually edit DEEP_ONBOARD.md — it is a generated artifact.
ONBOARD_EOF
    else
        cat > CLAUDE.md << 'CLEOF'
# Project Instructions

## Codebase Onboarding
Read docs/DEEP_ONBOARD.md before starting any task. It contains verified behavioral documentation, critical paths, gotchas, and conventions for this codebase.

## Onboarding Document Change Tracking

If you modify code that may affect claims in docs/DEEP_ONBOARD.md, append to docs/.onboard_changes.log:

    {ISO_TIMESTAMP} | {FILE:LINE} | {SECTION_PATH} | {BRIEF_DESCRIPTION}

Section path uses document headings: `{## Section}` or `{## Section} / {### Subsection}`.
Do not manually edit DEEP_ONBOARD.md — it is a generated artifact.
CLEOF
    fi
fi
```

**Step 3:** Copy validation report (**local repos only** — remote already copied in Step 1):
```bash
if [ "${DEEP_CRAWL_MODE:-local}" != "remote" ]; then
    cp /tmp/deep_crawl/VALIDATION_REPORT.md docs/DEEP_ONBOARD_VALIDATION.md
fi
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

Delivered to: {local: docs/DEEP_ONBOARD.md | remote: /tmp/deep_crawl/output/}
CLAUDE.md: {UPDATED/CREATED/SKIPPED (remote)} — document will auto-load in all sessions
Prompt caching: Active — subsequent sessions read at ~90% reduced cost
Clone: {remote only: /tmp/deep_crawl/repo/ — rm -rf when done}
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

**Remote repository:**
- `DEEP_CRAWL_ROOT` points to `/tmp/deep_crawl/repo/` (the clone directory)
- All file reads, greps, and investigation happen against the clone
- Phase 6 delivers to `/tmp/deep_crawl/output/` instead of project `docs/`
- CLAUDE.md update is skipped (read-only analysis of external repo)
- The clone is a full clone with git history — git log/blame work normally
- Private repos: `gh repo clone` handles auth via the user's `gh` credentials
- Cleanup: user should `rm -rf /tmp/deep_crawl/repo/` when done
- If the clone is very large (>2000 files), the monorepo edge case applies

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
        │   ├── compression_targets.json
        │   ├── quality_gates.json
        │   └── exemplar_templates.md
        └── templates/
            ├── DEEP_ONBOARD.md.template
            ├── CRAWL_PLAN.md.template
            └── VALIDATION_REPORT.md.template
```

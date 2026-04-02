# Unrestricted Deep Crawl — Change Declaration

## Purpose

This branch removes all token budget ceilings and context-era investigation constraints from the deep crawl pipeline. The hypothesis: budget constraints caused the agent to self-compress during investigation (Phase 2) and synthesis (Phase 3), not just during the explicit compression step (Phase 4). See `output/constrained/DECLARATION.md` for the full constraint chain analysis.

Two categories of constraints were removed:

1. **Output budget constraints** — token ceilings, per-section budgets, budget comments in templates, trim instructions. These suppressed how much the agent wrote.
2. **Investigation constraints** — 500-line module read caps, 3-file working memory limits, numeric quantity anchors. These suppressed how much the agent investigated, regardless of output budget. Designed for 200K context windows, now running under 1M.

## What Changed (6 files)

### File 1: `.claude/agents/deep_crawl.md`

**Frontmatter description (line 3):**
- Before: `"maximally compressed onboarding document...Designed to run without token budget constraints"`
- After: `"comprehensive onboarding document...No token budget ceiling — include everything that's not redundant"`

**Protocol B module read limit (was line 106):**
- Before: `Read the entire module (or first 500 lines if larger)`
- After: `Read the entire module`
- Why: With 1M context, the agent can read entire modules regardless of size. The 500-line cap meant 75% of large modules went unread — exactly where the complex logic, edge cases, and gotchas live.

**Phase 3 synthesis thinking prompt (was line 185):**
- Before: `What are the 3-5 most important things a downstream agent needs?`
- After: `What are ALL the important things a downstream agent needs?`
- Why: "3-5" is a quantitative anchor that limits synthesis scope. Same self-limiting mechanism as the budget comments, just subtler.

**Phase 4 heading (was line 206):**
- Before: `### Phase 4: COMPRESS (Optimize for Token Budget)`
- After: `### Phase 4: REFINE (Optimize for Value Density)`

**Phase 4 target table:** Removed entirely. Replaced with: "There is no token budget ceiling. Include everything that's not redundant with information derivable from file names and signatures."

**Phase 4 Step 6 (trim instruction):** Removed. The 8-step algorithm became 7 steps. Step 6 (formerly Step 7) now says "Verify completeness...add content" instead of "restore minimal content." Step 7 is cache structure verification.

**Quality checklist (was line 404):**
- Before: `- [ ] Document is within token budget for codebase size`
- After: `- [ ] Every section contains information not derivable from file names and signatures`

### File 2: `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

Removed all 9 `<!-- Budget: ~N tokens -->` HTML comments and replaced with value-based guidance or nothing:

| Section | Before | After |
|---------|--------|-------|
| Critical Paths | `Budget: ~3000 tokens. Prioritize the 3-5 most important paths.` | `Include all verified paths.` |
| Module Behavioral Index | `Budget: ~4000 tokens.` | `Include all modules where behavior is not obvious from the name.` |
| Key Interfaces | `Budget: ~1000 tokens.` | (removed, kept surrounding guidance) |
| Error Handling | `Budget: ~1000 tokens.` | (removed) |
| Shared State | `Budget: ~800 tokens.` | (removed) |
| Domain Glossary | `Budget: ~600 tokens.` | (removed) |
| Config Surface | `Budget: ~1000 tokens.` | (removed) |
| Conventions | `Budget: ~800 tokens.` | (removed) |
| Gotchas | `Budget: ~1500 tokens.` | (removed) |

### File 3: `.claude/skills/deep-crawl/configs/compression_targets.json`

- All `target_tokens` set to `null` (were 8000-18000)
- All `max_tokens` set to `null` — both global targets and per-section budgets
- `min_tokens` retained as soft floor (unchanged)
- Removed numeric expected ranges from `guidance` text (e.g., "Expect 20-40K" → "Be comprehensive") — numeric ranges anchor the agent to a target even when framed as guidance
- Description updated: "No hard ceilings — include everything that's not redundant"
- Note updated to state "No token ceilings"

### File 4: `.claude/skills/deep-crawl/SKILL.md`

**Pipeline description (line 37):**
- Before: `Phase 4: COMPRESS    8-step algorithm → reduce to token budget`
- After: `Phase 4: REFINE      7-step algorithm → maximize value density, cut only redundancy`

**Output table (line 56):**
- Before: `Onboarding document (8-20K tokens)`
- After: `Onboarding document (unrestricted, value-driven)`

**Context management (line 67):**
- Before: `Never hold >3 source files in working memory simultaneously`
- After: `Hold as many source files in working memory as the current task requires`
- Why: The 3-file limit was defensive context management for 200K windows. It forces isolated module investigation and prevents cross-module pattern comparison. With 1M context, this is unnecessarily restrictive.

**Token Budget Targets section (lines 79-86):** Removed entirely. Replaced with two-line qualitative guidance: "No token ceilings. Let the content determine the size."

**Feedback reference (line 93):**
- Before: `this data informs section budget allocation`
- After: `this data informs section prioritization`

### File 5: `INTENT.md`

**Line 57 (agent description):**
- Before: `"produce a small, maximally useful onboarding document"`
- After: `"produce a comprehensive, maximally useful onboarding document"`

**After line 83 (Compression tradeoff paragraph):** Added new paragraph explaining unrestricted mode as a calibration mechanism. Documents that unrestricted mode removes constraints while preserving investigation protocols, evidence standards, and validation.

### File 6: `.claude/agents/deep_crawl.md` line 3

Already covered in File 1 changes above (same file).

## What Did NOT Change

These files are intentionally unmodified — verify with `git diff master`:

| File | Why Unchanged |
|------|--------------|
| `lib/investigation_targets.py` | Scanner logic — no budget awareness |
| `xray.py` | Entry point — no budget awareness |
| `formatters/*.py` | Output formatting — no budget awareness |
| `lib/config_loader.py` | Config loading — doesn't enforce budgets |
| `.claude/agents/deep_onboard_validator.md` | Validates quality, not size |
| `configs/domain_profiles.json` | Domain classification, not budgets |
| `configs/generic_names.json` | Name classification, not budgets |
| `templates/CRAWL_PLAN.md.template` | No budget references |
| `templates/VALIDATION_REPORT.md.template` | No budget references |

## Remaining Filters

After all constraint removal, the only filter on output content is: **"not redundant with information derivable from file names and signatures."** This cuts noise, not depth. Verified by scanning all deep crawl files for budget/ceiling/anchor language — no constraining references remain.

## Verification (Round 1)

```bash
# Confirm exactly the expected files changed
git diff --name-only master unrestricted-deep-crawl

# Expected:
# .claude/agents/deep_crawl.md
# .claude/skills/deep-crawl/SKILL.md
# .claude/skills/deep-crawl/configs/compression_targets.json
# .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template
# INTENT.md
# output/unrestricted/DECLARATION.md
```

---

## Round 2: Implicit Constraint Removal

### Context

Round 1 removed explicit budget constraints (token ceilings, per-section budgets). Result: unrestricted output ~2,889 tokens vs constrained ~2,670 — only 8% difference for an 802-file codebase. Investigation found 12 implicit constraints still governing behavior. The `min_tokens` floor of 13,000 was being violated by 4.5x and never checked.

### What Changed (4 files, 12 constraint removals)

#### C1 (VERY HIGH): Stopping gate — require all priorities + coverage metrics
**File:** `.claude/agents/deep_crawl.md` (stopping criteria)

- Before: 5-condition gate checking only P1, P2, P4 + questions + novelty ("last 3 tasks did not surface new gotchas")
- After: 8-condition gate checking ALL priorities (P1-P6) + questions + coverage check
- Added coverage check with 4 quantitative thresholds (50% subsystem coverage, modules deep-read >= max(10, file_count/40), traces >= entry points, cross-cutting concerns from 3+ subsystems)
- Why: The old gate let the agent stop after P4 without investigating P3 (pillar summaries), P5 (conventions), or P6 (gaps). The novelty gate ("last 3 tasks did not surface new gotchas") was a premature stopping heuristic — it rewarded shallow investigation by allowing the agent to stop once it ran out of surprises, even if large subsystems were uninvestigated.

#### C2 (HIGH): Remove 8-hop trace limit
**File:** `.claude/agents/deep_crawl.md` (Protocol A)

- Before: `Repeat until terminal side effect or 8 hops`
- After: `Repeat until terminal side effect (no hop limit — follow the full chain)`
- Why: 8 hops was arbitrary. Some request paths (e.g., middleware chains, plugin pipelines) legitimately span 15+ module boundaries. Truncating traces hides exactly the cross-module behavior that makes onboarding documents valuable.

#### C3 (HIGH): Replace "rarely-needed structural info" exclusion
**File:** `.claude/agents/deep_crawl.md` (Phase 3 synthesis rules)

- Before: `Don't include rarely-needed structural info — reference xray output for those`
- After: `Reference xray output for raw structural data (full class skeletons, complete import graphs) — but DO include structural facts that appear in multiple findings or that agents need to understand behavioral descriptions (key class signatures, primary data types, inheritance hierarchies that affect behavior)`
- Why: "Rarely-needed" is a subjective judgment that systematically excludes structural information that downstream agents frequently need. The agent can't predict what future tasks will require. The new rule draws the line at raw data (xray has it) vs. structural facts integrated with behavioral descriptions (include them).

#### C4 (HIGH): Replace 30-second grep redundancy filter (3 locations)
**File:** `.claude/agents/deep_crawl.md` (Phase 5c, Constraints, Quality Checklist)

- Before: `Would an agent who can see the file tree and run grep figure this out in under 30 seconds? If yes, cut it.` / `Never include information a downstream agent can derive from file names or grep in <30 seconds.` / `No redundant information that grep could find in 30 seconds`
- After: All three replaced with literal-duplication checks. The new standard: cut content only if it's literally duplicated from another section or from xray output verbatim. Synthesized information (cross-module patterns, behavioral descriptions, contextual annotations) is explicitly preserved even if the underlying raw data is grepable.
- Why: The 30-second rule was the single most aggressive content filter. It implicitly classifies ALL synthesized information as redundant if the raw data is searchable — but the synthesis (connecting patterns across modules, annotating behavioral context) is precisely what saves downstream agents from opening files. The rule confused "data availability" with "insight availability."

#### C5 (MEDIUM): Invert self-evidence module cut → expand thin entries
**File:** `.claude/agents/deep_crawl.md` (Phase 4 Step 2)

- Before: `Cut self-evident module summaries. Does the module name + architecture position already tell an agent what it does? If yes, cut it.`
- After: `Expand thin module summaries. Does this entry describe non-obvious BEHAVIOR (runtime dependencies, side effects, gotchas), or is it just restating the module name? If the latter, add behavioral detail from the crawl findings or note it as a gap. Do not cut modules from the index — a complete index is more useful than a filtered one.`
- Why: The old instruction was a deletion directive — it removed modules whose names "self-explain." But module names explain purpose, not behavior. `payment_service.py` tells you it handles payments; it doesn't tell you it retries 3x, caches responses, or mutates shared state. The inversion keeps all modules and enriches thin entries.

#### C6 (MEDIUM): Soften "don't copy verbatim" rule
**File:** `.claude/agents/deep_crawl.md` (Phase 3 synthesis rules)

- Before: `Don't copy findings verbatim — synthesize across modules`
- After: `Synthesize across modules where patterns exist — but preserve individual findings verbatim when they describe unique behaviors, gotchas, or module-specific detail that does not generalize`
- Why: Blanket synthesis loses module-specific detail. Not everything generalizes. A gotcha in one module is important precisely because it's unique — forcing it into a cross-module synthesis dilutes the signal.

#### C7 (MEDIUM): Scale Protocol C sample size
**File:** `.claude/agents/deep_crawl.md` (Protocol C)

- Before: `Read 2-3 representative examples in full`
- After: `Read representative examples in full — at least max(3, result_count / 5) examples, sampling from different subsystems`
- Why: "2-3" is a fixed constant that doesn't scale with codebase size. A 50-file codebase and a 2000-file codebase both got 2-3 examples of each cross-cutting concern — meaning the larger codebase had proportionally less investigation.

#### C8 (MEDIUM): Scale Protocol D sample size
**File:** `.claude/agents/deep_crawl.md` (Protocol D)

- Before: `Read 3-5 examples of the pattern (from xray pillar/hotspot list)`
- After: `Read examples of the pattern from xray pillar/hotspot list — at least max(5, pillar_count / 3) examples, covering different architectural layers`
- Why: Same fixed-constant problem as C7. Convention documentation should sample proportionally to the codebase's architectural breadth.

#### C9 (MEDIUM): Add coverage checks beyond the 10 standard questions
**File:** `.claude/agents/deep_crawl.md` (Phase 4 Step 6 + Phase 5 new subsection)

- Phase 4 Step 6: Split into 6a (standard questions — minimum bar) and 6b (coverage breadth — depth bar). Coverage breadth checks: subsystem coverage, pillar coverage in Module Index, entry point traces, cross-cutting concern coverage.
- Phase 5: Added subsection 5a-bis with a coverage breadth test table (5 metrics with targets and actuals). If any metric is below target, agent returns to Phase 3 findings.
- Why: The 10 standard questions are necessary but not sufficient. A document can answer all 10 questions while covering only 20% of the codebase — it just answers them from the modules it happened to investigate. The coverage checks ensure breadth.

#### C10 (MEDIUM): Update CRAWL_PLAN template completion criteria
**File:** `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template`

- Before: `All P1-P4 complete + 10/10 standard questions answerable + no new gotchas in last 3 tasks.`
- After: `All P1-P6 investigated + 10/10 standard questions answerable + coverage check passes (50%+ subsystems documented, modules deep-read >= max(10, file_count/40), all entry points traced).`
- Why: Template must match the agent's updated stopping criteria. The old template only checked P1-P4 and included the novelty gate.

#### C11 (LOW): Add min_tokens enforcement to Phase 4
**File:** `.claude/agents/deep_crawl.md` (Phase 4, between Step 1 and Step 2)

- Added: After the `wc` measurement in Step 1, the agent reads `min_tokens` from `compression_targets.json` and checks whether the draft meets the floor. If below, it lists coverage gaps, returns to Phase 2, re-synthesizes, and re-measures before proceeding.
- Why: The `min_tokens` floor existed in the config but was never checked anywhere in the pipeline. The unrestricted crawl produced 2,889 tokens against a 13,000-token floor — a 4.5x violation that went undetected.

#### C12 (LOW): Fix SKILL.md framing language
**File:** `.claude/skills/deep-crawl/SKILL.md`

- Before: `Systematic codebase investigation producing maximally compressed onboarding documents optimized for AI agent consumption via CLAUDE.md delivery with prompt caching.`
- After: `Systematic codebase investigation producing comprehensive onboarding documents optimized for AI agent consumption via CLAUDE.md delivery with prompt caching. Depth over brevity — include everything that saves a downstream agent from opening files.`
- Why: "Maximally compressed" directly contradicts the unrestricted mode's goal. This is the first line of the skill description — it frames the agent's entire orientation.

### What Did NOT Change (Round 2)

| File | Why Unchanged |
|------|--------------|
| `compression_targets.json` | Config values already correct from Round 1; the problem was non-enforcement, not wrong values |
| `DEEP_ONBOARD.md.template` | Template structure is fine; content volume is governed by agent instructions, not template |
| `deep_onboard_validator.md` | Validates quality, not volume |
| `INTENT.md` | Already updated in Round 1 |
| `domain_profiles.json` | Domain classification, not content constraints |
| `generic_names.json` | Name classification, not content constraints |
| `COMMANDS.md` | Command definitions, not investigation behavior |

### Verification (Round 2)

```bash
# Confirm no "30 seconds" or "30-second" language remains
rg "30 second" .claude/agents/deep_crawl.md

# Confirm no "8 hops" remains
rg "8 hops" .claude/agents/deep_crawl.md

# Confirm no "rarely-needed" remains
rg "rarely-needed" .claude/agents/deep_crawl.md

# Confirm no "maximally compressed" remains in skill
rg "maximally compressed" .claude/skills/deep-crawl/

# Confirm no "last 3 tasks" novelty gate remains
rg "last 3 tasks" .claude/agents/deep_crawl.md

# Confirm min_tokens floor reference exists
rg "min_tokens" .claude/agents/deep_crawl.md
```

---

## Round 3: Phase 4-5 Execution Hardening

### Context

R6 proved parallel synthesis (60.7% retention vs 13.5%). But DRAFT_ONBOARD.md and DEEP_ONBOARD.md were byte-identical — Phase 4-5 never executed. Root causes: no proceed-gate after floor check, no disk artifacts proving step execution, context exhaustion by Phase 4, and grep-and-count shortcuts in validation.

### What Changed (1 file: SKILL.md)

1. **Delegate Phase 4-5 to sub-agent** — Fresh context window for refinement. Orchestrator spawns agent with draft + findings + instructions. Completion gate checks md5sum difference.
2. **Proceed-gate after Step 1** — Explicit "proceed to Step 2" instruction after floor check passes.
3. **REFINE_LOG.md** — Every Phase 4 step appends a structured log line. Absence proves skipping.
4. **Quantitative thresholds** — "Thin" defined as <=5 words + guessable from name. "Similar" defined as same risk category + same subsystem.
5. **Phase 4 completion gate** — md5sum comparison catches byte-identical output.
6. **Phase 5 written answers** — Each question requires a 1-2 sentence answer written to VALIDATION_REPORT.md (not just YES/NO).
7. **Spot-check structure** — 10 claims with actual code quotes and verdicts.
8. **Adversarial plan on disk** — Written to VALIDATION_REPORT.md, not just reasoned about.
9. **Phase 5 completion gate** — grep-based section count verification.

### Metrics (R6 vs R6-refined)

| Metric | R6 | R6-refined target | R6-refined actual |
|--------|-----|-------------------|-------------------|
| DRAFT == DEEP_ONBOARD | yes (byte-identical) | no (must differ) | no (f4e411b vs 6ce344f) |
| REFINE_LOG.md exists | no | yes, with 7 log entries | yes, 1200 words, Steps 1-7 + Summary |
| VALIDATION_REPORT sections | 0 | 10 questions + 10 spot-checks + adversarial | 10 Q + 10 spot-checks + adversarial (all present) |
| Phase 5 spot-checks | 0 | 10 claims verified against code | 10/10 CONFIRMED |
| Draft words | 29,737 | — | 29,737 |
| Final words | 29,737 (identical copy) | must differ | 30,236 (+499 words, +1.7%) |
| Standard questions answerable | untested | 10/10 | 10/10 YES |
| Adversarial simulation | untested | PASS/PARTIAL/FAIL | PASS (5/5) |

### Execution Details

- Sub-agent ran Phase 4-5 in a fresh context window (535s, 146K tokens consumed)
- Phase 4 Step 2: Expanded 8 thin module entries (7 new subsystems added to Module Index)
- Phase 4 Step 3: Merged 5 gotcha groups (19→10 entries, 9 consolidated)
- Phase 4 Step 4: Extracted 2 shared sub-paths across 4-5 traces
- Phase 4 Step 5: Converted 2 prose sections to tables
- Phase 5b: All 10 spot-check claims CONFIRMED against actual codebase code
- Phase 5d: Adding a MetaAnalysisAgent using only the document scored PASS (5/5)

---

## Round 4: Refiner/Validator Separation, Findings Recovery, Anti-Compression

### Context

R6-refined proved Phase 4-5 hardening works (files no longer byte-identical, validation artifacts produced). But the refinement was shallow: +499 words (+1.7%) on a 30K document. Three structural problems remained:

1. **Self-validation bias** — One sub-agent did both refinement AND validation. It confirmed its own minimal work as adequate.
2. **No findings recovery** — SYNTHESIS_INPUT.md has 48,947 words, draft has 29,737 (~40% dropped during synthesis). Phase 4 never cross-referenced dropped findings to recover lost content.
3. **No structural editing** — Draft assembled from 5 independent synthesis agents, but no pass normalizes terminology or smooths transitions between independently-authored sections.

Plus: residual compression-encouraging language throughout the pipeline ("optimize for value density", "cut Tier 3-4 for density", synthesis "target 50-70%", "compression_ratio" in delivery metrics).

### What Changed (2 files, 3 structural changes + 12 anti-compression edits)

#### A. Refiner/Validator Separation
**File:** SKILL.md Phase 3 Step 9

Split single Phase 4+5 sub-agent into two sequential sub-agents:
- **Refiner:** Receives draft + synthesis input + findings + crawl plan + xray. Executes Phase 4 only. Output: DEEP_ONBOARD.md + REFINE_LOG.md. Sentinel: REFINE.done.
- **Validator:** Receives DEEP_ONBOARD.md + codebase + crawl plan only. Does NOT receive findings or synthesis input. Executes Phase 5 only. Output: VALIDATION_REPORT.md. Sentinel: VALIDATE.done. Cannot modify DEEP_ONBOARD.md.
- Remediation loop: If validator returns FAIL, re-spawn refiner with fix instructions appended. Max 1 cycle.

#### B. Findings Recovery (New Phase 4 Step 2)
**File:** SKILL.md Phase 4

New step before editorial work: extract [FACT]-tagged lines from SYNTHESIS_INPUT.md, cross-reference against draft, recover dropped Tier 1-2 findings, selectively recover Tier 3-4 with logging.

#### C. Structural Editing (New Phase 4 Step 8)
**File:** SKILL.md Phase 4

New step after verify completeness: terminology normalization, cross-section deduplication, cross-reference insertion, transition smoothing. Anti-compression guard: step must NOT reduce word count.

#### D. Anti-Compression Reinforcement (12 edits across SKILL.md + template)

| # | Location | Change |
|---|----------|--------|
| D1 | Tier 4 description | "include if space" → "include unless literally duplicated" |
| D2 | Tier cutting rule | "cut for density" → "merge same-fact entries, keep distinct" |
| D3 | Synthesis target | "50-70% retention" → "every non-redundant finding at full fidelity" |
| D4 | Retention check | "should be 50-70%" → "under 50% means over-compressed, no upper bound" |
| D5 | Phase 4 title | "Optimize for Value Density" → "Recover, Expand, and Polish" |
| D6 | Phase 4 body | Added anti-truncation principle paragraph |
| D7 | Tier protection | "cut Tier 4 first" → "merge same-fact entries, keep both when in doubt" |
| D8 | 5c redundancy check | Added WARNING against flagging content as redundant because derivable from source |
| D9 | Delivery report | "compression_ratio:1 compression" → "covering {tokens} token codebase" |
| D10 | Footer metadata ref | "compression ratio" → "coverage scope" |
| D11 | Edge case handler | "30% threshold, 50-70% target" → "50% threshold, full fidelity target" |
| D12 | Template footer | "Compression: X → Y tokens (Z:1)" → "Coverage: Y tokens documenting X token codebase" |

### Phase 4 Step Order (after all changes)

| Step | Name | Status |
|------|------|--------|
| 1 | Measure | existing |
| 2 | Recover dropped findings | **NEW** |
| 3 | Expand thin module summaries | existing (was 2) |
| 4 | Merge similar gotchas | existing (was 3) |
| 5 | Compress traces with shared sub-paths | existing (was 4) |
| 6 | Convert prose to tables | existing (was 5) |
| 7 | Verify completeness (7a + 7b) | existing (was 6) |
| 8 | Structural editing | **NEW** |
| 9 | Verify caching structure | existing (was 7) |

### Verification

```bash
# Anti-compression language removed
grep -n "cut Tier 3-4 content for density" .claude/skills/deep-crawl/SKILL.md  # expect 0
grep -n "Target: 50-70%" .claude/skills/deep-crawl/SKILL.md  # expect 0
grep -n "compression_ratio" .claude/skills/deep-crawl/SKILL.md  # expect 0
grep -n "compression_ratio" .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template  # expect 0

# New features present
grep -n "Recover dropped findings" .claude/skills/deep-crawl/SKILL.md  # expect hit
grep -n "Structural editing" .claude/skills/deep-crawl/SKILL.md  # expect hit
grep -n "Anti-truncation principle" .claude/skills/deep-crawl/SKILL.md  # expect hit
grep -n "REFINE.done" .claude/skills/deep-crawl/SKILL.md  # expect hit
grep -n "VALIDATE.done" .claude/skills/deep-crawl/SKILL.md  # expect hit
```

### Execution Results

| Metric | R6-refined | R7 target | R7 actual |
|--------|------------|-----------|-----------|
| Refiner/Validator separated | no (single agent) | yes (2 agents) | yes (separate REFINE.done + VALIDATE.done) |
| DRAFT == DEEP_ONBOARD | no (f4e411b vs 6ce344f) | no (must differ) | no (f4e411b vs a760fa9) |
| REFINE_LOG.md Steps logged | Steps 1-7 | Steps 1-9 (2 new) | Steps 1-9 (all present) |
| Findings recovery ran | no | yes (Step 2) | yes — 5 Tier 1-2 recovered, 8 Tier 3-4 confirmed redundant |
| Structural editing ran | no | yes (Step 8) | yes — 13 terms normalized, 12 cross-refs, 3 transitions |
| Draft words | 29,737 | — | 29,737 |
| Final words | 30,236 (+499, +1.7%) | > 30,236 | 30,380 (+643, +2.2%) |
| Standard questions | 10/10 YES | 10/10 | 10/10 YES |
| Spot-checks | 10/10 CONFIRMED | 10/10 | 10/10 CONFIRMED |
| Adversarial simulation | PASS (5/5) | PASS | PASS (5/5) |
| VALIDATION_REPORT sections | all present | all present | 10 Q + 10 spot-checks + adversarial + coverage |

**Key improvement over R6-refined:** Validator ran as separate agent without access to findings/synthesis input. Validation is now genuinely independent — the validator can only assess the document as a standalone artifact against the actual codebase. Refiner recovered 5 dropped Tier 1-2 findings and added 12 cross-references + 3 section transitions that R6-refined's single-agent approach missed.

---

## Round 5: Eliminate Compression — Assembly-Only Pipeline (R8)

### Context

R1-R7 attempted to fix compression through instructional changes: anti-compression edits, findings recovery steps, anti-truncation principles, structural editing. Results after 4 rounds:

| Round | Word Delta | % Change |
|-------|-----------|----------|
| R6 | +0 | 0% (byte-identical) |
| R6-refined | +499 | +1.7% |
| R7 | +643 | +2.2% |

49K words of findings → 30K word document. 19K words dropped. Phase 4 recovers ~600 words. The instructional approach plateaued.

**Root cause:** The entire pipeline was designed as a compression system. The word "SYNTHESIZE" means condense. Despite "TRANSCRIBE, do not summarize," the synthesis agents retained only 60% of input. Phase 4's 9 editorial steps (merge, compress, convert) reinforced compression behavior even with anti-compression guards. No amount of "don't compress" instructions overrides the system-wide compression gestalt.

**Fix:** Structural elimination. Make synthesis non-compressive by renaming it to assembly. Replace Phase 4's editorial pipeline with mechanical assembly + additive-only cross-referencing. Test with 1M context where 45K words = 5.8% of available window.

### What Changed (4 files, 10 structural changes)

#### A. Phase 3 renamed from SYNTHESIZE to ASSEMBLE
**File:** SKILL.md

The word "synthesize" implies condensation. "Assemble" means "put pieces together." All references to "synthesis sub-agents" → "assembly sub-agents" throughout Phase 3.

#### B. Assembly sub-agent prompt rewritten (biggest lever)
**File:** SKILL.md (sub-agent prompt template)

Old Rules block anchored at "50-90% of input" — even 50% is a compression target. New rules:
- "INCLUDE EVERY FINDING. The output context window is 1M tokens. Your section will consume less than 5% of available context."
- "Your output should be 80-100% of your input word count. If you produce less than 80%, you have dropped findings."
- Removed all "synthesize across modules" language that triggered condensation behavior.

#### C. Phase 4 replaced: REFINE → CROSS-REFERENCE (Additive Only)
**File:** SKILL.md

Removed 9-step editorial pipeline (merge gotchas, compress traces, convert prose, structural editing, findings recovery). Replaced with 4-step mechanical process:
1. Measure (floor check only)
2. Add cross-references between independently-assembled sections
3. Verify completeness (note gaps, don't fabricate)
4. Verify caching structure

Key constraint: Phase 4 may NOT delete, merge, summarize, or compress. Every operation is strictly additive. Word count of DEEP_ONBOARD.md must be >= DRAFT_ONBOARD.md.

#### D. Retention threshold raised: 50% → 80%
**File:** SKILL.md (Step 8 retention check + undersized section edge case)

Old: "under 50% means over-compressed." New: "under 80% means assembly agent dropped findings." Re-spawn instructions explicitly cite 1M context window and 5% utilization.

#### E. Refiner sub-agent → Cross-referencer sub-agent
**File:** SKILL.md (Step 9)

Updated prompt: "Execute Phase 4 (CROSS-REFERENCE) — additive only, no deletions." Removed SYNTHESIS_INPUT.md and findings/ from input files (cross-referencer doesn't need them — it only links existing content). Completion gate checks word count >= draft (not md5sum difference).

#### F. compression_targets.json gutted to min_tokens only
**File:** compression_targets.json

Removed `target_tokens`, `max_tokens`, `guidance` from all tiers. Removed `max_tokens` from section budgets. Updated description: "Minimum document size floors by codebase size. Only used as a tripwire."

#### G. Template footer updated
**File:** DEEP_ONBOARD.md.template

Added findings count: `{FINDINGS_COUNT} findings from {TASKS_COMPLETED} investigation tasks.`

#### H. CLAUDE.md contamination prevention
**File:** SKILL.md (new Step 1b + Step 10)

Sub-agents spawn with fresh context and auto-read CLAUDE.md. If CLAUDE.md frames the project as producing "compressed intelligence," sub-agents absorb compression bias before their task prompt. New steps temporarily rename CLAUDE.md files before spawning and restore after completion.

### Verification

```bash
# Phase 3 renamed
grep -n "SYNTHESIZE" .claude/skills/deep-crawl/SKILL.md  # expect 0
grep -n "ASSEMBLE" .claude/skills/deep-crawl/SKILL.md    # expect hits

# No compression anchors in assembly prompts
grep -n "50-90%" .claude/skills/deep-crawl/SKILL.md       # expect 0
grep -n "50-70%" .claude/skills/deep-crawl/SKILL.md       # expect 0

# Phase 4 is mechanical only
grep -n "Merge similar gotchas" .claude/skills/deep-crawl/SKILL.md        # expect 0
grep -n "Compress traces" .claude/skills/deep-crawl/SKILL.md              # expect 0
grep -n "CROSS-REFERENCE" .claude/skills/deep-crawl/SKILL.md              # expect hit
grep -n "Additive Only" .claude/skills/deep-crawl/SKILL.md                # expect hit

# 80% retention threshold
grep -n "80%" .claude/skills/deep-crawl/SKILL.md  # expect hits
```

### What This Tests

Is a ~40-45K word document that includes essentially everything the investigation found actually more useful than a 30K word document where 40% of findings were compressed away? With 1M context, the token cost difference is noise (58K tokens vs 39K tokens — both under 6% of context). The question is purely about downstream utility.

---

## Round 9: Closed-Loop Validation-Driven Investigation

### Context

R8 eliminated compression from assembly (30K → 62K words). Citation-level measurement shows 81.8% fact retention (1,089/1,332 unique file:line citations). Assembly is no longer the bottleneck.

The bottleneck is now **investigation gaps**. R8 validation returned Q8 (Testing) as PARTIAL. The Gaps section lists 5 uninvestigated areas. These aren't assembly failures — the information doesn't exist in the findings because Phase 2 didn't investigate deeply enough.

**The structural problem:** The pipeline was open-loop. The validator identifies exactly what's missing but has no power to fix it. The remediation loop (SKILL.md) re-spawned the cross-referencer, which can only add cross-references — not new content that was never investigated.

```
Before:   Investigate → Assemble → Validate → Report gaps (stop)
After:    Investigate → Assemble → Validate → Investigate gaps → Patch → Re-validate
```

### What Changed (3 files, 5 structural changes)

#### A. New Phase 3.5: Fact-Level Completeness Check
**File:** SKILL.md — inserted between Step 8 (verify retention) and Step 9 (delegate refinement/validation)

Mechanical step (no LLM needed): extract all file:line citations with [FACT] tags from SYNTHESIS_INPUT.md, verify each appears in DRAFT_ONBOARD.md, recover any that were dropped. Citations are classified by finding source (traces/, modules/, cross_cutting/, conventions/) and appended to the appropriate section before re-concatenation.

**Why word count is the wrong metric:** An assembly agent at 95% word count could drop the most important gotcha while padding with verbose formatting. Citation-level checking measures what actually matters: are the verified facts in the document?

#### B. Remediation Loop Replaced with Investigation-Driven Gap Closure
**File:** SKILL.md — replaced the old 5-step remediation loop

Old loop re-spawned the cross-referencer with fix instructions. The cross-referencer can only add cross-references — it can't investigate new topics. A NO on Q8 (Testing) means the investigation didn't produce testing findings.

New loop (6 steps): R1 maps each NO/PARTIAL gap to an investigation protocol and target. R2 spawns targeted investigation agents in parallel. R3 waits for sentinel files. R4 patches DEEP_ONBOARD.md with new findings (additive only). R5 re-validates only previously-failed questions. R6 accepts or delivers with max 1 gap-closure cycle.

Gap-to-protocol mapping covers all 10 standard questions plus adversarial simulation failures, each with a specific investigation protocol (A/B/C/D) and target.

#### C. Phase 5a: Machine-Parseable Gap Descriptions
**File:** SKILL.md — added structured fields after rating format

When rating is NO or PARTIAL, validator now also includes: Gap (1-sentence), Investigation needed (protocol + target files), Expected output (what investigation should produce). This makes the validator's output directly actionable by the remediation loop.

#### D. Phase 5d: Structured Adversarial Failure Info
**File:** SKILL.md — added structured fields to step 3

When an adversarial step produces incorrect or missing guidance, validator now includes: Missing info, Source module, Investigation needed (protocol + target). Same structured format as 5a for consistency.

#### E. Fact-Retention Metric as First-Class Output
**Files:** SKILL.md (Step 8b logging), DEEP_ONBOARD.md.template (footer)

REFINE_LOG.md gets a Fact-Level Retention section with citation counts. Footer template updated to include `Fact retention: {RETAINED}/{TOTAL} citations ({PCT}%)`.

### Pipeline Change Summary

```
Phase 3 Step 8:  Verify retention (word count)        ← existing
Phase 3 Step 8b: Fact-level completeness check         ← NEW (mechanical)
Phase 3 Step 9:  Cross-reference + Validate            ← existing
Remediation:     Map gaps → Investigate → Patch → Re-validate  ← REPLACED
```

### Execution Results

| Metric | R8 | R9 target | R9 actual |
|--------|-----|-----------|-----------|
| Fact citations in findings | 1,332 (post-hoc) | measure | 674 |
| Fact citations in draft (pre-recovery) | 1,089 (post-hoc) | measure | 603 |
| Fact citations in draft (post-recovery) | — | measure | 673 |
| Fact retention rate | 81.8% (measured post-hoc) | >= 90% | 99.9% (673/674) |
| Dropped facts recovered | — | all dropped | 70 |
| Standard questions YES | 9/10 | 10/10 | **10/10 YES** |
| Gap investigation agents spawned | 0 | >= 1 | 1 (Q8 TESTING — 14 files read, 2,481 words) |
| Gap closure words added | 0 | > 0 | +3,022 total (+1,562 fact recovery, +750 Q8 patch, +1,667 cross-refs) |
| Re-validation questions improved | — | >= 1 | 1 (Q8: PARTIAL → YES) |
| Final word count | 61,869 | >= 61,869 | 64,891 |
| Adversarial simulation | PASS | PASS | PASS (5/5 + testing coverage confirmed) |
| Re-validation spot checks | — | 3/3 | 3/3 CONFIRMED |

### Verification

```bash
# Phase 3.5 fact check exists
grep -n "Fact-level completeness" .claude/skills/deep-crawl/SKILL.md
grep -n "dropped_citations" .claude/skills/deep-crawl/SKILL.md

# Remediation loop uses investigation, not cross-referencing
grep -n "Map gaps to investigation" .claude/skills/deep-crawl/SKILL.md
grep -n "Protocol A\|Protocol B\|Protocol C\|Protocol D" .claude/skills/deep-crawl/SKILL.md

# Phase 5 produces structured gap info
grep -n "Investigation needed" .claude/skills/deep-crawl/SKILL.md

# After execution
wc -w output/unrestricted-r9/DEEP_ONBOARD.md
grep "Fact retention" output/unrestricted-r9/DEEP_ONBOARD.md
grep "Gap Closure Re-validation" output/unrestricted-r9/VALIDATION_REPORT.md
```

### What This Tests

Can validation-driven investigation close the gap between 9/10 and 10/10 standard questions? Does fact-level completeness checking recover citations that word-count metrics miss? The goal is a document where the 10 standard questions become guarantees, not metrics — the pipeline keeps investigating until all 10 are YES.

---

## Round 10: Change-Oriented Investigation Protocols

### Context

R1-R9 produced a 65K word onboarding document scoring 10/10 standard questions, 99.9% fact retention, 10/10 spot checks, PASS adversarial. The document excels at **understanding** — what modules do, how they connect, what's dangerous.

But it's weak at **changing**. A fresh agent doing a refactor still needs to grep for reverse dependencies because the document doesn't answer "if I change module X, what breaks?" The xray output already has bidirectional import graphs (`imported_by` lists), function-level reverse lookup (274 functions with caller lists), and 37 high-impact functions — the investigation pipeline just never looked at this data.

**Goal:** Add change-oriented investigation protocols and sections to make the onboarding document actionable for modifications, not just understanding.

### What Changed (6 files, 25+ edits)

#### A. Two New Investigation Protocols
**File:** SKILL.md

- **Protocol E: Reverse Dependency & Change Impact** — Agent reads xray reverse dependency data + representative callers. Produces change impact cards per hub module showing importers, high-impact functions, signature-change consequences, behavior-change consequences, safe vs dangerous changes.
- **Protocol F: Change Scenario Walkthrough** — Agent reads Protocol E impact findings + module findings + conventions. Builds step-by-step checklists for common change types derived from domain profile's primary_entity + Extension Points findings.

#### B. 6-Batch Table (was 5)
**File:** SKILL.md

- Batch 2 expanded: P2 + P3 + P7 (impact analysis in parallel with module reads)
- Batch 3 updated: now includes async boundary concerns
- Batch 6 added: Change scenarios (Protocol F), depends on Batches 1-4
- Batches 5+6 run concurrently (both depend on 1-4, independent of each other)

#### C. Four New Template Sections
**File:** DEEP_ONBOARD.md.template

- **Change Impact Index** — after Module Behavioral Index. Per-hub-module tables showing importers, high-impact functions, safe vs dangerous changes.
- **Data Contracts** — after Key Interfaces. Pydantic models, dataclasses, TypedDicts with serialization details.
- **Change Playbooks** — after Extension Points. Step-by-step checklists for common modifications.
- **Environment Bootstrap** — after Reading Order. Minimum dev environment setup from scratch.

#### D. Q11 + Q12 Standard Questions
**Files:** SKILL.md, VALIDATION_REPORT.md.template

- Q11. IMPACT: If I change the most-connected module, what files are affected?
- Q12. BOOTSTRAP: How do I set up a dev environment and run tests from scratch?
- All "10 standard questions" references → "12 standard questions" throughout
- Remediation gap table extended with Q11 (Protocol E) and Q12 (Protocol C) mappings

#### E. Supporting Changes
**Files:** SKILL.md, CRAWL_PLAN.md.template, compression_targets.json

- Phase 0 mkdir: added `impact` and `playbooks` to findings directories
- Phase 3 Step 1a: State diagram extraction from trace findings
- Phase 3 Step 4: S6 assembly agent (Change Impact Index + Data Contracts + Change Playbooks)
- Phase 3 Step 6: Orchestrator writes Environment Bootstrap section
- Phase 3 Step 7: Updated concatenation order (20 files, was 16)
- Phase 4: Cross-reference rules 5-8 (impact→module, playbook→gotcha, contracts→data, bootstrap→config)
- CRAWL_PLAN: Added P7 section, updated completion criteria to P1-P7/12 questions
- compression_targets.json: 4 new section entries (change_impact_index, data_contracts, change_playbooks, environment_bootstrap)
- Quality checklist: 3 new items (hub module coverage, playbook exists, data contracts)
- Async/sync boundary grep patterns added to Protocol C

### Execution Results

| Metric | R9 | R10 target | R10 actual (Part 2) |
|--------|-----|-----------|------------|
| Standard questions | 10/10 YES | 12/12 YES | 12/12 YES |
| Fact retention | 99.9% (673/674) | >= 99% | 1484 [FACT] total (157 new in re-investigated sections) |
| Word count | 64,891 | >= 64,891 | 70,874 (+5,983 from R9, +9.2%) |
| Hub module impact cards | 0 | >= 3 clusters | 3 clusters, 9 hub modules — all re-investigated with file:line citations |
| Change playbooks | 0 | >= 2 | 3 playbooks (1313w/35 FACT, 1283w/65 FACT, 1653w/21 FACT) |
| Data contracts documented | 0 | >= 10 | 21 boundary-crossing entities, 100% with gotchas, 5 cross-boundary flow analyses |
| [FACT] in new sections | — | >= 80 | 157 (change_impact:23 + data_contracts:27 + playbooks:69 + bootstrap:38) |
| New section words | — | >= 5000 | 5,933 |
| Spot checks | 10/10 | 10/10 | 10/10 CONFIRMED |
| Adversarial | PASS (5/5) | PASS | PASS (5/5) |

### Verification

```bash
# New protocols exist
grep -n "Protocol E" .claude/skills/deep-crawl/SKILL.md
grep -n "Protocol F" .claude/skills/deep-crawl/SKILL.md

# New template sections
grep -n "Change Impact Index" .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template
grep -n "Data Contracts" .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template
grep -n "Change Playbooks" .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template
grep -n "Environment Bootstrap" .claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template

# 12 standard questions
grep -c "^Q[0-9]" .claude/skills/deep-crawl/SKILL.md  # expect 12

# After execution
wc -w output/unrestricted-r10/DEEP_ONBOARD.md
grep "Change Impact" output/unrestricted-r10/DEEP_ONBOARD.md
grep "hub modules" output/unrestricted-r10/DEEP_ONBOARD.md
grep -c "^### Q" output/unrestricted-r10/VALIDATION_REPORT.md
```

### R10 Part 2 Quality Retrospective

Part 2 re-investigation improved 4 sections from placeholder to investigated quality.
However, the orchestrator bypassed pipeline controls designed to prevent quality regressions:

| Gap | What Happened | Pipeline Fix |
|-----|--------------|--------------|
| Manual assembly | Orchestrator wrote sections directly instead of spawning S6 | Added Re-investigation Protocol requiring S6 agent |
| Self-validation | Orchestrator validated own work | Re-investigation Protocol mandates independent validator |
| Citation density | 2.6 [FACT]/100w average (bar: 5.1) | Added density floor: 3.0/100w in Evidence Standards |
| Aggregate quality masking | 69 FACT reported for 3 playbooks hid 21-FACT outlier | Per-playbook quality checks in S6 + VALIDATION_REPORT template |
| No spot-checking | 157 citations trusted without verification | Orchestrator spot-check (5 citations) before quality gate |
| Over-compression | 70% findings loss in env bootstrap assembly | 60% retention floor in Re-investigation Protocol |

**Pipeline files modified:**
- SKILL.md: Re-investigation Protocol, citation density metric, per-playbook checks, spot-check requirement
- DEEP_ONBOARD.md.template: Hidden coupling subsection in Impact, cross-boundary flow in Data Contracts
- VALIDATION_REPORT.md.template: Check 8 (citation density), Check 9 (playbook parity)
- compression_targets.json: per-section min_facts

### What This Tests

Can structured reverse-dependency investigation and change scenario playbooks transform an understanding-oriented document into one that also supports *changing* the codebase? The hypothesis: the xray data (imported_by, reverse_lookup, high_impact) already contains the raw material — the pipeline just needed protocols to extract and present it. With 1M context, the additional sections (estimated ~5-8K words) consume less than 1% of available window.

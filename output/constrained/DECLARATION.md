# Constrained Deep Crawl — Kosmos

## Run Metadata

| Field | Value |
|-------|-------|
| Date | 2026-03-28 |
| Target | Kosmos (autonomous AI scientist platform) |
| Location | `/mnt/c/python/kosmos` |
| Python files | 802 |
| Estimated codebase tokens | ~2.4M |
| DEEP_ONBOARD.md tokens | ~2,670 |
| Expected target (500-2000 files) | 15,000-18,000 |
| Hard max | 20,000 |
| Shortfall | 85% under target |
| Crawl plan tasks | 16 planned |
| Tasks completed | 3 |
| Modules indexed | 12 of 146 core files |
| Request traces | 3 of 10 flagged paths |

## Result Assessment

Quality was high — the validator scored 10/10 on all checks. But depth was shallow. The document covered the primary research execution path and a handful of core modules but missed the majority of the codebase's behavioral surface: LLM provider abstraction, knowledge graph persistence, experiment sandboxing, workflow state machine internals, and cross-cutting concerns (error handling, configuration, shared state).

The document reads like a Phase 1 summary, not a Phase 2+3+4 synthesis.

## The 6-File Constraint Chain

The following six locations each impose token ceilings that compound to suppress investigation depth. The agent encounters them in order during execution.

### Constraint 1: `compression_targets.json` — Global Ceiling

**File:** `.claude/skills/deep-crawl/configs/compression_targets.json`

```json
{"max_files": 2000, "label": "large", "min_tokens": 13000, "target_tokens": 16000, "max_tokens": 20000}
```

Sets the hard ceiling. The agent reads this during Phase 1 (PLAN) and knows the final document must fit in ~16-20K tokens.

### Constraint 2: `compression_targets.json` — Section Ceilings

**Same file**, `section_budgets` object:

```json
"critical_paths": {"max_tokens": 3000, ...},
"module_behavioral_index": {"max_tokens": 4000, ...},
"gotchas": {"max_tokens": 1500, ...}
```

Each section has an independent ceiling. Even if the global budget allows more, individual sections are capped. The sum of all section `max_tokens` is ~14,900 — already within the global target, meaning the section budgets ARE the effective budget.

### Constraint 3: `DEEP_ONBOARD.md.template` — 9 Budget Comments

**File:** `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template`

These HTML comments appear in the template the agent uses during Phase 3 (SYNTHESIZE):

```
<!-- Budget: ~3000 tokens. Prioritize the 3-5 most important paths. -->
<!-- Budget: ~4000 tokens. -->
<!-- Budget: ~1000 tokens. -->
<!-- Budget: ~1000 tokens. -->
<!-- Budget: ~800 tokens. -->
<!-- Budget: ~600 tokens. -->
<!-- Budget: ~1000 tokens. -->
<!-- Budget: ~800 tokens. -->
<!-- Budget: ~1500 tokens. -->
```

**This is the most insidious constraint.** These comments act during Phase 3 (synthesis), not Phase 4 (compression). The agent sees "Budget: ~3000 tokens. Prioritize the 3-5 most important paths" and generates only 3-5 paths — never creating the full content that Phase 4 would then compress. The spec's Phase 3/4 separation was designed to prevent exactly this, but the budget comments short-circuited it.

### Constraint 4: `deep_crawl.md` — Phase 4 Target Table

**File:** `.claude/agents/deep_crawl.md`, lines 207-216

```markdown
### Phase 4: COMPRESS (Optimize for Token Budget)

| Codebase Files | Target Tokens | Hard Max |
|----------------|---------------|----------|
| 500-2000       | 15-18K        | 20K      |
```

Explicit compression targets with a named "Hard Max." The agent treats these as inviolable constraints.

### Constraint 5: `deep_crawl.md` — Step 6 Trim Instruction

**File:** `.claude/agents/deep_crawl.md`, line 233

```markdown
**Step 6: Trim low-priority sections.** Cut from the bottom: Reading Order → Extension Points → Domain Glossary → Gaps.
```

Tells the agent to actively remove sections to hit budget. This is the kill switch — even if the agent over-generates, this step tells it to cut.

### Constraint 6: `deep_crawl.md` — Quality Checklist

**File:** `.claude/agents/deep_crawl.md`, line 404

```markdown
- [ ] Document is within token budget for codebase size
```

Final gate check. The agent won't declare success unless the document fits the budget. This creates a completion incentive to under-generate rather than risk failing the checklist.

### Constraint 7: `SKILL.md` — Pipeline Description and Budget Table

**File:** `.claude/skills/deep-crawl/SKILL.md`, lines 37, 56, 79-86

```markdown
Phase 4: COMPRESS    8-step algorithm → reduce to token budget
```

```markdown
| DEEP_ONBOARD.md | Onboarding document (8-20K tokens) | docs/ |
```

```markdown
| <100 files | 8-10K | 12K |
| 100-500 files | 12-15K | 17K |
```

Reinforces the budget framing in the skill's own documentation, which the agent reads during setup.

## Hypothesis

The agent self-compressed during Phase 2 (CRAWL) and Phase 3 (SYNTHESIZE), not just during Phase 4 (COMPRESS). Knowing the final document must fit in ~16-20K tokens, and seeing per-section budgets of 800-4000 tokens, the agent:

1. **Investigated fewer targets** — why trace 10 request paths if only 3-5 fit in the Critical Paths budget?
2. **Wrote thinner findings** — why deep-read 30 modules if the Module Index gets 4000 tokens?
3. **Self-censored during synthesis** — the template's budget comments told it to generate compressed output, bypassing the generate-then-compress design

The result: a high-quality but shallow document that covers 8% of what a downstream agent needs.

## Test Design

The unrestricted branch removes all token ceilings while preserving everything else (investigation protocols, evidence standards, quality checks, validation pipeline). If the hypothesis is correct, the unrestricted crawl on the same codebase should produce:

- Significantly more investigation tasks completed
- More modules indexed
- More request traces
- A larger document (expected 25-50K tokens)
- Equal or higher quality scores

The comparison between constrained and unrestricted outputs will determine whether token budgets should be soft guidance, hard ceilings, or absent entirely.

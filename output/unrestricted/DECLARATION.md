# Unrestricted Deep Crawl — Change Declaration

## Purpose

This branch removes all token budget ceilings from the deep crawl pipeline to test the hypothesis that budget constraints caused the agent to self-compress during investigation (Phase 2) and synthesis (Phase 3), not just during the explicit compression step (Phase 4). See `output/constrained/DECLARATION.md` for the full constraint chain analysis.

## What Changed (6 files)

### File 1: `.claude/agents/deep_crawl.md`

**Frontmatter description (line 3):**
- Before: `"maximally compressed onboarding document...Designed to run without token budget constraints"`
- After: `"comprehensive onboarding document...No token budget ceiling — include everything that's not redundant"`

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
- Added `guidance` text per bracket with natural size expectations (e.g., "Expect 20-40K tokens")
- Description updated: "No hard ceilings — include everything that's not redundant"
- Note updated to state "No token ceilings"

### File 4: `.claude/skills/deep-crawl/SKILL.md`

**Pipeline description (line 37):**
- Before: `Phase 4: COMPRESS    8-step algorithm → reduce to token budget`
- After: `Phase 4: REFINE      7-step algorithm → maximize value density, cut only redundancy`

**Output table (line 56):**
- Before: `Onboarding document (8-20K tokens)`
- After: `Onboarding document (unrestricted, value-driven)`

**Token Budget Targets section (lines 79-86):** Replaced with "Output Size Guidance" — expected ranges (not ceilings) with explanatory notes.

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

## CLAUDE.md Context Impact

The current spec auto-loads DEEP_ONBOARD.md via CLAUDE.md into every agent session. If the unrestricted output lands at 30-40K tokens instead of 15-18K, that's 15-20% of a 200K context window consumed before the agent starts working. This is still viable but changes the economics — less room for the agent to read files during tasks.

**Decision point for after the comparison:** If unrestricted output exceeds 25K tokens, reassess whether full auto-loading via CLAUDE.md is optimal or whether a summary + on-demand full document is better. Do not solve this now — measure first.

## Verification

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

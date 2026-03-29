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
Phase 4: REFINE      7-step algorithm → maximize value density, cut only redundancy
Phase 5: VALIDATE    Questions test → spot-check → adversarial sim → cache check
Phase 6: DELIVER     Copy to docs/ → update CLAUDE.md → enable prompt caching
```

## Evidence Standards

| Tag | Standard | Example |
|-----|----------|---------|
| [FACT] | Read specific code, cite file:line | "3x retry with backoff [FACT] (stripe.py:89)" |
| [PATTERN] | Observed in >=3 examples, state count | "DI via __init__ [PATTERN: 12/14 services]" |
| [ABSENCE] | Searched and confirmed non-existence | "No rate limiting [ABSENCE: grep — 0 hits]" |

No inferences or unverified signals in the output document.

## Output

| File | Purpose | Location |
|------|---------|----------|
| DEEP_ONBOARD.md | Onboarding document (unrestricted, value-driven) | docs/ |
| CLAUDE.md update | Auto-delivery to all sessions | project root |
| .onboard_feedback.log | Usage tracking from downstream agents | docs/ |
| VALIDATION_REPORT.md | QA results | docs/ |

## Context Management

The crawl uses disk as extended memory to handle codebases larger than
conversation context:

- Findings written to `/tmp/deep_crawl/findings/` immediately after each task
- Hold as many source files in working memory as the current task requires
- Batch by investigation task, not by file
- Checkpoint every 5 tasks for resumability
- Phase 3 reads all findings fresh from a concatenated file

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

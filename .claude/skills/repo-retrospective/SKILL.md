---
name: repo-retrospective
description: Quality assurance for AI onboarding documentation. Analyzes ONBOARD documents against X-Ray outputs and actual code to identify gaps, verify claims, and suggest improvements.
---

# repo-retrospective

Quality assurance skill for AI onboarding documentation. Ensures ONBOARD documents effectively enable fresh Claude instances to work in codebases.

## The Problem

```
ONBOARD documents are curated from X-Ray scans + investigation.

Curation involves judgment:
- What to include (critical for warm start)
- What to omit (noise, duplicates, low-value)
- What to verify (claims need evidence)
- What to flag (gotchas, hazards)

Judgment can be wrong:
- Critical information omitted
- Claims not properly verified
- Gotchas missed
- Gaps not acknowledged

Cost of errors: Hours of developer time wasted.
```

## The Solution

Retrospective analysis with five phases:

| Phase | Purpose | Output |
|-------|---------|--------|
| **Inventory** | Catalog ONBOARD claims | Checklist to verify |
| **Coverage** | Compare ONBOARD vs X-Ray | Gap analysis |
| **Verification** | Spot-check [VERIFIED] claims | Accuracy report |
| **Actionability** | Test usability with questions | Score (X/8) |
| **Recommendations** | Synthesize findings | Specific fixes |

---

## Quick Start

```bash
# Full retrospective
@repo_retrospective full \
  --onboard path/to/ONBOARD.md \
  --xray path/to/xray.md \
  --codebase /path/to/code

# Quick verification audit only
@repo_retrospective quick --onboard path/to/ONBOARD.md --codebase /path/to/code

# Coverage analysis only
@repo_retrospective coverage --onboard path/to/ONBOARD.md --xray path/to/xray.md

# Actionability test only
@repo_retrospective actionability --onboard path/to/ONBOARD.md
```

---

## When to Use

| Scenario | Mode | Purpose |
|----------|------|---------|
| Project completion | `full` | Final QA before commit |
| Mid-project checkpoint | `quick` | Verify claims are accurate |
| After X-Ray refresh | `coverage` | Ensure new signals captured |
| User suspects issues | `actionability` | Test document usability |

---

## Operating Modes

### `full` — Complete Retrospective

All five phases. Most thorough analysis.

**Inputs:**
- ONBOARD document path
- X-Ray output path
- Codebase path

**Output:** Full retrospective report with recommendations

**Token budget:** ~30-40K

---

### `quick` — Verification Audit

Spot-check [VERIFIED] claims only.

**Inputs:**
- ONBOARD document path
- Codebase path

**Output:** Verification audit report

**Token budget:** ~15-20K

---

### `coverage` — Gap Analysis

Compare ONBOARD against X-Ray output.

**Inputs:**
- ONBOARD document path
- X-Ray output path

**Output:** Coverage matrix with gaps identified

**Token budget:** ~15-20K

---

### `actionability` — Usability Test

Test if document enables effective coding.

**Inputs:**
- ONBOARD document path only

**Output:** Actionability score (X/8) with breakdown

**Token budget:** ~10-15K

---

## Coverage Categories

When comparing ONBOARD vs X-Ray:

| Category | Examples | Expected in ONBOARD? |
|----------|----------|---------------------|
| **Must Have** | Architecture diagram, Hazards, Top pillars | Yes |
| **Should Have** | Key data models, Critical side effects, Required env vars | Yes (curated) |
| **Nice to Have** | Decorator counts, Orphan files, Freshness stats | No (can omit) |

---

## Verification Outcomes

When auditing [VERIFIED] claims:

| Outcome | Meaning | Action Required |
|---------|---------|-----------------|
| **Confirmed** | Claim matches code exactly | None |
| **Partially True** | Correct but missing context | Recommend enhancement |
| **Outdated** | Code changed since verification | Re-investigate |
| **Inaccurate** | Claim doesn't match code | Critical fix needed |
| **Unverifiable** | Can't find cited location | Clarify reference |

---

## Actionability Questions

Standard questions to test document usability:

1. "What is this codebase?" (Orientation)
2. "Where does core logic live?" (Architecture)
3. "How do I add a new [entity]?" (Entry points)
4. "What happens when [X] fails?" (Error handling)
5. "What files should I never read?" (Hazards)
6. "What are common pitfalls?" (Gotchas)
7. "What env vars do I need?" (Configuration)
8. "How do I run tests?" (Development)

**Scoring:**
- 8/8 → Excellent
- 6-7/8 → Good
- 4-5/8 → Needs improvement
- <4/8 → Significant rework

---

## Quality Thresholds

### Ship It
- No critical gaps
- ≥80% [VERIFIED] claims confirmed
- Actionability ≥6/8
- All hazards included

### Needs Minor Fixes
- 1-2 moderate gaps
- 1-2 verification issues
- Actionability 5-7/8

### Needs Significant Rework
- Critical gaps found
- >20% claims unverifiable
- Actionability <5/8

---

## Confidence Levels

Findings are marked:

| Level | Meaning |
|-------|---------|
| `[CONFIRMED]` | Verified by reading actual code |
| `[ASSESSED]` | Based on document analysis only |
| `[UNCERTAIN]` | Needs human judgment |

---

## Output: Retrospective Report

```markdown
# Retrospective Report: [Project Name]

## Executive Summary
[1-2 sentences overall assessment]

## Coverage Analysis
### Critical Gaps (Must Fix)
### Moderate Gaps (Should Fix)
### Justified Omissions

## Verification Audit
### Confirmed Claims
### Issues Found

## Actionability Score
[X/8 with breakdown]

## Specific Recommendations
[Numbered, actionable items]

## Conclusion
[Ship It / Needs Minor Fixes / Needs Significant Rework]
```

---

## Integration with repo-xray

This skill is designed to QA documents produced by the `repo_xray` agent:

```
Workflow:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  1. xray.py scans codebase → xray.md + xray.json                       │
│                                                                         │
│  2. repo_xray agent investigates → ONBOARD.md                          │
│                                                                         │
│  3. repo_retrospective reviews → RETROSPECTIVE_REPORT.md               │
│     ↓                                                                  │
│     Identifies gaps, verifies claims, scores actionability             │
│     ↓                                                                  │
│     Produces specific recommendations                                  │
│                                                                         │
│  4. Developer/Agent fixes issues (if any)                              │
│                                                                         │
│  5. Final ONBOARD.md ready for use                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Files

```
repo-retrospective/
├── SKILL.md           # This file
├── COMMANDS.md        # Quick reference
└── templates/
    └── RETROSPECTIVE.md.template  # Report template
```

---

## Requirements

- Read access to ONBOARD document
- Read access to X-Ray output (for coverage mode)
- Read access to codebase (for verification mode)
- No external dependencies

---

*This skill ensures AI onboarding documentation maintains quality
and effectively solves the cold start problem.*

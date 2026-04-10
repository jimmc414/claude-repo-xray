# TS Pipeline Status Report

**Date:** 2026-04-08
**Branch:** ts-scanner
**Scope:** End-to-end assessment of TypeScript scanner → xray.md → deep crawl → DEEP_ONBOARD.md pipeline quality relative to the mature Python pipeline.

---

## Executive Summary

The TS pipeline is now **structurally complete** — 31 sections render in xray.md (vs 25 for Python), investigation targets are populated, domain profiles exist, and SKILL.md has TS-native protocol guidance. But the pipeline has **zero real-world validation**. The Python pipeline's quality comes from 14+ iterative crawl-and-fix cycles, not from more signals. The TS pipeline needs the same treatment.

**Bottom line:** Stop adding scanner features. Start running real deep crawls.

---

## Current State: What Works

### Scanner (ts-scanner/)
- 20 source modules, ~5,700 lines
- Extracts: functions, classes, interfaces, type aliases, enums, decorators, imports, calls, routes, config rules, CLI frameworks, side effects, security concerns, silent failures, SQL strings, env vars, async patterns, deprecation markers, logic maps, blast radius, investigation targets, tech debt, git analysis
- **NEW:** `ts_specific` signal (any_density, module_system, module_augmentations, namespaces)
- **FIXED:** `setParentNodes` crash, null guards on all 7 AST walkers
- 138 tests passing, clean tsc

### Formatter (markdown_formatter.py)
- **NEW:** Type System Overview (interfaces, union types, enums)
- **NEW:** Type Safety (any_density, @ts-ignore, module system)
- **NEW:** API Routes (method, path, handler, file)
- **FIXED:** TS fallback paths for state mutations, env vars, logic maps
- 31 sections render for TS projects

### Deep Crawl (SKILL.md)
- **NEW:** TS-specific guidance in Protocols A, B, C, D
- **NEW:** TS deep grep patterns (Promise gaps, barrel files, type safety, monorepo)
- **NEW:** TS gotcha taxonomy (6 categories)
- **NEW:** TS-aware S6 Data Contracts prompt
- **NEW:** Phase 1 barrel file + type safety prioritization signals
- Domain profiles: web_api_js, cli_tool_js, frontend_js, library_js, monorepo_js, nextjs_fullstack

### Data Flow
```
TS source → ts-scanner (AST) → XRayResults JSON → xray.py (git augmentation, investigation targets) → markdown_formatter → xray.md → deep crawl → DEEP_ONBOARD.md
```

All stages connected and producing output.

---

## Quality Comparison: Python vs TypeScript

### What's at parity or better

| Dimension | Python | TypeScript | Notes |
|-----------|--------|------------|-------|
| xray.md sections | 25 | 31 | TS has Type System, Type Safety, Routes extras |
| xray.md total lines | ~966 | ~1028 | Comparable density |
| investigation_targets populated | Yes | Yes | Same schema, same signals |
| Domain profiles | 9 | 6 (3 Python-only + 6 TS) | Coverage adequate for common archetypes |
| Git analysis | Full | Full | Same Python module runs for both |
| Import graph / tiers | Full | Full | TS scanner produces same schema |
| Call graph | Full | Full | TS scanner produces same schema |
| Logic maps | Full | Full | TS scanner pre-computes, Python generates on demand |

### What's behind

| Dimension | Python | TypeScript | Gap Size | Impact |
|-----------|--------|------------|----------|--------|
| Real deep crawl runs | 14+ | 0 | Critical | Protocols are untested |
| Protocol refinement iterations | ~50 fixes | 0 | Critical | TS guidance is theoretical |
| Data model depth (Pydantic fields) | Deep | Shallow (interfaces only) | Medium | Less useful data contract section |
| Framework-specific detection | None needed (Python is simpler) | Missing Zod, NestJS DI graph | Low | Protocol C grep compensates |
| Barrel file analysis | N/A | Missing | Low | Would improve import graph quality |

### Where TS is actually better

| Dimension | Notes |
|-----------|-------|
| Type system visibility | Python has no equivalent to interfaces/type aliases/enums in output |
| Type safety metrics | any_density, @ts-ignore counts have no Python analogue |
| Route detection | Python has no route extraction; TS detects Express/Fastify/NestJS routes |
| Config rule extraction | TS extracts tsconfig flags, ESLint, Prettier; Python only extracts linter rules |
| Decorator detail extraction | TS extracts decorator arguments (kwargs); Python only extracts names |

---

## Why the Python Pipeline Is Better (Honest Assessment)

It's not the scanner. The Python scanner extracts ~35 signals; the TS scanner extracts ~30+. The difference doesn't explain the quality gap.

**The Python pipeline is better because its protocols have been debugged through real usage.**

Each of the 14 Python deep crawls exposed specific failures:
- "Protocol A traces stop at the first side effect but the real behavior continues 3 hops further" → Protocol A got "no hop limit" instruction
- "Module deep reads don't check for test files" → Protocol B got test coverage checking
- "Gotchas are all in one flat list, impossible to scan" → S5 got domain-cluster gotcha organization
- "Change playbooks are too vague to follow" → S6 got 800-word minimum, 30-citation minimum
- "Calibration targets are too low for high-quality repos" → Quality gates got per-section tiers

None of these improvements came from adding scanner signals. They came from running crawls and fixing what broke.

The TS protocol additions (our work) are educated guesses about what TS-specific guidance agents need. They're likely 70% correct. The remaining 30% will only be discovered by running real crawls.

---

## Recommendation: The Validation-First Roadmap

### Phase 1: Run 3 Real Deep Crawls (Highest Priority)

| Crawl | Target | Why This Project | What It Tests |
|-------|--------|------------------|---------------|
| 1 | **NestJS API** (~50-200 files) | Decorator-heavy, DI container, Guards/Interceptors | Protocol A middleware traces, Protocol B decorator metadata, domain profile `web_api_js` |
| 2 | **Next.js app** (~50-200 files) | Server/client boundary, RSC, data fetching | Protocol A async boundaries, domain profile `nextjs_fullstack`, server vs client gotchas |
| 3 | **Express + React monorepo** (~100-400 files) | Barrel files, workspaces, shared types | Protocol C barrel analysis, domain profile `monorepo_js`, cross-package import issues |

**For each crawl, audit:**
1. Which xray.md sections were useful vs ignored by the crawl agent?
2. Which investigation targets led to productive investigation vs dead ends?
3. Which protocol instructions were followed vs caused confusion?
4. Which gotcha categories were populated vs empty?
5. Which DEEP_ONBOARD.md sections were thin or missing?

**Expected output:** 10-20 specific fixes per crawl to protocols, profiles, quality gates, and gotcha categories.

### Phase 2: Fix What Breaks (After Each Crawl)

Typical fixes based on Python crawl history:
- Protocol instruction refinements (more specific, less ambiguous)
- Domain profile `additional_investigation` task additions
- Gotcha category expansions
- Quality gate threshold adjustments
- Investigation target weighting changes
- New Protocol C grep patterns

### Phase 3: Scanner Additions (Only If Crawls Justify Them)

**Implement only if crawl audits show the agent wasting significant time on manual detection:**

| Addition | Trigger (crawl evidence needed) | Effort |
|----------|-------------------------------|--------|
| Barrel file analysis | Agent misidentifies barrel files as logic modules | Low (2-3 hrs) |
| Zod schema extraction | Agent spends >5 min per crawl manually parsing Zod schemas | High (1 day) |
| NestJS DI graph | Agent can't trace DI resolution without reading every @Module | High (1 day) |
| React hook dependency analysis | Agent misses stale closure bugs that hooks analysis would catch | High (1 day) |

### What NOT to Do

1. **Don't add Zod/React/NestJS detection preemptively.** Protocol C grep patterns compensate. The agent can `grep -rn "z.object" --include="*.ts"` in 2 seconds. Scanner detection saves marginal time.

2. **Don't chase signal count parity.** The Python scanner doesn't detect Django ORM models, SQLAlchemy relationships, or FastAPI Depends() either. Those are "nice to have" that didn't block any of the 14 successful Python crawls.

3. **Don't refine protocols without evidence.** The TS protocol additions are already substantial. More refinement without crawl data is guessing.

4. **Don't optimize the formatter before validating the crawl.** If a section renders but no crawl agent ever reads it, making it prettier is wasted work.

---

## One Exception: Barrel File Analysis

The one scanner addition worth making before running crawls:

**Why:** Barrel files (`index.ts` re-export hubs) affect the import graph that drives investigation target computation. If the scanner counts barrel re-exports as real import relationships, it inflates `imported_by` counts and misleads the crawl planner. This is a structural data quality issue, not a "nice to have" signal.

**Scope:**
- Flag `index.ts` files as barrel vs. logic (export count vs. code line count)
- Annotate import graph entries that pass through barrel files
- Add barrel files to xray.md as a subsection of Import Analysis

**Effort:** Low (half day). The detection logic already exists in the SKILL.md Protocol C grep patterns — it just needs to move into the scanner.

---

## Metrics for Success

After completing Phase 1 (3 real crawls), the TS pipeline should achieve:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| DEEP_ONBOARD.md word count | >8,000 words | `wc -w DEEP_ONBOARD.md` |
| Citation density | >3.0 [FACT] per 100 words | `grep -c '\[FACT\]' / wc -w * 100` |
| Gotcha count | >20 per crawl | `grep -c '^\-' gotchas section` |
| Module coverage | >60% of modules with >3 importers | Compare P2+P3 tasks vs module count |
| Playbook quality | >800 words, >30 citations each | Per-playbook check |
| Section completeness | All 12 template sections populated | Check DEEP_ONBOARD.md template |

These are the same quality gates the Python pipeline meets. If the TS pipeline hits them on 3 diverse projects, it's at parity.

---

## Files Changed in This Sprint

| File | Change |
|------|--------|
| `ts-scanner/src/ast-analysis.ts` | ts_specific detection (any, module system, augmentations, namespaces), null guards |
| `ts-scanner/src/import-analysis.ts` | setParentNodes fix, null guard |
| `ts-scanner/src/call-analysis.ts` | Null guard |
| `ts-scanner/src/cli-analysis.ts` | Null guards (3 walkers) |
| `ts-scanner/src/logic-maps.ts` | Null guard |
| `ts-scanner/src/types.ts` | Per-file ts_specific fields on FileAnalysis |
| `ts-scanner/src/index.ts` | aggregateTsSpecific(), TsSpecific import |
| `ts-scanner/test/fixtures/minimal/src/ts-specific.ts` | Test fixture |
| `ts-scanner/test/integration.test.ts` | File count 10→11 |
| `formatters/markdown_formatter.py` | Type System Overview, Type Safety, API Routes sections |
| `lib/gap_features.py` | TS data model extraction, TS fallback paths (logic maps, state mutations, env vars) |
| `xray.py` | Removed duplicate TS data model extraction |
| `.claude/skills/deep-crawl/SKILL.md` | TS protocols A-D, gotcha taxonomy, S6 data contracts, Phase 1 planning |
| `.claude/skills/deep-crawl/configs/domain_profiles.json` | library_js, monorepo_js, nextjs_fullstack profiles |
| `docs/TS_SCANNER_GAPS.md` | Gap inventory (future roadmap) |
| `docs/TS_PIPELINE_STATUS_REPORT.md` | This report |

---

## Barrel File Analysis (Implemented)

The one scanner addition made pre-crawl: barrel file detection in `import-analysis.ts`.

**Detection logic:** `index.ts` files with 3+ `export ... from` statements and more re-exports than logic lines are flagged as barrel files. Output includes re-export count, logic line count, and resolved source modules.

**Why pre-crawl:** Barrel files inflate `imported_by` counts in the import graph, which drives investigation target prioritization. Without barrel detection, the crawl planner can't distinguish "this module is important (many real dependents)" from "this module appears important (many imports pass through a barrel re-export)."

**Files changed:**
- `ts-scanner/src/types.ts` — added `barrel_files` field to `ImportAnalysis`
- `ts-scanner/src/import-analysis.ts` — added `detectBarrelFiles()` function
- `formatters/markdown_formatter.py` — renders Barrel Files subsection under Import Analysis

---

## Next Steps (Actionable)

1. Commit current changes on `ts-scanner` branch
2. Pick a NestJS project for Crawl #1 (recommend: a mid-size open-source NestJS API, 50-200 files)
3. Run: `python xray.py <target> --output both --out /tmp/xray`
4. Run: `/deep-crawl full`
5. Audit DEEP_ONBOARD.md against the metrics above
6. File findings, fix protocols, repeat for Crawls #2 and #3

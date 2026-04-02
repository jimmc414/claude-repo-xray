# Deep Crawl — Command Reference

This document explains how and why to run the deep crawl pipeline. It is the
entry point for AI agents working with this project and for humans setting it up.

## Why This Exists

AI coding assistants face a cold start problem. A codebase might span 2 million
tokens. A context window holds 200K. The assistant cannot read everything, yet
must understand the architecture to work effectively.

repo-xray solves this in two layers:

**Layer 1 — X-Ray Scanner** (`xray.py`): Deterministic, fast (seconds), zero
dependencies. Extracts 37+ signals from the AST, import graph, and git history.
Produces a ~15K token map. This tells you *what exists*.

**Layer 2 — Deep Crawl** (this pipeline): LLM-powered, exhaustive. Spawns
parallel investigation agents that read actual source code, trace request paths,
verify signals, and discover behavioral semantics that no static analysis can
see. Produces a comprehensive onboarding document where every claim has a
`file:line` citation. This tells you *how it works and what to watch out for*.

The deep crawl uses X-Ray output as its map. Run X-Ray first, then deep crawl.

## What This Produces

A single primary file (`docs/DEEP_ONBOARD.md`) containing 17 sections of verified
behavioral documentation:

- Critical paths traced end-to-end with code citations
- Module behavioral index with per-module analysis
- Change impact index showing hub modules and blast radii
- Key interfaces with usage patterns
- Data contracts and schema evolution risks
- Error handling strategy and recovery mechanisms
- Shared state (globals, caches, singletons)
- Configuration surface (env vars, config files, feature flags)
- Conventions and coding patterns
- Gotchas clustered by subsystem, severity-tagged, each with `file:line` evidence
- Change playbooks with step-by-step modification guides
- And more (domain glossary, hazards, extension points, reading order, bootstrap)

This file auto-loads in future Claude Code sessions via CLAUDE.md. Prompt
caching reduces subsequent read cost by ~90%.

## One-Time Setup (Per Machine)

The deep crawl skill lives inside the `claude-repo-xray` repository. To make it
available in Claude Code sessions across all repos, create a symlink:

```bash
# Clone if not already present
git clone https://github.com/jimmc414/claude-repo-xray.git /path/to/claude-repo-xray

# Create the global skill symlink
ln -sfn /path/to/claude-repo-xray/.claude/skills/deep-crawl ~/.claude/skills/deep-crawl
```

Or run the included setup script from the repo root:

```bash
cd /path/to/claude-repo-xray
./setup_deep_crawl.sh
```

Verify the skill is available by launching Claude Code in any repo — `/deep-crawl`
should appear in the skill list.

## Running Deep Crawl on a Target Repo

### Step 1: Run X-Ray (deterministic AST scan)

From the target repo's root directory:

```bash
python /path/to/claude-repo-xray/xray.py . --output both --out /tmp/xray
```

This produces `/tmp/xray/xray.json` and `/tmp/xray/xray.md`. Takes seconds to
minutes depending on repo size. No external dependencies required (stdlib only).

### Step 2: Run Deep Crawl (LLM-powered investigation)

Inside a Claude Code session in the target repo:

```
/deep-crawl full
```

This runs the full pipeline across 7 phases:

| Phase | Name | What Happens |
|-------|------|-------------|
| 0 | **Setup** | Create working directories, verify xray output, check for stale state |
| 1 | **Planning** | Read X-Ray signals, detect domain (web API, CLI, ML, etc.), build investigation plan, run 3 calibration exemplars |
| 2 | **Crawl** | Parallel sub-agents execute 6 investigation protocols across 6 batches (see below) |
| 3 | **Assembly** | Curate findings into 17-section document via independent assembly agents |
| 4 | **Cross-reference** | Add links between independently-assembled sections (strictly additive, no deletions) |
| 5 | **Validate** | Independent QA: 12 standard questions, 10 spot-checks against source, adversarial test |
| 6 | **Deliver** | Copy to `docs/DEEP_ONBOARD.md`, update CLAUDE.md, report metrics |

**Investigation protocols** (Phase 2):

| Protocol | Batch | Focus | Output Directory |
|----------|-------|-------|-----------------|
| A | 1 | Request traces — follow critical paths end-to-end | `findings/traces/` |
| B | 2 | Module deep reads — behavioral detail per module | `findings/modules/` |
| C | 3 | Cross-cutting concerns — error handling, config, state | `findings/cross_cutting/` |
| D | 4 | Convention documentation — patterns, testing, style | `findings/conventions/` |
| E | 5 | Reverse dependency & change impact — hub blast radii | `findings/impact/` |
| F | 6 | Change scenario walkthroughs — step-by-step playbooks | `findings/playbooks/` |

Batches 1-3 run concurrently. Batch 4 waits for 1-3. Batch 5 waits for 1-4.
Batch 6 waits for 1-5. Calibration exemplars are stored in `findings/calibration/`.

**Domain detection**: The crawl adapts investigation prompts based on detected
frameworks (FastAPI, Django, torch, airflow, asyncio, etc.). Domain-specific
questions are added automatically. Configuration: `configs/domain_profiles.json`.

Typical runtime: 30-70 minutes depending on repo size and model speed.

### Combined One-Liner (for scripting)

Inside Claude Code, send:

```
Run these steps: (1) python /path/to/claude-repo-xray/xray.py . --output both --out /tmp/xray (2) Then run /deep-crawl full
```

## All Commands

| Command | Mode | When to Use |
|---------|------|-------------|
| `/deep-crawl full` | Parallel sub-agents | Default. Highest quality, uses sub-agents for concurrent investigation. |
| `@deep_crawl full` | Sequential | Fallback if `/deep-crawl` is unavailable or sub-agents fail. |
| `@deep_crawl plan` | Sequential | Generate the investigation plan without running the crawl. Useful for review before committing to a full run. |
| `@deep_crawl resume` | Sequential | Continue a crawl interrupted mid-run. Checks `/tmp/deep_crawl/CRAWL_PLAN.md` for completed tasks and picks up where it stopped. |
| `@deep_crawl validate` | Sequential | QA an existing `DEEP_ONBOARD.md` without re-crawling. Runs Phase 5 only. |
| `@deep_crawl refresh` | Sequential | Incremental update after code changes. Re-run xray first, then this re-investigates only changed modules + dependents. |
| `@deep_crawl focus ./path` | Sequential | Deep crawl a specific subdirectory only. |

## Output Files

| File | Location | Purpose |
|------|----------|---------|
| `DEEP_ONBOARD.md` | `docs/` in target repo | The onboarding document |
| `DEEP_ONBOARD_VALIDATION.md` | `docs/` in target repo | QA report (spot checks, adversarial test) |
| `CLAUDE.md` | Target repo root (appended) | Auto-loads DEEP_ONBOARD in future sessions |
| `.onboard_changes.log` | `docs/` in target repo | Change tracking — models append here when modifying code that affects documented claims |
| `.onboard_feedback.log` | `docs/` in target repo | Usage tracking — downstream agents log which sections they reference |

### Intermediate Files

All intermediate state lives in `/tmp/deep_crawl/` (discardable after completion):

```
/tmp/deep_crawl/
├── CRAWL_PLAN.md                    Investigation plan with task checkboxes
├── DIFF_ANALYSIS.json               (refresh mode only) Change scope analysis
├── SYNTHESIS_INPUT.md               Concatenated findings for assembly
├── DRAFT_ONBOARD.md                 Pre-cross-reference document
├── DEEP_ONBOARD.md                  Final document (copied to docs/)
├── REFINE_LOG.md                    Phase 4 cross-reference log
├── VALIDATION_REPORT.md             Phase 5 QA results
├── findings/
│   ├── calibration/                 Quality exemplars (cal_a.md, cal_b.md, cal_c.md)
│   ├── traces/                      Protocol A: request path traces
│   ├── modules/                     Protocol B: per-module behavioral analysis
│   ├── cross_cutting/               Protocol C: error handling, config, state
│   ├── conventions/                 Protocol D: coding patterns, testing
│   ├── impact/                      Protocol E: hub module change impact
│   └── playbooks/                   Protocol F: change scenario walkthroughs
├── batch_status/                    Sentinel files (*.done) for batch tracking
└── sections/                        Assembled section drafts before merge
```

## Quality Guarantees

The pipeline enforces quality mechanically, not by hope:

- **Citation density**: >= 5.0 `[FACT]` per 100 words in investigation findings.
  Module deep reads (Batch 2): >= 400 words and 10 `[FACT]` citations per finding.
- **Findings quality gate**: After each batch, every finding is checked. Files
  below threshold trigger sub-agent re-spawn with corrective instructions.
- **Playbook quality gate**: 800 words, 30 `[FACT]`, 8 common mistakes, 3.0
  citation density per playbook.
- **Traceability gate**: Every completed investigation task appears in the assembled
  document. Every `[FACT]` citation from findings survives into the final output.
- **Document size floors**: Scaled to codebase size (4,600 words for small repos
  up to 11,500 for very large). See `configs/quality_gates.json`.
- **Spot-check verification**: 10 random `[FACT]` claims verified against actual
  source code. 9/10 must confirm.

## Change Tracking

After a deep crawl completes, Phase 6 injects a rule into the target repo's
CLAUDE.md instructing models to log changes that affect documented claims:

```
2026-04-01T14:23:00Z | executor.py:617 | Gotchas / Process Management | Changed timeout mechanism
```

These entries accumulate in `docs/.onboard_changes.log`. When `@deep_crawl refresh`
runs, it reads this log to achieve section-level targeting — re-investigating
only the specific sections affected, not the entire module. The log is advisory;
the diff crawl still runs dependency analysis independently.

## Requirements

- **Python 3.8+** — for xray.py (stdlib only, no pip dependencies)
- **Claude Code** — with a model that supports sub-agents (Opus/Sonnet)
- **Target repo** — must be a Python codebase (xray analyzes `.py` files)
- **Disk** — ~50MB in `/tmp/` for intermediate files

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `/deep-crawl` not found | Symlink missing. Run: `ln -sfn /path/to/claude-repo-xray/.claude/skills/deep-crawl ~/.claude/skills/deep-crawl` |
| "Run xray first" error | X-Ray output missing. Run: `python /path/to/claude-repo-xray/xray.py . --output both --out /tmp/xray` |
| Sub-agents stall | Check Claude usage limits. The crawl spawns 15-25 sub-agents. |
| Stale crawl state | Previous run left `/tmp/deep_crawl/`. Delete it: `rm -rf /tmp/deep_crawl` or use `@deep_crawl resume` to continue. |
| xray.py not found | Use absolute path to xray.py in your clone of claude-repo-xray |
| CLAUDE.md renamed to .assembly_save | Crawl interrupted during Phase 3. Restore: `mv CLAUDE.md.assembly_save CLAUDE.md` |
| Quality gate failures loop | A finding keeps failing the minimum threshold. Check if the module has minimal code. Sub-agents get one re-spawn attempt; after that the task is logged and skipped. |

## Notes

- The deep crawl reads the target repo's code directly — run it from the repo root.
- X-Ray is a build artifact consumed by deep crawl. The final deliverable is
  DEEP_ONBOARD.md only. X-Ray output does not need to be kept or committed.
- `/tmp/deep_crawl/` is not isolated per-repo. Running concurrent crawls on
  different repos will collide. Run one at a time or clear `/tmp/deep_crawl/`
  between runs.
- Phase 3 temporarily renames the target repo's CLAUDE.md (to
  `CLAUDE.md.assembly_save`) to prevent sub-agents from absorbing compression
  framing. It is restored at Phase 3 Step 10, before Phase 4 begins.
- Quality gates and structural thresholds are in
  `.claude/skills/deep-crawl/configs/quality_gates.json` (resolved via the
  symlink). These are repo-agnostic and do not need per-repo customization.

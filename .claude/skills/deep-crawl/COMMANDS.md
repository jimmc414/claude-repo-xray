# Deep Crawl Commands

## Prerequisites

```bash
# Local repos: run xray manually first
python xray.py . --output both

# Remote repos: xray runs automatically — no manual step needed
```

## Commands

| Command | Mode | What It Does |
|---------|------|-------------|
| `/deep-crawl full` | **Orchestrated** (parallel sub-agents) | Plan + parallel investigation + assemble + cross-reference + validate + deliver |
| `/deep-crawl full <github-url>` | **Orchestrated** | Clone remote repo, auto-run xray, then full crawl pipeline |
| `@deep_crawl full` | Sequential (single-agent fallback) | Same pipeline, sequential investigation |
| `@deep_crawl plan` | Sequential | Generate investigation plan only |
| `@deep_crawl resume` | Sequential | Continue from last checkpoint |
| `@deep_crawl validate` | Sequential | QA an existing DEEP_ONBOARD.md |
| `@deep_crawl refresh` | Sequential | Update for code changes |
| `@deep_crawl focus ./path` | Sequential | Deep crawl a specific subsystem |

## Recommended Workflow

### Local Repository
```bash
python xray.py . --output both   # 1. Scan
/deep-crawl full                                   # 2. Orchestrated crawl (preferred)
@deep_onboard_validator full                       # 3. Optional independent QA
# Output: output/<repo-name>/deep_onboard.md, CLAUDE.md updated
```

### Remote Repository
```bash
/deep-crawl full https://github.com/owner/repo    # Clone + scan + crawl (all automatic)
# Output: output/<repo-name>/deep_onboard.md
# Cleanup: rm -rf .deep_crawl/repo/
```

Supported URL formats: `https://github.com/owner/repo`, `gh:owner/repo`, `git@github.com:owner/repo.git`

## Sequential Fallback

If `/deep-crawl full` is unavailable or you prefer sequential execution:
```bash
@deep_crawl full
```

## After Code Changes

```bash
python xray.py . --output both
@deep_crawl refresh
```

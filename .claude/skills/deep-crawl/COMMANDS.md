# Deep Crawl Commands

## Prerequisites

```bash
python xray.py . --output both --out /tmp/xray
```

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

## Recommended Workflow

```bash
python xray.py . --output both --out /tmp/xray   # 1. Scan
/deep-crawl full                                   # 2. Orchestrated crawl (preferred)
@deep_onboard_validator full                       # 3. Optional independent QA
# Output: docs/DEEP_ONBOARD.md, CLAUDE.md updated
```

## Sequential Fallback

If `/deep-crawl full` is unavailable or you prefer sequential execution:
```bash
@deep_crawl full
```

## After Code Changes

```bash
python xray.py . --output both --out /tmp/xray
@deep_crawl refresh
```

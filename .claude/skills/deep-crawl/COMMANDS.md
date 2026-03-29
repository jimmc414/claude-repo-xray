# Deep Crawl Commands

## Prerequisites

```bash
python xray.py . --output both --out /tmp/xray
```

## Commands

| Command | What It Does |
|---------|-------------|
| `@deep_crawl full` | Plan → Crawl → Synthesize → Compress → Validate → Deliver |
| `@deep_crawl plan` | Generate investigation plan only |
| `@deep_crawl resume` | Continue from last checkpoint |
| `@deep_crawl validate` | QA an existing DEEP_ONBOARD.md |
| `@deep_crawl refresh` | Update for code changes (reads .onboard_feedback.log) |
| `@deep_crawl focus ./path` | Deep crawl a specific subsystem |

## Typical Workflow

```bash
python xray.py . --output both --out /tmp/xray   # 1. Scan
@deep_crawl full                                   # 2. Crawl + deliver
@deep_onboard_validator full                       # 3. Optional independent QA
# Output: docs/DEEP_ONBOARD.md, CLAUDE.md updated
```

## After Code Changes

```bash
python xray.py . --output both --out /tmp/xray
@deep_crawl refresh
```

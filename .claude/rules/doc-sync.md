# Rule: Documentation Sync Check

After any change to scanner functionality, output format, deep crawl pipeline, or project structure, verify the following documents are still accurate and update them if not.

## When This Rule Applies

This rule triggers when you modify any of these:

| Change Type | Files That Trigger |
|------------|-------------------|
| New/changed AST signal | `lib/ast_analysis.py` |
| New/changed analysis module | Any `lib/*.py` |
| Output format change | `formatters/markdown_formatter.py`, `formatters/json_formatter.py` |
| Config schema change | `configs/default_config.json`, `lib/config_loader.py` |
| Pipeline stage added/removed | `xray.py` |
| Deep crawl protocol change | `.claude/skills/deep-crawl/SKILL.md` |
| Agent definition change | `.claude/agents/*.md` |
| Quality gate threshold change | `.claude/skills/deep-crawl/configs/quality_gates.json` |
| Domain facet added | `.claude/skills/deep-crawl/configs/domain_profiles.json` |
| File moves or renames | Any structural reorganization |

## Documents to Check

Run through this checklist after completing the functional change. Update any document where the change invalidates existing content.

### Tier 1 — Always check (core docs referenced by users and agents)

| Document | What to verify |
|----------|---------------|
| `CLAUDE.md` | Architecture diagram, pipeline stages, module descriptions, conventions |
| `README.md` | Signal count, "What It Extracts" table, preset descriptions, file structure tree |
| `PROJECT_MAP.md` | File-by-file component map, pipeline stages table, signal counts, current state section |

### Tier 2 — Check if scanner or output changed

| Document | What to verify |
|----------|---------------|
| `docs/METHODOLOGY.md` | Signal count (section 1), extracted signals table (section 2.3), detection subsections, output formatting (section 2.10) |
| `docs/TECHNICAL_METRICS.md` | TOC completeness, section for every metric the scanner produces |
| `INTENT.md` | Signal count in design philosophy paragraph |

### Tier 3 — Check if deep crawl pipeline changed

| Document | What to verify |
|----------|---------------|
| `.claude/skills/deep-crawl/COMMANDS.md` | Command table matches SKILL.md |
| `.claude/skills/repo-xray/COMMANDS.md` | Options match actual CLI flags |
| `.claude/skills/repo-retrospective/COMMANDS.md` | Modes and workflows still valid |
| `docs/PLAN_INCREMENTAL_CRAWL.md` | Prerequisites table still references correct functions/line numbers |

### Tier 4 — Check if project structure changed

| Document | What to verify |
|----------|---------------|
| `README.md` | File structure tree at bottom |
| `PROJECT_MAP.md` | File-by-file component map, documentation section, dependency graph |
| `CLAUDE.md` | Architecture tree |
| `.gitignore` | New directories or file types covered |

## What "Update" Means

- Fix stale numbers (signal counts, file counts, section counts)
- Add/remove entries from tables and lists
- Update file paths if files moved
- Add new subsections if new capabilities were added
- Do NOT rewrite prose that is still accurate — only fix what the change broke

## Signal Count Sync Points

The scanner signal count appears in multiple places. When it changes, update all:

- `README.md` — "What it extracts" row
- `INTENT.md` — design philosophy paragraph
- `docs/METHODOLOGY.md` — section 1 overview
- `PROJECT_MAP.md` — current state section

## Quick Verification Command

After updating docs, run this to catch common drift:

```bash
# Check signal count consistency
for f in README.md INTENT.md docs/METHODOLOGY.md PROJECT_MAP.md; do
  echo "$f: $(grep -o '[0-9]*+ signals' "$f" 2>/dev/null || echo 'no match')"
done

# Check that tests still pass
python -m pytest tests/ -x -q
```

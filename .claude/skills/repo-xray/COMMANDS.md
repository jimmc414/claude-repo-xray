# repo-xray Commands

> Quick reference for AI context windows. See SKILL.md for details.

## Primary Command

```bash
python xray.py <target> [options]
```

## Common Patterns

```bash
# Full analysis (agent workflow)
python xray.py . --output both --out /tmp/xray
# Creates: xray.md (summary) + xray.json (reference)

# Quick survey
python xray.py . --preset minimal

# Standard analysis
python xray.py . --preset standard

# Focused on subdirectory
python xray.py ./src/core --preset full
```

## Output Options

| Flag | Effect |
|------|--------|
| `--output markdown` | Markdown only |
| `--output json` | JSON only |
| `--output both` | Both formats (recommended) |
| `--out PATH` | Write to PATH.md / PATH.json |

## Presets

| Preset | Tokens | Use Case |
|--------|--------|----------|
| `--preset minimal` | ~2K | Quick survey |
| `--preset standard` | ~8K | Balanced |
| `--preset full` | ~15K | Comprehensive |

## Disable Sections

```bash
--no-prose           # Skip natural language summary
--no-mermaid         # Skip architecture diagram
--no-logic-maps      # Skip complex function analysis
--no-hazards         # Skip large file warnings
--no-git             # Skip all git analysis
--no-critical-classes # Skip class skeletons
--no-data-models     # Skip Pydantic/dataclass extraction
```

## Agent Workflow

```bash
# Phase 1: Generate X-Ray
python xray.py . --output both --out /tmp/xray

# Phase 2: Agent reads /tmp/xray.md (orientation)
# Phase 2: Agent queries /tmp/xray.json (specifics)
# Phase 2: Agent uses Read/Grep/Glob (investigation)

# Phase 3: Agent synthesizes onboarding document
```

## Token Budget

| Operation | Tokens |
|-----------|--------|
| Markdown (minimal) | ~2K |
| Markdown (standard) | ~8K |
| Markdown (full) | ~15K |
| JSON (standard) | ~30K |
| JSON (full) | ~50K |

Agent typically consumes: ~20K (markdown + selective JSON + investigation)

## Codebase Size Strategy

| Size | Files | Strategy |
|------|-------|----------|
| Small | <100 | `--preset full` |
| Medium | 100-500 | `--preset standard` |
| Large | 500-2000 | Focus on subdirectories |
| Very Large | >2000 | Survey first, then focus |

## Configuration

```bash
# Generate config template
python xray.py --init-config > .xray.json

# Use custom config
python xray.py . --config my_config.json
```

## Help

```bash
python xray.py --help
```

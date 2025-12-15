---
name: repo-xray
description: AST-based Python codebase analysis. Use for exploring architecture, extracting interfaces, mapping dependencies, or generating onboarding documentation.
---

# repo-xray

Unified codebase analysis tool for AI coding assistants. Extracts structural, behavioral, and historical signals from Python codebases via AST parsing.

## Quick Start

```bash
# Full analysis (default)
python xray.py /path/to/project --verbose

# With preset for smaller output
python xray.py /path/to/project --preset minimal      # ~2K tokens
python xray.py /path/to/project --preset standard     # ~8K tokens

# Write to files
python xray.py /path/to/project --output both --out ./analysis
```

## Main Tool: xray.py

The unified entry point for all analysis.

### Presets

```bash
python xray.py . --preset minimal      # skeleton, imports only (~2K tokens)
python xray.py . --preset standard     # + complexity, git, calls, tests (~8K tokens)
python xray.py . --preset full         # all signals (~15K tokens, default)
```

### Individual Switches

```bash
python xray.py . --skeleton            # Code interfaces
python xray.py . --complexity          # Cyclomatic complexity
python xray.py . --git                 # Git history analysis
python xray.py . --imports             # Dependency graph
python xray.py . --calls               # Cross-module calls
python xray.py . --side-effects        # I/O operations
python xray.py . --tests               # Test coverage
python xray.py . --tech-debt           # TODO/FIXME markers
python xray.py . --types               # Type annotation coverage
python xray.py . --decorators          # Decorator inventory
```

### Output Formats

```bash
python xray.py . --output json         # JSON only (default)
python xray.py . --output markdown     # Markdown only
python xray.py . --output both         # Both formats
python xray.py . --out ./analysis      # Write to analysis.json, analysis.md
```

## Legacy Tools

Individual tools are still available for targeted analysis:

### mapper.py

Directory tree with token estimates.

```bash
python .claude/skills/repo-xray/scripts/mapper.py              # full tree
python .claude/skills/repo-xray/scripts/mapper.py --summary    # stats only
```

### skeleton.py

Extract interfaces: classes, methods, fields, decorators.

```bash
python .claude/skills/repo-xray/scripts/skeleton.py src/file.py
python .claude/skills/repo-xray/scripts/skeleton.py src/ --priority critical
```

### dependency_graph.py

Map import relationships.

```bash
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --mermaid
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --orphans
```

### git_analysis.py

Analyze git history.

```bash
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --risk
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --coupling
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --freshness
```

## Token Budget

| Operation | Tokens |
|-----------|--------|
| `--preset minimal` | ~2K |
| `--preset standard` | ~8K |
| `--preset full` | ~15K |
| `--skeleton` only | ~5K |
| `--imports` only | ~3K |
| `--git` only | ~2K |

## Analysis Signals

The tool extracts 28+ signals across 6 dimensions:

- **Structure**: skeleton, tokens, files, interfaces
- **Architecture**: layers, orphans, circulars, import aliases
- **History**: risk scores, coupling pairs, freshness
- **Complexity**: cyclomatic complexity, hotspots, async patterns
- **Behavior**: side effects, cross-module calls, reverse lookup
- **Coverage**: test files, functions, fixtures

## Configuration

Files in `configs/`:
- `presets.json` - Analysis preset definitions
- `ignore_patterns.json` - Directories and extensions to skip

## File Structure

```
claude-repo-xray/
├── xray.py                     # Main entry point
├── lib/                        # Analysis modules
│   ├── ast_analysis.py         # Skeleton, complexity, types
│   ├── import_analysis.py      # Dependencies, aliases
│   ├── call_analysis.py        # Cross-module calls
│   ├── git_analysis.py         # Risk, coupling, freshness
│   ├── tech_debt_analysis.py   # TODO/FIXME markers
│   └── test_analysis.py        # Test coverage
├── formatters/                 # Output formatting
└── configs/                    # Configuration
```

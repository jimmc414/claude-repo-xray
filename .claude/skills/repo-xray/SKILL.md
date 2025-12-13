---
name: repo-xray
description: AST-based Python codebase analysis. Use for exploring architecture, extracting interfaces, mapping dependencies, or generating onboarding documentation.
---

# repo-xray

Extracts structural information from Python codebases via AST parsing. Produces class signatures, method signatures, Pydantic fields, decorators, and import graphs without implementation details.

## Tools

### configure.py

Detects project structure and generates config files.

```bash
python .claude/skills/repo-xray/scripts/configure.py --dry-run   # preview
python .claude/skills/repo-xray/scripts/configure.py .           # generate
python .claude/skills/repo-xray/scripts/configure.py . --backup  # backup first
```

### mapper.py

Directory tree with token estimates per file.

```bash
python .claude/skills/repo-xray/scripts/mapper.py              # full tree
python .claude/skills/repo-xray/scripts/mapper.py --summary    # stats only
python .claude/skills/repo-xray/scripts/mapper.py src/         # specific dir
python .claude/skills/repo-xray/scripts/mapper.py --json       # JSON output
```

### skeleton.py

Extracts interfaces: classes, methods, fields, decorators, line numbers.

```bash
python .claude/skills/repo-xray/scripts/skeleton.py src/file.py              # single file
python .claude/skills/repo-xray/scripts/skeleton.py src/ --priority critical # by priority
python .claude/skills/repo-xray/scripts/skeleton.py src/ --pattern "*.py"    # by pattern
python .claude/skills/repo-xray/scripts/skeleton.py src/ --private           # include _private
python .claude/skills/repo-xray/scripts/skeleton.py src/ --no-line-numbers   # omit L{n}
python .claude/skills/repo-xray/scripts/skeleton.py src/ --json              # JSON output
```

Output example:
```python
@dataclass
class User:  # L34
    id: int  # L36
    name: str  # L37
    email: str = Field(...)  # L38

class UserService:  # L45
    def __init__(self, db: Database): ...  # L47
    async def get_user(self, user_id: int) -> User: ...  # L52
```

### dependency_graph.py

Maps import relationships. Auto-detects root package.

```bash
python .claude/skills/repo-xray/scripts/dependency_graph.py src/              # text output
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --mermaid    # Mermaid diagram
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --root pkg   # explicit root
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --focus api  # filter area
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --orphans    # dead code candidates
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --impact file.py  # blast radius
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --source-dir path # override source root
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --json       # JSON output
```

### git_analysis.py

Analyzes git history for temporal signals.

```bash
python .claude/skills/repo-xray/scripts/git_analysis.py src/                  # show usage
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --risk           # risk scores
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --coupling       # co-modification pairs
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --freshness      # activity categories
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --json           # combined JSON output
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --months 12      # custom history period
```

Output example (--risk):
```
RISK   FILE                              FACTORS
0.87   src/api/auth.py                   churn:15 hotfix:3 authors:5
0.72   src/core/workflow.py              churn:8 hotfix:1 authors:3
```

### generate_warm_start.py

Generates complete WARM_START.md documentation by combining all tools.

```bash
python .claude/skills/repo-xray/scripts/generate_warm_start.py /path/to/repo           # generate
python .claude/skills/repo-xray/scripts/generate_warm_start.py . -o WARM_START.md      # custom output
python .claude/skills/repo-xray/scripts/generate_warm_start.py . --debug               # raw JSON per section
python .claude/skills/repo-xray/scripts/generate_warm_start.py . --json                # JSON instead of markdown
python .claude/skills/repo-xray/scripts/generate_warm_start.py . -v                    # verbose progress
```

Features:
- Combines mapper, skeleton, dependency_graph, git_analysis
- Auto-detects project name and source directory
- Handles nested structures (e.g., `.claude/skills/`)
- `--debug` outputs `WARM_START_debug/*.json` for validation

## Workflow

1. `configure.py --dry-run` - understand project structure
2. `mapper.py --summary` - survey codebase size
3. `dependency_graph.py --mermaid` - architecture diagram
4. `skeleton.py --priority critical` - core interfaces
5. Verify imports work
6. `git_analysis.py --risk` - identify volatile files
7. `git_analysis.py --coupling` - find hidden dependencies
8. `@repo_architect generate` - full documentation

## Token Budget

| Operation | Tokens |
|-----------|--------|
| configure.py --dry-run | ~200 |
| mapper.py --summary | ~500 |
| skeleton.py (1 file) | ~200-500 |
| skeleton.py --priority critical | ~5K |
| dependency_graph.py | ~3K |
| dependency_graph.py --mermaid | ~500 |
| dependency_graph.py --orphans | ~1K |
| dependency_graph.py --impact | ~500 |
| git_analysis.py --risk | ~1K |
| git_analysis.py --coupling | ~500 |
| git_analysis.py --freshness | ~500 |
| git_analysis.py --json | ~3K |
| generate_warm_start.py | ~8-20K |

## Priority Levels

Defined in `configs/priority_modules.json`:

| Level | Typical Folders |
|-------|-----------------|
| critical | main, app, core, workflow |
| high | models, schemas, api, services |
| medium | utils, lib, common |
| low | tests, docs, examples |

## Configuration

Files in `configs/`:
- `ignore_patterns.json` - directories and extensions to skip
- `priority_modules.json` - module priority patterns

Both auto-generated by configure.py. Can be edited manually.

## Agent Integration

```
@repo_architect generate    # create WARM_START.md
@repo_architect refresh     # update existing
@repo_architect query "X"   # answer questions
```

See [reference.md](reference.md) for API details.
See [CHEATSHEET.md](CHEATSHEET.md) for command reference.

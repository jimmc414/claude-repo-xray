# repo-xray Commands

> Quick reference optimized for AI context windows. For detailed documentation with examples, see [reference.md](reference.md).

## Paths

**Global installation** (available everywhere):
```bash
python ~/.claude/skills/repo-xray/scripts/SCRIPT.py
```

**Project-local installation**:
```bash
python .claude/skills/repo-xray/scripts/SCRIPT.py
```

Replace `SCRIPT.py` with the tool name below.

---

## Tools

### configure.py

**Strategy**: Bootstrap the skill for a new project. Scans directory structure, detects root package from import patterns, generates ignore/priority configs.

**Raw output**: `configs/ignore_patterns.json`, `configs/priority_modules.json`

```
configure.py [dir]        Detect project structure
configure.py --dry-run    Preview without writing
configure.py --backup     Backup before overwriting
configure.py --force      Overwrite without prompt
```

### mapper.py

**Strategy**: Estimate context budget before diving in. Walks directory tree, calculates tokens per file (chars/4), flags large files that would consume excessive context.

**Raw output**: `{path, total_tokens, file_count, tree[], large_files[]}`

```
mapper.py [dir]           Directory tree with token counts
mapper.py --summary       Stats only
mapper.py --json          JSON output
```

### skeleton.py

**Strategy**: Understand interfaces without reading implementations. AST-parses Python files to extract class/method signatures, Pydantic fields, decorators, and line numbers. Achieves ~95% token reduction.

**Raw output**: `{files[{file, original_tokens, skeleton_tokens, skeleton}], summary}`

```
skeleton.py <path>             Extract interfaces
skeleton.py --priority LEVEL   Filter: critical, high, medium, low
skeleton.py --pattern GLOB     Filter by filename
skeleton.py --private          Include _private methods
skeleton.py --no-line-numbers  Omit L{n}
skeleton.py --json             JSON output
```

### dependency_graph.py

**Strategy**: Map the architecture without reading code. Parses imports to build a directed graph, then classifies modules into layers (foundation/core/orchestration) based on import patterns and naming conventions.

**Raw output**: `{modules{name: {imports[], imported_by[]}}, layers{}, circular[], external{}}`

```
dependency_graph.py [dir]      Import analysis
dependency_graph.py --mermaid  Mermaid diagram
dependency_graph.py --root PKG Set root package
dependency_graph.py --focus X  Filter to area
dependency_graph.py --orphans  Dead code candidates
dependency_graph.py --impact F Blast radius for file F
dependency_graph.py --source-dir P Override source root
dependency_graph.py --json     JSON output
```

### git_analysis.py

**Strategy**: Extract temporal signals from git history. Identifies volatile files (risk), hidden dependencies not visible in imports (coupling), and maintenance activity (freshness).

**Raw output**: `{risk[{file, risk_score, churn, hotfixes, authors}], coupling[{file_a, file_b, count}], freshness{active[], aging[], stale[], dormant[]}}`

```
git_analysis.py [dir]          Git history analysis
git_analysis.py --risk         Risk scores (churn, hotfixes, authors)
git_analysis.py --coupling     Co-modification pairs
git_analysis.py --freshness    Active/Aging/Stale/Dormant
git_analysis.py --json         Combined JSON output
git_analysis.py --months N     History period (default: 6)
```

### generate_warm_start.py

**Strategy**: Orchestrate all tools into unified documentation. Calls mapper, dependency_graph, git_analysis, and skeleton, then renders collected data into a markdown template.

**Raw output**: All tool outputs combined. Use `--debug` to retain raw JSON in `WARM_START_debug/` for inspection or validation.

```
generate_warm_start.py [dir]   Generate WARM_START.md
generate_warm_start.py -o FILE Custom output path
generate_warm_start.py --debug Output raw JSON to WARM_START_debug/
generate_warm_start.py --json  JSON instead of markdown
generate_warm_start.py -v      Verbose progress
```

---

## Workflow

```bash
# 1. Understand structure
python SCRIPTS/configure.py --dry-run

# 2. Survey size
python SCRIPTS/mapper.py --summary

# 3. Architecture diagram
python SCRIPTS/dependency_graph.py src/ --mermaid

# 4. Core interfaces
python SCRIPTS/skeleton.py src/ --priority critical

# 5. Verify imports
python -c "from pkg.main import Main"

# 6. Risk assessment
python SCRIPTS/git_analysis.py src/ --risk

# 7. Hidden coupling
python SCRIPTS/git_analysis.py src/ --coupling

# 8. Generate docs (automated)
python SCRIPTS/generate_warm_start.py . -v

# Or via agent (enhanced)
@repo_architect generate
```

---

## Token Budget

| Command | Tokens |
|---------|--------|
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

---

## Priority Levels

| Level | Folders |
|-------|---------|
| critical | main, app, core, workflow |
| high | models, schemas, api, services |
| medium | utils, lib, common |
| low | tests, docs, examples |

---

## Output Example

skeleton.py output:
```python
@dataclass
class User:  # L34
    id: int  # L36
    name: str  # L37
    email: str = Field(...)  # L38

class UserService:  # L45
    def __init__(self, db: Database): ...  # L47
    async def get_user(self, id: int) -> User: ...  # L52
```

---

## Directories to Skip

```
__pycache__/    .git/           venv/
node_modules/   artifacts/      data/
logs/           *.pyc           *.pkl
```

---

## Agent Commands

```
@repo_architect generate    Create WARM_START.md
@repo_architect refresh     Update existing
@repo_architect query "X"   Answer question
```

# repo-xray Cheatsheet

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

## Commands

### configure.py
```
configure.py [dir]        Detect project structure
configure.py --dry-run    Preview without writing
configure.py --backup     Backup before overwriting
configure.py --force      Overwrite without prompt
```

### mapper.py
```
mapper.py [dir]           Directory tree with token counts
mapper.py --summary       Stats only
mapper.py --json          JSON output
```

### skeleton.py
```
skeleton.py <path>             Extract interfaces
skeleton.py --priority LEVEL   Filter: critical, high, medium, low
skeleton.py --pattern GLOB     Filter by filename
skeleton.py --private          Include _private methods
skeleton.py --no-line-numbers  Omit L{n}
skeleton.py --json             JSON output
```

### dependency_graph.py
```
dependency_graph.py [dir]      Import analysis
dependency_graph.py --mermaid  Mermaid diagram
dependency_graph.py --root PKG Set root package
dependency_graph.py --focus X  Filter to area
dependency_graph.py --orphans  Dead code candidates
dependency_graph.py --impact F Blast radius for file F
dependency_graph.py --json     JSON output
```

### git_analysis.py
```
git_analysis.py [dir]          Git history analysis
git_analysis.py --risk         Risk scores (churn, hotfixes, authors)
git_analysis.py --coupling     Co-modification pairs
git_analysis.py --freshness    Active/Aging/Stale/Dormant
git_analysis.py --json         Combined JSON output
git_analysis.py --months N     History period (default: 6)
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

# 8. Generate docs
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

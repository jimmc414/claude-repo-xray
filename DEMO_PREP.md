# Repo X-Ray: 3-Minute Lightning Demo

## The Problem (15 seconds)

**Opening line:**
> "A 2-million token codebase, a 200K context window—AI can't read everything, so it guesses. X-Ray gives it a map."

**Context if needed:**
- Claude's context window: ~200K tokens
- Average enterprise codebase: 1-10 million tokens
- Current solutions: hope the AI guesses right, or manually curate context
- X-Ray: automated extraction of architecturally significant signals

---

## Part 1: Python Mechanics (90 seconds)

### 1. Single-Pass AST Traversal (30 sec)

**Code snippet** (`xray.py:147-160`):
```python
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        # Extract skeleton, complexity, side effects—all at once
```

**What's happening:**
- `ast.walk()` yields every node in the syntax tree via BFS
- Single parse extracts: function signatures, class hierarchies, complexity metrics, side effects, docstrings
- Pure stdlib—no external dependencies

**Why it matters:**
- One parse, multiple signals
- 500-file codebase processes in ~2 seconds
- No dependency hell, works anywhere Python runs

**Demo hook:**
> "We parse once and extract everything. Most tools parse repeatedly for each metric. This is why X-Ray stays fast even on large codebases."

---

### 2. BFS for Dependency Distance (30 sec)

**Code snippet** (`xray.py:785-810`):
```python
def _compute_dependency_depth(self, graph: Dict[str, Set[str]]) -> Dict[str, int]:
    queue = deque([(start, 0)])
    while queue:
        current, dist = queue.popleft()
        for neighbor in graph[current]:
            if neighbor not in visited:
                distances[neighbor] = dist + 1
                queue.append((neighbor, dist + 1))
```

**What's happening:**
- Builds a directed graph from import statements
- BFS from entry points computes "distance" to every module
- Distance = minimum number of imports to reach a module

**Why it matters:**
- Reveals architectural layers that import lists don't show
- "This module is 5 hops from main" tells you it's deep infrastructure
- O(V+E) complexity—scales linearly with codebase size

**Demo hook:**
> "Import lists tell you what depends on what. Dependency distance tells you how deep you are in the architecture. A module at distance 1 is core; distance 5 is probably a utility."

---

### 3. Cyclomatic Complexity with BoolOp Handling (30 sec)

**Code snippet** (`xray.py:553-570`):
```python
def _compute_cyclomatic_complexity(self, node: ast.AST) -> int:
    cc = 1  # Base complexity
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ...)):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            cc += len(child.values) - 1  # Each additional operand = branch
```

**What's happening:**
- Standard: count `if`, `for`, `while`, `except`, etc.
- The trick: `if a and b and c` creates 3 execution paths, not 1
- `BoolOp.values` contains the operands; `len - 1` = additional branches

**Why it matters:**
- Most complexity tools get this wrong
- Accurate complexity = accurate hotspot detection
- Matters for identifying code that needs careful review

**Demo hook:**
> "Everyone counts if statements. But `if a and b and c` has three ways to exit early. We count those. It's the difference between finding real complexity and missing it."

---

## Part 2: The Agent Wrapper (45 seconds)

### The Insight

**Key point:**
> "X-Ray extracts signals. But signals aren't always accurate—a 'complexity hotspot' might be essential business logic or accidental mess. The agent verifies before including."

**What makes this different:**
- X-Ray outputs raw signals (JSON + markdown summary)
- The Claude agent has access to the actual codebase
- It uses Read/Grep/Glob as a "microscope" to verify what X-Ray flagged
- Final output is curated, not dumped

---

### Three-Phase Workflow

| Phase | What Happens | Tools Used |
|-------|--------------|------------|
| **Orient** | Run X-Ray, read markdown summary | Bash, Read |
| **Investigate** | Verify flagged hotspots, check coupling claims | Read, Grep, Glob |
| **Synthesize** | Produce curated onboarding document | Write |

**Orient phase:**
- Agent runs `python xray.py /path/to/repo`
- Reads the generated markdown (~15K tokens)
- Now knows: architecture, entry points, complexity hotspots, side effects

**Investigate phase:**
- Agent sees "function X has complexity 45"
- Uses Read to examine it: is this essential or accidental complexity?
- Sees "modules A and B have high coupling"
- Uses Grep to verify: are they legitimately related or poorly factored?

**Synthesize phase:**
- Agent produces `ONBOARDING.md`
- Not a dump of signals—a document answering: "What do I need to know to work here?"
- Tailored for a fresh Claude instance starting work on this codebase

---

### The Output

**What the agent produces:**
```markdown
# Codebase Onboarding: [Project Name]

## Quick Orientation
One paragraph: what this codebase does, primary language, key patterns.

## Architecture Overview
Module structure, layers, main entry points.

## Critical Components
The 3-5 most important files and why they matter.

## Complexity Guide
Where the dragons live—and whether they're necessary dragons.

## Side Effects & External Dependencies
What talks to databases, APIs, filesystem. What can break.
```

**Demo hook:**
> "The agent doesn't just pass through X-Ray output. It investigates, verifies, and curates. The result is a document that actually helps an AI work in the codebase—not just a data dump."

---

## Closing (10 seconds)

**Final line:**
> "X-Ray compresses a multi-million token codebase into ~15K tokens of actionable intelligence. The agent adds judgment. Together, they solve the cold start problem."

---

## Timing Summary

| Section | Duration | Cumulative |
|---------|----------|------------|
| Opening / Problem | 15s | 0:15 |
| AST traversal | 30s | 0:45 |
| BFS dependency distance | 30s | 1:15 |
| Cyclomatic complexity | 30s | 1:45 |
| Agent wrapper | 45s | 2:30 |
| Closing | 10s | 2:40 |
| **Buffer** | 20s | **3:00** |

---

## Backup Material (If Questions Arise)

### Co-Modification Coupling

**Code snippet** (`xray.py:830-875`):
```python
def _analyze_co_modifications(self, repo_path: str) -> List[Tuple[str, str, int]]:
    # Mine git history for files that change together
    # Uses frequent itemset mining on commit file lists
```

**What it does:**
- Parses git log for commits touching multiple files
- Finds pairs that frequently change together
- High co-modification without import relationship = hidden coupling

**Why it matters:**
> "These two files have no imports between them, but they've changed together in 47 commits. That's behavioral coupling—the kind that breaks refactors."

---

### Logic Maps

**Code snippet** (`xray.py:620-680`):
```python
def _build_logic_map(self, node: ast.FunctionDef) -> str:
    # Symbolic representation of control flow
    # -> (flow), * (loop), ? (conditional), [DB] (side effect)
```

**Example output:**
```
-> validate_input ? (invalid: raise ValidationError)
-> [DB] fetch_user ? (not_found: return None)
* process_items -> [API] send_notification
-> return result
```

**Why it matters:**
> "A 200-line function compressed to 15 lines of logic. You can see the shape without reading the implementation."

---

### Side Effect Classification

**Categories detected:**
- `[DB]` - Database operations (ORM patterns, raw SQL)
- `[API]` - External HTTP calls
- `[FS]` - Filesystem operations
- `[ENV]` - Environment variable access
- `[LOG]` - Logging calls
- `[NET]` - Network/socket operations

**Why it matters:**
> "Side effects are where bugs hide and tests get hard. X-Ray flags every function that touches the outside world."

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `xray.py` | Core extraction engine (all Python mechanics) |
| `.claude/agents/repo_xray.md` | Agent definition (three-phase workflow) |
| `.claude/skills/repo-xray/SKILL.md` | Skill documentation |
| `.claude/skills/repo-xray/templates/ONBOARD.md.template` | Output template |
| `README.md` | Project overview |

---

## Potential Questions & Answers

**Q: Why not just use tree-sitter or a language server?**
> "For Python, the stdlib AST module is fast, accurate, and has zero dependencies. Tree-sitter adds complexity without benefit for single-language analysis. For multi-language support, tree-sitter would be the right choice."

**Q: How does this compare to CodeQL or Semgrep?**
> "Different goals. Those are security/pattern analysis tools. X-Ray is specifically designed to produce context for AI assistants—signals that help an AI understand architecture, not find vulnerabilities."

**Q: What about languages other than Python?**
> "The architecture supports it—swap the AST parser. Python first because it's our primary use case and the stdlib parser is excellent. Tree-sitter bindings would enable JS/TS/Go/Rust."

**Q: How big can the codebase be?**
> "Tested on codebases up to 500 files. Processing time is ~2 seconds. Memory scales linearly with AST size. The bottleneck is usually git history parsing for co-modification analysis."

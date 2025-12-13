**Objective Statement:**

Phase 2 aims to evolve the solution from **syntactic extraction** (Phase 1’s static AST parsing and the current state of claude-repo-xray) to **semantic verification** by deploying an autonomous LLM-driven agent to validate imports, identify undocumented critical logic, and prune irrelevant boilerplate. This process intends to trade a high, one-time generation cost for a highly optimized, hallucination-free "Warm Start" artifact that maximizes the functional density of an AI coding assistant's context window for all future sessions.



This is a sophisticated engineering challenge. Phase 1 (AST Parsing) solves the **Structural Cold Start** problem efficiently, but it leaves a **Semantic Gap**: it tells the AI *where* the code is, but not *how* it behaves, *why* it works, or *if* the dependencies are actually valid.

To solve this without blowing the token budget on a full-read, we need a **"Surgical Audit"** strategy. We must identify the "Brain" of the application (usually \<5% of the codebase) and "hydrate" our structural map with dense behavioral logic.

Here is the complete design for **Phase 2: The Semantic Investigator**.

### The Strategy: "Target, Trace, Verify"

We replace the "Read Everything" approach with a heuristic-driven agentic workflow:

1.  **Target (Complexity Analysis)**: We use a new tool (`complexity.py`) to calculate **Cyclomatic Complexity**. This pinpoints the most logic-dense files (the "Brain") while ignoring boilerplate/DTOs (the "Body").
2.  **Trace (Surgical Reading)**: We use a **Smart Reader** (`smart_read.py`) that reads *only* the implementation of complex methods while keeping the surrounding file as a skeleton. This maintains context (imports, class attributes) for near-zero token cost while exposing the critical logic.
3.  **Verify (Runtime Validation)**: We use a **Verifier** (`verify.py`) to confirm that imports and entry points identified in Phase 1 are actually resolvable, catching dead code or missing dependencies.
4.  **Crystallize (Logic Mapping)**: The Agent synthesizes this into a `HOT_START.md` document containing "Logic Maps"—dense pseudocode summaries of critical paths.

-----

### 1\. New Agent: `repo_investigator`

This agent builds upon the Architect. It is the "Deep Diver" that hydrates the skeleton.

**File:** `.claude/agents/repo_investigator.md`

````markdown
---
name: repo_investigator
description: Senior Engineer Agent (Phase 2). Performs deep semantic analysis on codebases. Identifies logic hotspots, validates dependencies, and generates the "HOT_START.md" semantic guide.
tools: Read, Bash
model: sonnet
skills: repo-xray, repo-investigator
parent: repo_architect
---

# Repo Investigator

You are the **Principal Software Engineer** performing a semantic audit.
Your goal is to upgrade the Structural Map (`WARM_START.md`) into a Behavioral Guide (`HOT_START.md`).

## Your Strategy: "Target, Trace, Verify"

### 1. Target (Find the Brain)
You do not read random files. You hunt for complexity.
- Use `complexity.py` to identify the top 10 files with the highest Cyclomatic Complexity.
- These are your targets. They contain the business rules.

### 2. Trace (Surgical Read)
- **Do not** read full files if they are > 300 lines.
- Use `smart_read.py` to read *only* the specific complex methods identified in step 1.
- Trace the data flow: Validation -> State Mutation -> Side Effects (DB/API).

### 3. Verify (Truth Check)
- Use `verify.py` on the Entry Points identified in Phase 1.
- Confirm that critical imports actually resolve. Mark failures as "Broken Paths".

### 4. Crystallize (Logic Mapping)
Synthesize your findings into **Logic Maps**. Do not output raw code.
Use Arrow Notation: `Check(User) -> Valid? -> [DB Write] -> Return`.

## Your Toolkit (`repo-investigator`)

```bash
# 1. FIND HOTSPOTS
python .claude/skills/repo-investigator/scripts/complexity.py [dir] --top 10

# 2. SURGICAL READ (Expands focus method, skeletonizes the rest)
python .claude/skills/repo-investigator/scripts/smart_read.py <file> --focus <method_name>

# 3. VERIFY IMPORTS
python .claude/skills/repo-investigator/scripts/verify.py <module_path>
````

## Workflow Example

1.  **Ingest**: Read `WARM_START.md`.
2.  **Scan**: `python .../complexity.py src/ --top 5`.
3.  **Loop**: For each hotspot:
      - `python .../smart_read.py src/core/workflow.py --focus process_order`
      - Generate Logic Map.
4.  **Check**: `python .../verify.py src/core/workflow.py`
5.  **Output**: Create `HOT_START.md`.

<!-- end list -->

````

---

### 2. New Skill: `repo-investigator`

Create the directory: `.claude/skills/repo-investigator/scripts/`.

#### Tool A: `complexity.py` (The Targeter)
Calculates complexity to tell the agent *where* to look.

```python
#!/usr/bin/env python3
"""
Repo Investigator: Complexity Scanner
Calculates Cyclomatic Complexity to identify the "Brain" of the codebase.
"""
import ast
import os
import argparse
import json
from typing import Dict, List

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.score = 0
        self.functions = {}  # name -> score

    def visit_FunctionDef(self, node):
        self._score_node(node)

    def visit_AsyncFunctionDef(self, node):
        self._score_node(node)

    def _score_node(self, node):
        # Base complexity = 1. +1 for every branch.
        cc = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, 
                                  ast.With, ast.AsyncWith, ast.ExceptHandler, ast.Assert)):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
        
        # Filter out trivial getters/setters
        if cc > 3: 
            self.functions[node.name] = cc
        self.score += cc

def analyze_file(filepath: str) -> Dict:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        return {
            "path": filepath,
            "score": visitor.score,
            "hotspots": visitor.functions
        }
    except Exception:
        return {"path": filepath, "score": 0, "hotspots": {}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", default=".", nargs="?")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = []
    ignore = {'.git', '__pycache__', 'venv', 'node_modules', 'tests', 'test'}

    for root, dirs, files in os.walk(args.directory):
        dirs[:] = [d for d in dirs if d not in ignore]
        for file in files:
            if file.endswith(".py"):
                results.append(analyze_file(os.path.join(root, file)))

    # Sort by total file complexity
    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:args.top]

    if args.json:
        print(json.dumps(top, indent=2))
    else:
        print(f"{'SCORE':<8} {'FILE':<50} {'HOTSPOTS (Method:CC)'}")
        print("-" * 80)
        for r in top:
            # Format top 3 hotspots
            spots = sorted(r['hotspots'].items(), key=lambda x: x[1], reverse=True)[:3]
            spot_str = ", ".join([f"{k}:{v}" for k,v in spots])
            print(f"{r['score']:<8} {r['path']:<50} {spot_str}...")

if __name__ == "__main__":
    main()
````

#### Tool B: `smart_read.py` (The Surgical Reader)

The critical innovation: Reads *implementation* of target methods but *signatures* of everything else. This provides full semantic context at 10% of the token cost.

```python
#!/usr/bin/env python3
"""
Repo Investigator: Smart Reader
Extracts full implementation of focused methods while skeletonizing the rest.
Preserves class hierarchy, attributes, and module imports.
"""
import ast
import sys
import argparse

def get_source(lines, node):
    """Extract source lines for a node, handling decorators."""
    start = node.lineno - 1
    if hasattr(node, 'decorator_list') and node.decorator_list:
        start = node.decorator_list[0].lineno - 1
    return lines[start : node.end_lineno]

def smart_read(filepath, focus_methods):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        lines = source.splitlines()
        tree = ast.parse(source)
    except Exception as e:
        return f"Error reading {filepath}: {e}"

    output = []
    
    # Iterate top-level nodes
    for node in tree.body:
        # Keep imports and assignments (constants)
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)):
            output.extend(get_source(lines, node))
            continue

        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if isinstance(node, ast.ClassDef):
                # Class Header
                output.append("")
                output.append(lines[node.lineno-1].strip().split(':')[0] + ":")
                
                # Check children
                has_visible_children = False
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if child.name in focus_methods:
                            # EXPAND: Full source
                            output.extend(get_source(lines, child))
                            has_visible_children = True
                        else:
                            # SKELETON: Signature only
                            sig = lines[child.lineno-1].strip().split(':')[0]
                            output.append(f"    {sig}: ... # L{child.lineno}")
                    elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                        # Keep class attributes
                        output.append("    " + lines[child.lineno-1].strip())
                
                if not has_visible_children:
                    output.append("    # ... (No focused methods)")

            elif node.name in focus_methods:
                # EXPAND Top-level function
                output.append("")
                output.extend(get_source(lines, node))
            else:
                # SKELETON Top-level function
                sig = lines[node.lineno-1].split(':')[0]
                output.append(f"{sig}: ... # L{node.lineno}")

    return "\n".join(output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--focus", nargs="+", default=[], help="Methods to expand")
    args = parser.parse_args()
    print(smart_read(args.file, args.focus))
```

#### Tool C: `verify.py` (The Truth Checker)

Ensures the "Warm Start" isn't a hallucination by checking importability.

```python
#!/usr/bin/env python3
"""
Repo Investigator: Verifier
Attempts to import a module to verify dependencies are satisfied.
"""
import importlib
import sys
import os

def verify(path):
    # Convert file path to module path
    if path.endswith('.py'): path = path[:-3]
    module_name = path.replace(os.sep, '.')
    
    print(f"Verifying {module_name}...")
    try:
        sys.path.append(os.getcwd())
        importlib.import_module(module_name)
        print("✅ OK: Module is importable.")
    except ImportError as e:
        print(f"❌ FAIL: ImportError - {e}")
    except Exception as e:
        print(f"⚠️ WARN: Runtime check failed ({e}), but import found.")

if __name__ == "__main__":
    verify(sys.argv[1])
```

-----

### 3\. The Artifact: `HOT_START.md` Template

This is the document the `repo_investigator` generates. It focuses on **System Dynamics**, not just structure.

**File:** `.claude/skills/repo-xray/templates/HOT_START.md.template`

````markdown
# {PROJECT_NAME}: Semantic Hot Start

> **Phase 2 Analysis**
> Contains validated Logic Maps and System Dynamics.
> Generated: {TIMESTAMP}

---

## 1. System Dynamics (The "Mental Model")

*High-density logic maps of the system's "Brain".*

### Critical Workflow: {WORKFLOW_NAME}
**Entry Point:** `{ENTRY_FILE}:{METHOD}`

```mermaid
sequenceDiagram
    participant Entry
    participant Logic
    participant State
    Entry->>Logic: Validate Input
    Logic->>State: Check Cache
    State-->>Logic: Cache Miss
    Logic->>Logic: Compute (Complex)
    Logic->>State: Update DB
````

### Logic Map: `{COMPLEX_CLASS}`

*File: `{FILE_PATH}`*

```python
def {CRITICAL_METHOD}(self, data):
    # 1. Validation Logic
    #    -> Check {CONDITION} -> Raise {ERROR}
    
    # 2. State Mutation
    #    -> Lock {RESOURCE}
    #    -> Update {FIELD} = {VALUE}
    
    # 3. Side Effects
    #    -> [DB] Insert Record
    #    -> [API] Call External Service (Retries: 3)
```

-----

## 2\. Validated Hidden Dependencies

  * **Environment**: Requires `OPENAI_API_KEY` (Validated in `config.py`).
  * **Infrastructure**: Depends on `Redis` (Found in `cache.py`).
  * **Broken Paths**: *Warning* - Module `src/legacy/old.py` fails to import.

-----

## 3\. Reference (Phase 1)

[Include WARM\_START.md Architecture Diagram here]

```
```
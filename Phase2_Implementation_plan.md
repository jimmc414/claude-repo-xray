# Phase 2 Implementation Plan: The Semantic Investigator

## 1. Overview

### Objective

Phase 2 evolves repo-xray from **structural extraction** to **semantic analysis**. While Phase 1 tells the AI *where* code is, Phase 2 tells it *how* code behaves, *why* it matters, and *if* dependencies resolve.

### Strategy: "Triangulate, Trace, Verify"

1. **Triangulate** - Use Unified Priority Score to identify the "Brain" of the codebase
   - Combines: Cyclomatic Complexity + Import Weight + Risk Score + Freshness
   - Surfaces architecturally critical code that pure CC misses

2. **Trace** - Surgical reading of high-priority code
   - Read full implementation of complex methods
   - Skeletonize everything else for context
   - ~10% token cost of full file read

3. **Verify** - Validate that documented code actually works
   - Safe mode: AST-based checking (no execution)
   - Strict mode: Runtime import verification
   - Catch dead imports and missing dependencies

### Output Artifact: HOT_START.md

A semantic companion to WARM_START.md containing:
- Logic Maps (dense pseudocode of critical paths)
- Validated dependencies
- System dynamics (data flow, state mutations, side effects)

### Design Principles

- **Stateless**: No session persistence
- **Deterministic**: Same inputs produce same outputs
- **Phase 1 Dependent**: Consumes JSON from Phase 1 tools
- **Token Efficient**: Every tool optimized for context budget

---

## 2. New Skill: repo-investigator

### Directory Structure

```
.claude/skills/repo-investigator/
├── SKILL.md
├── scripts/
│   ├── complexity.py      # Unified Priority Score calculator
│   ├── smart_read.py      # Surgical method reader
│   └── verify.py          # Import verification
└── templates/
    └── HOT_START.md.template
```

### SKILL.md

```markdown
# Repo Investigator

Semantic analysis tools for deep codebase understanding. Builds on Phase 1's structural analysis.

## Tools

### complexity.py - Unified Priority Scoring

Calculates priority score combining multiple signals.

```bash
# Basic complexity scan
python .claude/skills/repo-investigator/scripts/complexity.py [directory]

# Unified scoring (requires Phase 1 JSON outputs)
python .claude/skills/repo-investigator/scripts/complexity.py src/ \
  --unified deps.json git.json

# Top N results
python .claude/skills/repo-investigator/scripts/complexity.py src/ --top 10

# JSON output
python .claude/skills/repo-investigator/scripts/complexity.py src/ --json
```

**Unified Priority Score Formula:**
```
Priority = (CC * 0.35) + (ImportWeight * 0.25) + (RiskScore * 0.25) + (Freshness * 0.15)
```

### smart_read.py - Surgical Reader

Reads full implementation of complex methods while skeletonizing the rest.

```bash
# Auto-expand top N complex methods
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py \
  --focus-top 3

# Expand specific methods
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py \
  --focus process_order validate_input
```

### verify.py - Import Verifier

Validates that imports and symbols resolve correctly.

```bash
# Safe mode (AST-only, no execution)
python .claude/skills/repo-investigator/scripts/verify.py src/core/workflow.py --mode safe

# Strict mode (runtime import check)
python .claude/skills/repo-investigator/scripts/verify.py src/core/workflow.py --mode strict
```

## Workflow

1. Generate Phase 1 data:
   ```bash
   python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --json > deps.json
   python .claude/skills/repo-xray/scripts/git_analysis.py src/ --json > git.json
   ```

2. Calculate unified priorities:
   ```bash
   python .claude/skills/repo-investigator/scripts/complexity.py src/ --unified deps.json git.json
   ```

3. Surgical read of top files:
   ```bash
   python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py --focus-top 3
   ```

4. Verify critical modules:
   ```bash
   python .claude/skills/repo-investigator/scripts/verify.py src/core/workflow.py --mode safe
   ```
```

---

## 3. New Tool: complexity.py

### Purpose

Calculate Unified Priority Score by combining:
- **Cyclomatic Complexity (35%)** - Logic density from AST analysis
- **Import Weight (25%)** - Architectural importance from dependency graph
- **Risk Score (25%)** - Historical volatility from git analysis
- **Freshness (15%)** - Maintenance activity (active code more relevant)

### Command Reference

```bash
# Basic complexity scan (CC only)
python .claude/skills/repo-investigator/scripts/complexity.py [directory]

# Unified scoring with Phase 1 data
python .claude/skills/repo-investigator/scripts/complexity.py src/ \
  --unified deps.json git.json

# Limit results
python .claude/skills/repo-investigator/scripts/complexity.py src/ --top 10

# JSON output for downstream tools
python .claude/skills/repo-investigator/scripts/complexity.py src/ --json
```

### Output Format

**Text Mode:**
```
SCORE  FILE                              DETAILS
0.92   src/core/workflow.py              CC:45 Imp:0.72 Risk:0.65 Fresh:active
0.87   src/api/auth.py                   CC:23 Imp:0.45 Risk:0.87 Fresh:active
0.81   src/core/base.py                  CC:12 Imp:0.95 Risk:0.32 Fresh:aging
```

**JSON Mode:**
```json
[
  {
    "path": "src/core/workflow.py",
    "score": 0.92,
    "metrics": {
      "cc": 45,
      "imp_score": 0.72,
      "risk": 0.65,
      "freshness": 1.0
    },
    "hotspots": {
      "process_order": 12,
      "validate_input": 8,
      "handle_error": 6
    }
  }
]
```

### Full Implementation

```python
#!/usr/bin/env python3
"""
Repo Investigator: Unified Complexity Scanner

Calculates Unified Priority Score combining:
- Cyclomatic Complexity (35%)
- Import Weight from dependency graph (25%)
- Risk Score from git history (25%)
- Freshness score (15%)

Requires Phase 1 JSON outputs for unified scoring.

Usage:
    python complexity.py [directory] [options]

Examples:
    python complexity.py src/
    python complexity.py src/ --unified deps.json git.json
    python complexity.py src/ --top 10 --json
"""
import argparse
import ast
import json
import os
import sys
from typing import Dict, List, Tuple


def calculate_cc(filepath: str) -> Tuple[int, Dict[str, int]]:
    """
    Calculate Cyclomatic Complexity for a file.

    Returns:
        Tuple of (total_score, {method_name: cc_score})
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return 0, {}

    total_score = 0
    methods = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = 1  # Base complexity

            for child in ast.walk(node):
                # Decision points
                if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    cc += 1
                # Exception handlers
                elif isinstance(child, ast.ExceptHandler):
                    cc += 1
                # Boolean operators (and/or add complexity)
                elif isinstance(child, ast.BoolOp):
                    cc += len(child.values) - 1
                # Comprehensions with conditions
                elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    for generator in child.generators:
                        cc += len(generator.ifs)

            # Filter trivial methods (CC <= 3)
            if cc > 3:
                methods[node.name] = cc

            total_score += cc

    return total_score, methods


def normalize_dict(values: Dict[str, float]) -> Dict[str, float]:
    """Normalize dictionary values to 0-1 range."""
    if not values:
        return {}
    max_val = max(values.values())
    if max_val == 0:
        return {k: 0.0 for k in values}
    return {k: v / max_val for k, v in values.items()}


def load_phase1_data(deps_path: str, git_path: str) -> Tuple[Dict, Dict, Dict]:
    """
    Load Phase 1 JSON outputs.

    Returns:
        Tuple of (import_weights, risk_scores, freshness_map)
    """
    imports = {}
    risks = {}
    freshness = {}

    # Load dependency graph
    try:
        with open(deps_path, 'r') as f:
            deps = json.load(f)

        for mod_name, info in deps.get('modules', {}).items():
            # Use imported_by count as weight
            imported_by = info.get('imported_by', [])
            # Try to extract file path from module info
            if 'file' in info:
                imports[info['file']] = len(imported_by)
            # Also store by module name for matching
            imports[mod_name] = len(imported_by)
    except Exception as e:
        print(f"Warning: Could not load deps file: {e}", file=sys.stderr)

    # Load git analysis
    try:
        with open(git_path, 'r') as f:
            git = json.load(f)

        # Risk scores
        for item in git.get('risk', []):
            risks[item['file']] = item['risk_score']

        # Freshness: Active=1.0, Aging=0.7, Stale=0.4, Dormant=0.1
        freshness_scores = {
            'active': 1.0,
            'aging': 0.7,
            'stale': 0.4,
            'dormant': 0.1
        }
        for category, score in freshness_scores.items():
            for item in git.get('freshness', {}).get(category, []):
                freshness[item['file']] = score

    except Exception as e:
        print(f"Warning: Could not load git file: {e}", file=sys.stderr)

    return imports, risks, freshness


def scan_directory(directory: str, ignore_dirs: set = None) -> List[str]:
    """Scan directory for Python files."""
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', 'node_modules', '.venv', 'env'}

    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for filename in filenames:
            if filename.endswith('.py'):
                files.append(os.path.join(root, filename))

    return files


def main():
    parser = argparse.ArgumentParser(
        description="Calculate Unified Priority Score for Python files"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current)"
    )
    parser.add_argument(
        "--unified",
        nargs=2,
        metavar=('DEPS_JSON', 'GIT_JSON'),
        help="Phase 1 JSON outputs for unified scoring"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top results to show (default: 10)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum score to include (default: 0)"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load Phase 1 data if provided
    imports = {}
    risks = {}
    freshness = {}

    if args.unified:
        imports, risks, freshness = load_phase1_data(args.unified[0], args.unified[1])

    # Scan and analyze files
    files = scan_directory(args.directory)

    raw_cc = {}
    all_hotspots = {}

    for filepath in files:
        cc, methods = calculate_cc(filepath)
        if cc > 0:
            raw_cc[filepath] = cc
            all_hotspots[filepath] = methods

    if not raw_cc:
        if args.json:
            print("[]")
        else:
            print("No Python files with complexity found")
        return

    # Normalize scores
    norm_cc = normalize_dict(raw_cc)
    norm_imports = normalize_dict(imports)

    # Calculate unified scores
    results = []

    for filepath, cc_val in raw_cc.items():
        rel_path = os.path.relpath(filepath, args.directory)
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]

        # Get component scores
        s_cc = norm_cc.get(filepath, 0)
        s_imp = norm_imports.get(filepath, 0) or norm_imports.get(rel_path, 0)
        s_risk = risks.get(rel_path, 0)
        s_fresh = freshness.get(rel_path, 0.5)  # Default to mid if unknown

        # Unified Priority Score Formula
        # CC: 35%, Import Weight: 25%, Risk: 25%, Freshness: 15%
        if args.unified:
            score = (s_cc * 0.35) + (s_imp * 0.25) + (s_risk * 0.25) + (s_fresh * 0.15)
        else:
            # Without Phase 1 data, just use CC
            score = s_cc

        if score < args.min_score:
            continue

        results.append({
            "path": filepath,
            "score": round(score, 3),
            "metrics": {
                "cc": cc_val,
                "imp_score": round(s_imp, 2),
                "risk": round(s_risk, 2),
                "freshness": round(s_fresh, 2)
            },
            "hotspots": all_hotspots.get(filepath, {})
        })

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)
    top_results = results[:args.top]

    # Output
    if args.json:
        print(json.dumps(top_results, indent=2))
    else:
        print(f"{'SCORE':<6} {'FILE':<50} {'DETAILS'}")
        print("-" * 90)

        for r in top_results:
            m = r['metrics']
            if args.unified:
                details = f"CC:{m['cc']} Imp:{m['imp_score']} Risk:{m['risk']} Fresh:{m['freshness']}"
            else:
                spots = sorted(r['hotspots'].items(), key=lambda x: x[1], reverse=True)[:2]
                details = ", ".join(f"{k}:{v}" for k, v in spots) if spots else f"CC:{m['cc']}"

            print(f"{r['score']:<6} {r['path']:<50} {details}")


if __name__ == "__main__":
    main()
```

---

## 4. New Tool: smart_read.py

### Purpose

Surgical reading that expands complex methods while skeletonizing the rest. Provides full semantic context at ~10% token cost.

### Command Reference

```bash
# Auto-expand top N most complex methods
python .claude/skills/repo-investigator/scripts/smart_read.py <file> --focus-top 3

# Expand specific methods by name
python .claude/skills/repo-investigator/scripts/smart_read.py <file> --focus method1 method2

# Show skeleton only (no expansion)
python .claude/skills/repo-investigator/scripts/smart_read.py <file> --focus-top 0
```

### Output Format

```python
# Imports preserved
from typing import Optional, List
from .models import User, Order

# Constants preserved
DEFAULT_TIMEOUT = 30

class OrderProcessor:
    status: str
    items: List[Item]

    def __init__(self, config): ...  # L15
    def validate_order(self, order): ...  # L25

    # EXPANDED: Complex method (CC=12)
    def process_order(self, order: Order) -> bool:
        """Process an order through the system."""
        if not self.validate_order(order):
            raise ValidationError("Invalid order")

        for item in order.items:
            if item.quantity <= 0:
                continue
            if not self._check_inventory(item):
                return False
            self._reserve_item(item)

        self._calculate_total(order)
        self._apply_discounts(order)
        return self._finalize(order)

    def _check_inventory(self, item): ...  # L78
    def _reserve_item(self, item): ...  # L92
```

### Full Implementation

```python
#!/usr/bin/env python3
"""
Repo Investigator: Smart Reader

Surgical reading that expands complex methods while skeletonizing the rest.
Preserves imports, class attributes, and method signatures for context.

Usage:
    python smart_read.py <file> [options]

Examples:
    python smart_read.py src/core/workflow.py --focus-top 3
    python smart_read.py src/core/workflow.py --focus process_order validate
"""
import argparse
import ast
import sys
from typing import List, Set, Tuple


def calculate_complexity(node: ast.AST) -> int:
    """Calculate cyclomatic complexity for a function node."""
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            cc += 1
        elif isinstance(child, ast.ExceptHandler):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            cc += len(child.values) - 1
    return cc


def get_source_lines(lines: List[str], node: ast.AST) -> List[str]:
    """Extract source lines for a node, including decorators."""
    start = node.lineno - 1

    # Include decorators
    if hasattr(node, 'decorator_list') and node.decorator_list:
        start = node.decorator_list[0].lineno - 1

    return lines[start:node.end_lineno]


def find_top_complex_methods(tree: ast.AST, n: int) -> Set[str]:
    """Find the N most complex methods in the AST."""
    candidates = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = calculate_complexity(node)
            candidates.append((node.name, cc))

    # Sort by complexity, take top N
    candidates.sort(key=lambda x: x[1], reverse=True)
    return {name for name, cc in candidates[:n] if cc > 3}


def smart_read(filepath: str, focus_top: int = 0, focus_methods: List[str] = None) -> str:
    """
    Read file with surgical expansion of complex methods.

    Args:
        filepath: Path to Python file
        focus_top: Auto-expand top N complex methods
        focus_methods: Explicit list of methods to expand

    Returns:
        Surgically processed source code
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        return f"Error reading file: {e}"

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"Syntax error in file: {e}"

    lines = source.splitlines()

    # Determine which methods to expand
    expand_methods = set(focus_methods or [])

    if focus_top > 0:
        expand_methods.update(find_top_complex_methods(tree, focus_top))

    output = []

    for node in tree.body:
        # Keep imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            output.extend(get_source_lines(lines, node))
            continue

        # Keep module-level assignments (constants)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            output.extend(get_source_lines(lines, node))
            continue

        # Handle classes
        if isinstance(node, ast.ClassDef):
            # Class header with bases
            class_line = lines[node.lineno - 1]
            output.append("")
            output.append(class_line)

            for child in node.body:
                # Class attributes
                if isinstance(child, (ast.Assign, ast.AnnAssign)):
                    output.append("    " + lines[child.lineno - 1].strip())

                # Methods
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name in expand_methods:
                        # EXPAND: Full implementation
                        cc = calculate_complexity(child)
                        output.append(f"")
                        output.append(f"    # EXPANDED: {child.name} (CC={cc})")
                        for line in get_source_lines(lines, child):
                            output.append(line)
                    else:
                        # SKELETON: Signature only
                        sig_line = lines[child.lineno - 1].rstrip()
                        if not sig_line.endswith(':'):
                            sig_line = sig_line.split(':')[0]
                        output.append(f"    {sig_line.strip()}: ...  # L{child.lineno}")

            continue

        # Handle top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in expand_methods:
                # EXPAND
                cc = calculate_complexity(node)
                output.append("")
                output.append(f"# EXPANDED: {node.name} (CC={cc})")
                output.extend(get_source_lines(lines, node))
            else:
                # SKELETON
                sig_line = lines[node.lineno - 1].split(':')[0]
                output.append(f"{sig_line}: ...  # L{node.lineno}")

            continue

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Surgical reader for Python files"
    )
    parser.add_argument(
        "file",
        help="Python file to read"
    )
    parser.add_argument(
        "--focus-top",
        type=int,
        default=3,
        help="Auto-expand top N complex methods (default: 3)"
    )
    parser.add_argument(
        "--focus",
        nargs="+",
        default=[],
        help="Specific method names to expand"
    )

    args = parser.parse_args()

    result = smart_read(args.file, args.focus_top, args.focus)
    print(result)


if __name__ == "__main__":
    main()
```

---

## 5. New Tool: verify.py

### Purpose

Validate that imports and symbols resolve correctly. Two modes:
- **Safe Mode**: AST-based checking, no code execution
- **Strict Mode**: Runtime import verification

### Command Reference

```bash
# Safe mode (default): AST-only validation
python .claude/skills/repo-investigator/scripts/verify.py <file> --mode safe

# Strict mode: Runtime import check
python .claude/skills/repo-investigator/scripts/verify.py <file> --mode strict

# Check specific module path
python .claude/skills/repo-investigator/scripts/verify.py mypackage.core.workflow --mode strict
```

### Output Format

```
[OK] AST Valid
[OK] Import Successful

# Or with issues:
[OK] AST Valid (Warning: Potential missing imports: mypackage.legacy.old)
[FAIL] ImportError: No module named 'mypackage.missing'
```

### Full Implementation

```python
#!/usr/bin/env python3
"""
Repo Investigator: Import Verifier

Two-tier verification:
- Safe mode (AST-only): Checks syntax and local file references
- Strict mode (Runtime): Actually imports the module

Usage:
    python verify.py <path> [options]

Examples:
    python verify.py src/core/workflow.py --mode safe
    python verify.py mypackage.core.workflow --mode strict
"""
import argparse
import ast
import importlib
import os
import sys
from typing import Tuple, List


# Standard library modules (subset for quick checking)
STDLIB_MODULES = {
    'os', 'sys', 're', 'json', 'typing', 'pathlib', 'collections',
    'datetime', 'asyncio', 'logging', 'argparse', 'dataclasses',
    'abc', 'enum', 'functools', 'itertools', 'copy', 'time',
    'math', 'random', 'hashlib', 'base64', 'io', 'contextlib',
    'subprocess', 'shutil', 'tempfile', 'glob', 'fnmatch',
    'unittest', 'traceback', 'warnings', 'inspect', 'ast',
    'concurrent', 'multiprocessing', 'threading', 'queue',
    'http', 'urllib', 'socket', 'ssl', 'email', 'html', 'xml',
    'sqlite3', 'pickle', 'csv', 'configparser', 'struct', 'codecs'
}


def check_safe(filepath: str) -> Tuple[bool, str, List[str]]:
    """
    AST-based verification (no execution).

    Checks:
    1. File exists and is readable
    2. File parses as valid Python
    3. Imported modules appear to exist locally

    Returns:
        Tuple of (success, message, warnings)
    """
    warnings = []

    # Check file exists
    if not os.path.exists(filepath):
        return False, "File not found", warnings

    # Read and parse
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"Syntax error: {e}", warnings
    except Exception as e:
        return False, f"Read error: {e}", warnings

    # Check imports
    cwd = os.getcwd()
    missing = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split('.')[0]
                if mod in STDLIB_MODULES:
                    continue
                if not _module_exists_locally(mod, cwd):
                    missing.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue  # Skip relative imports (harder to verify)
            if node.module:
                mod = node.module.split('.')[0]
                if mod in STDLIB_MODULES:
                    continue
                if not _module_exists_locally(mod, cwd):
                    missing.append(node.module)

    if missing:
        warnings.append(f"Potential missing imports: {', '.join(missing[:5])}")

    return True, "AST Valid", warnings


def _module_exists_locally(module_name: str, cwd: str) -> bool:
    """Check if a module exists as a local file or package."""
    # Check as file
    if os.path.exists(os.path.join(cwd, f"{module_name}.py")):
        return True

    # Check as package
    pkg_path = os.path.join(cwd, module_name)
    if os.path.isdir(pkg_path) and os.path.exists(os.path.join(pkg_path, "__init__.py")):
        return True

    # Check in common source directories
    for src_dir in ['src', 'lib', 'app']:
        src_path = os.path.join(cwd, src_dir)
        if os.path.exists(os.path.join(src_path, f"{module_name}.py")):
            return True
        pkg_path = os.path.join(src_path, module_name)
        if os.path.isdir(pkg_path) and os.path.exists(os.path.join(pkg_path, "__init__.py")):
            return True

    return False


def check_strict(module_path: str) -> Tuple[bool, str]:
    """
    Runtime import verification.

    Actually imports the module to verify all dependencies resolve.
    WARNING: This executes module-level code.

    Returns:
        Tuple of (success, message)
    """
    # Convert file path to module path if needed
    if module_path.endswith('.py'):
        module_path = module_path[:-3]
    module_name = module_path.replace(os.sep, '.').replace('/', '.')

    # Clean up module name
    if module_name.startswith('.'):
        module_name = module_name[1:]

    try:
        # Add current directory to path
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())

        # Attempt import
        importlib.import_module(module_name)
        return True, "Import Successful"

    except ImportError as e:
        return False, f"ImportError: {e}"
    except Exception as e:
        return False, f"Runtime error: {type(e).__name__}: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Verify Python imports and dependencies"
    )
    parser.add_argument(
        "path",
        help="File path or module path to verify"
    )
    parser.add_argument(
        "--mode",
        choices=["safe", "strict"],
        default="safe",
        help="Verification mode (default: safe)"
    )

    args = parser.parse_args()

    # Determine if path is file or module
    path = args.path
    is_file = path.endswith('.py') or os.path.exists(path)

    if is_file and not os.path.exists(path):
        # Try adding .py
        if os.path.exists(path + '.py'):
            path = path + '.py'

    # Safe mode
    if args.mode == "safe" or is_file:
        if not is_file:
            # Convert module path to file path for safe check
            file_path = path.replace('.', os.sep) + '.py'
        else:
            file_path = path

        ok, msg, warnings = check_safe(file_path)
        if warnings:
            msg = f"{msg} (Warning: {'; '.join(warnings)})"

        if not ok:
            print(f"[FAIL] {msg}")
            sys.exit(1)

        print(f"[OK] {msg}")

    # Strict mode
    if args.mode == "strict":
        ok, msg = check_strict(path)
        if not ok:
            print(f"[FAIL] {msg}")
            sys.exit(1)
        print(f"[OK] {msg}")


if __name__ == "__main__":
    main()
```

---

## 6. New Agent: repo_investigator.md

**Location**: `.claude/agents/repo_investigator.md`

```markdown
---
name: repo_investigator
description: Senior Engineer Agent for semantic analysis. Builds on Phase 1's structural map to create behavioral documentation. Generates HOT_START.md with Logic Maps and validated dependencies.
tools: Read, Bash
model: sonnet
skills: repo-xray, repo-investigator
parent: repo_architect
---

# Repo Investigator

You are a Principal Software Engineer performing a semantic audit. Your goal is to upgrade the Structural Map (WARM_START.md) into a Behavioral Guide (HOT_START.md).

## Your Strategy: "Triangulate, Trace, Verify"

### 1. Triangulate (Find the Brain)

You do not read random files. You hunt for importance using multiple signals.

```bash
# Generate Phase 1 data first
python .claude/skills/repo-xray/scripts/dependency_graph.py src/ --json > deps.json
python .claude/skills/repo-xray/scripts/git_analysis.py src/ --json > git.json

# Calculate Unified Priority Score
python .claude/skills/repo-investigator/scripts/complexity.py src/ --unified deps.json git.json --top 10
```

The Unified Priority Score combines:
- Cyclomatic Complexity (35%) - Logic density
- Import Weight (25%) - Architectural importance
- Risk Score (25%) - Historical volatility
- Freshness (15%) - Maintenance activity

### 2. Trace (Surgical Read)

Do NOT read full files if they are > 300 lines. Use surgical reading.

```bash
# Auto-expand top 3 complex methods, skeletonize rest
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py --focus-top 3

# Or target specific methods
python .claude/skills/repo-investigator/scripts/smart_read.py src/core/workflow.py --focus process_order validate
```

Trace the data flow: Validation -> State Mutation -> Side Effects (DB/API).

### 3. Verify (Truth Check)

Confirm that critical imports actually resolve.

```bash
# Safe mode (no execution)
python .claude/skills/repo-investigator/scripts/verify.py src/core/workflow.py --mode safe

# Strict mode (runtime check)
python .claude/skills/repo-investigator/scripts/verify.py mypackage.core.workflow --mode strict
```

Mark failures as "Broken Paths" in HOT_START.md.

### 4. Crystallize (Logic Mapping)

Synthesize findings into Logic Maps. Do NOT output raw code.

Use Arrow Notation:
```
-> : control flow
[X] : side effect (DB, API, File)
<X> : external input
{X} : state mutation
?  : conditional branch
```

Example:
```
process_order(order):
  Validate(order) -> valid? -> {status=processing}
  for item in order.items:
    check_inventory(item) -> available? -> [DB: reserve]
  -> calculate_total -> apply_discounts
  -> [DB: save] -> [Email: confirmation]
  -> Return(success)
```

## Workflow

1. **Ingest**: Read WARM_START.md to understand structure
2. **Generate Phase 1 Data**: Run dependency_graph.py and git_analysis.py with --json
3. **Scan**: Run complexity.py --unified to find top priority files
4. **Loop**: For each high-priority file:
   - smart_read.py --focus-top 3
   - Generate Logic Map
   - Note side effects and dependencies
5. **Verify**: verify.py --mode safe on all documented modules
6. **Output**: Create HOT_START.md

## Token Budget

| Operation | Tokens | Purpose |
|-----------|--------|---------|
| Read WARM_START.md | 500-1000 | Context |
| complexity.py output | 200 | Targeting |
| smart_read.py (per file) | 300-800 | Deep reading |
| verify.py output | 50 | Validation |
| Logic Map synthesis | 500/file | Your analysis |
| HOT_START.md output | 1000-2000 | Final artifact |

**Rule**: If fewer than 5 files contain 80% of complexity, consider reading them directly instead of surgical approach.

## Constraints

1. Never generate Logic Maps for code you haven't read
2. Always use smart_read.py before documenting a file
3. Mark unverified imports as "Unverified" in output
4. Respect the stateless design - no session persistence
5. No emoji in output
```

---

## 7. New Template: HOT_START.md.template

**Location**: `.claude/skills/repo-investigator/templates/HOT_START.md.template`

```markdown
# {PROJECT_NAME}: Semantic Hot Start

> Phase 2 semantic analysis companion to WARM_START.md
> Generated: {TIMESTAMP}
> Priority files analyzed: {FILE_COUNT}

---

## 1. System Dynamics

High-density logic maps of the system's critical paths.

### Targeting Summary

| Rank | File | Priority Score | Factors |
|------|------|----------------|---------|
{PRIORITY_TABLE}

---

## 2. Logic Maps

### {WORKFLOW_NAME}

**Entry Point**: `{ENTRY_FILE}:{METHOD_NAME}`
**Priority Score**: {PRIORITY_SCORE}

#### Data Flow
```
{LOGIC_MAP}
```

#### Key Decisions
{KEY_DECISIONS}

#### Side Effects
{SIDE_EFFECTS}

---

{ADDITIONAL_LOGIC_MAPS}

---

## 3. Dependency Verification

### Verified Modules
{VERIFIED_MODULES}

### Broken Paths
{BROKEN_PATHS}

### Warnings
{VERIFICATION_WARNINGS}

---

## 4. Hidden Dependencies

### Environment Variables
{ENV_VARS}

### External Services
{EXTERNAL_SERVICES}

### Configuration Files
{CONFIG_FILES}

---

## 5. Logic Map Legend

```
->    : Control flow
[X]   : Side effect (DB write, API call, file I/O)
<X>   : External input (user input, API response)
{X}   : State mutation (object modification)
?     : Conditional branch
*     : Loop iteration
!     : Exception/error path
//    : Comment/annotation
```

---

## 6. Reference

This document complements:
- WARM_START.md (structural architecture)
- Phase 1 tools (repo-xray)

To refresh: `@repo_investigator refresh`
To query: `@repo_investigator query "how does X work?"`

---

*Generated by repo_investigator using repo-investigator skill*
```

### Placeholder Definitions

| Placeholder | Source | Format |
|-------------|--------|--------|
| `{PROJECT_NAME}` | From configure.py or directory name | String |
| `{TIMESTAMP}` | Generation time | ISO 8601 |
| `{FILE_COUNT}` | Number of files analyzed | Integer |
| `{PRIORITY_TABLE}` | complexity.py --unified | Markdown table |
| `{WORKFLOW_NAME}` | Agent analysis | String (e.g., "Order Processing") |
| `{ENTRY_FILE}` | From analysis | File path |
| `{METHOD_NAME}` | From analysis | Function/method name |
| `{PRIORITY_SCORE}` | From complexity.py | Float (0-1) |
| `{LOGIC_MAP}` | Agent synthesis | Arrow notation diagram |
| `{KEY_DECISIONS}` | Agent analysis | Bullet list |
| `{SIDE_EFFECTS}` | Agent analysis | Bullet list |
| `{VERIFIED_MODULES}` | verify.py results | Bullet list |
| `{BROKEN_PATHS}` | verify.py failures | Bullet list or "None detected" |
| `{ENV_VARS}` | Agent analysis | Table: Name, Usage, Required |
| `{EXTERNAL_SERVICES}` | Agent analysis | Table: Service, Purpose |
| `{CONFIG_FILES}` | Agent analysis | Bullet list |

---

## 8. Integration Points

### How Phase 2 Consumes Phase 1 Output

```
Phase 1 Tools                    Phase 2 Tools
─────────────                    ─────────────
dependency_graph.py --json  ──►  complexity.py --unified
git_analysis.py --json      ──►  complexity.py --unified
                                      │
                                      ▼
                                 smart_read.py
                                      │
                                      ▼
                                  verify.py
                                      │
                                      ▼
                                 HOT_START.md
```

### JSON Format: dependency_graph.py

```json
{
  "modules": {
    "mypackage.core.workflow": {
      "file": "src/core/workflow.py",
      "imports": ["mypackage.core.base", "mypackage.models.order"],
      "imported_by": ["mypackage.api.handler", "mypackage.cli.main"]
    }
  },
  "layers": {
    "foundation": ["mypackage.core.base"],
    "core": ["mypackage.core.workflow"],
    "orchestration": ["mypackage.api.handler"]
  },
  "circular_dependencies": [],
  "summary": {
    "total_modules": 25,
    "internal_edges": 48
  }
}
```

### JSON Format: git_analysis.py

```json
{
  "risk": [
    {
      "file": "src/core/workflow.py",
      "risk_score": 0.72,
      "churn": 15,
      "hotfixes": 2,
      "authors": 4
    }
  ],
  "coupling": [
    {
      "file_a": "src/api/auth.py",
      "file_b": "src/api/session.py",
      "count": 12
    }
  ],
  "freshness": {
    "active": [{"file": "src/api/handler.py", "days": 5}],
    "aging": [{"file": "src/models/user.py", "days": 45}],
    "stale": [],
    "dormant": [{"file": "src/legacy/old.py", "days": 200}]
  }
}
```

### JSON Format: complexity.py --json

```json
[
  {
    "path": "src/core/workflow.py",
    "score": 0.92,
    "metrics": {
      "cc": 45,
      "imp_score": 0.72,
      "risk": 0.65,
      "freshness": 1.0
    },
    "hotspots": {
      "process_order": 12,
      "validate_input": 8
    }
  }
]
```

---

## 9. Testing Plan

### Test Environment
- Repository: `/mnt/c/python/kosmos`
- Ensure Phase 1 tools work first

### Phase 2 Test Cases

#### 9.1 complexity.py Tests

```bash
# Basic CC-only scan
python .claude/skills/repo-investigator/scripts/complexity.py /mnt/c/python/kosmos
# Expected: List of files with CC scores

# Generate Phase 1 data
python .claude/skills/repo-xray/scripts/dependency_graph.py /mnt/c/python/kosmos --json > /tmp/deps.json
python .claude/skills/repo-xray/scripts/git_analysis.py /mnt/c/python/kosmos --json > /tmp/git.json

# Unified scoring
python .claude/skills/repo-investigator/scripts/complexity.py /mnt/c/python/kosmos \
  --unified /tmp/deps.json /tmp/git.json
# Expected: Files ranked by Unified Priority Score

# JSON output
python .claude/skills/repo-investigator/scripts/complexity.py /mnt/c/python/kosmos \
  --unified /tmp/deps.json /tmp/git.json --json
# Expected: Valid JSON array with score and metrics
```

#### 9.2 smart_read.py Tests

```bash
# Find a file with complexity
FILE=$(python .claude/skills/repo-investigator/scripts/complexity.py /mnt/c/python/kosmos --top 1 | tail -1 | awk '{print $2}')

# Auto-expand top 3 methods
python .claude/skills/repo-investigator/scripts/smart_read.py "$FILE" --focus-top 3
# Expected: Imports, class signatures, expanded complex methods, skeletonized rest

# Skeleton only
python .claude/skills/repo-investigator/scripts/smart_read.py "$FILE" --focus-top 0
# Expected: Only signatures, no expanded methods

# Non-existent file
python .claude/skills/repo-investigator/scripts/smart_read.py /nonexistent.py
# Expected: Error message
```

#### 9.3 verify.py Tests

```bash
# Safe mode on valid file
python .claude/skills/repo-investigator/scripts/verify.py /mnt/c/python/kosmos/kosmos/__init__.py --mode safe
# Expected: [OK] AST Valid

# Safe mode on file with external imports
python .claude/skills/repo-investigator/scripts/verify.py /mnt/c/python/kosmos/kosmos/core.py --mode safe
# Expected: [OK] with possible warnings about missing imports

# Strict mode (requires kosmos to be importable)
cd /mnt/c/python/kosmos && python .claude/skills/repo-investigator/scripts/verify.py kosmos.core --mode strict
# Expected: [OK] Import Successful or [FAIL] with specific error
```

#### 9.4 Integration Test

```bash
cd /mnt/c/python/kosmos

# Full workflow
python .claude/skills/repo-xray/scripts/dependency_graph.py kosmos/ --json > /tmp/deps.json
python .claude/skills/repo-xray/scripts/git_analysis.py . --json > /tmp/git.json

python .claude/skills/repo-investigator/scripts/complexity.py kosmos/ \
  --unified /tmp/deps.json /tmp/git.json --top 5 --json > /tmp/priorities.json

# Verify JSON chain works
python -c "
import json
with open('/tmp/priorities.json') as f:
    data = json.load(f)
print(f'Top file: {data[0][\"path\"]}')
print(f'Score: {data[0][\"score\"]}')
"
```

### Acceptance Criteria

1. complexity.py produces valid unified scores when given Phase 1 data
2. smart_read.py correctly expands high-CC methods and skeletonizes others
3. verify.py safe mode never executes code
4. verify.py strict mode catches import errors
5. All tools exit 0 on success, non-zero on failure
6. JSON outputs are valid and parseable
7. Logic Map notation is documented and consistent

---

## 10. File Checklist

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `.claude/skills/repo-investigator/SKILL.md` | ~100 | Skill documentation |
| `.claude/skills/repo-investigator/scripts/complexity.py` | ~200 | Unified Priority Score |
| `.claude/skills/repo-investigator/scripts/smart_read.py` | ~150 | Surgical reader |
| `.claude/skills/repo-investigator/scripts/verify.py` | ~150 | Import verification |
| `.claude/skills/repo-investigator/templates/HOT_START.md.template` | ~100 | Output template |
| `.claude/agents/repo_investigator.md` | ~150 | Agent definition |

### Directory Structure to Create

```
.claude/
├── agents/
│   └── repo_investigator.md          # NEW
└── skills/
    └── repo-investigator/            # NEW directory
        ├── SKILL.md
        ├── scripts/
        │   ├── complexity.py
        │   ├── smart_read.py
        │   └── verify.py
        └── templates/
            └── HOT_START.md.template
```

### Estimated Total

| Category | Lines |
|----------|-------|
| New Python code | ~500 |
| Documentation | ~350 |
| **Total** | ~850 |

---

## Summary

Phase 2 adds semantic analysis capabilities through the `repo-investigator` skill:

1. **Unified Priority Scoring** - Combines CC, import weight, risk, and freshness
2. **Surgical Reading** - Expands complex methods, skeletonizes rest
3. **Import Verification** - Safe and strict modes for validation
4. **repo_investigator Agent** - "Triangulate, Trace, Verify" workflow
5. **HOT_START.md** - Semantic companion to WARM_START.md

The tools are stateless, deterministic, and designed to consume Phase 1 JSON outputs for integrated analysis.

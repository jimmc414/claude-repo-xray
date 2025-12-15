"""
Repo X-Ray: Unified AST Analysis Module

Single-pass AST analysis that extracts all structural and behavioral information:
- Skeleton extraction (classes, functions, signatures)
- Complexity metrics (cyclomatic complexity, hotspots)
- Type annotation coverage
- Decorator inventory
- Async patterns
- Side effect detection (I/O, network, DB)
- Internal call graph

Design principle: Parse each file ONCE, extract everything.

Usage:
    from ast_analysis import analyze_file, analyze_codebase

    result = analyze_file("/path/to/file.py")
    codebase = analyze_codebase(["/path/to/file1.py", "/path/to/file2.py"])
"""

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Side Effect Detection Patterns
# =============================================================================

# Patterns that indicate side effects
SIDE_EFFECT_PATTERNS = {
    'db': ['db.save', 'db.commit', 'session.commit', 'cursor.execute',
           'insert(', 'update(', 'delete(', 'query('],
    'api': ['requests.', 'httpx.', 'aiohttp.', '.post(', '.put(', '.patch(',
           'fetch(', 'api.send'],
    'file': ['file.write', '.write(', 'json.dump', 'pickle.dump', 'export('],
    'env': ['os.environ', 'setenv', 'putenv'],
    'subprocess': ['subprocess.', 'os.system', 'os.exec', 'Popen('],
}

# Safe patterns to exclude from side effect detection
SAFE_PATTERNS = [
    '.get(',      # dict.get(), os.environ.get(), etc.
    'ast.get_',   # ast.get_docstring(), etc.
    'isupper',    # str.isupper()
    'islower',    # str.islower()
    'startswith',
    'endswith',
    '.read(',     # Reading is not a side effect
]


# =============================================================================
# Core Data Structures
# =============================================================================

class FileAnalysis:
    """Analysis results for a single file."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = Path(filepath).name

        # Structure
        self.classes: List[Dict] = []
        self.functions: List[Dict] = []
        self.constants: List[Dict] = []

        # Metrics
        self.line_count: int = 0
        self.total_cc: int = 0
        self.hotspots: Dict[str, int] = {}  # name -> CC score

        # Types
        self.total_functions: int = 0
        self.typed_functions: int = 0
        self.type_coverage: float = 0.0

        # Decorators
        self.decorators: Dict[str, int] = defaultdict(int)

        # Async
        self.async_functions: int = 0
        self.sync_functions: int = 0
        self.async_for_loops: int = 0
        self.async_context_managers: int = 0

        # Side effects
        self.side_effects: List[Dict] = []

        # Calls (internal)
        self.internal_calls: List[Dict] = []

        # Tokens
        self.original_tokens: int = 0
        self.skeleton_tokens: int = 0

        # Errors
        self.parse_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "filepath": self.filepath,
            "line_count": self.line_count,
            "classes": self.classes,
            "functions": self.functions,
            "constants": self.constants,
            "complexity": {
                "total_cc": self.total_cc,
                "hotspots": self.hotspots
            },
            "type_coverage": {
                "total_functions": self.total_functions,
                "typed_functions": self.typed_functions,
                "coverage_percent": self.type_coverage
            },
            "decorators": dict(self.decorators),
            "async_patterns": {
                "async_functions": self.async_functions,
                "sync_functions": self.sync_functions,
                "async_for_loops": self.async_for_loops,
                "async_context_managers": self.async_context_managers
            },
            "side_effects": self.side_effects,
            "internal_calls": self.internal_calls,
            "tokens": {
                "original": self.original_tokens,
                "skeleton": self.skeleton_tokens
            },
            "parse_error": self.parse_error
        }


# =============================================================================
# AST Helper Functions
# =============================================================================

def _get_name(node) -> str:
    """Get name from various AST node types."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    elif isinstance(node, ast.Subscript):
        return f"{_get_name(node.value)}[{_get_annotation(node.slice)}]"
    return "..."


def _get_annotation(node) -> str:
    """Get type annotation string."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        return repr(node.value)
    elif isinstance(node, ast.Subscript):
        value = _get_name(node.value)
        slice_val = _get_annotation(node.slice)
        return f"{value}[{slice_val}]"
    elif isinstance(node, ast.Tuple):
        return ", ".join(_get_annotation(e) for e in node.elts)
    elif isinstance(node, ast.Attribute):
        return _get_name(node)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{_get_annotation(node.left)} | {_get_annotation(node.right)}"
    elif isinstance(node, ast.List):
        if node.elts:
            return "[" + ", ".join(_get_annotation(e) for e in node.elts[:2]) + ", ...]"
        return "[]"
    return "..."


def _get_constant_repr(node) -> str:
    """Get string representation of a constant value."""
    if isinstance(node, ast.Constant):
        val = node.value
        if isinstance(val, str):
            val_str = val.replace('\n', '\\n')
            if len(val_str) > 50:
                return f'"{val_str[:47]}..."'
            return f'"{val_str}"'
        return repr(val)
    elif isinstance(node, ast.List):
        return "[...]"
    elif isinstance(node, ast.Dict):
        return "{...}"
    elif isinstance(node, ast.Call):
        func_name = _get_name(node.func)
        return f"{func_name}(...)"
    elif isinstance(node, ast.Name):
        return node.id
    return "..."


def _get_default_repr(node) -> str:
    """Get string representation of default value."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str) and len(node.value) > 20:
            return '"..."'
        return repr(node.value)
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, (ast.List, ast.Tuple)):
        return "..." if node.elts else "[]"
    elif isinstance(node, ast.Dict):
        return "..." if node.keys else "{}"
    elif isinstance(node, ast.Call):
        return f"{_get_name(node.func)}(...)"
    return "..."


def _extract_decorator_name(dec) -> str:
    """Extract decorator name from AST node."""
    if isinstance(dec, ast.Name):
        return dec.id
    elif isinstance(dec, ast.Attribute):
        return dec.attr
    elif isinstance(dec, ast.Call):
        if isinstance(dec.func, ast.Name):
            return dec.func.id
        elif isinstance(dec.func, ast.Attribute):
            return dec.func.attr
    return "unknown"


def _get_call_text(node: ast.Call) -> str:
    """Get text representation of a function call."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        return _get_name(node.func)
    return "..."


def _detect_side_effect(call_text: str) -> Optional[Dict]:
    """Detect if a call has side effects."""
    call_lower = call_text.lower()

    # Skip safe patterns
    for safe in SAFE_PATTERNS:
        if safe in call_lower:
            return None

    # Check for side effect patterns
    for category, patterns in SIDE_EFFECT_PATTERNS.items():
        for pattern in patterns:
            if pattern in call_lower:
                return {"category": category, "call": call_text}

    return None


# =============================================================================
# Complexity Analysis
# =============================================================================

def _calculate_function_cc(node) -> int:
    """Calculate cyclomatic complexity for a function."""
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

    return cc


# =============================================================================
# Function Analysis
# =============================================================================

def _extract_function_info(
    node,
    include_line_numbers: bool = True
) -> Dict[str, Any]:
    """Extract full information about a function/method."""
    is_async = isinstance(node, ast.AsyncFunctionDef)

    # Build argument list
    args = []
    defaults_offset = len(node.args.args) - len(node.args.defaults)

    for i, arg in enumerate(node.args.args):
        arg_info = {"name": arg.arg}
        if arg.annotation:
            arg_info["type"] = _get_annotation(arg.annotation)

        default_idx = i - defaults_offset
        if 0 <= default_idx < len(node.args.defaults):
            arg_info["default"] = _get_default_repr(node.args.defaults[default_idx])

        args.append(arg_info)

    # *args
    if node.args.vararg:
        vararg_info = {"name": f"*{node.args.vararg.arg}"}
        if node.args.vararg.annotation:
            vararg_info["type"] = _get_annotation(node.args.vararg.annotation)
        args.append(vararg_info)

    # **kwargs
    if node.args.kwarg:
        kwarg_info = {"name": f"**{node.args.kwarg.arg}"}
        if node.args.kwarg.annotation:
            kwarg_info["type"] = _get_annotation(node.args.kwarg.annotation)
        args.append(kwarg_info)

    # Return type
    returns = _get_annotation(node.returns) if node.returns else None

    # Docstring
    docstring = ast.get_docstring(node)
    docstring_summary = None
    if docstring:
        docstring_summary = docstring.strip().splitlines()[0][:100]

    # Decorators
    decorators = [_extract_decorator_name(d) for d in node.decorator_list]

    # Complexity
    cc = _calculate_function_cc(node)

    # Type coverage check
    has_type_hints = (
        node.returns is not None or
        any(arg.annotation is not None for arg in node.args.args
            if arg.arg not in ('self', 'cls'))
    )

    result = {
        "name": node.name,
        "is_async": is_async,
        "args": args,
        "returns": returns,
        "docstring": docstring_summary,
        "decorators": decorators,
        "complexity": cc,
        "has_type_hints": has_type_hints,
        "start_line": node.lineno,
        "end_line": getattr(node, 'end_lineno', node.lineno)  # Python 3.8+
    }

    return result


# =============================================================================
# Class Analysis
# =============================================================================

def _extract_class_info(
    node: ast.ClassDef,
    include_line_numbers: bool = True
) -> Dict[str, Any]:
    """Extract full information about a class."""
    # Base classes
    bases = [_get_name(b) for b in node.bases]

    # Docstring
    docstring = ast.get_docstring(node)
    docstring_summary = None
    if docstring:
        docstring_summary = docstring.strip().splitlines()[0][:100]

    # Decorators
    decorators = [_extract_decorator_name(d) for d in node.decorator_list]

    # Fields (class attributes and annotated assignments)
    fields = []
    for child in node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            field = {
                "name": child.target.id,
                "type": _get_annotation(child.annotation),
                "line": child.lineno
            }
            if child.value:
                field["default"] = _get_constant_repr(child.value)
            fields.append(field)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    fields.append({
                        "name": target.id,
                        "value": _get_constant_repr(child.value),
                        "line": child.lineno
                    })

    # Methods
    methods = []
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_extract_function_info(child, include_line_numbers))

    # Nested classes
    nested_classes = []
    for child in node.body:
        if isinstance(child, ast.ClassDef):
            nested_classes.append(_extract_class_info(child, include_line_numbers))

    result = {
        "name": node.name,
        "bases": bases,
        "docstring": docstring_summary,
        "decorators": decorators,
        "fields": fields,
        "methods": methods,
        "nested_classes": nested_classes,
        "start_line": node.lineno,
        "end_line": getattr(node, 'end_lineno', node.lineno)
    }

    return result


# =============================================================================
# Skeleton Generation
# =============================================================================

def generate_skeleton(
    tree: ast.Module,
    include_private: bool = False,
    include_line_numbers: bool = True
) -> str:
    """Generate skeleton text from parsed AST."""
    lines = []

    # Module docstring
    doc = ast.get_docstring(tree)
    if doc:
        summary = doc.strip().splitlines()[0][:100]
        lines.append(f'"""{summary}..."""')
        lines.append("")

    def format_decorators(decorators: List, prefix: str) -> List[str]:
        result = []
        for dec in decorators:
            if isinstance(dec, ast.Name):
                result.append(f"{prefix}@{dec.id}")
            elif isinstance(dec, ast.Attribute):
                result.append(f"{prefix}@{_get_name(dec)}")
            elif isinstance(dec, ast.Call):
                func_name = _get_name(dec.func)
                result.append(f"{prefix}@{func_name}(...)")
        return result

    def process_function(node, indent: int):
        prefix = "    " * indent
        lines.extend(format_decorators(node.decorator_list, prefix))

        is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""

        # Build argument string
        args = []
        defaults_offset = len(node.args.args) - len(node.args.defaults)

        for i, arg in enumerate(node.args.args):
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {_get_annotation(arg.annotation)}"
            default_idx = i - defaults_offset
            if 0 <= default_idx < len(node.args.defaults):
                arg_str += f" = {_get_default_repr(node.args.defaults[default_idx])}"
            args.append(arg_str)

        if node.args.vararg:
            vararg = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                vararg += f": {_get_annotation(node.args.vararg.annotation)}"
            args.append(vararg)

        if node.args.kwarg:
            kwarg = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                kwarg += f": {_get_annotation(node.args.kwarg.annotation)}"
            args.append(kwarg)

        ret = ""
        if node.returns:
            ret = f" -> {_get_annotation(node.returns)}"

        line_ref = f"  # L{node.lineno}-{getattr(node, 'end_lineno', node.lineno)}" if include_line_numbers else ""
        lines.append(f"{prefix}{is_async}def {node.name}({', '.join(args)}){ret}: ...{line_ref}")

        if (doc := ast.get_docstring(node)):
            summary = doc.strip().splitlines()[0][:80]
            lines.append(f'{prefix}    """{summary}..."""')

    def process_class(node: ast.ClassDef, indent: int):
        prefix = "    " * indent

        lines.extend(format_decorators(node.decorator_list, prefix))

        bases = [_get_name(b) for b in node.bases]
        base_str = f"({', '.join(bases)})" if bases else ""
        line_ref = f"  # L{node.lineno}-{getattr(node, 'end_lineno', node.lineno)}" if include_line_numbers else ""
        lines.append(f"{prefix}class {node.name}{base_str}:{line_ref}")

        if (doc := ast.get_docstring(node)):
            summary = doc.strip().splitlines()[0][:80]
            lines.append(f'{prefix}    """{summary}..."""')

        has_content = False

        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                field_name = child.target.id
                type_hint = _get_annotation(child.annotation)
                default = f" = {_get_constant_repr(child.value)}" if child.value else ""
                line_ref = f"  # L{child.lineno}" if include_line_numbers else ""
                lines.append(f"{prefix}    {field_name}: {type_hint}{default}{line_ref}")
                has_content = True

            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        val = _get_constant_repr(child.value)
                        line_ref = f"  # L{child.lineno}" if include_line_numbers else ""
                        lines.append(f"{prefix}    {target.id} = {val}{line_ref}")
                        has_content = True

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (include_private or not child.name.startswith('_') or
                    (child.name.startswith('__') and child.name.endswith('__'))):
                    process_function(child, indent + 1)
                    has_content = True

            elif isinstance(child, ast.ClassDef):
                process_class(child, indent + 1)
                has_content = True

        if not has_content:
            lines.append(f"{prefix}    pass")

        lines.append("")

    # Process top-level nodes
    for node in tree.body:
        # Global constants
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    val = _get_constant_repr(node.value)
                    line_ref = f"  # L{node.lineno}" if include_line_numbers else ""
                    lines.append(f'{target.id} = {val}{line_ref}')

        # Classes
        elif isinstance(node, ast.ClassDef):
            process_class(node, 0)

        # Module-level functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if include_private or not node.name.startswith('_'):
                process_function(node, 0)
                lines.append("")

    return "\n".join(lines)


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_file(
    filepath: str,
    include_private: bool = True,
    include_line_numbers: bool = True
) -> FileAnalysis:
    """
    Perform comprehensive single-pass AST analysis of a Python file.

    Args:
        filepath: Path to Python file
        include_private: Include private methods in skeleton
        include_line_numbers: Include line numbers in skeleton

    Returns:
        FileAnalysis object with all extracted information
    """
    result = FileAnalysis(filepath)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        result.parse_error = f"Syntax error: {e}"
        return result
    except Exception as e:
        result.parse_error = f"Parse error: {e}"
        return result

    result.line_count = source.count('\n') + 1
    result.original_tokens = len(source) // 4

    # Generate skeleton and count tokens
    skeleton = generate_skeleton(tree, include_private, include_line_numbers)
    result.skeleton_tokens = len(skeleton) // 4

    # Track all function names in this file for internal call detection
    all_function_names = set()

    # Process all nodes in a single walk
    for node in ast.walk(tree):
        # Classes
        if isinstance(node, ast.ClassDef) and node.col_offset == 0:
            class_info = _extract_class_info(node, include_line_numbers)
            result.classes.append(class_info)

            # Collect decorators
            for dec_name in class_info["decorators"]:
                result.decorators[dec_name] += 1

            # Collect method names
            for method in class_info["methods"]:
                all_function_names.add(f"{node.name}.{method['name']}")
                for dec_name in method["decorators"]:
                    result.decorators[dec_name] += 1

        # Module-level functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:  # Top-level only
                func_info = _extract_function_info(node, include_line_numbers)
                result.functions.append(func_info)
                all_function_names.add(node.name)

                # Collect decorators
                for dec_name in func_info["decorators"]:
                    result.decorators[dec_name] += 1

                # Track complexity
                result.total_cc += func_info["complexity"]
                if func_info["complexity"] > 3:
                    result.hotspots[node.name] = func_info["complexity"]

                # Track type coverage
                result.total_functions += 1
                if func_info["has_type_hints"]:
                    result.typed_functions += 1

            # Async tracking
            if isinstance(node, ast.AsyncFunctionDef):
                result.async_functions += 1
            else:
                result.sync_functions += 1

        # Global constants
        elif isinstance(node, ast.Assign) and node.col_offset == 0:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result.constants.append({
                        "name": target.id,
                        "value": _get_constant_repr(node.value),
                        "line": node.lineno
                    })

        # Async patterns
        elif isinstance(node, ast.AsyncFor):
            result.async_for_loops += 1
        elif isinstance(node, ast.AsyncWith):
            result.async_context_managers += 1

        # Function calls - detect side effects and internal calls
        elif isinstance(node, ast.Call):
            call_text = _get_call_text(node)

            # Side effect detection
            side_effect = _detect_side_effect(call_text)
            if side_effect:
                side_effect["line"] = node.lineno
                result.side_effects.append(side_effect)

            # Internal call tracking (calls to functions in this file)
            if call_text in all_function_names or any(
                call_text.endswith(f".{name}") for name in all_function_names
            ):
                result.internal_calls.append({
                    "call": call_text,
                    "line": node.lineno
                })

    # Calculate type coverage percentage
    if result.total_functions > 0:
        result.type_coverage = round(
            (result.typed_functions / result.total_functions) * 100, 1
        )

    return result


def analyze_codebase(
    files: List[str],
    include_private: bool = True,
    include_line_numbers: bool = True,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Analyze multiple Python files and aggregate results.

    Args:
        files: List of file paths to analyze
        include_private: Include private methods
        include_line_numbers: Include line numbers
        verbose: Print progress

    Returns:
        Dict with aggregated analysis results
    """
    results = {
        "files": {},
        "summary": {
            "total_files": len(files),
            "total_lines": 0,
            "total_tokens": 0,
            "total_classes": 0,
            "total_functions": 0,
            "typed_functions": 0,
            "type_coverage": 0.0,
            "total_cc": 0,
            "average_cc": 0.0
        },
        "all_classes": [],
        "all_functions": [],
        "hotspots": [],
        "decorators": defaultdict(int),
        "async_patterns": {
            "async_functions": 0,
            "sync_functions": 0,
            "async_for_loops": 0,
            "async_context_managers": 0
        },
        "side_effects": {
            "by_type": defaultdict(list),
            "by_file": {}
        }
    }

    function_count_for_avg = 0

    for i, filepath in enumerate(files):
        if verbose:
            print(f"  [{i+1}/{len(files)}] Analyzing {Path(filepath).name}...")

        analysis = analyze_file(filepath, include_private, include_line_numbers)
        results["files"][filepath] = analysis.to_dict()

        # Aggregate summaries
        results["summary"]["total_lines"] += analysis.line_count
        results["summary"]["total_tokens"] += analysis.original_tokens
        results["summary"]["total_classes"] += len(analysis.classes)
        results["summary"]["total_functions"] += len(analysis.functions)
        results["summary"]["typed_functions"] += analysis.typed_functions
        results["summary"]["total_cc"] += analysis.total_cc

        function_count_for_avg += len(analysis.functions)

        # Collect all classes and functions
        for cls in analysis.classes:
            cls["file"] = filepath
            results["all_classes"].append(cls)

        for func in analysis.functions:
            func["file"] = filepath
            results["all_functions"].append(func)

        # Collect hotspots
        for name, cc in analysis.hotspots.items():
            results["hotspots"].append({
                "file": filepath,
                "function": name,
                "complexity": cc
            })

        # Aggregate decorators
        for dec, count in analysis.decorators.items():
            results["decorators"][dec] += count

        # Aggregate async patterns
        results["async_patterns"]["async_functions"] += analysis.async_functions
        results["async_patterns"]["sync_functions"] += analysis.sync_functions
        results["async_patterns"]["async_for_loops"] += analysis.async_for_loops
        results["async_patterns"]["async_context_managers"] += analysis.async_context_managers

        # Aggregate side effects
        for se in analysis.side_effects:
            results["side_effects"]["by_type"][se["category"]].append({
                "file": filepath,
                "call": se["call"],
                "line": se["line"]
            })

        if analysis.side_effects:
            results["side_effects"]["by_file"][filepath] = analysis.side_effects

    # Calculate averages
    if function_count_for_avg > 0:
        results["summary"]["average_cc"] = round(
            results["summary"]["total_cc"] / function_count_for_avg, 2
        )

    if results["summary"]["total_functions"] > 0:
        results["summary"]["type_coverage"] = round(
            (results["summary"]["typed_functions"] / results["summary"]["total_functions"]) * 100, 1
        )

    # Sort hotspots by complexity
    results["hotspots"].sort(key=lambda x: x["complexity"], reverse=True)

    # Convert defaultdicts to regular dicts
    results["decorators"] = dict(results["decorators"])
    results["side_effects"]["by_type"] = dict(results["side_effects"]["by_type"])

    return results


# =============================================================================
# Convenience Functions
# =============================================================================

def get_skeleton(
    filepath: str,
    include_private: bool = False,
    include_line_numbers: bool = True
) -> Tuple[str, int, int]:
    """
    Extract skeleton from a Python file.

    Backwards-compatible with the original ast_utils.get_skeleton().

    Args:
        filepath: Path to Python file
        include_private: Include _private methods
        include_line_numbers: Include line numbers

    Returns:
        Tuple of (skeleton_text, original_tokens, skeleton_tokens)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"# Syntax error in {filepath}: {e}", 0, 0
    except Exception as e:
        return f"# Error parsing {filepath}: {e}", 0, 0

    original_tokens = len(source) // 4
    skeleton = generate_skeleton(tree, include_private, include_line_numbers)
    skeleton_tokens = len(skeleton) // 4

    return skeleton, original_tokens, skeleton_tokens


def parse_imports(filepath: str) -> Tuple[List[str], List[str]]:
    """
    Parse imports from a Python file.

    Returns:
        Tuple of (absolute_imports, relative_imports)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return [], []

    absolute_imports = []
    relative_imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0:
                prefix = "." * node.level
                relative_imports.append(f"{prefix}{module}")
            else:
                absolute_imports.append(module)

    return absolute_imports, relative_imports


def get_class_hierarchy(filepath: str) -> Dict[str, List[str]]:
    """
    Extract class inheritance hierarchy from a Python file.

    Returns:
        Dict mapping class names to their base classes
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return {}

    hierarchy = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [_get_name(base) for base in node.bases]
            hierarchy[node.name] = bases

    return hierarchy

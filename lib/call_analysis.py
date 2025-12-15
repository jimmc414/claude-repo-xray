"""
Repo X-Ray: Cross-Module Call Analysis (NEW - Codegraph Feature)

Analyzes function calls across the entire codebase:
- Cross-module call site detection
- Reverse call lookup ("Who calls this?")
- Most-called functions ranking
- Isolated functions detection

This module finds where functions are called ACROSS module boundaries,
not just within a single file (which ast_analysis handles).

Usage:
    from call_analysis import analyze_calls

    # Requires AST analysis results
    from ast_analysis import analyze_codebase
    ast_results = analyze_codebase(files)

    call_results = analyze_calls(files, ast_results)
"""

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# Call Site Detection
# =============================================================================

class CallVisitor(ast.NodeVisitor):
    """AST visitor that extracts all function calls with context."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.calls: List[Dict] = []
        self.current_function: Optional[str] = None
        self.current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node)

    def _visit_function(self, node):
        old_func = self.current_function
        if self.current_class:
            self.current_function = f"{self.current_class}.{node.name}"
        else:
            self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_func

    def visit_Call(self, node: ast.Call):
        call_info = self._extract_call_info(node)
        if call_info:
            self.calls.append(call_info)
        self.generic_visit(node)

    def _extract_call_info(self, node: ast.Call) -> Optional[Dict]:
        """Extract information about a function call."""
        call_name = None
        call_type = "unknown"

        if isinstance(node.func, ast.Name):
            # Simple call: func()
            call_name = node.func.id
            call_type = "function"

        elif isinstance(node.func, ast.Attribute):
            # Method/attribute call: obj.method()
            parts = self._get_attr_chain(node.func)
            if parts:
                call_name = ".".join(parts)
                call_type = "method" if len(parts) > 1 else "function"

        if not call_name:
            return None

        return {
            "call": call_name,
            "type": call_type,
            "line": node.lineno,
            "caller": self.current_function or "(module level)",
            "file": self.filepath
        }

    def _get_attr_chain(self, node) -> List[str]:
        """Get the chain of attributes: a.b.c -> ['a', 'b', 'c']"""
        parts = []
        current = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)
            return list(reversed(parts))

        return []


def extract_calls(filepath: str) -> List[Dict]:
    """Extract all function calls from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return []

    visitor = CallVisitor(filepath)
    visitor.visit(tree)
    return visitor.calls


# =============================================================================
# Known Functions Registry
# =============================================================================

def build_function_registry(ast_results: Dict[str, Any]) -> Dict[str, Dict]:
    """
    Build a registry of all known functions from AST analysis results.

    Returns:
        {
            "qualified_name": {
                "file": str,
                "name": str,
                "type": "function" | "method",
                "class": Optional[str],
                "start_line": int,
                "end_line": int
            }
        }
    """
    registry = {}

    for filepath, file_data in ast_results.get("files", {}).items():
        # Get module name from filepath
        module_name = Path(filepath).stem

        # Register top-level functions
        for func in file_data.get("functions", []):
            qualified_name = f"{module_name}.{func['name']}"
            registry[qualified_name] = {
                "file": filepath,
                "name": func["name"],
                "type": "function",
                "class": None,
                "start_line": func.get("start_line", 0),
                "end_line": func.get("end_line", 0)
            }
            # Also register by simple name
            registry[func["name"]] = registry[qualified_name]

        # Register class methods
        for cls in file_data.get("classes", []):
            for method in cls.get("methods", []):
                # Fully qualified: module.Class.method
                qualified_name = f"{module_name}.{cls['name']}.{method['name']}"
                method_data = {
                    "file": filepath,
                    "name": method["name"],
                    "type": "method",
                    "class": cls["name"],
                    "start_line": method.get("start_line", 0),
                    "end_line": method.get("end_line", 0)
                }
                registry[qualified_name] = method_data

                # Also register as Class.method
                class_method_name = f"{cls['name']}.{method['name']}"
                registry[class_method_name] = method_data

    return registry


# =============================================================================
# Cross-Module Call Analysis
# =============================================================================

def analyze_cross_module_calls(
    files: List[str],
    function_registry: Dict[str, Dict],
    root_dir: str
) -> Dict[str, Any]:
    """
    Find where functions are called across module boundaries.

    Returns:
        {
            "cross_module_calls": {
                "qualified_name": {
                    "call_count": int,
                    "calling_modules": int,
                    "call_sites": [{"file": str, "line": int, "caller": str}]
                }
            },
            "most_called": [{"function": str, "call_sites": int, "modules": int}],
            "most_callers": [{"function": str, "calls_made": int}],
            "isolated_functions": [str]  # Never called from outside their module
        }
    """
    # Collect all calls from all files
    all_calls = []
    for filepath in files:
        calls = extract_calls(filepath)
        all_calls.extend(calls)

    # Track cross-module calls
    cross_module_calls = defaultdict(lambda: {
        "call_count": 0,
        "calling_modules": set(),
        "call_sites": []
    })

    # Track who makes the most calls
    caller_counts = defaultdict(int)

    for call in all_calls:
        call_name = call["call"]
        caller_file = call["file"]
        caller_module = Path(caller_file).stem

        # Try to match against known functions
        matched_function = None

        # Try exact match first
        if call_name in function_registry:
            matched_function = call_name
        else:
            # Try with module prefix
            for known_name in function_registry:
                if known_name.endswith(f".{call_name}"):
                    matched_function = known_name
                    break

        if matched_function:
            func_info = function_registry[matched_function]
            target_file = func_info["file"]
            target_module = Path(target_file).stem

            # Only count cross-module calls
            if caller_module != target_module:
                entry = cross_module_calls[matched_function]
                entry["call_count"] += 1
                entry["calling_modules"].add(caller_module)
                entry["call_sites"].append({
                    "file": caller_file,
                    "line": call["line"],
                    "caller": call["caller"]
                })

        # Track caller activity
        if call["caller"] != "(module level)":
            caller_key = f"{caller_module}.{call['caller']}"
            caller_counts[caller_key] += 1

    # Convert to output format
    cross_module_output = {}
    for func_name, data in cross_module_calls.items():
        cross_module_output[func_name] = {
            "call_count": data["call_count"],
            "calling_modules": len(data["calling_modules"]),
            "call_sites": data["call_sites"][:10]  # Limit to 10 examples
        }

    # Find most called functions
    most_called = sorted(
        [
            {
                "function": name,
                "call_sites": data["call_count"],
                "modules": len(data["calling_modules"])
            }
            for name, data in cross_module_calls.items()
        ],
        key=lambda x: x["call_sites"],
        reverse=True
    )[:15]

    # Find functions that make the most calls
    most_callers = sorted(
        [
            {"function": name, "calls_made": count}
            for name, count in caller_counts.items()
        ],
        key=lambda x: x["calls_made"],
        reverse=True
    )[:15]

    # Find isolated functions (never called from outside their module)
    called_functions = set(cross_module_calls.keys())
    all_functions = set(function_registry.keys())
    isolated = [f for f in all_functions if f not in called_functions]

    return {
        "cross_module_calls": cross_module_output,
        "most_called": most_called,
        "most_callers": most_callers,
        "isolated_functions": isolated[:20]  # Top 20
    }


# =============================================================================
# Reverse Call Lookup
# =============================================================================

def build_reverse_lookup(cross_module_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a reverse lookup: for any function, find all its callers.

    This is derived from cross_module_calls but organized differently.

    Returns:
        {
            "qualified_name": {
                "callers": [{"function": str, "file": str, "line": int}],
                "caller_count": int,
                "module_count": int,
                "impact_rating": "low" | "medium" | "high"
            }
        }
    """
    reverse_lookup = {}

    for func_name, data in cross_module_results.get("cross_module_calls", {}).items():
        callers = [
            {
                "function": site["caller"],
                "file": site["file"],
                "line": site["line"]
            }
            for site in data["call_sites"]
        ]

        caller_count = data["call_count"]
        module_count = data["calling_modules"]

        # Determine impact rating
        if module_count >= 5 or caller_count >= 10:
            impact = "high"
        elif module_count >= 2 or caller_count >= 5:
            impact = "medium"
        else:
            impact = "low"

        reverse_lookup[func_name] = {
            "callers": callers,
            "caller_count": caller_count,
            "module_count": module_count,
            "impact_rating": impact
        }

    return reverse_lookup


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_calls(
    files: List[str],
    ast_results: Dict[str, Any],
    root_dir: str = ".",
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Perform comprehensive cross-module call analysis.

    Args:
        files: List of Python file paths
        ast_results: Results from ast_analysis.analyze_codebase()
        root_dir: Root directory of the project
        verbose: Print progress

    Returns:
        Complete call analysis results
    """
    import sys

    if verbose:
        print("Analyzing cross-module calls...", file=sys.stderr)

    # Build function registry from AST results
    if verbose:
        print("  Building function registry...", file=sys.stderr)
    function_registry = build_function_registry(ast_results)

    if verbose:
        print(f"  Registered {len(function_registry)} functions", file=sys.stderr)

    # Analyze cross-module calls
    if verbose:
        print("  Detecting cross-module calls...", file=sys.stderr)
    cross_module_results = analyze_cross_module_calls(files, function_registry, root_dir)

    # Build reverse lookup
    if verbose:
        print("  Building reverse lookup...", file=sys.stderr)
    reverse_lookup = build_reverse_lookup(cross_module_results)

    # Identify high-impact functions (called from many places)
    high_impact = [
        {"function": name, "impact": data["impact_rating"], "callers": data["caller_count"]}
        for name, data in reverse_lookup.items()
        if data["impact_rating"] == "high"
    ]

    return {
        "cross_module": cross_module_results["cross_module_calls"],
        "reverse_lookup": reverse_lookup,
        "most_called": cross_module_results["most_called"],
        "most_callers": cross_module_results["most_callers"],
        "isolated_functions": cross_module_results["isolated_functions"],
        "high_impact": sorted(high_impact, key=lambda x: x["callers"], reverse=True),
        "summary": {
            "total_cross_module_calls": sum(
                d["call_count"] for d in cross_module_results["cross_module_calls"].values()
            ),
            "functions_with_cross_module_callers": len(cross_module_results["cross_module_calls"]),
            "high_impact_functions": len(high_impact),
            "isolated_functions": len(cross_module_results["isolated_functions"])
        }
    }

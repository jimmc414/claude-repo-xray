"""
Repo X-Ray: Import Analysis Module

Analyzes import relationships, dependencies, and module structure:
- Import graph building with alias resolution
- Dependency distance calculation (NEW - codegraph feature)
- Import alias tracking (NEW - codegraph feature)
- Orphan detection
- Circular dependency detection
- Architectural layer classification

Usage:
    from import_analysis import analyze_imports

    result = analyze_imports("/path/to/project")
"""

import ast
import json
import os
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# Configuration
# =============================================================================

# Known external/stdlib packages to exclude from root detection
EXTERNAL_PACKAGES = {
    "os", "sys", "re", "json", "typing", "pathlib", "collections",
    "datetime", "asyncio", "logging", "argparse", "dataclasses",
    "abc", "enum", "functools", "itertools", "copy", "time",
    "math", "random", "hashlib", "base64", "io", "contextlib",
    "subprocess", "shutil", "tempfile", "glob", "fnmatch",
    "unittest", "traceback", "warnings", "inspect", "ast",
    "concurrent", "multiprocessing", "threading", "queue",
    "pytest", "numpy", "pandas", "requests", "pydantic", "fastapi",
    "flask", "django", "sqlalchemy", "redis", "boto3", "aiohttp",
    "click", "typer", "rich", "httpx", "uvicorn", "yaml", "toml"
}

# Entry point patterns (not orphans)
ENTRY_POINT_PATTERNS = {
    "main.py", "__main__.py", "cli.py", "app.py", "wsgi.py", "asgi.py",
    "setup.py", "manage.py", "fabfile.py", "conftest.py"
}

# Layer detection keywords
ORCHESTRATION_KEYWORDS = ["manager", "orchestrator", "coordinator", "workflow", "pipeline", "factory", "runner"]
FOUNDATION_KEYWORDS = ["util", "utils", "base", "common", "helper", "abstract", "config", "constants"]


# =============================================================================
# Import Parsing with Alias Tracking
# =============================================================================

def parse_imports_with_aliases(filepath: str) -> Dict[str, Any]:
    """
    Parse imports from a Python file with alias tracking.

    Returns:
        {
            "imports": ["pandas", "numpy", ...],
            "aliases": {"pd": "pandas", "np": "numpy"},
            "from_imports": {"os.path": ["join", "exists"]},
            "relative_imports": [".utils", "..core"],
            "all_modules": ["pandas", "numpy", "os.path", ...]
        }
    """
    result = {
        "imports": [],
        "aliases": {},
        "from_imports": defaultdict(list),
        "relative_imports": [],
        "all_modules": []
    }

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)
                result["all_modules"].append(alias.name)
                if alias.asname:
                    result["aliases"][alias.asname] = alias.name

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            if node.level > 0:
                # Relative import
                prefix = "." * node.level
                result["relative_imports"].append(f"{prefix}{module}")
            else:
                # Absolute import
                result["imports"].append(module)
                result["all_modules"].append(module)

            # Track what's imported from the module
            for alias in node.names:
                result["from_imports"][module].append(alias.name)
                if alias.asname:
                    if module:
                        result["aliases"][alias.asname] = f"{module}.{alias.name}"
                    else:
                        result["aliases"][alias.asname] = alias.name

    # Convert defaultdict to regular dict
    result["from_imports"] = dict(result["from_imports"])

    return result


def parse_imports(filepath: str) -> Tuple[List[str], List[str]]:
    """
    Parse imports from a Python file (legacy interface).

    Returns:
        Tuple of (absolute_imports, relative_imports)
    """
    result = parse_imports_with_aliases(filepath)
    return result["imports"], result["relative_imports"]


# =============================================================================
# Module Path Utilities
# =============================================================================

def module_path_to_name(filepath: str, root_dir: str) -> str:
    """Convert file path to module name."""
    rel_path = os.path.relpath(filepath, root_dir)
    module = rel_path.replace(os.sep, ".").replace("/", ".")
    if module.endswith(".py"):
        module = module[:-3]
    if module.endswith(".__init__"):
        module = module[:-9]
    return module


def resolve_relative_import(importing_module: str, relative_import: str) -> str:
    """Resolve a relative import to absolute module name."""
    level = 0
    while relative_import.startswith("."):
        level += 1
        relative_import = relative_import[1:]

    parts = importing_module.split(".")
    if level > len(parts):
        return relative_import

    base = ".".join(parts[:-level]) if level > 0 else importing_module
    if relative_import:
        return f"{base}.{relative_import}" if base else relative_import
    return base


# =============================================================================
# Root Package Detection
# =============================================================================

def auto_detect_root_package(
    directory: str,
    ignore_dirs: Optional[Set[str]] = None
) -> Optional[str]:
    """
    Auto-detect the root package name by analyzing import patterns.

    Strategy:
    1. Find directories with __init__.py (potential packages)
    2. Scan all .py files for 'from X import' statements
    3. Count first-level imports that match potential packages
    4. Return most common match
    """
    if ignore_dirs is None:
        ignore_dirs = {"__pycache__", ".git", "tests", "venv", ".venv"}

    # Find potential packages
    potential_packages = set()
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path) and not item.startswith("."):
                try:
                    if (Path(item_path) / "__init__.py").exists():
                        potential_packages.add(item)
                except (PermissionError, OSError):
                    pass
    except Exception:
        return None

    if not potential_packages:
        return None

    # Count imports
    import_counts: Counter = Counter()

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for filename in files:
            if not filename.endswith('.py'):
                continue

            filepath = os.path.join(root, filename)
            abs_imports, _ = parse_imports(filepath)

            for imp in abs_imports:
                first = imp.split(".")[0]
                if first in potential_packages:
                    import_counts[first] += 1

    if import_counts:
        return import_counts.most_common(1)[0][0]

    # Fallback: return largest potential package
    if potential_packages:
        pkg_sizes = {}
        for pkg in potential_packages:
            pkg_path = Path(directory) / pkg
            try:
                pkg_sizes[pkg] = sum(1 for _ in pkg_path.rglob("*.py"))
            except Exception:
                pkg_sizes[pkg] = 0
        if pkg_sizes:
            return max(pkg_sizes, key=pkg_sizes.get)

    return None


# =============================================================================
# Dependency Graph Building
# =============================================================================

def build_import_graph(
    files: List[str],
    root_dir: str,
    root_package: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a dependency graph for Python files.

    Args:
        files: List of Python file paths
        root_dir: Root directory of the project
        root_package: Optional root package name

    Returns:
        {
            "modules": {module_name: {"file": path, "imports": [...], "imported_by": [...]}},
            "internal_edges": [(from, to), ...],
            "external_deps": {module: [external_imports]},
            "circular": [(a, b), ...],
            "aliases": {alias: module}  # NEW: Global alias map
        }
    """
    # First pass: discover all modules
    modules = {}
    global_aliases = {}

    for filepath in files:
        module_name = module_path_to_name(filepath, root_dir)

        while module_name.startswith('.'):
            module_name = module_name[1:]

        if root_package and not module_name.startswith(root_package):
            module_name = f"{root_package}.{module_name}"

        modules[module_name] = {
            "file": filepath,
            "imports": [],
            "imported_by": []
        }

    # Build lookup by leaf name
    leaf_to_modules = defaultdict(list)
    for mod_name in modules:
        leaf = mod_name.split(".")[-1]
        leaf_to_modules[leaf].append(mod_name)

    # Second pass: analyze imports
    internal_edges = []
    external_deps = defaultdict(set)

    for module_name, info in modules.items():
        import_data = parse_imports_with_aliases(info["file"])

        # Collect aliases
        for alias, full_name in import_data["aliases"].items():
            global_aliases[alias] = full_name

        # Process absolute imports
        for imp in import_data["imports"]:
            base = imp.split(".")[0]
            target = None

            # Try to find matching internal module
            if imp in modules:
                target = imp
            else:
                for known_module in modules:
                    if known_module.startswith(f"{imp}.") or imp.startswith(f"{known_module}."):
                        target = known_module
                        break

            if not target and base in leaf_to_modules:
                candidates = leaf_to_modules[base]
                if len(candidates) == 1:
                    target = candidates[0]
                elif candidates:
                    module_dir = os.path.dirname(info["file"])
                    for cand in candidates:
                        if os.path.dirname(modules[cand]["file"]) == module_dir:
                            target = cand
                            break
                    if not target:
                        target = candidates[0]

            if target and target != module_name:
                if target not in info["imports"]:
                    info["imports"].append(target)
                    modules[target]["imported_by"].append(module_name)
                    internal_edges.append((module_name, target))
            elif not target and base not in EXTERNAL_PACKAGES:
                external_deps[module_name].add(base)

        # Process relative imports
        for rel_imp in import_data["relative_imports"]:
            resolved = resolve_relative_import(module_name, rel_imp)
            target = resolved
            while target and target not in modules:
                target = ".".join(target.split(".")[:-1])

            if target and target != module_name:
                if target not in info["imports"]:
                    info["imports"].append(target)
                    modules[target]["imported_by"].append(module_name)
                    internal_edges.append((module_name, target))

    # Find circular dependencies
    circular = []
    seen_pairs = set()
    for a, b in internal_edges:
        if (b, a) in seen_pairs:
            circular.append((min(a, b), max(a, b)))
        seen_pairs.add((a, b))
    circular = list(set(circular))

    return {
        "modules": modules,
        "internal_edges": internal_edges,
        "external_deps": {k: list(v) for k, v in external_deps.items()},
        "circular": circular,
        "aliases": global_aliases
    }


# =============================================================================
# Dependency Distance Calculation (NEW - Codegraph Feature)
# =============================================================================

def calculate_dependency_distance(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate dependency distance (hops) between modules using BFS.

    Returns:
        {
            "max_depth": int,
            "avg_depth": float,
            "distances": {(from, to): {"hops": int, "path": [modules]}},
            "tightly_coupled": [{"file_a": str, "file_b": str, "bidirectional": bool}],
            "hub_modules": [{"module": str, "connections": int}]  # Most connected
        }
    """
    modules = graph["modules"]

    if not modules:
        return {
            "max_depth": 0,
            "avg_depth": 0.0,
            "distances": {},
            "tightly_coupled": [],
            "hub_modules": []
        }

    # Build adjacency list
    adjacency = defaultdict(set)
    for module_name, info in modules.items():
        for imported in info["imports"]:
            adjacency[module_name].add(imported)

    # Calculate distances using BFS from each module
    all_distances = {}
    all_depths = []

    for start_module in modules:
        distances = {start_module: 0}
        queue = deque([start_module])
        paths = {start_module: [start_module]}

        while queue:
            current = queue.popleft()
            current_dist = distances[current]

            for neighbor in adjacency[current]:
                if neighbor not in distances:
                    distances[neighbor] = current_dist + 1
                    paths[neighbor] = paths[current] + [neighbor]
                    queue.append(neighbor)

        # Store distances from this module
        for end_module, dist in distances.items():
            if dist > 0:
                all_distances[(start_module, end_module)] = {
                    "hops": dist,
                    "path": paths[end_module]
                }
                all_depths.append(dist)

    # Find tightly coupled modules (bidirectional with short distance)
    tightly_coupled = []
    for (a, b), info in all_distances.items():
        if info["hops"] <= 2 and (b, a) in all_distances:
            if a < b:  # Avoid duplicates
                tightly_coupled.append({
                    "file_a": a,
                    "file_b": b,
                    "bidirectional": True,
                    "distance": info["hops"]
                })

    # Find hub modules (most connections)
    connection_counts = Counter()
    for module_name, info in modules.items():
        total_connections = len(info["imports"]) + len(info["imported_by"])
        connection_counts[module_name] = total_connections

    hub_modules = [
        {"module": mod, "connections": count}
        for mod, count in connection_counts.most_common(10)
        if count > 0
    ]

    return {
        "max_depth": max(all_depths) if all_depths else 0,
        "avg_depth": round(sum(all_depths) / len(all_depths), 2) if all_depths else 0.0,
        "distances": all_distances,
        "tightly_coupled": tightly_coupled[:10],  # Top 10
        "hub_modules": hub_modules
    }


# =============================================================================
# Alias Usage Analysis (NEW - Codegraph Feature)
# =============================================================================

def analyze_alias_usage(files: List[str]) -> Dict[str, Any]:
    """
    Analyze import alias usage across the codebase.

    Returns:
        {
            "aliases": [{"alias": "pd", "module": "pandas", "usage_count": 47, "files": [...]}],
            "most_used": [{"alias": str, "count": int}],
            "common_patterns": {"pd": "pandas", "np": "numpy", ...}
        }
    """
    alias_usage = defaultdict(lambda: {"module": None, "files": [], "count": 0})

    for filepath in files:
        import_data = parse_imports_with_aliases(filepath)

        for alias, module in import_data["aliases"].items():
            alias_usage[alias]["module"] = module
            alias_usage[alias]["files"].append(filepath)
            alias_usage[alias]["count"] += 1

    # Convert to list and sort by usage
    aliases = [
        {
            "alias": alias,
            "module": data["module"],
            "usage_count": data["count"],
            "files": data["files"]
        }
        for alias, data in alias_usage.items()
    ]
    aliases.sort(key=lambda x: x["usage_count"], reverse=True)

    # Find common patterns
    common_patterns = {
        item["alias"]: item["module"]
        for item in aliases
        if item["usage_count"] >= 2
    }

    return {
        "aliases": aliases[:20],  # Top 20
        "most_used": [{"alias": a["alias"], "count": a["usage_count"]} for a in aliases[:10]],
        "common_patterns": common_patterns
    }


# =============================================================================
# Architectural Layer Detection
# =============================================================================

def identify_layers(graph: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Identify architectural layers based on import patterns and naming conventions.
    """
    modules = graph["modules"]

    layers = {
        "foundation": [],
        "core": [],
        "orchestration": [],
        "leaf": []
    }

    for name, info in modules.items():
        imported_by_count = len(info["imported_by"])
        imports_count = len(info["imports"])
        ratio = imported_by_count / (imports_count + 1)

        module_lower = name.lower()

        if any(kw in module_lower for kw in ORCHESTRATION_KEYWORDS):
            layers["orchestration"].append(name)
        elif any(kw in module_lower for kw in FOUNDATION_KEYWORDS):
            layers["foundation"].append(name)
        elif imported_by_count == 0 and imports_count == 0:
            layers["leaf"].append(name)
        elif ratio > 2:
            layers["foundation"].append(name)
        elif ratio < 0.5 and imports_count > 2:
            layers["orchestration"].append(name)
        else:
            layers["core"].append(name)

    # Sort by import count within each layer
    for layer in layers:
        layers[layer].sort(
            key=lambda x: len(modules.get(x, {}).get("imported_by", [])),
            reverse=True
        )

    return layers


# =============================================================================
# Orphan Detection
# =============================================================================

def is_entry_point(filepath: str) -> bool:
    """Check if file is likely an entry point (not an orphan)."""
    filename = os.path.basename(filepath)

    if filename in ENTRY_POINT_PATTERNS:
        return True
    if filename.startswith("test_"):
        return True
    if filename.endswith("_test.py"):
        return True

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return 'if __name__ ==' in content or "if __name__==" in content
    except Exception:
        return False


def find_orphans(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find files with zero importers that aren't entry points."""
    modules = graph["modules"]
    orphans = []

    for name, info in modules.items():
        if len(info["imported_by"]) == 0:
            filepath = info["file"]
            if is_entry_point(filepath):
                continue

            filename = os.path.basename(filepath).lower()
            confidence = 0.9

            if "script" in filepath.lower():
                confidence = 0.6
            elif any(kw in filename for kw in ["deprecated", "legacy", "old"]):
                confidence = 0.95
            elif any(kw in filename for kw in ["util", "helper"]):
                confidence = 0.7

            orphans.append({
                "file": filepath,
                "module": name,
                "confidence": confidence
            })

    return sorted(orphans, key=lambda x: x["confidence"], reverse=True)


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_imports(
    files: List[str],
    root_dir: str,
    root_package: Optional[str] = None,
    auto_detect: bool = True,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Perform comprehensive import analysis.

    Args:
        files: List of Python file paths
        root_dir: Root directory of the project
        root_package: Optional root package name
        auto_detect: Auto-detect root package if not provided
        verbose: Print progress

    Returns:
        Complete import analysis results
    """
    if verbose:
        print("Analyzing imports...", file=sys.stderr)

    # Auto-detect root package if needed
    if root_package is None and auto_detect:
        root_package = auto_detect_root_package(root_dir)
        if verbose and root_package:
            print(f"  Auto-detected root package: {root_package}", file=sys.stderr)

    # Build import graph
    if verbose:
        print("  Building import graph...", file=sys.stderr)
    graph = build_import_graph(files, root_dir, root_package)

    # Calculate dependency distances
    if verbose:
        print("  Calculating dependency distances...", file=sys.stderr)
    distances = calculate_dependency_distance(graph)

    # Analyze alias usage
    if verbose:
        print("  Analyzing alias usage...", file=sys.stderr)
    alias_analysis = analyze_alias_usage(files)

    # Identify layers
    layers = identify_layers(graph)

    # Find orphans
    orphans = find_orphans(graph)

    # Collect all external dependencies
    all_external = set()
    for deps in graph["external_deps"].values():
        all_external.update(deps)

    return {
        "graph": {
            module_name: {
                "imports": info["imports"],
                "imported_by": info["imported_by"]
            }
            for module_name, info in graph["modules"].items()
        },
        "layers": layers,
        "aliases": alias_analysis["aliases"],
        "alias_patterns": alias_analysis["common_patterns"],
        "orphans": orphans,
        "circular": graph["circular"],
        "external_deps": sorted(list(all_external)),
        "distances": {
            "max_depth": distances["max_depth"],
            "avg_depth": distances["avg_depth"],
            "tightly_coupled": distances["tightly_coupled"],
            "hub_modules": distances["hub_modules"]
        },
        "summary": {
            "total_modules": len(graph["modules"]),
            "internal_edges": len(graph["internal_edges"]),
            "circular_count": len(graph["circular"]),
            "orphan_count": len(orphans),
            "external_deps_count": len(all_external)
        }
    }

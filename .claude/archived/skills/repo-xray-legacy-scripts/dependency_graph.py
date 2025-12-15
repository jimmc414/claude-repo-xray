#!/usr/bin/env python3
"""
Repo X-Ray Dependency Graph Generator

Analyzes import relationships between Python modules.
Identifies core modules, circular dependencies, and architectural layers.
Supports auto-detection of root package from import patterns.

Usage:
    python dependency_graph.py [directory] [options]

Examples:
    python dependency_graph.py src/
    python dependency_graph.py src/ --root mypackage
    python dependency_graph.py src/ --focus api
    python dependency_graph.py src/ --json
    python dependency_graph.py src/ --mermaid
"""

import argparse
import ast
import json
import os
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Exports for programmatic use
__all__ = [
    'build_dependency_graph',
    'identify_layers',
    'generate_mermaid',
    'find_orphans',
    'calculate_impact',
    'auto_detect_root_package',
    'detect_source_root',
]


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


# Find the skill root directory
SCRIPT_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = SKILL_ROOT / "configs"


def load_ignore_patterns() -> Set[str]:
    """Load directory ignore patterns from config."""
    config_path = CONFIG_DIR / "ignore_patterns.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        return set(config.get("directories", []))
    return {"__pycache__", ".git", "tests"}


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


def module_path_to_name(filepath: str, root_dir: str) -> str:
    """Convert file path to module name."""
    rel_path = os.path.relpath(filepath, root_dir)
    # Remove .py extension and convert path separators
    module = rel_path.replace(os.sep, ".").replace("/", ".")
    if module.endswith(".py"):
        module = module[:-3]
    if module.endswith(".__init__"):
        module = module[:-9]
    return module


def resolve_relative_import(
    importing_module: str,
    relative_import: str
) -> str:
    """Resolve a relative import to absolute module name."""
    # Count leading dots
    level = 0
    while relative_import.startswith("."):
        level += 1
        relative_import = relative_import[1:]

    # Go up 'level' packages
    parts = importing_module.split(".")
    if level > len(parts):
        return relative_import  # Can't resolve

    base = ".".join(parts[:-level]) if level > 0 else importing_module
    if relative_import:
        return f"{base}.{relative_import}" if base else relative_import
    return base


def auto_detect_root_package(directory: str) -> Optional[str]:
    """
    Auto-detect the root package name by analyzing import patterns.

    Strategy:
    1. Find directories with __init__.py (potential packages)
    2. Scan all .py files for 'from X import' statements
    3. Count first-level imports that match potential packages
    4. Return most common match

    Returns:
        Package name or None if cannot determine
    """
    ignore_dirs = load_ignore_patterns()

    # Find potential packages (directories with __init__.py)
    potential_packages = set()
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path) and not item.startswith("."):
                try:
                    if (Path(item_path) / "__init__.py").exists():
                        potential_packages.add(item)
                except (PermissionError, OSError):
                    # Skip directories we can't access
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

    # Fallback: return largest potential package by file count
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


def detect_source_root(directory: str) -> Optional[str]:
    """
    Detect the logical source root for Python files.

    For projects where code is in nested directories (like .claude/skills/repo-xray/scripts/),
    this finds the deepest common directory containing Python files that represents
    the logical package boundary.

    Returns:
        Path to the detected source root, or None if unclear
    """
    ignore_dirs = load_ignore_patterns()
    directory = os.path.abspath(directory)

    # Collect all directories containing Python files
    py_dirs = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        py_files = [f for f in files if f.endswith('.py')]
        if py_files:
            py_dirs.append((root, len(py_files)))

    if not py_dirs:
        return None

    # If all Python files are in one directory tree, find the root of that tree
    if len(py_dirs) == 1:
        return py_dirs[0][0]

    # Find the deepest common parent that contains Python files
    # Prefer directories with more Python files
    py_dirs.sort(key=lambda x: (-x[1], -len(x[0])))  # Most files, then deepest

    # Check if most Python files are in a nested structure
    # (like .claude/skills/repo-xray/scripts/)
    top_dir = py_dirs[0][0]
    rel_path = os.path.relpath(top_dir, directory)

    # If the top directory is deeply nested and contains sibling imports pattern
    if rel_path != '.' and len(rel_path.split(os.sep)) >= 2:
        # Check for sibling import patterns (sys.path manipulation)
        for py_dir, _ in py_dirs:
            for py_file in Path(py_dir).glob('*.py'):
                try:
                    content = py_file.read_text(encoding='utf-8')
                    if 'sys.path.insert' in content or 'sys.path.append' in content:
                        # This directory uses sibling imports, use it as source root
                        return str(py_dir)
                except Exception:
                    pass

    # Find common ancestor of all Python directories
    if len(py_dirs) > 1:
        paths = [Path(d[0]) for d in py_dirs]
        common_parts = list(paths[0].parts)
        for p in paths[1:]:
            new_common = []
            for i, (a, b) in enumerate(zip(common_parts, p.parts)):
                if a == b:
                    new_common.append(a)
                else:
                    break
            common_parts = new_common

        if common_parts:
            common_path = str(Path(*common_parts))
            if common_path != directory:
                return common_path

    return None


def build_dependency_graph(
    directory: str,
    root_package: Optional[str] = None,
    auto_detect: bool = True,
    source_dir: Optional[str] = None
) -> Dict:
    """
    Build a dependency graph for all Python files.

    Args:
        directory: Directory to analyze
        root_package: Root package name (e.g., 'mypackage')
        auto_detect: If True and root_package is None, auto-detect
        source_dir: Override source root directory for module name generation

    Returns dict with:
    {
        "modules": {module: {"file": path, "imports": [...], "imported_by": [...]}},
        "internal_edges": [(from, to), ...],
        "external_deps": {module: [external_imports]},
        "circular": [(a, b), ...]
    }
    """
    # Auto-detect root package if not provided
    if root_package is None and auto_detect:
        root_package = auto_detect_root_package(directory)
        if root_package:
            print(f"  Auto-detected root package: {root_package}", file=sys.stderr)

    # Detect source root for nested project structures
    # Only use source root detection when no root package was found
    # (indicates non-standard project structure like code in hidden directories)
    if source_dir is None and root_package is None:
        source_dir = detect_source_root(directory)
        if source_dir and source_dir != directory:
            print(f"  Detected source root: {source_dir}", file=sys.stderr)

    # Use detected source_dir or fall back to directory
    module_base_dir = source_dir if source_dir else directory

    ignore_dirs = load_ignore_patterns()

    # First pass: discover all modules
    modules = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for filename in files:
            if not filename.endswith('.py'):
                continue

            filepath = os.path.join(root, filename)

            # Use source_dir as base for module names if within it
            if source_dir and filepath.startswith(source_dir):
                module_name = module_path_to_name(filepath, source_dir)
            else:
                module_name = module_path_to_name(filepath, module_base_dir)

            # Clean up module names that start with dots
            while module_name.startswith('.'):
                module_name = module_name[1:]

            if root_package and not module_name.startswith(root_package):
                module_name = f"{root_package}.{module_name}"

            modules[module_name] = {
                "file": filepath,
                "imports": [],
                "imported_by": []
            }

    # Build a lookup for matching imports by leaf name (for sibling imports)
    leaf_to_modules = defaultdict(list)
    for mod_name in modules:
        leaf = mod_name.split(".")[-1]
        leaf_to_modules[leaf].append(mod_name)

    # Second pass: analyze imports
    internal_edges = []
    external_deps = defaultdict(set)

    for module_name, info in modules.items():
        abs_imports, rel_imports = parse_imports(info["file"])

        # Process absolute imports
        for imp in abs_imports:
            # Get base module (first component)
            base = imp.split(".")[0]

            # Check if it's an internal import - try multiple matching strategies
            target = None

            # Strategy 1: Exact match
            if imp in modules:
                target = imp

            # Strategy 2: Match by prefix (import is a parent of a known module)
            if not target:
                for known_module in modules:
                    if known_module.startswith(f"{imp}."):
                        target = known_module
                        break

            # Strategy 3: Known module is prefix of import
            if not target:
                for known_module in modules:
                    if imp.startswith(f"{known_module}."):
                        target = known_module
                        break

            # Strategy 4: Match by leaf name (for sibling imports like "from mapper import ...")
            if not target and base in leaf_to_modules:
                candidates = leaf_to_modules[base]
                if len(candidates) == 1:
                    target = candidates[0]
                elif candidates:
                    # Multiple matches - prefer one in same directory
                    module_dir = os.path.dirname(info["file"])
                    for cand in candidates:
                        cand_file = modules[cand]["file"]
                        if os.path.dirname(cand_file) == module_dir:
                            target = cand
                            break
                    if not target:
                        target = candidates[0]  # Fall back to first

            if target and target != module_name:
                if target not in info["imports"]:
                    info["imports"].append(target)
                    modules[target]["imported_by"].append(module_name)
                    internal_edges.append((module_name, target))
            elif not target and base not in EXTERNAL_PACKAGES:
                external_deps[module_name].add(base)

        # Process relative imports
        for rel_imp in rel_imports:
            resolved = resolve_relative_import(module_name, rel_imp)
            # Find matching module
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
        "circular": circular
    }


def identify_layers(graph: Dict) -> Dict[str, List[str]]:
    """
    Identify architectural layers based on import patterns AND naming conventions.

    Modules that are imported by many others = core/foundation
    Modules that import many others = orchestration/high-level
    Keywords in module names provide additional hints for layer assignment.
    """
    modules = graph["modules"]

    # Keyword patterns for layer hints
    ORCHESTRATION_KEYWORDS = ["manager", "orchestrator", "coordinator", "workflow", "pipeline", "factory", "runner"]
    FOUNDATION_KEYWORDS = ["util", "utils", "base", "common", "helper", "abstract", "config", "constants"]

    # Score modules by import patterns
    scores = {}
    for name, info in modules.items():
        imported_by_count = len(info["imported_by"])
        imports_count = len(info["imports"])

        # High imported_by, low imports = foundation
        # Low imported_by, high imports = orchestration
        scores[name] = {
            "imported_by": imported_by_count,
            "imports": imports_count,
            "ratio": imported_by_count / (imports_count + 1)
        }

    # Categorize with keyword hints
    layers = {
        "foundation": [],  # Imported by many, imports few
        "core": [],        # Balance of both
        "orchestration": [],  # Imports many, imported by few
        "leaf": []         # Little interaction
    }

    for name, score in scores.items():
        module_lower = name.lower()

        # Check keyword hints first
        if any(kw in module_lower for kw in ORCHESTRATION_KEYWORDS):
            layers["orchestration"].append(name)
        elif any(kw in module_lower for kw in FOUNDATION_KEYWORDS):
            layers["foundation"].append(name)
        # Then use import-based scoring
        elif score["imported_by"] == 0 and score["imports"] == 0:
            layers["leaf"].append(name)
        elif score["ratio"] > 2:
            layers["foundation"].append(name)
        elif score["ratio"] < 0.5 and score["imports"] > 2:
            layers["orchestration"].append(name)
        else:
            layers["core"].append(name)

    # Sort by import count within each layer
    for layer in layers:
        layers[layer].sort(key=lambda x: scores[x]["imported_by"], reverse=True)

    return layers


def generate_mermaid(graph: Dict, focus: Optional[str] = None) -> str:
    """Generate a Mermaid.js graph diagram."""
    layers = identify_layers(graph)
    modules = graph["modules"]

    lines = ["graph TD"]

    # Add subgraphs for layers
    for layer_name in ["orchestration", "core", "foundation"]:
        layer_modules = layers.get(layer_name, [])
        if not layer_modules:
            continue

        # Filter by focus if specified
        if focus:
            layer_modules = [m for m in layer_modules if focus.lower() in m.lower()]

        if not layer_modules:
            continue

        lines.append(f"    subgraph {layer_name.upper()}")
        for mod in layer_modules[:10]:  # Limit to top 10 per layer
            # Shorten module name for display
            short_name = mod.split(".")[-1]
            safe_id = mod.replace(".", "_")
            lines.append(f"        {safe_id}[{short_name}]")
        lines.append("    end")

    # Add edges for focused modules or orchestration layer
    edges_added = set()
    target_modules = []

    if focus:
        target_modules = [m for m in modules if focus.lower() in m.lower()]
    else:
        target_modules = layers.get("orchestration", [])[:5]

    for mod in target_modules:
        info = modules.get(mod, {})
        mod_id = mod.replace(".", "_")

        for imp in info.get("imports", [])[:5]:  # Limit edges
            imp_id = imp.replace(".", "_")
            edge = (mod_id, imp_id)
            if edge not in edges_added:
                lines.append(f"    {mod_id} --> {imp_id}")
                edges_added.add(edge)

    # Add circular dependency warnings
    for a, b in graph.get("circular", []):
        a_id = a.replace(".", "_")
        b_id = b.replace(".", "_")
        lines.append(f"    {a_id} <-.-> {b_id}")

    return "\n".join(lines)


def print_text_graph(graph: Dict, focus: Optional[str] = None):
    """Print a text-based dependency graph."""
    modules = graph["modules"]
    layers = identify_layers(graph)

    print("=" * 70)
    print("DEPENDENCY GRAPH")
    print("=" * 70)
    print()

    # Print layers
    print("ARCHITECTURAL LAYERS:")
    print("-" * 40)
    for layer_name, layer_modules in layers.items():
        if layer_modules:
            print(f"\n  {layer_name.upper()} ({len(layer_modules)} modules):")
            for mod in layer_modules[:10]:  # Top 10 per layer
                info = modules[mod]
                print(f"    {mod}")
                print(f"      imported by: {len(info['imported_by'])} | imports: {len(info['imports'])}")

    # Circular dependencies
    if graph["circular"]:
        print()
        print("CIRCULAR DEPENDENCIES (potential issues):")
        print("-" * 40)
        for a, b in graph["circular"]:
            print(f"  {a} <-> {b}")

    # Focus mode
    if focus:
        print()
        print(f"FOCUS: modules matching '{focus}'")
        print("-" * 40)
        for name, info in modules.items():
            if focus.lower() in name.lower():
                print(f"\n  {name}")
                if info["imports"]:
                    print(f"    imports:")
                    for imp in sorted(info["imports"]):
                        print(f"      <- {imp}")
                if info["imported_by"]:
                    print(f"    imported by:")
                    for imp in sorted(info["imported_by"]):
                        print(f"      -> {imp}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print(f"  Total modules: {len(modules)}")
    print(f"  Internal dependencies: {len(graph['internal_edges'])}")
    print(f"  Circular dependencies: {len(graph['circular'])}")

    # Top external deps
    all_external = set()
    for deps in graph["external_deps"].values():
        all_external.update(deps)
    print(f"  External packages: {len(all_external)}")
    if all_external:
        print(f"    Top: {', '.join(sorted(all_external)[:10])}")


# Entry point patterns (not orphans)
ENTRY_POINT_PATTERNS = {
    "main.py", "__main__.py", "cli.py", "app.py", "wsgi.py", "asgi.py",
    "setup.py", "manage.py", "fabfile.py", "conftest.py"
}

ENTRY_POINT_PREFIXES = ("test_",)
ENTRY_POINT_SUFFIXES = ("_test.py",)


def is_entry_point(filepath: str, source: str = None) -> bool:
    """Check if file is likely an entry point (not an orphan)."""
    filename = os.path.basename(filepath)

    # Check filename patterns
    if filename in ENTRY_POINT_PATTERNS:
        return True
    if filename.startswith(ENTRY_POINT_PREFIXES):
        return True
    if any(filename.endswith(s) for s in ENTRY_POINT_SUFFIXES):
        return True

    # Check for if __name__ == "__main__"
    if source is None:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception:
            return False

    return 'if __name__ ==' in source or "if __name__==" in source


def find_orphans(graph: Dict) -> List[Dict]:
    """Find files with zero importers that aren't entry points."""
    modules = graph["modules"]
    orphans = []

    for name, info in modules.items():
        if len(info["imported_by"]) == 0:
            filepath = info["file"]
            if is_entry_point(filepath):
                continue

            # Calculate confidence
            confidence = 0.9
            filename = os.path.basename(filepath).lower()

            # Lower confidence for certain patterns
            if "script" in filepath.lower():
                confidence = 0.6
            elif "deprecated" in filename or "legacy" in filename or "old" in filename:
                confidence = 0.95
            elif "util" in filename or "helper" in filename:
                confidence = 0.7

            orphans.append({
                "file": filepath,
                "module": name,
                "confidence": confidence,
                "notes": get_orphan_notes(filepath, filename)
            })

    return sorted(orphans, key=lambda x: x["confidence"], reverse=True)


def get_orphan_notes(filepath: str, filename: str) -> str:
    """Generate notes explaining orphan classification."""
    if "deprecated" in filename or "legacy" in filename:
        return "Name suggests deprecated"
    if "old" in filename:
        return "Name suggests superseded"
    if "script" in filepath.lower():
        return "Might be CLI script"
    return "No imports, not entry point pattern"


def calculate_impact(graph: Dict, target_file: str, max_depth: int = 2) -> Dict:
    """Calculate blast radius for a file."""
    modules = graph["modules"]

    # Find the module for this file
    target_module = None
    for name, info in modules.items():
        if info["file"] == target_file or info["file"].endswith(target_file):
            target_module = name
            break

    if not target_module:
        return {"error": f"File not found: {target_file}"}

    # Direct dependents
    direct = modules[target_module]["imported_by"]

    # Transitive dependents (BFS)
    seen = set(direct)
    frontier = list(direct)
    for _ in range(max_depth - 1):
        next_frontier = []
        for mod in frontier:
            if mod in modules:
                for dep in modules[mod]["imported_by"]:
                    if dep not in seen:
                        seen.add(dep)
                        next_frontier.append(dep)
        frontier = next_frontier

    return {
        "file": target_file,
        "module": target_module,
        "direct_dependents": direct,
        "direct_count": len(direct),
        "transitive_dependents": list(seen),
        "transitive_count": len(seen)
    }


def print_orphans(orphans: List[Dict]):
    """Print orphan analysis."""
    if not orphans:
        print("No orphan candidates found")
        return

    print("ORPHAN CANDIDATES (0 importers, excluding entry points)")
    print(f"{'CONFIDENCE':<12} {'FILE':<40} {'NOTES'}")
    print("-" * 80)
    for o in orphans[:20]:
        print(f"{o['confidence']:<12.2f} {o['file']:<40} {o['notes']}")


def print_impact(impact: Dict):
    """Print impact analysis."""
    if "error" in impact:
        print(f"Error: {impact['error']}")
        return

    print(f"IMPACT ANALYSIS: {impact['file']}")
    print()
    print(f"Direct dependents (import this file): {impact['direct_count']}")
    for dep in impact['direct_dependents'][:10]:
        print(f"  {dep}")
    if impact['direct_count'] > 10:
        print(f"  ... ({impact['direct_count'] - 10} more)")

    print()
    print(f"Transitive dependents (2 levels): {impact['transitive_count']}")

    if impact['transitive_count'] > 10:
        print()
        print("WARNING: Changes to this file have wide blast radius.")
        print("SUGGESTION: Consider smaller, incremental changes with tests.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate dependency graph for Python codebase"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current)"
    )
    parser.add_argument(
        "--root",
        help="Root package name (auto-detected if not specified)"
    )
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable auto-detection of root package"
    )
    parser.add_argument(
        "--source-dir",
        help="Override source root directory for module name generation"
    )
    parser.add_argument(
        "--focus",
        help="Focus on modules matching this string"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--mermaid",
        action="store_true",
        help="Output as Mermaid.js diagram"
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="Find files with zero importers (dead code candidates)"
    )
    parser.add_argument(
        "--impact",
        metavar="FILE",
        help="Calculate blast radius for a specific file"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    graph = build_dependency_graph(
        args.directory,
        args.root,
        auto_detect=not args.no_auto_detect,
        source_dir=args.source_dir
    )

    # Handle orphans and impact modes
    if args.orphans:
        orphans = find_orphans(graph)
        if args.json:
            print(json.dumps({"orphans": orphans}, indent=2))
        else:
            print_orphans(orphans)
        return

    if args.impact:
        impact = calculate_impact(graph, args.impact)
        if args.json:
            print(json.dumps(impact, indent=2))
        else:
            print_impact(impact)
        return

    if args.mermaid:
        print(generate_mermaid(graph, args.focus))
    elif args.json:
        # Clean up for JSON output
        output = {
            "modules": {
                k: {
                    "imports": v["imports"],
                    "imported_by": v["imported_by"]
                }
                for k, v in graph["modules"].items()
            },
            "layers": identify_layers(graph),
            "circular_dependencies": graph["circular"],
            "external_dependencies": graph["external_deps"],
            "summary": {
                "total_modules": len(graph["modules"]),
                "internal_edges": len(graph["internal_edges"]),
                "circular_count": len(graph["circular"])
            }
        }
        print(json.dumps(output, indent=2))
    else:
        print_text_graph(graph, args.focus)


if __name__ == "__main__":
    main()

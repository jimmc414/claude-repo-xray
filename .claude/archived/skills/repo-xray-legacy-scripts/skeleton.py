#!/usr/bin/env python3
"""
Repo X-Ray Code Skeleton Extractor

Extracts Python file interfaces (classes, methods, signatures) via AST.
Achieves ~95% token reduction compared to reading full source.

Enhanced features:
- Pydantic/dataclass field extraction
- Decorator support (@tool, @agent.register)
- Global constants (SYSTEM_PROMPT, CONFIG)
- Line numbers for navigation

Usage:
    python skeleton.py <file_or_directory> [options]

Examples:
    python skeleton.py src/core/workflow.py
    python skeleton.py src/agents/
    python skeleton.py src/ --pattern "**/base*.py"
    python skeleton.py src/ --priority critical
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add lib to path for imports
SCRIPT_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
LIB_DIR = SKILL_ROOT / "lib"
CONFIG_DIR = SKILL_ROOT / "configs"

sys.path.insert(0, str(SKILL_ROOT))

# Import from shared library (DRY principle)
from lib.ast_utils import get_skeleton

import ast


# =============================================================================
# Type Annotation Coverage
# =============================================================================

def calculate_type_coverage(filepath: str) -> Dict:
    """Calculate type annotation coverage for a file.

    Returns:
        Dict with total_functions, typed_functions, coverage_percent
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return {'total_functions': 0, 'typed_functions': 0, 'coverage_percent': 0.0}

    total_funcs = 0
    typed_funcs = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total_funcs += 1
            has_return_type = node.returns is not None
            has_arg_types = any(
                arg.annotation is not None
                for arg in node.args.args
                if arg.arg != 'self' and arg.arg != 'cls'
            )
            if has_return_type or has_arg_types:
                typed_funcs += 1

    return {
        'total_functions': total_funcs,
        'typed_functions': typed_funcs,
        'coverage_percent': round((typed_funcs / total_funcs * 100), 1) if total_funcs else 0.0
    }


def calculate_codebase_type_coverage(files: list) -> Dict:
    """Calculate aggregate type coverage across multiple files."""
    total = 0
    typed = 0

    for filepath in files:
        cov = calculate_type_coverage(filepath)
        total += cov['total_functions']
        typed += cov['typed_functions']

    return {
        'total_functions': total,
        'typed_functions': typed,
        'coverage_percent': round((typed / total * 100), 1) if total else 0.0,
        'files_analyzed': len(files)
    }


# =============================================================================
# Decorator Inventory
# =============================================================================

def extract_decorators(filepath: str) -> Dict[str, int]:
    """Extract decorator usage counts from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return {}

    decorators = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                # Get decorator name
                if isinstance(dec, ast.Name):
                    name = dec.id
                elif isinstance(dec, ast.Attribute):
                    name = dec.attr
                elif isinstance(dec, ast.Call):
                    if isinstance(dec.func, ast.Name):
                        name = dec.func.id
                    elif isinstance(dec.func, ast.Attribute):
                        name = dec.func.attr
                    else:
                        name = 'unknown'
                else:
                    name = 'unknown'
                decorators[name] = decorators.get(name, 0) + 1

    return decorators


def calculate_codebase_decorators(files: list) -> Dict[str, int]:
    """Aggregate decorator usage across codebase."""
    totals = {}
    for filepath in files:
        file_decs = extract_decorators(filepath)
        for dec, count in file_decs.items():
            totals[dec] = totals.get(dec, 0) + count

    # Sort by frequency, descending
    return dict(sorted(totals.items(), key=lambda x: -x[1]))


def load_priority_patterns() -> Dict:
    """Load priority patterns from config."""
    config_path = CONFIG_DIR / "priority_modules.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def load_ignore_patterns() -> Tuple[Set[str], Set[str], List[str]]:
    """Load ignore patterns from config."""
    config_path = CONFIG_DIR / "ignore_patterns.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        return (
            set(config.get("directories", [])),
            set(config.get("extensions", [])),
            config.get("files", [])
        )
    return ({"__pycache__", ".git"}, {".pyc"}, [])


def find_python_files(
    directory: str,
    pattern: Optional[str] = None,
    priority: Optional[str] = None
) -> List[str]:
    """Find Python files matching criteria."""
    ignore_dirs, ignore_exts, _ = load_ignore_patterns()
    priority_config = load_priority_patterns()

    files = []

    # Get glob patterns for priority level
    glob_patterns = []
    if priority and priority_config.get("priority_patterns", {}).get(priority):
        glob_patterns = priority_config["priority_patterns"][priority].get("patterns", [])

    for root, dirs, filenames in os.walk(directory):
        # Filter directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for filename in filenames:
            if not filename.endswith('.py'):
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, directory)

            # Check custom pattern
            if pattern and not fnmatch.fnmatch(rel_path, pattern):
                continue

            # Check priority patterns
            if glob_patterns:
                if not any(fnmatch.fnmatch(rel_path, p.lstrip('**/')) for p in glob_patterns):
                    continue

            files.append(filepath)

    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="Extract Python file skeletons via AST"
    )
    parser.add_argument(
        "path",
        help="Python file or directory to analyze"
    )
    parser.add_argument(
        "--pattern",
        help="Glob pattern to filter files (e.g., '**/base*.py')"
    )
    parser.add_argument(
        "--priority",
        choices=["critical", "high", "medium", "low"],
        help="Filter by priority level from config"
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Include private methods (starting with _)"
    )
    parser.add_argument(
        "--no-line-numbers",
        action="store_true",
        help="Omit line numbers from output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if os.path.isfile(args.path):
        files = [args.path]
    elif os.path.isdir(args.path):
        files = find_python_files(args.path, args.pattern, args.priority)
    else:
        print(f"Error: '{args.path}' not found", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("No Python files found matching criteria", file=sys.stderr)
        sys.exit(1)

    results = []
    total_original = 0
    total_skeleton = 0
    include_line_numbers = not args.no_line_numbers

    for filepath in files:
        # Use shared library function
        skeleton, orig_tok, skel_tok = get_skeleton(
            filepath,
            include_private=args.private,
            include_line_numbers=include_line_numbers
        )
        total_original += orig_tok
        total_skeleton += skel_tok

        if args.json:
            results.append({
                "file": filepath,
                "original_tokens": orig_tok,
                "skeleton_tokens": skel_tok,
                "reduction": f"{(1 - skel_tok/orig_tok)*100:.1f}%" if orig_tok > 0 else "N/A",
                "skeleton": skeleton
            })
        else:
            print(f"# {'=' * 60}")
            print(f"# FILE: {filepath}")
            print(f"# Tokens: {orig_tok} -> {skel_tok} ({(1 - skel_tok/orig_tok)*100:.1f}% reduction)" if orig_tok > 0 else "# Tokens: N/A")
            print(f"# {'=' * 60}")
            print(skeleton)
            print()

    if args.json:
        output = {
            "files": results,
            "summary": {
                "file_count": len(files),
                "total_original_tokens": total_original,
                "total_skeleton_tokens": total_skeleton,
                "overall_reduction": f"{(1 - total_skeleton/total_original)*100:.1f}%" if total_original > 0 else "N/A"
            }
        }
        print(json.dumps(output, indent=2))
    else:
        print("=" * 60)
        print("SUMMARY")
        print(f"  Files processed: {len(files)}")
        print(f"  Original tokens: {total_original}")
        print(f"  Skeleton tokens: {total_skeleton}")
        if total_original > 0:
            print(f"  Reduction: {(1 - total_skeleton/total_original)*100:.1f}%")


if __name__ == "__main__":
    main()

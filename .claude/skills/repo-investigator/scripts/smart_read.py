#!/usr/bin/env python3
"""
Repo Investigator: Smart Reader

Surgical reading that expands complex methods while skeletonizing the rest.
Preserves imports, class attributes, and method signatures for context.

Features:
- Auto-expand top N complex methods
- Expand specific methods by name
- Coupled file analysis for related files
- Cross-reference detection between files

Usage:
    python smart_read.py <file> [options]

Examples:
    python smart_read.py src/core/workflow.py --focus-top 3
    python smart_read.py src/core/workflow.py --focus process_order validate
    python smart_read.py src/config.py src/provider.py --coupled
"""
import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


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
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for generator in child.generators:
                cc += len(generator.ifs)
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


def extract_symbols(filepath: str) -> Dict[str, List[int]]:
    """Extract all defined symbols and their line numbers from a file."""
    symbols = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols[node.name] = symbols.get(node.name, []) + [node.lineno]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols[node.name] = symbols.get(node.name, []) + [node.lineno]
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            symbols[node.id] = symbols.get(node.id, []) + [node.lineno]
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols[target.id] = symbols.get(target.id, []) + [node.lineno]

    return symbols


def find_cross_references(file1: str, file2: str) -> List[Dict]:
    """Find symbols defined in file1 that are used in file2."""
    cross_refs = []

    symbols1 = extract_symbols(file1)

    try:
        with open(file2, 'r', encoding='utf-8') as f:
            source2 = f.read()
        tree2 = ast.parse(source2)
        lines2 = source2.splitlines()
    except Exception:
        return cross_refs

    # Find uses of symbols from file1 in file2
    for node in ast.walk(tree2):
        if isinstance(node, ast.Name) and node.id in symbols1:
            cross_refs.append({
                "symbol": node.id,
                "defined_in": os.path.basename(file1),
                "defined_at": symbols1[node.id],
                "used_in": os.path.basename(file2),
                "used_at": node.lineno
            })
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            # Check for module.symbol patterns
            full_name = f"{node.value.id}.{node.attr}"
            if node.attr in symbols1:
                cross_refs.append({
                    "symbol": node.attr,
                    "defined_in": os.path.basename(file1),
                    "defined_at": symbols1[node.attr],
                    "used_in": os.path.basename(file2),
                    "used_at": node.lineno
                })

    # Deduplicate by symbol+line
    seen = set()
    unique_refs = []
    for ref in cross_refs:
        key = (ref["symbol"], ref["used_at"])
        if key not in seen:
            seen.add(key)
            unique_refs.append(ref)

    return unique_refs


def smart_read(
    filepath: str,
    focus_top: int = 0,
    focus_methods: List[str] = None,
    verbose: bool = False
) -> str:
    """
    Read file with surgical expansion of complex methods.

    Args:
        filepath: Path to Python file
        focus_top: Auto-expand top N complex methods
        focus_methods: Explicit list of methods to expand
        verbose: Show progress messages

    Returns:
        Surgically processed source code
    """
    if verbose:
        print(f"Processing {filepath}...", file=sys.stderr)

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

    if verbose and expand_methods:
        print(f"Expanding methods: {', '.join(expand_methods)}", file=sys.stderr)

    output = []
    output.append(f"# File: {os.path.basename(filepath)}")
    output.append(f"# Original: {len(lines)} lines")
    output.append("")

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
                # Class docstring
                if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant):
                    if isinstance(child.value.value, str):
                        # Skip docstrings, just note them
                        output.append('    """..."""')
                        continue

                # Class attributes
                if isinstance(child, (ast.Assign, ast.AnnAssign)):
                    output.append("    " + lines[child.lineno - 1].strip())

                # Methods
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name in expand_methods:
                        # EXPAND: Full implementation
                        cc = calculate_complexity(child)
                        output.append("")
                        output.append(f"    # EXPANDED: {child.name} (CC={cc})")
                        for line in get_source_lines(lines, child):
                            output.append(line)
                    else:
                        # SKELETON: Signature only
                        sig_line = lines[child.lineno - 1].rstrip()
                        if not sig_line.rstrip().endswith(':'):
                            # Multi-line signature, find the colon
                            for i in range(child.lineno - 1, min(child.lineno + 5, len(lines))):
                                if ':' in lines[i]:
                                    sig_line = lines[child.lineno - 1].rstrip()
                                    break
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
                sig_line = lines[node.lineno - 1].rstrip()
                if ':' in sig_line:
                    sig_line = sig_line.split(':')[0]
                output.append(f"{sig_line}: ...  # L{node.lineno}")

            continue

    return "\n".join(output)


def coupled_read(
    files: List[str],
    focus_top: int = 3,
    focus_methods: List[str] = None,
    verbose: bool = False
) -> str:
    """
    Read multiple coupled files together, showing cross-references.

    Args:
        files: List of file paths to analyze together
        focus_top: Auto-expand top N complex methods per file
        focus_methods: Explicit list of methods to expand
        verbose: Show progress messages

    Returns:
        Combined analysis with cross-references
    """
    output = []
    output.append("# COUPLED FILE ANALYSIS")
    output.append(f"# Files: {', '.join(os.path.basename(f) for f in files)}")
    output.append("")

    # Find all cross-references between files
    all_cross_refs = []
    for i, file1 in enumerate(files):
        for file2 in files[i+1:]:
            # Check both directions
            refs_1_to_2 = find_cross_references(file1, file2)
            refs_2_to_1 = find_cross_references(file2, file1)
            all_cross_refs.extend(refs_1_to_2)
            all_cross_refs.extend(refs_2_to_1)

    # Output cross-references summary
    if all_cross_refs:
        output.append("## Cross-References")
        output.append("")

        # Group by symbol
        by_symbol = {}
        for ref in all_cross_refs:
            sym = ref["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(ref)

        for sym, refs in sorted(by_symbol.items()):
            defined_in = refs[0]["defined_in"]
            defined_at = refs[0]["defined_at"]
            uses = [f"{r['used_in']}:L{r['used_at']}" for r in refs]
            output.append(f"# CROSS-REF: {sym} (defined in {defined_in}:L{defined_at[0]}) used in {', '.join(uses)}")

        output.append("")
        output.append("---")
        output.append("")

    # Process each file
    for filepath in files:
        result = smart_read(filepath, focus_top, focus_methods, verbose)
        output.append(result)
        output.append("")
        output.append("---")
        output.append("")

    return "\n".join(output)


def write_debug_output(
    files: List[str],
    output: str,
    cross_refs: List[Dict],
    output_dir: str,
    verbose: bool = False
):
    """Write debug output to SMART_READ_debug/ directory."""
    debug_path = Path(output_dir)
    debug_path.mkdir(parents=True, exist_ok=True)

    # Write processed output
    with open(debug_path / "surgical_read.txt", 'w') as f:
        f.write(output)

    # Write metadata
    metadata = {
        "files_analyzed": files,
        "cross_references": cross_refs,
        "output_lines": len(output.splitlines())
    }
    with open(debug_path / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    if verbose:
        print(f"Debug output written to {debug_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Surgical reader for Python files"
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Python file(s) to read"
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
    parser.add_argument(
        "--coupled",
        action="store_true",
        help="Treat input files as historically coupled, show cross-references"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress messages"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write debug output to SMART_READ_debug/"
    )

    args = parser.parse_args()

    # Validate files exist
    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            sys.exit(1)

    # Process files
    if args.coupled and len(args.files) > 1:
        result = coupled_read(args.files, args.focus_top, args.focus, args.verbose)

        # Collect cross-refs for debug output
        cross_refs = []
        for i, file1 in enumerate(args.files):
            for file2 in args.files[i+1:]:
                cross_refs.extend(find_cross_references(file1, file2))
                cross_refs.extend(find_cross_references(file2, file1))

        if args.debug:
            write_debug_output(args.files, result, cross_refs, "SMART_READ_debug", args.verbose)
    else:
        # Single file or non-coupled mode
        if len(args.files) == 1:
            result = smart_read(args.files[0], args.focus_top, args.focus, args.verbose)
        else:
            # Multiple files without coupling - process separately
            results = []
            for filepath in args.files:
                results.append(smart_read(filepath, args.focus_top, args.focus, args.verbose))
                results.append("\n---\n")
            result = "\n".join(results)

        if args.debug:
            write_debug_output(args.files, result, [], "SMART_READ_debug", args.verbose)

    print(result)


if __name__ == "__main__":
    main()

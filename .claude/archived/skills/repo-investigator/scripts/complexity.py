#!/usr/bin/env python3
"""
Repo Investigator: Unified Complexity Scanner

Calculates Unified Priority Score combining:
- Cyclomatic Complexity (CC) - Logic density from AST analysis
- Import Weight - Architectural importance from dependency graph
- Risk Score - Historical volatility from git analysis
- Freshness - Maintenance activity (active code more relevant)
- Untested (optional) - Test coverage signal from Phase 1

Requires Phase 1 JSON outputs for unified scoring.

Usage:
    python complexity.py [directory] [options]

Examples:
    python complexity.py src/
    python complexity.py src/ --unified deps.json git.json
    python complexity.py src/ --unified deps.json git.json --warm-start-debug ./WARM_START_debug
    python complexity.py src/ --top 10 --json
"""
import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def calculate_cc(filepath: str, verbose: bool = False) -> Tuple[int, Dict[str, int]]:
    """
    Calculate Cyclomatic Complexity for a file.

    Returns:
        Tuple of (total_score, {method_name: cc_score})
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception as e:
        if verbose:
            print(f"Warning: Could not parse {filepath}: {e}", file=sys.stderr)
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


def count_async_patterns(filepath: str) -> Dict:
    """Count async/await patterns in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return {}

    async_funcs = sum(1 for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef))
    sync_funcs = sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    async_fors = sum(1 for n in ast.walk(tree) if isinstance(n, ast.AsyncFor))
    async_withs = sum(1 for n in ast.walk(tree) if isinstance(n, ast.AsyncWith))

    return {
        'async_functions': async_funcs,
        'sync_functions': sync_funcs,
        'async_for_loops': async_fors,
        'async_context_managers': async_withs,
    }


def calculate_codebase_async_patterns(files: list) -> Dict:
    """Aggregate async patterns across codebase."""
    totals = {
        'async_functions': 0,
        'sync_functions': 0,
        'async_for_loops': 0,
        'async_context_managers': 0,
    }

    for filepath in files:
        patterns = count_async_patterns(filepath)
        for key in totals:
            totals[key] += patterns.get(key, 0)

    return totals


def normalize_dict(values: Dict[str, float]) -> Dict[str, float]:
    """Normalize dictionary values to 0-1 range."""
    if not values:
        return {}
    max_val = max(values.values())
    if max_val == 0:
        return {k: 0.0 for k in values}
    return {k: v / max_val for k, v in values.items()}


def validate_phase1_inputs(deps: Dict, git: Dict, verbose: bool = False) -> List[str]:
    """Check Phase 1 JSON for issues before using."""
    warnings = []

    if not deps.get("modules"):
        warnings.append("deps.json has no modules - layer classification will fail")

    if not git.get("risk"):
        warnings.append("git.json has no risk data - risk scores will be 0")

    if not git.get("coupling"):
        warnings.append("git.json has no coupling data - may indicate git format bug")

    if not git.get("freshness"):
        warnings.append("git.json has no freshness data - freshness scores will use defaults")

    if verbose:
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)

    return warnings


def load_phase1_data(
    deps_path: str,
    git_path: str,
    warm_start_debug_path: Optional[str] = None,
    verbose: bool = False
) -> Tuple[Dict, Dict, Dict, Dict]:
    """
    Load Phase 1 JSON outputs.

    Returns:
        Tuple of (import_weights, risk_scores, freshness_map, test_coverage)
    """
    imports = {}
    risks = {}
    freshness = {}
    test_coverage = {}
    deps = {}
    git = {}

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

        if verbose:
            print(f"Loaded {len(deps.get('modules', {}))} modules from deps.json", file=sys.stderr)

    except FileNotFoundError:
        if verbose:
            print(f"Warning: deps file not found: {deps_path}", file=sys.stderr)
    except Exception as e:
        if verbose:
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

        if verbose:
            print(f"Loaded {len(risks)} risk scores, {len(freshness)} freshness scores from git.json", file=sys.stderr)

    except FileNotFoundError:
        if verbose:
            print(f"Warning: git file not found: {git_path}", file=sys.stderr)
    except Exception as e:
        if verbose:
            print(f"Warning: Could not load git file: {e}", file=sys.stderr)

    # Validate inputs
    validate_phase1_inputs(deps, git, verbose)

    # Load test coverage from WARM_START_debug if provided
    if warm_start_debug_path:
        try:
            debug_dir = Path(warm_start_debug_path)
            test_data_path = debug_dir / "section_13_test_coverage.json"
            if test_data_path.exists():
                test_data = json.loads(test_data_path.read_text())
                tested_dirs = set(test_data.get("tested_dirs", []))

                # For each module, determine if its directory is tested
                for mod_name in deps.get('modules', {}).keys():
                    parts = mod_name.split(".")
                    if len(parts) >= 2:
                        # Check if second part (typically subpackage) is tested
                        test_coverage[mod_name] = 0.0 if parts[1] in tested_dirs else 1.0

                if verbose:
                    print(f"Loaded test coverage: {len(tested_dirs)} tested directories", file=sys.stderr)
            else:
                if verbose:
                    print(f"Warning: section_13_test_coverage.json not found in {warm_start_debug_path}", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"Warning: Could not load test coverage: {e}", file=sys.stderr)

    return imports, risks, freshness, test_coverage


def scan_directory(directory: str, ignore_dirs: set = None, verbose: bool = False) -> List[str]:
    """Scan directory for Python files."""
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', 'node_modules', '.venv', 'env', '.claude'}

    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for filename in filenames:
            if filename.endswith('.py'):
                files.append(os.path.join(root, filename))

    if verbose:
        print(f"Found {len(files)} Python files to analyze", file=sys.stderr)

    return files


def write_debug_output(results: List[Dict], output_dir: str, verbose: bool = False):
    """Write debug output to PRIORITY_debug/ directory."""
    debug_path = Path(output_dir)
    debug_path.mkdir(parents=True, exist_ok=True)

    # Write full results
    with open(debug_path / "priorities.json", 'w') as f:
        json.dump(results, f, indent=2)

    # Write summary
    summary = {
        "total_files": len(results),
        "top_10": [{"path": r["path"], "score": r["score"]} for r in results[:10]],
        "score_distribution": {
            "high": len([r for r in results if r["score"] >= 0.7]),
            "medium": len([r for r in results if 0.4 <= r["score"] < 0.7]),
            "low": len([r for r in results if r["score"] < 0.4])
        }
    }
    with open(debug_path / "summary.json", 'w') as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print(f"Debug output written to {debug_path}", file=sys.stderr)


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
        "--warm-start-debug",
        metavar="PATH",
        help="Path to WARM_START_debug/ for test coverage signal (enables 5-signal formula)"
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
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress messages"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write debug output to PRIORITY_debug/"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load Phase 1 data if provided
    imports = {}
    risks = {}
    freshness = {}
    test_coverage = {}
    use_5_signal = False

    if args.unified:
        imports, risks, freshness, test_coverage = load_phase1_data(
            args.unified[0],
            args.unified[1],
            args.warm_start_debug,
            args.verbose
        )
        # Enable 5-signal formula if test coverage data is available
        use_5_signal = bool(test_coverage)

    # Scan and analyze files
    files = scan_directory(args.directory, verbose=args.verbose)

    raw_cc = {}
    all_hotspots = {}

    for filepath in files:
        if args.verbose:
            print(f"Analyzing {filepath}...", file=sys.stderr)
        cc, methods = calculate_cc(filepath, args.verbose)
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
        s_untested = test_coverage.get(rel_path, 0.5)  # Default to mid if unknown

        # Unified Priority Score Formula
        if args.unified:
            if use_5_signal:
                # Enhanced 5-signal formula
                # CC: 30%, Import: 20%, Risk: 20%, Freshness: 15%, Untested: 15%
                score = (
                    (s_cc * 0.30) +
                    (s_imp * 0.20) +
                    (s_risk * 0.20) +
                    (s_fresh * 0.15) +
                    (s_untested * 0.15)
                )
            else:
                # Base 4-signal formula
                # CC: 35%, Import Weight: 25%, Risk: 25%, Freshness: 15%
                score = (s_cc * 0.35) + (s_imp * 0.25) + (s_risk * 0.25) + (s_fresh * 0.15)
        else:
            # Without Phase 1 data, just use CC
            score = s_cc

        if score < args.min_score:
            continue

        result = {
            "path": filepath,
            "score": round(score, 3),
            "metrics": {
                "cc": cc_val,
                "imp_score": round(s_imp, 2),
                "risk": round(s_risk, 2),
                "freshness": round(s_fresh, 2)
            },
            "hotspots": all_hotspots.get(filepath, {})
        }

        # Add untested score if using 5-signal formula
        if use_5_signal:
            result["metrics"]["untested"] = round(s_untested, 2)

        results.append(result)

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)

    # Write debug output if requested
    if args.debug:
        write_debug_output(results, "PRIORITY_debug", args.verbose)

    top_results = results[:args.top]

    # Output
    if args.json:
        print(json.dumps(top_results, indent=2))
    else:
        formula = "5-signal (with test coverage)" if use_5_signal else "4-signal" if args.unified else "CC only"
        print(f"Priority Score ({formula})")
        print(f"{'SCORE':<6} {'FILE':<50} {'DETAILS'}")
        print("-" * 90)

        for r in top_results:
            m = r['metrics']
            if args.unified:
                details = f"CC:{m['cc']} Imp:{m['imp_score']} Risk:{m['risk']} Fresh:{m['freshness']}"
                if use_5_signal:
                    details += f" Untested:{m.get('untested', 'N/A')}"
            else:
                spots = sorted(r['hotspots'].items(), key=lambda x: x[1], reverse=True)[:2]
                details = ", ".join(f"{k}:{v}" for k, v in spots) if spots else f"CC:{m['cc']}"

            print(f"{r['score']:<6} {r['path']:<50} {details}")


if __name__ == "__main__":
    main()

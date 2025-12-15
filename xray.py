#!/usr/bin/env python3
"""
Repo X-Ray: Unified Codebase Analysis Tool

Generates comprehensive analysis of Python codebases for AI coding agents.
Combines structural, behavioral, and historical signals in a single pass.

Usage:
    python xray.py ./target                       # Full analysis (default)
    python xray.py ./target --preset minimal      # Quick structural overview
    python xray.py ./target --preset standard     # Balanced analysis
    python xray.py ./target --output both         # JSON + Markdown output
    python xray.py ./target --out ./analysis      # Custom output path

Examples:
    python xray.py /path/to/repo
    python xray.py . --skeleton --git --imports
    python xray.py . --preset full --verbose
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add lib directory to path
SCRIPT_DIR = Path(__file__).parent
LIB_DIR = SCRIPT_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

VERSION = "2.0.0"

# Analysis switches
ANALYSIS_SWITCHES = [
    "skeleton",
    "complexity",
    "git",
    "imports",
    "calls",
    "side-effects",
    "tests",
    "tech-debt",
    "types",
    "decorators",
    "author-expertise",
    "commit-sizes",
]


def load_presets() -> Dict[str, Any]:
    """Load preset configurations from configs/presets.json."""
    config_path = SCRIPT_DIR / "configs" / "presets.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)

    # Fallback defaults
    return {
        "minimal": {
            "description": "Quick structural overview (~2K tokens)",
            "includes": ["skeleton", "imports"]
        },
        "standard": {
            "description": "Balanced analysis for most tasks (~8K tokens)",
            "includes": [
                "skeleton", "complexity", "git", "imports",
                "calls", "side-effects", "tests", "tech-debt"
            ]
        },
        "full": {
            "default": True,
            "description": "Complete analysis with all signals (~15K tokens)",
            "includes": ANALYSIS_SWITCHES
        }
    }


def get_active_analyses(args: argparse.Namespace, presets: Dict) -> List[str]:
    """Determine which analyses to run based on args and presets."""
    # Check if any explicit switches are set
    explicit_switches = [
        sw.replace("-", "_") for sw in ANALYSIS_SWITCHES
        if getattr(args, sw.replace("-", "_"), False)
    ]

    if explicit_switches:
        return explicit_switches

    # Use preset
    preset_name = args.preset or "full"
    preset = presets.get(preset_name, presets.get("full", {}))
    return [sw.replace("-", "_") for sw in preset.get("includes", ANALYSIS_SWITCHES)]


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="Unified codebase analysis tool for AI coding agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Presets:
  minimal   Quick structural overview (~2K tokens)
  standard  Balanced analysis for most tasks (~8K tokens)
  full      Complete analysis with all signals (~15K tokens) [DEFAULT]

Examples:
  %(prog)s /path/to/repo
  %(prog)s . --preset standard
  %(prog)s . --skeleton --git --imports
  %(prog)s . --output both --out ./analysis
"""
    )

    # Positional argument
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current directory)"
    )

    # Preset selection
    parser.add_argument(
        "--preset",
        choices=["minimal", "standard", "full"],
        default=None,
        help="Analysis preset (default: full if no switches specified)"
    )

    # Individual analysis switches
    switches = parser.add_argument_group("Analysis Switches (override preset)")
    switches.add_argument("--skeleton", action="store_true", help="Extract code skeletons (classes, functions)")
    switches.add_argument("--complexity", action="store_true", help="Calculate cyclomatic complexity")
    switches.add_argument("--git", action="store_true", help="Analyze git history (risk, coupling, freshness)")
    switches.add_argument("--imports", action="store_true", help="Build import graph, detect orphans")
    switches.add_argument("--calls", action="store_true", help="Cross-module call analysis")
    switches.add_argument("--side-effects", action="store_true", dest="side_effects", help="Detect I/O, network, DB operations")
    switches.add_argument("--tests", action="store_true", help="Test coverage and fixture analysis")
    switches.add_argument("--tech-debt", action="store_true", dest="tech_debt", help="TODO/FIXME/HACK markers")
    switches.add_argument("--types", action="store_true", help="Type annotation coverage")
    switches.add_argument("--decorators", action="store_true", help="Decorator inventory")
    switches.add_argument("--author-expertise", action="store_true", dest="author_expertise", help="Git blame expertise")
    switches.add_argument("--commit-sizes", action="store_true", dest="commit_sizes", help="Commit size analysis")

    # Gap Analysis Features (markdown enhancements)
    gap = parser.add_argument_group("Gap Analysis Features (markdown enhancements)")
    gap.add_argument("--mermaid", action="store_true", help="Include Mermaid architecture diagram")
    gap.add_argument("--priority-scores", action="store_true", dest="priority_scores", help="Calculate composite priority scores")
    gap.add_argument("--inline-skeletons", type=int, metavar="N", dest="inline_skeletons", help="Include skeleton code for top N classes")
    gap.add_argument("--hazards", action="store_true", help="List large files that may waste context")
    gap.add_argument("--data-models", action="store_true", dest="data_models", help="Show Pydantic/dataclass models")
    gap.add_argument("--logic-maps", type=int, metavar="N", dest="logic_maps", help="Include logic maps for top N complex functions")
    gap.add_argument("--entry-points", action="store_true", dest="entry_points", help="Highlight entry points")
    gap.add_argument("--side-effects-detail", action="store_true", dest="side_effects_detail", help="Per-function side effects")
    gap.add_argument("--verify-imports", action="store_true", dest="verify_imports", help="Verify import paths")
    gap.add_argument("--layer-details", action="store_true", dest="layer_details", help="Import counts in layer tables")
    gap.add_argument("--prose", action="store_true", help="Natural language architecture overview")
    gap.add_argument("--signatures", action="store_true", help="Full method signatures for hotspots")
    gap.add_argument("--state-mutations", action="store_true", dest="state_mutations", help="Track attribute modifications")
    gap.add_argument("--verify-commands", action="store_true", dest="verify_commands", help="Generate verification commands")
    gap.add_argument("--explain", action="store_true", help="Add explanatory text before each section (verbose output)")
    gap.add_argument("--persona-map", action="store_true", dest="persona_map", help="Show agent prompts and personas")

    # Output options
    output = parser.add_argument_group("Output Options")
    output.add_argument(
        "--output",
        choices=["json", "markdown", "both"],
        default="json",
        help="Output format (default: json)"
    )
    output.add_argument(
        "--out",
        metavar="PATH",
        help="Output file path (without extension). Default: ./analysis"
    )

    # Verbosity
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress on stderr"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include debug information in output"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}"
    )

    return parser


def run_analysis(target: str, analyses: List[str], verbose: bool = False) -> Dict[str, Any]:
    """
    Run the specified analyses on the target directory.

    This is the main orchestration function that calls individual analysis modules.
    """
    from file_discovery import discover_python_files, load_ignore_patterns
    from ast_analysis import analyze_codebase
    from import_analysis import analyze_imports
    from call_analysis import analyze_calls
    from git_analysis import (
        analyze_risk, analyze_coupling, analyze_freshness,
        analyze_commit_sizes, get_tracked_files
    )
    from tech_debt_analysis import analyze_tech_debt
    from test_analysis import analyze_tests

    if verbose:
        print(f"Analyzing: {target}", file=sys.stderr)
        print(f"Analyses: {', '.join(analyses)}", file=sys.stderr)

    # Load ignore patterns
    ignore_dirs, ignore_exts, ignore_files = load_ignore_patterns()

    # Discover Python files
    if verbose:
        print("Discovering Python files...", file=sys.stderr)
    files = discover_python_files(target, ignore_dirs, ignore_exts, ignore_files)

    if verbose:
        print(f"Found {len(files)} Python files", file=sys.stderr)

    if not files:
        return {
            "metadata": {
                "tool_version": VERSION,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "target_directory": str(Path(target).resolve()),
                "error": "No Python files found"
            },
            "summary": {"total_files": 0}
        }

    # Initialize result structure
    result = {
        "metadata": {
            "tool_version": VERSION,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "target_directory": str(Path(target).resolve()),
            "preset": None,
            "analysis_options": analyses,
            "file_count": len(files)
        },
        "summary": {
            "total_files": len(files),
            "total_lines": 0,
            "total_tokens": 0,
            "total_functions": 0,
            "total_classes": 0
        }
    }

    # Core AST analysis (skeleton, complexity, types, decorators, side_effects all come from here)
    ast_results = None
    if any(a in analyses for a in ["skeleton", "complexity", "types", "decorators", "side_effects", "calls"]):
        if verbose:
            print("Running AST analysis...", file=sys.stderr)
        ast_results = analyze_codebase(files, verbose=verbose)

        # Update summary
        result["summary"]["total_lines"] = ast_results["summary"]["total_lines"]
        result["summary"]["total_tokens"] = ast_results["summary"]["total_tokens"]
        result["summary"]["total_functions"] = ast_results["summary"]["total_functions"]
        result["summary"]["total_classes"] = ast_results["summary"]["total_classes"]
        result["summary"]["type_coverage"] = ast_results["summary"]["type_coverage"]

    if "skeleton" in analyses and ast_results:
        result["structure"] = {
            "files": ast_results.get("files", {}),
            "classes": ast_results.get("all_classes", []),
            "functions": ast_results.get("all_functions", [])
        }

    if "complexity" in analyses and ast_results:
        result["complexity"] = {
            "hotspots": ast_results.get("hotspots", [])[:20],
            "average_cc": ast_results["summary"].get("average_cc", 0.0),
            "total_cc": ast_results["summary"].get("total_cc", 0)
        }
        result["hotspots"] = ast_results.get("hotspots", [])

    if "types" in analyses and ast_results:
        result["types"] = {
            "coverage": ast_results["summary"].get("type_coverage", 0.0),
            "typed_functions": ast_results["summary"].get("typed_functions", 0),
            "total_functions": ast_results["summary"].get("total_functions", 0)
        }

    if "decorators" in analyses and ast_results:
        result["decorators"] = {"inventory": ast_results.get("decorators", {})}

    if "side_effects" in analyses and ast_results:
        result["side_effects"] = ast_results.get("side_effects", {})

    # Async patterns (always included with skeleton/complexity)
    if ast_results:
        result["async_patterns"] = ast_results.get("async_patterns", {})

    # Import analysis
    if "imports" in analyses:
        if verbose:
            print("Running import analysis...", file=sys.stderr)
        import_results = analyze_imports(files, target, verbose=verbose)
        result["imports"] = import_results

    # Call analysis (requires AST results)
    if "calls" in analyses and ast_results:
        if verbose:
            print("Running call analysis...", file=sys.stderr)
        call_results = analyze_calls(files, ast_results, target, verbose=verbose)
        result["calls"] = call_results

    # Git analysis
    if "git" in analyses:
        if verbose:
            print("Running git analysis...", file=sys.stderr)
        try:
            tracked_files = get_tracked_files(target)
            risk = analyze_risk(target, tracked_files, verbose=verbose)
            coupling = analyze_coupling(target, verbose=verbose)
            freshness = analyze_freshness(target, tracked_files, verbose=verbose)

            result["git"] = {
                "risk": risk,
                "coupling": coupling,
                "freshness": freshness
            }
        except Exception as e:
            if verbose:
                print(f"  Git analysis failed: {e}", file=sys.stderr)
            result["git"] = {"error": str(e)}

    # Author expertise (git-based)
    if "author_expertise" in analyses:
        if verbose:
            print("Running author expertise analysis...", file=sys.stderr)
        # This would require git blame which is slow, so we skip for now
        result["author_expertise"] = {"note": "Use git blame for detailed expertise"}

    # Commit sizes (git-based)
    if "commit_sizes" in analyses:
        if verbose:
            print("Running commit size analysis...", file=sys.stderr)
        try:
            commit_sizes = analyze_commit_sizes(target, verbose=verbose)
            result["commit_sizes"] = commit_sizes
        except Exception as e:
            if verbose:
                print(f"  Commit size analysis failed: {e}", file=sys.stderr)
            result["commit_sizes"] = []

    # Test analysis
    if "tests" in analyses:
        if verbose:
            print("Running test analysis...", file=sys.stderr)
        test_results = analyze_tests(target, verbose=verbose)
        result["tests"] = test_results

    # Tech debt analysis
    if "tech_debt" in analyses:
        if verbose:
            print("Running tech debt analysis...", file=sys.stderr)
        debt_results = analyze_tech_debt(files, verbose=verbose)
        result["tech_debt"] = debt_results

    return result


def output_json(result: Dict[str, Any], output_path: Optional[str] = None):
    """Write JSON output."""
    # Add formatters to path
    sys.path.insert(0, str(SCRIPT_DIR / "formatters"))
    from json_formatter import format_json

    json_str = format_json(result)

    if output_path:
        path = Path(output_path).with_suffix(".json")
        path.write_text(json_str)
        print(f"JSON output written to: {path}", file=sys.stderr)
    else:
        print(json_str)


def output_markdown(
    result: Dict[str, Any],
    output_path: Optional[str] = None,
    gap_features: Optional[Dict[str, Any]] = None
):
    """Write Markdown output."""
    sys.path.insert(0, str(SCRIPT_DIR / "formatters"))
    from markdown_formatter import format_markdown

    md_str = format_markdown(result, gap_features=gap_features)

    if output_path:
        path = Path(output_path).with_suffix(".md")
        path.write_text(md_str)
        print(f"Markdown output written to: {path}", file=sys.stderr)
    else:
        print(md_str)


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Validate target directory
    if not os.path.isdir(args.target):
        print(f"Error: '{args.target}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load presets and determine active analyses
    presets = load_presets()
    analyses = get_active_analyses(args, presets)

    if args.verbose:
        print(f"X-Ray v{VERSION}", file=sys.stderr)

    # Run analysis
    result = run_analysis(args.target, analyses, args.verbose)

    # Add preset info if used
    if args.preset or not any(
        getattr(args, sw.replace("-", "_"), False)
        for sw in ANALYSIS_SWITCHES
    ):
        result["metadata"]["preset"] = args.preset or "full"

    # Collect gap feature flags
    gap_features = {
        "mermaid": getattr(args, "mermaid", False),
        "priority_scores": getattr(args, "priority_scores", False),
        "inline_skeletons": getattr(args, "inline_skeletons", None),
        "hazards": getattr(args, "hazards", False),
        "data_models": getattr(args, "data_models", False),
        "logic_maps": getattr(args, "logic_maps", None),
        "entry_points": getattr(args, "entry_points", False),
        "side_effects_detail": getattr(args, "side_effects_detail", False),
        "verify_imports": getattr(args, "verify_imports", False),
        "layer_details": getattr(args, "layer_details", False),
        "prose": getattr(args, "prose", False),
        "signatures": getattr(args, "signatures", False),
        "state_mutations": getattr(args, "state_mutations", False),
        "verify_commands": getattr(args, "verify_commands", False),
        "explain": getattr(args, "explain", False),
        "persona_map": getattr(args, "persona_map", False),
        "target_dir": args.target,
    }

    # Check if any gap features are enabled
    has_gap_features = any(
        v for k, v in gap_features.items()
        if k != "target_dir" and v
    )

    # Output results
    output_path = args.out or "./analysis"

    if args.output == "json":
        output_json(result, args.out)
    elif args.output == "markdown":
        output_markdown(result, args.out, gap_features if has_gap_features else None)
    elif args.output == "both":
        output_json(result, output_path)
        output_markdown(result, output_path, gap_features if has_gap_features else None)


if __name__ == "__main__":
    main()

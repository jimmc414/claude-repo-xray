#!/usr/bin/env python3
"""
Repo X-Ray: Unified Codebase Analysis Tool

Generates comprehensive analysis of Python codebases for AI coding agents.
Combines structural, behavioral, and historical signals in a single pass.

Usage:
    python xray.py ./target                       # Full analysis (all sections)
    python xray.py ./target --config my.json      # Use custom config
    python xray.py ./target --preset minimal      # Use minimal preset
    python xray.py ./target --no-mermaid          # Disable specific section
    python xray.py --init-config > .xray.json     # Generate config file

The tool uses a config-driven approach where all sections are enabled by default.
Users can customize output by:
  1. Creating a config file (--init-config) and modifying it
  2. Placing .xray.json in the project root
  3. Using --no-<section> flags to disable specific sections

Examples:
    python xray.py /path/to/repo
    python xray.py . --config configs/minimal.json
    python xray.py . --no-explain --no-persona-map
    python xray.py --init-config > .xray.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add lib directory to path
SCRIPT_DIR = Path(__file__).parent
LIB_DIR = SCRIPT_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

VERSION = "3.1.0"  # Added 9 new features: github_about, cli_args, instance_vars, etc.

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
Configuration:
  By default, all sections are enabled. Customize output by:
  1. Using --config to load a config file
  2. Placing .xray.json in the project root (auto-detected)
  3. Using --no-<section> flags to disable specific sections
  4. Using --preset for predefined configurations

Presets:
  minimal   Quick structural overview (~2K tokens)
  standard  Balanced analysis for most tasks (~8K tokens)
  full      Complete analysis with all signals [DEFAULT]

Examples:
  %(prog)s /path/to/repo                    # All sections enabled
  %(prog)s . --config my_config.json        # Use custom config
  %(prog)s . --no-explain --no-persona-map  # Disable specific sections
  %(prog)s --init-config > .xray.json       # Generate config template
"""
    )

    # Positional argument
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current directory)"
    )

    # Configuration options
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "--config",
        metavar="PATH",
        help="Load configuration from JSON file"
    )
    config_group.add_argument(
        "--init-config",
        action="store_true",
        dest="init_config",
        help="Print default config to stdout and exit"
    )
    config_group.add_argument(
        "--preset",
        choices=["minimal", "standard", "full"],
        default=None,
        help="Use predefined configuration preset"
    )

    # Section disable flags (--no-<section>)
    disable = parser.add_argument_group("Disable Sections (override config)")
    disable.add_argument("--no-prose", action="store_true", dest="no_prose", help="Disable prose summary")
    disable.add_argument("--no-mermaid", action="store_true", dest="no_mermaid", help="Disable Mermaid diagram")
    disable.add_argument("--no-priority-scores", action="store_true", dest="no_priority_scores", help="Disable priority scores")
    disable.add_argument("--no-critical-classes", action="store_true", dest="no_critical_classes", help="Disable critical classes")
    disable.add_argument("--no-data-models", action="store_true", dest="no_data_models", help="Disable data models")
    disable.add_argument("--no-logic-maps", action="store_true", dest="no_logic_maps", help="Disable logic maps")
    disable.add_argument("--no-hazards", action="store_true", dest="no_hazards", help="Disable hazards section")
    disable.add_argument("--no-entry-points", action="store_true", dest="no_entry_points", help="Disable entry points")
    disable.add_argument("--no-side-effects-detail", action="store_true", dest="no_side_effects_detail", help="Disable detailed side effects")
    disable.add_argument("--no-layer-details", action="store_true", dest="no_layer_details", help="Disable layer details")
    disable.add_argument("--no-verify-imports", action="store_true", dest="no_verify_imports", help="Disable import verification")
    disable.add_argument("--no-signatures", action="store_true", dest="no_signatures", help="Disable signatures")
    disable.add_argument("--no-state-mutations", action="store_true", dest="no_state_mutations", help="Disable state mutations")
    disable.add_argument("--no-verify-commands", action="store_true", dest="no_verify_commands", help="Disable verification commands")
    disable.add_argument("--no-explain", action="store_true", dest="no_explain", help="Disable explanatory text")
    disable.add_argument("--no-persona-map", action="store_true", dest="no_persona_map", help="Disable persona map")
    disable.add_argument("--no-investigation-targets", action="store_true", dest="no_investigation_targets", help="Disable investigation targets section")
    disable.add_argument("--no-blast-radius", action="store_true", dest="no_blast_radius", help="Disable blast radius analysis")
    disable.add_argument("--no-route-detection", action="store_true", dest="no_route_detection", help="Disable HTTP route detection")

    # Legacy analysis switches (for backwards compatibility)
    switches = parser.add_argument_group("Analysis Switches (legacy, for backwards compatibility)")
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

    # Legacy gap feature flags (for backwards compatibility)
    gap = parser.add_argument_group("Section Enable Flags (legacy, for backwards compatibility)")
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
    gap.add_argument("--explain", action="store_true", help="Add explanatory text before each section")
    gap.add_argument("--persona-map", action="store_true", dest="persona_map", help="Show agent prompts and personas")

    # Output options
    output = parser.add_argument_group("Output Options")
    output.add_argument(
        "--output",
        choices=["json", "markdown", "both"],
        default="markdown",
        help="Output format (default: markdown)"
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


def detect_language(target: str) -> str:
    """Detect the primary language of a project directory.

    Returns 'python', 'typescript', or 'mixed'.
    """
    ts_extensions = {".ts", ".tsx", ".mts", ".cts"}
    py_extensions = {".py"}
    ignore_dirs = {"node_modules", "dist", "build", ".git", "__pycache__", ".venv", "venv", ".next", ".nuxt"}

    has_ts = False
    has_py = False

    for dirpath, dirnames, filenames in os.walk(target):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in ts_extensions and not filename.endswith(".d.ts"):
                has_ts = True
            elif ext in py_extensions:
                has_py = True
            if has_ts and has_py:
                return "mixed"

    if has_ts:
        return "typescript"
    return "python"


def _find_ts_scanner(verbose: bool = False) -> Optional[Path]:
    """Locate the TS scanner binary. Search order:
    1. XRAY_TS_SCANNER env var (explicit path to index.js)
    2. Sibling directory ../repo-xray-ts-scanner/dist/index.js
    3. Legacy in-tree ts-scanner/dist/index.js
    """
    # 1. Explicit env var
    env_path = os.environ.get("XRAY_TS_SCANNER")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        if verbose:
            print(f"XRAY_TS_SCANNER={env_path} does not exist", file=sys.stderr)

    # 2. Sibling repo (common local dev layout)
    sibling = SCRIPT_DIR.parent / "repo-xray-ts-scanner" / "dist" / "index.js"
    if sibling.exists():
        return sibling

    # 3. Legacy in-tree path
    legacy = SCRIPT_DIR / "ts-scanner" / "dist" / "index.js"
    if legacy.exists():
        return legacy

    if verbose:
        print("TS scanner not found. Set XRAY_TS_SCANNER or clone repo-xray-ts-scanner as sibling directory.", file=sys.stderr)
    return None


def invoke_ts_scanner(target: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """Invoke the TypeScript scanner subprocess and return parsed JSON results.

    Uses a temp file for stdout to avoid pipe buffer truncation on large codebases.
    """
    import tempfile

    scanner_path = _find_ts_scanner(verbose)
    if not scanner_path:
        return None

    cmd = ["node", str(scanner_path), target]
    if verbose:
        cmd.append("--verbose")

    try:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        with open(tmp_path, "w") as stdout_file:
            proc = subprocess.run(
                cmd, stdout=stdout_file, stderr=subprocess.PIPE, text=True, timeout=120
            )

        # Exit code 0 = success, 2 = success with parse warnings
        if proc.returncode not in (0, 2):
            if verbose:
                print(f"TS scanner failed (exit {proc.returncode}): {proc.stderr[:200]}", file=sys.stderr)
            return None

        if verbose and proc.stderr:
            # Forward TS scanner verbose output
            for line in proc.stderr.strip().split("\n"):
                print(f"  [TS] {line}", file=sys.stderr)

        with open(tmp_path, "r") as f:
            return json.load(f)

    except FileNotFoundError:
        if verbose:
            print("Node.js not found — cannot run TS scanner", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        if verbose:
            print("TS scanner timed out after 120s", file=sys.stderr)
        return None
    except (json.JSONDecodeError, OSError) as e:
        if verbose:
            print(f"TS scanner output error: {e}", file=sys.stderr)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _augment_with_git(results: Dict[str, Any], target: str, analyses: List[str], verbose: bool) -> Dict[str, Any]:
    """Add git analysis to TS scanner results (git signals are language-agnostic)."""
    from git_analysis import (
        analyze_risk, analyze_coupling, analyze_freshness,
        analyze_commit_sizes, get_tracked_files,
        analyze_function_churn, analyze_coupling_clusters, analyze_velocity,
        _TS_EXTENSIONS
    )

    if "git" in analyses:
        if verbose:
            print("Running git analysis...", file=sys.stderr)
        try:
            lang = results.get("metadata", {}).get("language", "python")
            exts = _TS_EXTENSIONS if lang == "typescript" else (".py",)
            tracked_files = get_tracked_files(target, extensions=exts)
            risk = analyze_risk(target, tracked_files, verbose=verbose, extensions=exts)
            coupling = analyze_coupling(target, verbose=verbose, extensions=exts)
            freshness = analyze_freshness(target, tracked_files, verbose=verbose, extensions=exts)
            function_churn = analyze_function_churn(target, tracked_files, verbose=verbose, extensions=exts)
            coupling_clusters = analyze_coupling_clusters(coupling)
            velocity = analyze_velocity(target, tracked_files, verbose=verbose, extensions=exts)

            results["git"] = {
                "risk": risk,
                "coupling": coupling,
                "freshness": freshness,
                "function_churn": function_churn,
                "coupling_clusters": coupling_clusters,
                "velocity": velocity,
            }
        except Exception as e:
            if verbose:
                print(f"  Git analysis failed: {e}", file=sys.stderr)
            results["git"] = {"error": str(e)}

    return results


def run_analysis(target: str, analyses: List[str], verbose: bool = False) -> Dict[str, Any]:
    """
    Run the specified analyses on the target directory.

    This is the main orchestration function that calls individual analysis modules.
    Supports Python, TypeScript, and mixed-language projects.
    """
    from file_discovery import discover_python_files, load_ignore_patterns
    from ast_analysis import analyze_codebase
    from import_analysis import analyze_imports
    from call_analysis import analyze_calls
    from git_analysis import (
        analyze_risk, analyze_coupling, analyze_freshness,
        analyze_commit_sizes, get_tracked_files,
        analyze_function_churn, analyze_coupling_clusters, analyze_velocity
    )
    from tech_debt_analysis import analyze_tech_debt
    from test_analysis import analyze_tests

    if verbose:
        print(f"Analyzing: {target}", file=sys.stderr)
        print(f"Analyses: {', '.join(analyses)}", file=sys.stderr)

    # Detect project language
    language = detect_language(target)
    if verbose:
        print(f"Detected language: {language}", file=sys.stderr)

    # For pure TypeScript projects, delegate entirely to the TS scanner
    if language == "typescript":
        ts_results = invoke_ts_scanner(target, verbose=verbose)
        if ts_results:
            # Run git analysis on top of TS scanner results (git is language-agnostic)
            ts_results = _augment_with_git(ts_results, target, analyses, verbose)

            # Compute investigation targets for TS results
            try:
                from investigation_targets import compute_investigation_targets
                from gap_features import detect_entry_points, extract_data_models

                ast_results_ts = {"files": ts_results.get("structure", {}).get("files", {})}

                gap_results = {}
                gap_results["entry_points"] = detect_entry_points(ts_results, target)

                gap_results["data_models"] = extract_data_models(ts_results)

                ts_results["investigation_targets"] = compute_investigation_targets(
                    ast_results=ast_results_ts,
                    import_results=ts_results.get("imports", {}),
                    call_results=ts_results.get("calls", {}),
                    git_results=ts_results.get("git", {}),
                    gap_results=gap_results,
                    root_dir=target, verbose=verbose,
                )
            except Exception as e:
                if verbose:
                    print(f"  Investigation targets failed: {e}", file=sys.stderr)

            return ts_results
        # Fall through to Python pipeline if TS scanner not available
        if verbose:
            print("TS scanner unavailable, falling back to Python pipeline", file=sys.stderr)

    # Load ignore patterns
    ignore_dirs, ignore_exts, ignore_files = load_ignore_patterns()

    # Discover Python files
    if verbose:
        print("Discovering Python files...", file=sys.stderr)
    files = discover_python_files(target, ignore_dirs, ignore_exts, ignore_files)

    if verbose:
        print(f"Found {len(files)} Python files", file=sys.stderr)

    if not files:
        # Last resort: try TS scanner for mixed projects where no .py files found
        if language == "mixed":
            ts_results = invoke_ts_scanner(target, verbose=verbose)
            if ts_results:
                ts_results = _augment_with_git(ts_results, target, analyses, verbose)
                return ts_results

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

    # New scanner signals from AST analysis
    if ast_results:
        result["security_concerns"] = ast_results.get("security_concerns", {})
        result["silent_failures"] = ast_results.get("silent_failures", {})
        result["sql_strings"] = ast_results.get("sql_strings", {})
        result["deprecation_markers"] = ast_results.get("deprecation_markers", [])
        result["resource_leaks"] = ast_results.get("resource_leaks", {})

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

    # Route analysis (requires AST results with decorator_details)
    if ast_results:
        try:
            from route_analysis import analyze_routes
            if verbose:
                print("Running route analysis...", file=sys.stderr)
            route_results = analyze_routes(ast_results, verbose=verbose)
            if route_results.get("routes"):
                result["routes"] = route_results
        except Exception as e:
            if verbose:
                print(f"  Route analysis failed: {e}", file=sys.stderr)

    # Git analysis
    if "git" in analyses:
        if verbose:
            print("Running git analysis...", file=sys.stderr)
        try:
            tracked_files = get_tracked_files(target)
            risk = analyze_risk(target, tracked_files, verbose=verbose)
            coupling = analyze_coupling(target, verbose=verbose)
            freshness = analyze_freshness(target, tracked_files, verbose=verbose)

            # Derived git signals
            function_churn = analyze_function_churn(target, tracked_files, verbose=verbose)
            coupling_clusters = analyze_coupling_clusters(coupling)
            velocity = analyze_velocity(target, tracked_files, verbose=verbose)

            result["git"] = {
                "risk": risk,
                "coupling": coupling,
                "freshness": freshness,
                "function_churn": function_churn,
                "coupling_clusters": coupling_clusters,
                "velocity": velocity
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

        # Merge comment-based deprecations into deprecation_markers
        for dep in debt_results.get("deprecations", []):
            result.setdefault("deprecation_markers", []).append(dep)

    # Blast radius analysis (requires import + call results, benefits from git coupling)
    if result.get("imports"):
        try:
            from blast_analysis import analyze_blast_radius
            if verbose:
                print("Running blast radius analysis...", file=sys.stderr)
            blast_results = analyze_blast_radius(
                result.get("imports", {}),
                result.get("calls", {}),
                result.get("git", {}),
                verbose=verbose,
            )
            if blast_results.get("files"):
                result["blast_radius"] = blast_results
        except Exception as e:
            if verbose:
                print(f"  Blast radius analysis failed: {e}", file=sys.stderr)

    # Investigation targets (deep crawl signals from combined analysis results)
    # NOTE: This must run AFTER all other analyses because it reads their results.
    # Reordering the pipeline above may break this.
    try:
        from investigation_targets import compute_investigation_targets
        from gap_features import detect_entry_points, extract_data_models

        if verbose:
            print("Computing investigation targets...", file=sys.stderr)

        gap_results = {}
        if result.get("structure"):
            try:
                gap_results["entry_points"] = detect_entry_points(result, target)
            except Exception:
                gap_results["entry_points"] = []
            try:
                gap_results["data_models"] = extract_data_models(result)
            except Exception:
                gap_results["data_models"] = []

        investigation = compute_investigation_targets(
            ast_results=ast_results or {},
            import_results=result.get("imports", {}),
            call_results=result.get("calls", {}),
            git_results=result.get("git", {}),
            gap_results=gap_results,
            root_dir=target,
            verbose=verbose,
        )
        result["investigation_targets"] = investigation
    except Exception as e:
        if verbose:
            print(f"  Investigation targets failed: {e}", file=sys.stderr)

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


def config_to_gap_features(config: Dict[str, Any], target_dir: str) -> Dict[str, Any]:
    """
    Convert config sections to gap_features dict for backwards compatibility with formatter.

    This bridges the new config system with the existing formatter that expects gap_features dict.
    """
    sections = config.get("sections", {})

    # Helper to check if section is enabled
    def is_enabled(key):
        val = sections.get(key)
        if isinstance(val, dict):
            return val.get("enabled", True)
        return bool(val)

    # Helper to get count parameter
    def get_count(key, default=10):
        val = sections.get(key)
        if isinstance(val, dict):
            return val.get("count", default)
        return default

    return {
        "mermaid": is_enabled("mermaid"),
        "priority_scores": is_enabled("architectural_pillars") or is_enabled("maintenance_hotspots"),
        "architectural_pillars": is_enabled("architectural_pillars"),
        "maintenance_hotspots": is_enabled("maintenance_hotspots"),
        "inline_skeletons": get_count("critical_classes", 10) if is_enabled("critical_classes") else None,
        "hazards": is_enabled("hazards"),
        "data_models": is_enabled("data_models"),
        "logic_maps": get_count("logic_maps", 5) if is_enabled("logic_maps") else None,
        "entry_points": is_enabled("entry_points"),
        "side_effects_detail": is_enabled("side_effects_detail"),
        "verify_imports": is_enabled("verify_imports"),
        "layer_details": is_enabled("layer_details"),
        "prose": is_enabled("prose"),
        "signatures": is_enabled("signatures"),
        "state_mutations": is_enabled("state_mutations"),
        "verify_commands": is_enabled("verify_commands"),
        "explain": is_enabled("explain"),
        "persona_map": is_enabled("persona_map"),
        "environment_variables": is_enabled("environment_variables"),
        "target_dir": target_dir,
        # v3.1 features
        "github_about": is_enabled("github_about"),
        "data_flow": is_enabled("data_flow"),
        "cli_arguments": is_enabled("cli_arguments"),
        "instance_vars": is_enabled("instance_vars"),
        "pydantic_validators": is_enabled("pydantic_validators"),
        "hazard_patterns": is_enabled("hazard_patterns"),
        "env_defaults": is_enabled("env_defaults"),
        "test_example": is_enabled("test_example"),
        "linter_rules": is_enabled("linter_rules"),
        "investigation_targets": is_enabled("investigation_targets"),
        # v3.2 scanner enhancements
        "security_concerns": is_enabled("security_concerns"),
        "silent_failures": is_enabled("silent_failures"),
        "async_violations": is_enabled("async_violations"),
        "db_query_patterns": is_enabled("db_query_patterns"),
        "deprecation_markers": is_enabled("deprecation_markers"),
        # v3.3 codesight-inspired features
        "blast_radius": is_enabled("blast_radius"),
        "route_detection": is_enabled("route_detection"),
        "resource_leaks": is_enabled("resource_leaks"),
        "magic_methods": is_enabled("magic_methods"),
    }


def apply_disable_flags(config: Dict[str, Any], args) -> Dict[str, Any]:
    """Apply --no-<section> flags to disable sections in config."""
    import copy
    result = copy.deepcopy(config)
    sections = result.setdefault("sections", {})

    # Map --no-* flags to section keys
    disable_map = {
        "no_prose": "prose",
        "no_mermaid": "mermaid",
        "no_priority_scores": ["architectural_pillars", "maintenance_hotspots"],
        "no_critical_classes": "critical_classes",
        "no_data_models": "data_models",
        "no_logic_maps": "logic_maps",
        "no_hazards": "hazards",
        "no_entry_points": "entry_points",
        "no_side_effects_detail": "side_effects_detail",
        "no_layer_details": "layer_details",
        "no_verify_imports": "verify_imports",
        "no_signatures": "signatures",
        "no_state_mutations": "state_mutations",
        "no_verify_commands": "verify_commands",
        "no_explain": "explain",
        "no_persona_map": "persona_map",
        "no_investigation_targets": "investigation_targets",
        "no_blast_radius": "blast_radius",
        "no_route_detection": "route_detection",
    }

    for flag, section_keys in disable_map.items():
        if getattr(args, flag, False):
            if isinstance(section_keys, list):
                for key in section_keys:
                    if isinstance(sections.get(key), dict):
                        sections[key]["enabled"] = False
                    else:
                        sections[key] = False
            else:
                if isinstance(sections.get(section_keys), dict):
                    sections[section_keys]["enabled"] = False
                else:
                    sections[section_keys] = False

    return result


def main():
    """Main entry point."""
    from config_loader import load_config, generate_config_template, get_active_analyses as config_get_analyses

    parser = create_parser()
    args = parser.parse_args()

    # Handle --init-config
    if args.init_config:
        print(generate_config_template())
        sys.exit(0)

    # Validate target directory
    if not os.path.isdir(args.target):
        print(f"Error: '{args.target}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load configuration
    config_path = args.config
    if args.preset:
        # Map preset to config file
        preset_configs = {
            "minimal": SCRIPT_DIR / "configs" / "minimal.json",
            "standard": SCRIPT_DIR / "configs" / "standard.json",
            "full": SCRIPT_DIR / "configs" / "default_config.json",
        }
        preset_config = preset_configs.get(args.preset)
        if preset_config and preset_config.exists():
            config_path = str(preset_config)

    # Load config (checks .xray.json in target dir if no explicit config)
    config = load_config(config_path, args.target)

    # Apply --no-<section> flags
    config = apply_disable_flags(config, args)

    # Get active analyses from config
    analyses = config_get_analyses(config)

    if args.verbose:
        print(f"X-Ray v{VERSION}", file=sys.stderr)
        print(f"Config: {config_path or 'defaults'}", file=sys.stderr)

    # Run analysis
    result = run_analysis(args.target, analyses, args.verbose)

    # Add config info to metadata
    result["metadata"]["config"] = config_path or "defaults"
    result["metadata"]["preset"] = args.preset

    # Convert config to gap_features for formatter compatibility
    gap_features = config_to_gap_features(config, args.target)

    # Output results
    output_path = args.out or "./analysis"

    if args.output == "json":
        output_json(result, args.out)
    elif args.output == "markdown":
        output_markdown(result, args.out, gap_features)
    elif args.output == "both":
        output_json(result, output_path)
        output_markdown(result, output_path, gap_features)


if __name__ == "__main__":
    main()

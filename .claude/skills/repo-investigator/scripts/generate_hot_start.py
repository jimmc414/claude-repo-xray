#!/usr/bin/env python3
"""
Repo Investigator: HOT_START.md Generator

Generates a complete HOT_START.md semantic analysis document for any Python repository.
Combines all Phase 2 analysis tools into a single automated workflow.

Requires Phase 1 data (deps.json, git.json) or will generate them automatically.

Usage:
    python generate_hot_start.py /path/to/repo
    python generate_hot_start.py /path/to/repo -o HOT_START.md
    python generate_hot_start.py /path/to/repo --phase1-dir ./phase1_data
    python generate_hot_start.py /path/to/repo --debug -v

Features:
    - Single command generates complete semantic documentation
    - Automated Logic Map generation from AST analysis
    - Import verification with untested module prioritization
    - Integrates with Phase 1 outputs for unified priority scoring
"""

import argparse
import ast
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set

# =============================================================================
# Detail Level Configuration
# =============================================================================

DETAIL_LEVELS = {
    'compact': 1,
    'normal': 2,
    'verbose': 3,
    'full': 4,
    '1': 1,
    '2': 2,
    '3': 3,
    '4': 4,
}

DETAIL_LEVEL_HELP = """
Detail levels (name or number):
  1/compact  - Priority table + verification summary only (~500 tokens)
  2/normal   - Standard output with logic maps (~2,700 tokens) [default]
  3/verbose  - Preserve literals in logic maps (~5,000 tokens)
  4/full     - Add docstrings and method signatures (~8,000 tokens)
"""

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
REPO_XRAY_SCRIPTS = SKILL_ROOT.parent / "repo-xray" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_XRAY_SCRIPTS))

# Import Phase 2 tools
from complexity import (
    calculate_cc,
    load_phase1_data,
    scan_directory,
    normalize_dict,
    validate_phase1_inputs,
)
from smart_read import (
    smart_read,
    find_top_complex_methods,
    calculate_complexity,
)
from verify import (
    check_safe,
    scan_directory as verify_scan_directory,
)

# Import Phase 1 tools (for direct data generation)
try:
    from dependency_graph import build_dependency_graph, find_orphans, identify_layers
    PHASE1_AVAILABLE = True
except ImportError:
    PHASE1_AVAILABLE = False

# Import git analysis tools
try:
    from git_analysis import analyze_risk, analyze_coupling, analyze_freshness, get_tracked_files
    GIT_ANALYSIS_AVAILABLE = True
except ImportError:
    GIT_ANALYSIS_AVAILABLE = False


# =============================================================================
# Logic Map Generation
# =============================================================================

class LogicMapGenerator:
    """Generates Logic Maps from Python AST."""

    # Patterns that indicate side effects (more specific to reduce false positives)
    SIDE_EFFECT_PATTERNS = {
        'db': ['db.save', 'db.commit', 'session.commit', 'cursor.execute',
               'insert(', 'update(', 'delete(', 'query('],
        'api': ['requests.', 'httpx.', 'aiohttp.', '.post(', '.put(', '.patch(',
               'fetch(', 'api.send'],
        'file': ['file.write', '.write(', 'json.dump', 'pickle.dump', 'export('],
        'email': ['send_email', 'send_mail', 'notify(', 'smtp.send'],
        'cache': ['cache.set', 'redis.set', 'cache.invalidate', 'cache.clear'],
    }

    # Common stdlib/builtin patterns to exclude from side effect detection
    SAFE_PATTERNS = [
        '.get(',      # dict.get(), os.environ.get(), etc.
        'ast.get_',   # ast.get_docstring(), etc.
        'isupper',    # str.isupper()
        'islower',    # str.islower()
        'isdigit',    # str.isdigit()
        'isinstance', # builtin
        'hasattr',    # builtin
        'getattr',    # builtin
        'setattr',    # builtin (only mutates in-memory objects)
        'len(',       # builtin
        'str(',       # builtin
        'int(',       # builtin
        'list(',      # builtin
        'dict(',      # builtin
        'set(',       # builtin (Python set, not cache set)
        'open(',      # Only flag if followed by write mode
    ]

    # Patterns that indicate external input
    INPUT_PATTERNS = ['request.', 'input(', 'args.', 'params.', 'payload.', 'body.']

    def __init__(self, filepath: str, detail_level: int = 2):
        self.filepath = filepath
        self.detail_level = detail_level
        self.source = ""
        self.tree = None
        self.lines = []

    def parse(self) -> bool:
        """Parse the source file."""
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.source = f.read()
            self.tree = ast.parse(self.source)
            self.lines = self.source.splitlines()
            return True
        except Exception:
            return False

    def generate_logic_map(self, method_name: str) -> Optional[Dict]:
        """Generate a Logic Map for a specific method."""
        if not self.tree:
            return None

        # Find the method
        method_node = None
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_name:
                    method_node = node
                    break

        if not method_node:
            return None

        # Analyze the method
        logic_map = {
            'method': method_name,
            'line': method_node.lineno,
            'complexity': calculate_complexity(method_node),
            'flow': [],
            'side_effects': [],
            'inputs': [],
            'state_mutations': [],
            'conditions': [],
            'signature': None,
            'docstring': None,
        }

        # Extract signature and docstring at full detail level
        if self.detail_level >= 4:
            logic_map['signature'] = self._extract_signature(method_node)
            docstring = ast.get_docstring(method_node)
            if docstring:
                # Truncate long docstrings to first line or 100 chars
                first_line = docstring.strip().split('\n')[0]
                logic_map['docstring'] = first_line[:100] + "..." if len(first_line) > 100 else first_line

        self._analyze_node(method_node, logic_map)

        return logic_map

    def _analyze_node(self, node: ast.AST, logic_map: Dict, depth: int = 0):
        """Recursively analyze AST nodes to build logic map."""
        prefix = "  " * depth

        for child in ast.iter_child_nodes(node):
            # Conditionals
            if isinstance(child, ast.If):
                condition = self._get_condition_text(child.test)
                logic_map['conditions'].append(condition)
                logic_map['flow'].append(f"{prefix}-> {condition}?")
                self._analyze_node(child, logic_map, depth + 1)

            # Loops
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                target = self._node_to_text(child.target)
                iter_name = self._node_to_text(child.iter)
                logic_map['flow'].append(f"{prefix}* for {target} in {iter_name}:")
                self._analyze_node(child, logic_map, depth + 1)

            elif isinstance(child, ast.While):
                condition = self._get_condition_text(child.test)
                logic_map['flow'].append(f"{prefix}* while {condition}:")
                self._analyze_node(child, logic_map, depth + 1)

            # Function calls - check for side effects
            elif isinstance(child, ast.Call):
                call_text = self._get_call_text(child)
                side_effect = self._detect_side_effect(call_text)
                if side_effect:
                    logic_map['side_effects'].append(side_effect)
                    logic_map['flow'].append(f"{prefix}[{side_effect}]")
                elif self._is_external_input(call_text):
                    logic_map['inputs'].append(call_text)
                    logic_map['flow'].append(f"{prefix}<{call_text}>")

            # Assignments - check for state mutations
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Attribute):
                        # self.x = ... is a state mutation
                        if isinstance(target.value, ast.Name) and target.value.id == 'self':
                            mutation = f"self.{target.attr}"
                            logic_map['state_mutations'].append(mutation)
                            logic_map['flow'].append(f"{prefix}{{{mutation}}}")

            # Return statements
            elif isinstance(child, ast.Return):
                if child.value:
                    ret_text = self._node_to_text(child.value)
                    logic_map['flow'].append(f"{prefix}-> Return({ret_text})")
                else:
                    logic_map['flow'].append(f"{prefix}-> Return")

            # Exception handling
            elif isinstance(child, ast.Try):
                logic_map['flow'].append(f"{prefix}try:")
                self._analyze_node(child, logic_map, depth + 1)
                for handler in child.handlers:
                    exc_type = handler.type.id if handler.type and hasattr(handler.type, 'id') else "Exception"
                    logic_map['flow'].append(f"{prefix}! except {exc_type}")

            # Recurse into other nodes
            else:
                self._analyze_node(child, logic_map, depth)

    def _get_condition_text(self, node: ast.AST) -> str:
        """Extract readable text from a condition node."""
        if isinstance(node, ast.Compare):
            left = self._node_to_text(node.left)
            ops = [self._op_to_text(op) for op in node.ops]
            comparators = [self._node_to_text(c) for c in node.comparators]
            parts = [left]
            for op, comp in zip(ops, comparators):
                parts.extend([op, comp])
            return " ".join(parts)
        elif isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            values = [self._get_condition_text(v) for v in node.values]
            return f" {op} ".join(values)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"not {self._get_condition_text(node.operand)}"
        else:
            return self._node_to_text(node)

    def _node_to_text(self, node: ast.AST) -> str:
        """Convert AST node to readable text."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._node_to_text(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_call_text(node)
        elif isinstance(node, ast.Constant):
            # Always preserve string literals at verbose+ (important for understanding)
            if isinstance(node.value, str):
                if self.detail_level >= 3:
                    # Truncate long strings
                    val = node.value[:30] + "..." if len(node.value) > 30 else node.value
                    return repr(val)
                return "..."
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            if self.detail_level >= 3:
                slice_text = self._node_to_text(node.slice)
                return f"{self._node_to_text(node.value)}[{slice_text}]"
            return f"{self._node_to_text(node.value)}[...]"
        elif isinstance(node, ast.List):
            if self.detail_level >= 4 and len(node.elts) <= 3:
                items = [self._node_to_text(e) for e in node.elts]
                return f"[{', '.join(items)}]"
            return "[...]"
        elif isinstance(node, ast.Dict):
            return "{...}"
        elif isinstance(node, ast.Tuple):
            if self.detail_level >= 3 and len(node.elts) <= 3:
                items = [self._node_to_text(e) for e in node.elts]
                return f"({', '.join(items)})"
            return "(...)"
        else:
            return "..."

    def _get_call_text(self, node: ast.Call) -> str:
        """Get text representation of a function call."""
        func_name = self._node_to_text(node.func)

        # At verbose+, preserve important string arguments (like file extensions, patterns)
        if self.detail_level >= 3 and node.args:
            preserved_args = []
            for arg in node.args[:2]:  # Only first 2 args to keep it readable
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    val = arg.value[:20] + "..." if len(arg.value) > 20 else arg.value
                    preserved_args.append(repr(val))
                elif isinstance(arg, ast.Name):
                    preserved_args.append(arg.id)
                else:
                    preserved_args.append("...")
            if preserved_args:
                return f"{func_name}({', '.join(preserved_args)})"

        return f"{func_name}(...)"

    def _op_to_text(self, op: ast.AST) -> str:
        """Convert comparison operator to text."""
        ops = {
            ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
            ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
            ast.In: "in", ast.NotIn: "not in",
        }
        return ops.get(type(op), "?")

    def _detect_side_effect(self, call_text: str) -> Optional[str]:
        """Detect if a call has side effects."""
        call_lower = call_text.lower()

        # First check for safe patterns (stdlib/builtins) - skip these
        for safe in self.SAFE_PATTERNS:
            if safe in call_lower:
                return None

        # Then check for actual side effect patterns
        for category, patterns in self.SIDE_EFFECT_PATTERNS.items():
            for pattern in patterns:
                if pattern in call_lower:
                    return f"{category.upper()}: {call_text}"
        return None

    def _is_external_input(self, call_text: str) -> bool:
        """Check if a call represents external input."""
        call_lower = call_text.lower()
        return any(pattern in call_lower for pattern in self.INPUT_PATTERNS)

    def _extract_signature(self, node: ast.FunctionDef) -> str:
        """Extract method signature with type hints."""
        parts = []

        # Function name
        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        parts.append(f"{async_prefix}def {node.name}(")

        # Arguments
        args = []
        defaults_offset = len(node.args.args) - len(node.args.defaults)

        for i, arg in enumerate(node.args.args):
            arg_str = arg.arg
            # Add type annotation if present
            if arg.annotation:
                arg_str += f": {self._annotation_to_text(arg.annotation)}"
            # Add default value if present
            default_idx = i - defaults_offset
            if default_idx >= 0 and default_idx < len(node.args.defaults):
                default = node.args.defaults[default_idx]
                arg_str += f"={self._node_to_text(default)}"
            args.append(arg_str)

        # *args
        if node.args.vararg:
            arg_str = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                arg_str += f": {self._annotation_to_text(node.args.vararg.annotation)}"
            args.append(arg_str)

        # **kwargs
        if node.args.kwarg:
            arg_str = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                arg_str += f": {self._annotation_to_text(node.args.kwarg.annotation)}"
            args.append(arg_str)

        parts.append(", ".join(args))
        parts.append(")")

        # Return type
        if node.returns:
            parts.append(f" -> {self._annotation_to_text(node.returns)}")

        return "".join(parts)

    def _annotation_to_text(self, node: ast.AST) -> str:
        """Convert type annotation to text."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Subscript):
            base = self._annotation_to_text(node.value)
            if isinstance(node.slice, ast.Tuple):
                items = [self._annotation_to_text(e) for e in node.slice.elts]
                return f"{base}[{', '.join(items)}]"
            else:
                return f"{base}[{self._annotation_to_text(node.slice)}]"
        elif isinstance(node, ast.Attribute):
            return f"{self._annotation_to_text(node.value)}.{node.attr}"
        elif isinstance(node, ast.Constant):
            return repr(node.value) if isinstance(node.value, str) else str(node.value)
        else:
            return "..."


def generate_logic_map_text(logic_map: Dict) -> str:
    """Convert a logic map dictionary to arrow notation text."""
    lines = [f"{logic_map['method']}():"]

    if logic_map['flow']:
        for item in logic_map['flow']:
            lines.append(f"  {item}")
    else:
        lines.append("  -> (simple flow)")

    return "\n".join(lines)


# =============================================================================
# Phase 1 Data Management
# =============================================================================

def ensure_phase1_data(
    directory: str,
    phase1_dir: Optional[str],
    verbose: bool = False
) -> Tuple[str, str, Optional[str]]:
    """
    Ensure Phase 1 data exists, generating if necessary.

    Returns:
        Tuple of (deps_path, git_path, warm_start_debug_path)
    """
    if phase1_dir:
        deps_path = os.path.join(phase1_dir, "deps.json")
        git_path = os.path.join(phase1_dir, "git.json")
        warm_start_debug = os.path.join(phase1_dir, "WARM_START_debug")
        if os.path.exists(warm_start_debug):
            return deps_path, git_path, warm_start_debug
        return deps_path, git_path, None

    # Check for existing files in current directory
    if os.path.exists("deps.json") and os.path.exists("git.json"):
        warm_start_debug = "WARM_START_debug" if os.path.exists("WARM_START_debug") else None
        return "deps.json", "git.json", warm_start_debug

    # Phase 1 data not found - continue without it
    if verbose:
        print("Phase 1 data not found. Continuing with CC-only analysis.", file=sys.stderr)
        print("  For full unified scoring, first run:", file=sys.stderr)
        print("    python .../repo-xray/scripts/dependency_graph.py <dir> --json > deps.json", file=sys.stderr)
        print("    python .../repo-xray/scripts/git_analysis.py <dir> --json > git.json", file=sys.stderr)

    return "", "", None


# =============================================================================
# Main Generation
# =============================================================================

def collect_analysis_data(
    directory: str,
    deps_path: str,
    git_path: str,
    warm_start_debug: Optional[str],
    top_n: int = 10,
    verbose: bool = False,
    detail_level: int = 2
) -> Dict[str, Any]:
    """Collect all analysis data for HOT_START generation."""

    data = {
        "project_name": Path(directory).resolve().name,
        "timestamp": datetime.now().isoformat(),
        "detail_level": detail_level,
        "priorities": [],
        "logic_maps": [],
        "verification": [],
        "hidden_deps": {
            "env_vars": [],
            "external_services": [],
            "config_files": [],
        },
        "dependency_graph": {
            "modules": {},
            "edges": [],
            "import_weights": {},
            "external_deps": {},
            "circular": [],
            "orphans": [],
            "layers": {},
        },
        "git_analysis": {
            "risk": [],
            "coupling": [],
            "freshness": {},
        },
    }

    # Generate Phase 1 data directly if available
    imports = {}
    risks = {}
    freshness = {}
    test_coverage = {}
    dep_graph = None

    if PHASE1_AVAILABLE:
        if verbose:
            print("Generating dependency graph (Phase 1)...", file=sys.stderr)
        try:
            dep_graph = build_dependency_graph(directory)
            modules = dep_graph.get("modules", {})
            edges = dep_graph.get("internal_edges", [])

            # Calculate import weights (how many modules import each module)
            import_weights = {}
            for mod_name, info in modules.items():
                for imp in info.get("imports", []):
                    import_weights[imp] = import_weights.get(imp, 0) + 1

            # Create module name to filepath mapping
            mod_to_file = {}
            for mod_name, info in modules.items():
                filepath = info.get("file", "")
                if filepath:
                    mod_to_file[mod_name] = filepath
                    # Also map short module name
                    short_name = mod_name.split(".")[-1]
                    if short_name not in mod_to_file:
                        mod_to_file[short_name] = filepath

            # Normalize import weights and map to filepaths
            if import_weights:
                max_weight = max(import_weights.values())
                # Create imports dict keyed by filepath
                for mod_name, weight in import_weights.items():
                    norm_weight = weight / max_weight
                    # Try to find the filepath for this module
                    if mod_name in mod_to_file:
                        imports[mod_to_file[mod_name]] = norm_weight
                    # Also try short name
                    short_name = mod_name.split(".")[-1]
                    if short_name in mod_to_file:
                        imports[mod_to_file[short_name]] = norm_weight
                    # Keep module name as fallback
                    imports[mod_name] = norm_weight

            # Store raw dependency data
            data["dependency_graph"]["modules"] = {
                k: {"file": v.get("file", ""), "imports": v.get("imports", [])}
                for k, v in modules.items()
            }
            data["dependency_graph"]["edges"] = edges
            data["dependency_graph"]["import_weights"] = import_weights
            data["dependency_graph"]["external_deps"] = dep_graph.get("external_deps", {})
            data["dependency_graph"]["circular"] = dep_graph.get("circular", [])
            # Generate layer classification
            layers = identify_layers(dep_graph)
            data["dependency_graph"]["layers"] = layers

            # Find orphans
            try:
                orphans = find_orphans(dep_graph)
                data["dependency_graph"]["orphans"] = orphans
            except Exception:
                pass

            if verbose:
                print(f"  Found {len(modules)} modules, {len(edges)} internal edges", file=sys.stderr)
                if data["dependency_graph"]["circular"]:
                    print(f"  Circular dependencies: {len(data['dependency_graph']['circular'])}", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not generate dependency graph: {e}", file=sys.stderr)

    # Generate Git analysis data directly
    if GIT_ANALYSIS_AVAILABLE:
        if verbose:
            print("Running git analysis...", file=sys.stderr)
        try:
            # Get tracked files
            tracked_files = get_tracked_files(directory)

            # Analyze risk
            risk_data = analyze_risk(directory, tracked_files, months=6, verbose=False)
            data["git_analysis"]["risk"] = risk_data
            for r in risk_data:
                rel_path = r.get("file", "")
                risks[rel_path] = r.get("risk_score", 0)

            # Analyze coupling
            coupling_data = analyze_coupling(directory, max_commits=200, min_cooccurrences=3, verbose=False)
            data["git_analysis"]["coupling"] = coupling_data

            # Analyze freshness
            freshness_data = analyze_freshness(directory, tracked_files, verbose=False)
            data["git_analysis"]["freshness"] = freshness_data

            if verbose:
                print(f"  Risk files: {len(risk_data)}, Coupling pairs: {len(coupling_data)}", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not run git analysis: {e}", file=sys.stderr)

    # Fall back to JSON files if direct generation failed
    if not imports and deps_path and os.path.exists(deps_path) and git_path and os.path.exists(git_path):
        if verbose:
            print("Loading Phase 1 data from JSON...", file=sys.stderr)
        imports, risks, freshness, test_coverage = load_phase1_data(
            deps_path, git_path, warm_start_debug, verbose
        )

    # Scan for Python files
    if verbose:
        print("Scanning for Python files...", file=sys.stderr)

    files = scan_directory(directory, verbose=verbose)

    if not files:
        if verbose:
            print("No Python files found", file=sys.stderr)
        return data

    # Calculate complexity scores
    if verbose:
        print("Calculating complexity scores...", file=sys.stderr)

    raw_cc = {}
    all_hotspots = {}

    for filepath in files:
        cc, methods = calculate_cc(filepath, verbose=False)
        if cc > 0:
            raw_cc[filepath] = cc
            all_hotspots[filepath] = methods

    # Normalize and calculate unified scores
    norm_cc = normalize_dict(raw_cc)
    norm_imports = normalize_dict(imports)

    use_5_signal = bool(test_coverage)

    results = []
    for filepath, cc_val in raw_cc.items():
        rel_path = os.path.relpath(filepath, directory)

        s_cc = norm_cc.get(filepath, 0)
        s_imp = norm_imports.get(filepath, 0) or norm_imports.get(rel_path, 0)
        s_risk = risks.get(rel_path, 0)
        s_fresh = freshness.get(rel_path, 0.5)
        s_untested = test_coverage.get(rel_path, 0.5)

        if use_5_signal:
            score = (s_cc * 0.30) + (s_imp * 0.20) + (s_risk * 0.20) + (s_fresh * 0.15) + (s_untested * 0.15)
        elif imports or risks:
            score = (s_cc * 0.35) + (s_imp * 0.25) + (s_risk * 0.25) + (s_fresh * 0.15)
        else:
            score = s_cc

        results.append({
            "path": rel_path,
            "full_path": filepath,
            "score": round(score, 3),
            "metrics": {
                "cc": cc_val,
                "imp_score": round(s_imp, 2),
                "risk": round(s_risk, 2),
                "freshness": round(s_fresh, 2),
                "untested": round(s_untested, 2) if use_5_signal else None,
            },
            "hotspots": all_hotspots.get(filepath, {}),
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    data["priorities"] = results[:top_n]

    # Generate Logic Maps for top files
    if verbose:
        print(f"Generating Logic Maps for top {min(5, len(data['priorities']))} files...", file=sys.stderr)

    for priority in data["priorities"][:5]:
        filepath = priority["full_path"]
        hotspots = priority["hotspots"]

        if not hotspots:
            continue

        generator = LogicMapGenerator(filepath, detail_level)
        if not generator.parse():
            continue

        # Generate logic map for top 2 complex methods
        top_methods = sorted(hotspots.items(), key=lambda x: x[1], reverse=True)[:2]

        for method_name, cc in top_methods:
            logic_map = generator.generate_logic_map(method_name)
            if logic_map:
                logic_map["file"] = priority["path"]
                logic_map["priority_score"] = priority["score"]
                data["logic_maps"].append(logic_map)

    # Run verification
    if verbose:
        print("Running import verification...", file=sys.stderr)

    for filepath in files[:20]:  # Limit to first 20 files
        rel_path = os.path.relpath(filepath, directory)
        ok, msg, warnings = check_safe(filepath, verbose=False)
        data["verification"].append({
            "file": rel_path,
            "status": "OK" if ok else "FAIL",
            "message": msg,
            "warnings": warnings,
        })

    # Detect hidden dependencies
    if verbose:
        print("Detecting hidden dependencies...", file=sys.stderr)

    data["hidden_deps"] = detect_hidden_dependencies(files, verbose)

    return data


def detect_hidden_dependencies(files: List[str], verbose: bool = False) -> Dict:
    """Detect environment variables, external services, and config files."""
    hidden = {
        "env_vars": set(),
        "external_services": set(),
        "config_files": set(),
    }

    env_patterns = [
        r'os\.environ\.get\(["\'](\w+)["\']',
        r'os\.environ\[["\'](\w+)["\']',
        r'os\.getenv\(["\'](\w+)["\']',
        r'environ\.get\(["\'](\w+)["\']',
    ]

    # Map service categories to their import patterns
    service_patterns = {
        'database': ['psycopg2', 'pymongo', 'sqlalchemy', 'sqlite3', 'mysql', 'pymysql'],
        'cache': ['redis', 'memcache', 'pylibmc'],
        'queue': ['celery', 'pika', 'kafka', 'kombu'],  # pika for rabbitmq
        'storage': ['boto3', 'google.cloud.storage', 'azure.storage'],
        'api': ['requests', 'httpx', 'aiohttp', 'urllib3'],
    }

    config_patterns = [
        r'open\(["\']([^"\']+\.(?:json|yaml|yml|toml|ini|cfg|env))["\']',
        r'load\(["\']([^"\']+\.(?:json|yaml|yml|toml))["\']',
        r'Path\(["\']([^"\']+\.(?:json|yaml|yml|toml|ini|cfg))["\']',
    ]

    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find env vars
            for pattern in env_patterns:
                for match in re.finditer(pattern, content):
                    hidden["env_vars"].add(match.group(1))

            # Find external services - check for actual import statements
            for service, imports in service_patterns.items():
                for imp in imports:
                    # Match: import X, from X import, from X.Y import
                    import_pattern = rf'(?:^|\n)\s*(?:import\s+{re.escape(imp)}|from\s+{re.escape(imp)}(?:\.\w+)*\s+import)'
                    if re.search(import_pattern, content):
                        hidden["external_services"].add(service)

            # Find config files
            for pattern in config_patterns:
                for match in re.finditer(pattern, content):
                    hidden["config_files"].add(match.group(1))

        except Exception:
            continue

    return {
        "env_vars": sorted(hidden["env_vars"]),
        "external_services": sorted(hidden["external_services"]),
        "config_files": sorted(hidden["config_files"]),
    }


def generate_hot_start_md(data: Dict, detail_level: int = 2) -> str:
    """Generate HOT_START.md content from collected data.

    Detail levels:
        1 (compact): Priority table + verification summary only
        2 (normal): Standard output with logic maps
        3 (verbose): Preserve literals in logic maps
        4 (full): Add docstrings and method signatures
    """
    lines = []
    level_names = {1: 'compact', 2: 'normal', 3: 'verbose', 4: 'full'}

    # Header
    lines.append(f"# {data['project_name']}: Semantic Hot Start (Pass 2: Behavioral Analysis)")
    lines.append("")
    lines.append(f"> Semantic analysis companion to WARM_START.md")
    lines.append(f"> Generated: {data['timestamp']}")
    lines.append(f"> Priority files analyzed: {len(data['priorities'])}")
    lines.append(f"> Detail level: {detail_level} ({level_names.get(detail_level, 'unknown')})")
    lines.append(">")
    lines.append("> **Pass 2** extracts behavioral metadata: control flow, logic maps, method signatures, and module relationships.")
    lines.append("> See **WARM_START.md** for Pass 1 (structural analysis).")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 1: System Dynamics
    lines.append("## 1. System Dynamics")
    lines.append("")
    lines.append("High-density logic maps of the system's critical paths.")
    lines.append("")

    # Priority table
    lines.append("### Targeting Summary")
    lines.append("")
    lines.append("| Rank | File | Priority Score | Factors |")
    lines.append("|------|------|----------------|---------|")

    for i, p in enumerate(data["priorities"], 1):
        m = p["metrics"]
        factors = f"CC:{m['cc']} Imp:{m['imp_score']} Risk:{m['risk']}"
        if m.get("untested") is not None:
            factors += f" Untested:{m['untested']}"
        lines.append(f"| {i} | `{p['path']}` | {p['score']} | {factors} |")

    lines.append("")
    lines.append("**Factor Legend**: CC=Cyclomatic Complexity, Imp=Import Weight (how many modules depend on this), Risk=Git churn risk score, Untested=No test coverage detected")
    lines.append("")

    # Add Mermaid architecture diagram
    dep_graph = data.get("dependency_graph", {})
    edges = dep_graph.get("edges", [])
    layers = dep_graph.get("layers", {})

    if edges or layers:
        lines.append("### Architecture Overview")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph TD")

        # Group by layers if available
        if layers:
            for layer_name in ["orchestration", "core", "foundation"]:
                layer_modules = layers.get(layer_name, [])
                if layer_modules:
                    lines.append(f"    subgraph {layer_name.upper()}")
                    for mod in layer_modules[:8]:  # Limit to 8 per layer
                        short = mod.split(".")[-1] if "." in mod else mod
                        lines.append(f"        {mod.replace('.', '_').replace('-', '_')}[{short}]")
                    lines.append("    end")

        # Add edges (limited to keep diagram readable)
        shown_edges = set()
        for a, b in edges[:20]:
            a_id = a.replace(".", "_").replace("-", "_")
            b_id = b.replace(".", "_").replace("-", "_")
            edge_key = f"{a_id}->{b_id}"
            if edge_key not in shown_edges:
                lines.append(f"    {a_id} --> {b_id}")
                shown_edges.add(edge_key)

        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("")

    # At compact level, skip logic maps entirely
    if detail_level == 1:
        # Just show verification summary
        ok_count = sum(1 for v in data["verification"] if v["status"] == "OK")
        fail_count = len(data["verification"]) - ok_count
        lines.append("## 2. Verification Summary")
        lines.append("")
        lines.append(f"**Status**: {ok_count} passed, {fail_count} failed")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Use `--detail normal` or higher for Logic Maps and full analysis.*")
        lines.append("")
        return "\n".join(lines)

    # Section 2: Logic Maps (level 2+)
    lines.append("## 2. Logic Maps")
    lines.append("")

    if data["logic_maps"]:
        for lm in data["logic_maps"]:
            lines.append(f"### {lm['method']}")
            lines.append("")

            # At full level, show signature and docstring
            if detail_level >= 4:
                if lm.get("signature"):
                    lines.append(f"```python")
                    lines.append(lm["signature"])
                    lines.append("```")
                    lines.append("")
                if lm.get("docstring"):
                    lines.append(f"> {lm['docstring']}")
                    lines.append("")

            lines.append(f"**Entry Point**: `{lm['file']}:{lm['method']}` (L{lm['line']})")
            lines.append(f"**Complexity**: CC={lm['complexity']}")
            lines.append(f"**Priority Score**: {lm['priority_score']}")
            lines.append("")

            # Data Flow
            lines.append("#### Data Flow")
            lines.append("```")
            lines.append(generate_logic_map_text(lm))
            lines.append("```")
            lines.append("")

            # Side Effects
            if lm["side_effects"]:
                lines.append("#### Side Effects")
                for se in lm["side_effects"]:
                    lines.append(f"- {se}")
                lines.append("")

            # State Mutations
            if lm["state_mutations"]:
                lines.append("#### State Mutations")
                for sm in lm["state_mutations"]:
                    lines.append(f"- `{sm}`")
                lines.append("")

            lines.append("---")
            lines.append("")
    else:
        lines.append("*No complex methods detected for Logic Map generation.*")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Section 3: Dependency Verification
    lines.append("## 3. Dependency Verification")
    lines.append("")

    ok_count = sum(1 for v in data["verification"] if v["status"] == "OK")
    fail_count = len(data["verification"]) - ok_count

    lines.append(f"**Summary**: {ok_count} passed, {fail_count} failed")
    lines.append("")

    # Verified Modules
    lines.append("### Verified Modules")
    verified = [v for v in data["verification"] if v["status"] == "OK"]
    if verified:
        for v in verified[:10]:
            lines.append(f"- `{v['file']}`")
    else:
        lines.append("*None verified*")
    lines.append("")

    # Broken Paths
    lines.append("### Broken Paths")
    broken = [v for v in data["verification"] if v["status"] == "FAIL"]
    if broken:
        for v in broken:
            lines.append(f"- `{v['file']}`: {v['message']}")
    else:
        lines.append("*None detected*")
    lines.append("")

    # Warnings
    lines.append("### Warnings")
    warnings = [v for v in data["verification"] if v["warnings"]]
    if warnings:
        for v in warnings[:5]:
            for w in v["warnings"]:
                lines.append(f"- `{v['file']}`: {w}")
    else:
        lines.append("*No warnings*")
    lines.append("")

    lines.append("---")
    lines.append("")

    # Section 4: Hidden Dependencies
    lines.append("## 4. Hidden Dependencies")
    lines.append("")

    # Environment Variables
    lines.append("### Environment Variables")
    if data["hidden_deps"]["env_vars"]:
        lines.append("")
        lines.append("| Variable | Required |")
        lines.append("|----------|----------|")
        for var in data["hidden_deps"]["env_vars"]:
            lines.append(f"| `{var}` | ? |")
    else:
        lines.append("*None detected*")
    lines.append("")

    # External Services
    lines.append("### External Services")
    if data["hidden_deps"]["external_services"]:
        lines.append("")
        lines.append("| Service | Purpose |")
        lines.append("|---------|---------|")
        for svc in data["hidden_deps"]["external_services"]:
            lines.append(f"| {svc} | - |")
    else:
        lines.append("*None detected*")
    lines.append("")

    # Config Files
    lines.append("### Configuration Files")
    if data["hidden_deps"]["config_files"]:
        for cfg in data["hidden_deps"]["config_files"]:
            lines.append(f"- `{cfg}`")
    else:
        lines.append("*None detected*")
    lines.append("")

    lines.append("---")
    lines.append("")

    # Section 5: Module Dependencies (from Phase 1)
    lines.append("## 5. Module Dependencies")
    lines.append("")

    dep_graph = data.get("dependency_graph", {})
    edges = dep_graph.get("edges", [])
    import_weights = dep_graph.get("import_weights", {})
    external_deps = dep_graph.get("external_deps", {})
    circular = dep_graph.get("circular", [])
    orphans = dep_graph.get("orphans", [])

    if edges or import_weights:
        # Show most-imported modules (foundation modules)
        if import_weights:
            lines.append("### Foundation Modules")
            lines.append("")
            lines.append("Modules imported by multiple other modules (high import weight):")
            lines.append("")
            lines.append("| Module | Imported By |")
            lines.append("|--------|-------------|")
            sorted_weights = sorted(import_weights.items(), key=lambda x: -x[1])
            for mod, count in sorted_weights[:15]:  # Show more
                if count > 0:
                    lines.append(f"| `{mod}` | {count} modules |")
            lines.append("")

        # Show dependency edges
        if edges:
            lines.append("### Internal Dependencies")
            lines.append("")
            lines.append("How modules connect (A imports B):")
            lines.append("")
            lines.append("```")
            # Group by source module
            edge_by_source = {}
            for a, b in edges:
                if a not in edge_by_source:
                    edge_by_source[a] = []
                edge_by_source[a].append(b)

            for source in sorted(edge_by_source.keys()):
                targets = edge_by_source[source]
                # Shorten module names for display
                short_source = source.split(".")[-1] if "." in source else source
                short_targets = [t.split(".")[-1] if "." in t else t for t in targets]
                lines.append(f"{short_source} -> {', '.join(short_targets)}")
            lines.append("```")
            lines.append("")

        # External dependencies
        if external_deps:
            all_external = set()
            for deps in external_deps.values():
                all_external.update(deps)
            if all_external:
                lines.append("### External Dependencies")
                lines.append("")
                lines.append("Third-party packages detected (inferred from imports):")
                lines.append("")
                lines.append(f"`{', '.join(sorted(all_external))}`")
                lines.append("")

        # Circular dependencies
        if circular:
            lines.append("### Circular Dependencies ⚠️")
            lines.append("")
            lines.append("| Module A | Module B |")
            lines.append("|----------|----------|")
            for a, b in circular[:10]:
                short_a = a.split(".")[-1] if "." in a else a
                short_b = b.split(".")[-1] if "." in b else b
                lines.append(f"| `{short_a}` | `{short_b}` |")
            lines.append("")

        # Orphan files
        if orphans:
            lines.append("### Orphan Candidates")
            lines.append("")
            lines.append("Files with zero importers (may be entry points, dead code, or utility scripts):")
            lines.append("")
            lines.append("| File | Confidence | Notes |")
            lines.append("|------|------------|-------|")
            for o in orphans[:10]:
                lines.append(f"| `{o.get('file', '')}` | {o.get('confidence', 0):.2f} | {o.get('notes', '')} |")
            lines.append("")
    else:
        lines.append("*No internal dependencies detected (Phase 1 data not available)*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Section 5.5: Git Analysis
    git_data = data.get("git_analysis", {})
    risk_data = git_data.get("risk", [])
    coupling_data = git_data.get("coupling", [])
    freshness_data = git_data.get("freshness", {})

    if risk_data or coupling_data or freshness_data:
        lines.append("## 5.5 Git Analysis")
        lines.append("")

        # Risk analysis
        if risk_data:
            lines.append("### High-Risk Files")
            lines.append("")
            lines.append("Files with high churn and hotfix density (volatile):")
            lines.append("")
            lines.append("| Risk | File | Factors |")
            lines.append("|------|------|---------|")
            for r in risk_data[:15]:
                risk_score = r.get("risk_score", 0)
                filepath = r.get("file", "")
                churn = r.get("churn", 0)
                hotfixes = r.get("hotfixes", 0)
                authors = r.get("authors", 0)
                lines.append(f"| {risk_score:.2f} | `{filepath}` | churn:{churn} hotfix:{hotfixes} authors:{authors} |")
            lines.append("")

        # Coupling analysis
        if coupling_data:
            lines.append("### Hidden Coupling")
            lines.append("")
            lines.append("Files that change together (hidden dependencies):")
            lines.append("")
            lines.append("| File A | File B | Co-commits |")
            lines.append("|--------|--------|------------|")
            for c in coupling_data[:15]:
                file_a = c.get("file_a", "")
                file_b = c.get("file_b", "")
                count = c.get("count", 0)
                lines.append(f"| `{file_a}` | `{file_b}` | {count} |")
            lines.append("")

        # Freshness analysis
        if freshness_data:
            lines.append("### Freshness Summary")
            lines.append("")
            lines.append("| Category | Count | Description |")
            lines.append("|----------|-------|-------------|")
            active = freshness_data.get("active", [])
            aging = freshness_data.get("aging", [])
            stale = freshness_data.get("stale", [])
            dormant = freshness_data.get("dormant", [])
            lines.append(f"| Active | {len(active)} | Changed in last 30 days |")
            lines.append(f"| Aging | {len(aging)} | Changed 30-90 days ago |")
            lines.append(f"| Stale | {len(stale)} | Changed 90-180 days ago |")
            lines.append(f"| Dormant | {len(dormant)} | Not changed in 180+ days |")
            lines.append("")

            # Show dormant files if any
            if dormant:
                lines.append("**Dormant files** (potential dead code):")
                lines.append("")
                for d in dormant[:10]:
                    filepath = d.get("file", "")
                    days = d.get("days_since_change", 0)
                    lines.append(f"- `{filepath}` ({days} days)")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Section 6: Logic Map Legend
    lines.append("## 6. Logic Map Legend")
    lines.append("")
    lines.append("```")
    lines.append("->    : Control flow")
    lines.append("[X]   : Side effect (DB write, API call, file I/O)")
    lines.append("<X>   : External input (user input, API response)")
    lines.append("{X}   : State mutation (object modification)")
    lines.append("?     : Conditional branch")
    lines.append("*     : Loop iteration")
    lines.append("!     : Exception/error path")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 7: Developer Activity (Placeholder)
    lines.append("## 7. Developer Activity")
    lines.append("")
    lines.append("*Coming soon: Behavioral analysis from Claude Code sessions*")
    lines.append("")
    lines.append("This section will show:")
    lines.append("- **Reference Hotspots**: Files most frequently read for context")
    lines.append("- **Change Hotspots**: Files most frequently edited")
    lines.append("- **Behavioral Coupling**: Files modified together across sessions")
    lines.append("- **Iteration Intensity**: Files with many revisions during development")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 8: Reference
    lines.append("## 8. Reference")
    lines.append("")
    lines.append("This document complements:")
    lines.append("- WARM_START.md (structural architecture)")
    lines.append("- Phase 1 tools (repo-xray)")
    lines.append("")
    lines.append("To refresh: `python generate_hot_start.py . -v`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by repo-investigator*")

    return "\n".join(lines)


def write_debug_output(data: Dict, output_dir: str, verbose: bool = False):
    """Write debug output to HOT_START_debug/ directory."""
    debug_path = Path(output_dir)
    debug_path.mkdir(parents=True, exist_ok=True)

    # Write full data
    with open(debug_path / "analysis_data.json", 'w') as f:
        # Convert sets to lists for JSON serialization
        json_data = json.loads(json.dumps(data, default=str))
        json.dump(json_data, f, indent=2)

    # Write priorities
    with open(debug_path / "priorities.json", 'w') as f:
        json.dump(data["priorities"], f, indent=2)

    # Write logic maps
    with open(debug_path / "logic_maps.json", 'w') as f:
        json.dump(data["logic_maps"], f, indent=2)

    # Write verification
    with open(debug_path / "verification.json", 'w') as f:
        json.dump(data["verification"], f, indent=2)

    if verbose:
        print(f"Debug output written to {debug_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate HOT_START.md semantic analysis document"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current)"
    )
    parser.add_argument(
        "-o", "--output",
        default="HOT_START.md",
        help="Output file path (default: HOT_START.md)"
    )
    parser.add_argument(
        "--phase1-dir",
        metavar="PATH",
        help="Directory containing Phase 1 outputs (deps.json, git.json)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top priority files to analyze (default: 10)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress messages"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write debug output to HOT_START_debug/"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw data as JSON instead of markdown"
    )
    parser.add_argument(
        "-d", "--detail",
        default="full",
        metavar="LEVEL",
        help="Detail level: compact/1, normal/2, verbose/3, full/4 (default: full)"
    )

    args = parser.parse_args()

    # Parse detail level
    detail_input = str(args.detail).lower()
    if detail_input not in DETAIL_LEVELS:
        print(f"Error: Invalid detail level '{args.detail}'", file=sys.stderr)
        print(DETAIL_LEVEL_HELP, file=sys.stderr)
        sys.exit(1)
    detail_level = DETAIL_LEVELS[detail_input]

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Ensure Phase 1 data
    deps_path, git_path, warm_start_debug = ensure_phase1_data(
        args.directory, args.phase1_dir, args.verbose
    )

    # Collect analysis data
    data = collect_analysis_data(
        args.directory,
        deps_path,
        git_path,
        warm_start_debug,
        args.top,
        args.verbose,
        detail_level
    )

    # Write debug output if requested
    if args.debug:
        write_debug_output(data, "HOT_START_debug", args.verbose)

    # Generate output
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        content = generate_hot_start_md(data, detail_level)

        with open(args.output, 'w') as f:
            f.write(content)

        if args.verbose:
            print(f"Generated {args.output}", file=sys.stderr)
            print(f"  - {len(data['priorities'])} priority files", file=sys.stderr)
            print(f"  - {len(data['logic_maps'])} logic maps", file=sys.stderr)
            print(f"  - {len(data['verification'])} files verified", file=sys.stderr)


if __name__ == "__main__":
    main()

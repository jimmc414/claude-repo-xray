"""
Repo X-Ray: Gap Analysis Features

Implements additional features from GAP_ANALYSIS.md to restore functionality
from the old WARM_START + HOT_START format.

Features:
- Priority scores (composite file ranking)
- Mermaid diagrams (architecture visualization)
- Hazard detection (large file warnings)
- Data model extraction (Pydantic, dataclass, TypedDict)
- Entry point detection
- Logic map generation (control flow visualization)
- Import verification
- Architecture prose generation
- State mutation tracking
- Verification commands
"""

import ast
import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# GitHub About Section
# =============================================================================

def _parse_git_remote_url(target_dir: str) -> Optional[Tuple[str, str]]:
    """
    Parse the GitHub owner/repo from .git/config remote URL.

    Supports formats:
    - git@github.com:owner/repo.git
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo

    Returns (owner, repo) tuple or None if not a GitHub repo.
    """
    git_config = Path(target_dir) / ".git" / "config"
    if not git_config.exists():
        return None

    try:
        with open(git_config, "r", encoding="utf-8") as f:
            content = f.read()

        # Find remote "origin" URL
        import re
        # Match [remote "origin"] section
        match = re.search(r'\[remote "origin"\][^\[]*url\s*=\s*([^\n]+)', content)
        if not match:
            return None

        url = match.group(1).strip()

        # Parse SSH format: git@github.com:owner/repo.git
        ssh_match = re.match(r'git@github\.com:([^/]+)/(.+?)(?:\.git)?$', url)
        if ssh_match:
            return (ssh_match.group(1), ssh_match.group(2))

        # Parse HTTPS format: https://github.com/owner/repo.git
        https_match = re.match(r'https?://github\.com/([^/]+)/(.+?)(?:\.git)?$', url)
        if https_match:
            return (https_match.group(1), https_match.group(2))

    except (IOError, OSError):
        pass

    return None


def get_github_about(target_dir: str) -> Dict[str, Any]:
    """
    Extract GitHub repo description and topics.

    Strategy:
    1. Try gh CLI first (works for private repos with auth)
    2. Fall back to GitHub API (public repos only)
    3. Return error message if both fail

    Returns dict with:
    - description: str - repo description
    - topics: list - repo topics/tags
    - error: str - error message if failed
    """
    # Method 1: Try gh CLI (handles auth automatically)
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "description,repositoryTopics"],
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            topics = []
            # repositoryTopics is a list of {"name": "topic"} objects
            if "repositoryTopics" in data:
                for topic in data.get("repositoryTopics", []):
                    if isinstance(topic, dict) and "name" in topic:
                        topics.append(topic["name"])
                    elif isinstance(topic, str):
                        topics.append(topic)
            return {
                "description": data.get("description", ""),
                "topics": topics,
                "source": "gh-cli"
            }
    except FileNotFoundError:
        pass  # gh not installed
    except subprocess.TimeoutExpired:
        pass  # gh timed out
    except (json.JSONDecodeError, KeyError):
        pass  # Invalid response

    # Method 2: Fall back to GitHub API
    repo_info = _parse_git_remote_url(target_dir)
    if not repo_info:
        return {"error": "Not a GitHub repository"}

    owner, repo = repo_info

    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "repo-xray"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "description": data.get("description", ""),
                "topics": data.get("topics", []),
                "source": "github-api"
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Private repository or not found (requires gh CLI with auth)"}
        return {"error": f"GitHub API error: {e.code}"}
    except urllib.error.URLError:
        return {"error": "Unable to reach GitHub API"}
    except Exception as e:
        return {"error": f"Failed to fetch repo info: {str(e)}"}


# =============================================================================
# Priority Score Calculation
# =============================================================================

def normalize_values(values: Dict[str, float]) -> Dict[str, float]:
    """Min-max normalize values to 0-1 range."""
    if not values:
        return {}

    min_val = min(values.values())
    max_val = max(values.values())

    if max_val == min_val:
        return {k: 0.5 for k in values}

    return {k: (v - min_val) / (max_val - min_val) for k, v in values.items()}


def get_architectural_pillars(results: Dict[str, Any], n: int = 10) -> List[Dict[str, Any]]:
    """
    Get top N files ranked by architectural importance (import weight).

    These are the foundation files that many other modules depend on.
    Understanding these files first provides the most leverage.

    Returns sorted list of files with import counts and descriptions.
    """
    imports = results.get("imports", {})
    graph = imports.get("graph", {})
    structure = results.get("structure", {})
    files = structure.get("files", {})

    # Build file import weight map
    file_weights = []
    seen_names = set()

    for mod_name, mod_data in graph.items():
        if isinstance(mod_data, dict):
            imported_by = mod_data.get("imported_by", [])
            imported_by_count = len(imported_by)
        else:
            imported_by_count = 0
            imported_by = []

        if imported_by_count == 0:
            continue

        # Get short name for deduplication
        short_name = mod_name.split(".")[-1] if "." in mod_name else mod_name
        if short_name in seen_names:
            continue
        seen_names.add(short_name)

        # Find the full filepath for this module
        filepath = None
        for fp in files.keys():
            if mod_name in fp or mod_name.replace(".", "/") in fp:
                filepath = fp
                break

        file_weights.append({
            "file": filepath or mod_name,
            "module": mod_name,
            "imported_by_count": imported_by_count,
            "imported_by": imported_by[:5],  # Sample of importers
            "reason": f"imported by {imported_by_count} modules"
        })

    # Sort by import count descending
    file_weights.sort(key=lambda x: x["imported_by_count"], reverse=True)

    return file_weights[:n]


def get_maintenance_hotspots(results: Dict[str, Any], n: int = 10) -> List[Dict[str, Any]]:
    """
    Get top N files ranked by maintenance risk (git churn/hotfixes).

    These are files with high volatility that need careful attention.
    High churn and hotfix rates indicate unstable or problematic code.

    Returns sorted list of files with risk scores and factors.
    """
    git = results.get("git", {})
    risk = git.get("risk", [])

    if not risk:
        return []

    # Deduplicate by filename
    seen_names = set()
    hotspots = []

    for r in risk:
        filepath = r.get("file", "")
        if not filepath:
            continue

        # Get short name for deduplication
        short_name = Path(filepath).name
        if short_name in seen_names:
            continue
        seen_names.add(short_name)

        risk_score = r.get("risk_score", 0)
        churn = r.get("churn", 0)
        hotfixes = r.get("hotfixes", 0)
        authors = r.get("authors", 0)

        # Build reason string
        factors = []
        if churn > 5:
            factors.append(f"churn:{churn}")
        if hotfixes > 0:
            factors.append(f"hotfixes:{hotfixes}")
        if authors > 3:
            factors.append(f"authors:{authors}")

        hotspots.append({
            "file": filepath,
            "risk_score": risk_score,
            "churn": churn,
            "hotfixes": hotfixes,
            "authors": authors,
            "reason": ", ".join(factors) if factors else "moderate risk"
        })

    # Sort by risk score descending
    hotspots.sort(key=lambda x: x["risk_score"], reverse=True)

    return hotspots[:n]


def calculate_priority_scores(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Calculate composite priority scores for files.

    Uses weighted formula:
    score = (CC × 0.25) + (ImportWeight × 0.20) + (GitRisk × 0.30) +
            (Freshness × 0.15) + (Untested × 0.10)

    Git risk is weighted highest because files with frequent hotfixes and
    high churn are the ones developers need to understand most.

    Returns sorted list of files with scores and reasons.

    NOTE: Consider using get_architectural_pillars() and get_maintenance_hotspots()
    for separate, clearer views of important files.
    """
    files_data = {}

    # Helper to normalize paths for matching
    def normalize_path(p: str) -> str:
        """Get the last meaningful portion of a path for matching."""
        parts = p.replace("\\", "/").split("/")
        # Try to find the project root (e.g., kosmos/agents/...)
        for i, part in enumerate(parts):
            if part in ("kosmos", "src", "lib", "tests"):
                return "/".join(parts[i:])
        # Fallback to filename
        return parts[-1] if parts else p

    # Build a mapping of normalized paths to full paths
    path_map = {}

    # Collect complexity scores from hotspots
    hotspots = results.get("hotspots", [])
    for hs in hotspots:
        filepath = hs.get("file", "")
        if filepath:
            norm_path = normalize_path(filepath)
            path_map[norm_path] = filepath
            if filepath not in files_data:
                files_data[filepath] = {"cc": 0, "reasons": [], "norm_path": norm_path}
            files_data[filepath]["cc"] = max(files_data[filepath]["cc"], hs.get("complexity", 0))

    # Collect git risk scores (may use different path format)
    git = results.get("git", {})
    risk = git.get("risk", [])
    for r in risk:
        filepath = r.get("file", "")
        if not filepath:
            continue

        norm_path = normalize_path(filepath)
        # Try to match to existing full path
        matched_path = path_map.get(norm_path, filepath)

        if matched_path not in files_data:
            files_data[matched_path] = {"cc": 0, "reasons": [], "norm_path": norm_path}
            path_map[norm_path] = matched_path

        files_data[matched_path]["git_risk"] = r.get("risk_score", 0)
        files_data[matched_path]["churn"] = r.get("churn", 0)
        files_data[matched_path]["hotfixes"] = r.get("hotfixes", 0)

    # Collect import weights (from calls data)
    calls = results.get("calls", {})
    most_called = calls.get("most_called", [])
    for mc in most_called:
        func = mc.get("function", "")
        call_sites = mc.get("call_sites", 0)
        # Extract module name from function
        if "." in func:
            module_part = func.rsplit(".", 1)[0]
            # Match against known files
            for filepath, data in files_data.items():
                if module_part in filepath or module_part in data.get("norm_path", ""):
                    data["import_weight"] = max(data.get("import_weight", 0), call_sites)
                    break

    # Collect freshness (inverse - active files get lower freshness penalty)
    freshness = git.get("freshness", {})
    for category, category_files in freshness.items():
        weight = {"active": 0.0, "aging": 0.3, "stale": 0.6, "dormant": 1.0}.get(category, 0)
        for f in category_files:
            fp = f.get("file", f) if isinstance(f, dict) else f
            norm_fp = normalize_path(fp)
            matched_path = path_map.get(norm_fp, fp)
            if matched_path in files_data:
                files_data[matched_path]["freshness"] = weight

    # Check which files have tests (untested files get penalty)
    tests = results.get("tests", {})
    tested_modules = set(tests.get("tested_modules", []))

    # Normalize each signal
    cc_scores = {f: d.get("cc", 0) for f, d in files_data.items()}
    import_scores = {f: d.get("import_weight", 0) for f, d in files_data.items()}
    risk_scores = {f: d.get("git_risk", 0) for f, d in files_data.items()}
    freshness_scores = {f: d.get("freshness", 0.5) for f, d in files_data.items()}

    n_cc = normalize_values(cc_scores)
    n_imp = normalize_values(import_scores)
    n_risk = normalize_values(risk_scores)
    n_fresh = normalize_values(freshness_scores)

    # Calculate composite scores
    priority_files = []
    seen_basenames = set()  # Track to avoid duplicates

    for filepath, data in files_data.items():
        # Skip duplicates based on normalized path
        norm = data.get("norm_path", normalize_path(filepath))
        if norm in seen_basenames:
            continue
        seen_basenames.add(norm)

        s_cc = n_cc.get(filepath, 0)
        s_imp = n_imp.get(filepath, 0)
        s_risk = n_risk.get(filepath, 0)
        s_fresh = n_fresh.get(filepath, 0)

        # Check if file has tests
        filename_stem = Path(filepath).stem
        s_untested = 0.0 if filename_stem in tested_modules else 1.0

        # Weighted score (total = 1.0)
        # CC: 0.25, Import: 0.20, GitRisk: 0.30, Freshness: 0.15, Untested: 0.10
        score = (s_cc * 0.25) + (s_imp * 0.20) + (s_risk * 0.30) + (s_fresh * 0.15) + (s_untested * 0.10)

        # Build reasons list
        reasons = []
        if data.get("cc", 0) > 10:
            reasons.append(f"CC:{data.get('cc', 0)}")
        if data.get("git_risk", 0) > 0.5:
            reasons.append(f"risk:{data.get('git_risk', 0):.2f}")
        if data.get("churn", 0) > 5:
            reasons.append(f"churn:{data.get('churn', 0)}")
        if data.get("hotfixes", 0) > 3:
            reasons.append(f"hotfix:{data.get('hotfixes', 0)}")
        if data.get("import_weight", 0) > 10:
            reasons.append("many callers")
        if s_untested > 0:
            reasons.append("untested")

        priority_files.append({
            "file": filepath,
            "score": round(score, 3),
            "reasons": reasons if reasons else ["active"],
            "raw_risk": data.get("git_risk", 0)  # Keep raw risk for fallback
        })

    # Sort by score descending
    priority_files.sort(key=lambda x: x["score"], reverse=True)

    # Fallback: ensure top git risk files appear even if they didn't score high
    # This handles cases where high-risk files have low CC
    top_risk_files = [pf for pf in priority_files if pf.get("raw_risk", 0) > 0.7]
    top_20 = priority_files[:20]

    # Add any high-risk files not in top 20
    top_20_paths = {pf["file"] for pf in top_20}
    for risk_file in top_risk_files[:3]:  # At most 3 high-risk additions
        if risk_file["file"] not in top_20_paths:
            top_20.append(risk_file)

    # Remove raw_risk from output and re-sort
    for pf in top_20:
        pf.pop("raw_risk", None)

    top_20.sort(key=lambda x: x["score"], reverse=True)

    return top_20[:20]


# =============================================================================
# Mermaid Diagram Generation
# =============================================================================

def _infer_data_flow(call_data: Dict[str, Any], layers: Dict[str, List]) -> str:
    """
    Infer data flow direction from call analysis.

    Analyzes cross-module calls to determine if the system is:
    - Push-based: Higher layers call lower layers (orchestration → core → foundation)
    - Pull-based: Lower layers call higher layers (foundation → core → orchestration)
    - Bidirectional: Mixed call patterns

    Returns a string describing the data flow pattern.
    """
    if not call_data:
        return ""

    # Get module sets for each layer
    def get_layer_modules(layer_name: str) -> Set[str]:
        mods = layers.get(layer_name, [])
        result = set()
        for mod in mods:
            if isinstance(mod, dict):
                mod = mod.get("module", mod.get("name", str(mod)))
            result.add(mod)
            # Also add short name
            if "." in mod:
                result.add(mod.split(".")[-1])
        return result

    orch_mods = get_layer_modules("orchestration")
    core_mods = get_layer_modules("core")
    found_mods = get_layer_modules("foundation")

    # Count calls between layers
    cross_module = call_data.get("cross_module", {})

    orch_to_core = 0
    core_to_orch = 0
    core_to_found = 0
    found_to_core = 0

    for caller, callees in cross_module.items():
        caller_short = caller.split(".")[-1] if "." in caller else caller

        for callee_info in callees:
            callee = callee_info.get("callee", "") if isinstance(callee_info, dict) else str(callee_info)
            callee_short = callee.split(".")[-1] if "." in callee else callee

            # Orchestration → Core
            if (caller in orch_mods or caller_short in orch_mods) and \
               (callee in core_mods or callee_short in core_mods):
                orch_to_core += 1
            # Core → Orchestration
            elif (caller in core_mods or caller_short in core_mods) and \
                 (callee in orch_mods or callee_short in orch_mods):
                core_to_orch += 1
            # Core → Foundation
            elif (caller in core_mods or caller_short in core_mods) and \
                 (callee in found_mods or callee_short in found_mods):
                core_to_found += 1
            # Foundation → Core
            elif (caller in found_mods or caller_short in found_mods) and \
                 (callee in core_mods or callee_short in core_mods):
                found_to_core += 1

    # Determine flow direction
    downward = orch_to_core + core_to_found
    upward = core_to_orch + found_to_core

    if downward == 0 and upward == 0:
        return ""

    if downward > upward * 2:
        return "Foundation → Core → Orchestration (push-based)"
    elif upward > downward * 2:
        return "Orchestration → Core → Foundation (pull-based)"
    else:
        return "Bidirectional (mixed data flow)"


def generate_mermaid_diagram(
    import_data: Dict[str, Any],
    call_data: Optional[Dict[str, Any]] = None,
    max_nodes: int = 30
) -> str:
    """
    Generate a Mermaid architecture diagram from import analysis.

    Creates subgraphs for ORCHESTRATION, CORE, and FOUNDATION layers.
    Optionally includes data flow annotations based on call analysis.
    """
    layers = import_data.get("layers", {})
    graph = import_data.get("graph", {})

    lines = ["```mermaid", "graph TD"]

    # Track nodes we've added
    added_nodes = set()

    # Add subgraphs for each layer
    for layer_name in ["orchestration", "core", "foundation"]:
        layer_modules = layers.get(layer_name, [])
        if not layer_modules:
            continue

        # Limit modules per layer
        display_modules = layer_modules[:10]

        lines.append(f"    subgraph {layer_name.upper()}")
        for mod in display_modules:
            # Shorten module name for display
            if isinstance(mod, dict):
                mod = mod.get("module", mod.get("name", str(mod)))
            short_name = mod.split(".")[-1] if "." in mod else mod
            safe_id = mod.replace(".", "_").replace("-", "_")
            lines.append(f"        {safe_id}[{short_name}]")
            added_nodes.add(mod)
        lines.append("    end")

    # Add edges from orchestration to other layers
    edges_added = set()
    orch_modules = layers.get("orchestration", [])[:5]

    for mod in orch_modules:
        if isinstance(mod, dict):
            mod = mod.get("module", mod.get("name", str(mod)))
        mod_id = mod.replace(".", "_").replace("-", "_")

        # Get imports for this module from graph
        # Handle both formats: list of imports or dict with 'imports' key
        mod_data = graph.get(mod, [])
        if isinstance(mod_data, dict):
            imports = mod_data.get("imports", [])
        else:
            imports = mod_data

        for imp in imports[:3]:  # Limit edges per module
            if imp in added_nodes:
                imp_id = imp.replace(".", "_").replace("-", "_")
                edge = (mod_id, imp_id)
                if edge not in edges_added:
                    lines.append(f"    {mod_id} --> {imp_id}")
                    edges_added.add(edge)

    # Add circular dependency warnings
    circular = import_data.get("circular", [])
    for pair in circular[:5]:
        if len(pair) >= 2:
            a, b = pair[0], pair[1]
            a_id = a.replace(".", "_").replace("-", "_")
            b_id = b.replace(".", "_").replace("-", "_")
            lines.append(f"    {a_id} <-.-> {b_id}")

    lines.append("```")

    # Add data flow annotation if call data is available
    if call_data:
        data_flow = _infer_data_flow(call_data, layers)
        if data_flow:
            lines.append("")
            lines.append(f"*Data Flow: {data_flow}*")

    return "\n".join(lines)


# =============================================================================
# Hazard Detection (Large Files)
# =============================================================================

def detect_hazards(results: Dict[str, Any], threshold_tokens: int = 10000) -> List[Dict[str, Any]]:
    """
    Find files with high token counts that may waste context.

    Returns sorted list of hazardous files with recommendations.
    """
    hazards = []
    seen_basenames = set()  # Track to avoid duplicates

    structure = results.get("structure", {})
    files = structure.get("files", {})

    for filepath, data in files.items():
        tokens_data = data.get("tokens", 0)
        # Handle both int and dict formats
        if isinstance(tokens_data, dict):
            tokens = tokens_data.get("original", 0)
        else:
            tokens = tokens_data

        if tokens >= threshold_tokens:
            filename = Path(filepath).name

            # Skip duplicates (same filename in different paths)
            if filename in seen_basenames:
                continue
            seen_basenames.add(filename)

            # Determine recommendation
            recommendation = "Use skeleton view"
            if "generated" in filename.lower() or "auto" in filename.lower():
                recommendation = "Skip - auto-generated"
            elif "test" in filename.lower():
                recommendation = "Skip unless debugging tests"
            elif tokens > 50000:
                recommendation = "Never read directly"

            hazards.append({
                "file": filepath,
                "tokens": tokens,
                "recommendation": recommendation
            })

    # Sort by tokens descending
    hazards.sort(key=lambda x: x["tokens"], reverse=True)

    return hazards[:20]  # Top 20


# =============================================================================
# Data Model Extraction
# =============================================================================

# Patterns that indicate data model base classes
DATA_MODEL_BASES = {
    "BaseModel", "pydantic.BaseModel",
    "TypedDict", "typing.TypedDict", "typing_extensions.TypedDict",
    "NamedTuple", "typing.NamedTuple",
}

DATA_MODEL_DECORATORS = {"dataclass", "dataclasses.dataclass", "attrs.define", "attr.s"}

# Pydantic Field constraint keywords
FIELD_CONSTRAINTS = {
    "gt", "ge", "lt", "le",  # Numeric constraints
    "min_length", "max_length",  # String constraints
    "regex", "pattern",  # Regex validation
    "strict", "frozen",  # Behavior modifiers
    "default", "default_factory",  # Defaults
    "alias", "validation_alias", "serialization_alias",  # Aliases
    "title", "description",  # Documentation
    "examples",  # Examples
}


def _extract_field_constraints(filepath: str, class_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract Pydantic Field() constraints for a class.

    Looks for patterns like:
        field_name: type = Field(..., gt=0, le=100)

    Returns dict mapping field names to their constraints.
    """
    constraints = {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    # Look for annotated assignments: field: type = Field(...)
                    if isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name):
                            field_name = item.target.id

                            # Get the type annotation
                            type_str = None
                            if item.annotation:
                                if isinstance(item.annotation, ast.Name):
                                    type_str = item.annotation.id
                                elif isinstance(item.annotation, ast.Subscript):
                                    try:
                                        type_str = ast.unparse(item.annotation)
                                    except:
                                        type_str = "..."

                            # Check if value is a Field() call
                            if item.value and isinstance(item.value, ast.Call):
                                func = item.value.func
                                # Check for Field() or pydantic.Field()
                                is_field = False
                                if isinstance(func, ast.Name) and func.id == "Field":
                                    is_field = True
                                elif isinstance(func, ast.Attribute) and func.attr == "Field":
                                    is_field = True

                                if is_field:
                                    field_constraints = {"type": type_str}

                                    # Extract constraint keyword arguments
                                    for kw in item.value.keywords:
                                        if kw.arg in FIELD_CONSTRAINTS:
                                            if isinstance(kw.value, ast.Constant):
                                                field_constraints[kw.arg] = kw.value.value
                                            elif isinstance(kw.value, ast.Name):
                                                field_constraints[kw.arg] = kw.value.id
                                            elif isinstance(kw.value, ast.Call):
                                                # e.g., default_factory=list
                                                if isinstance(kw.value.func, ast.Name):
                                                    field_constraints[kw.arg] = f"{kw.value.func.id}()"

                                    # Only add if we found any constraints
                                    if len(field_constraints) > 1:  # More than just 'type'
                                        constraints[field_name] = field_constraints

                break  # Found the class, stop searching

    except (IOError, OSError, SyntaxError):
        pass

    return constraints


def _extract_validators(filepath: str, class_name: str) -> List[Dict[str, Any]]:
    """
    Extract @validator/@field_validator decorators for a class.

    Returns list of validator definitions.
    """
    validators = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        for decorator in item.decorator_list:
                            # Check for @validator or @field_validator
                            dec_name = None
                            fields = []

                            if isinstance(decorator, ast.Call):
                                func = decorator.func
                                if isinstance(func, ast.Name):
                                    if func.id in ("validator", "field_validator"):
                                        dec_name = func.id
                                elif isinstance(func, ast.Attribute):
                                    if func.attr in ("validator", "field_validator"):
                                        dec_name = func.attr

                                # Get validated field names from positional args
                                if dec_name:
                                    for arg in decorator.args:
                                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                            fields.append(arg.value)

                            elif isinstance(decorator, ast.Name):
                                if decorator.id in ("validator", "field_validator"):
                                    dec_name = decorator.id

                            if dec_name:
                                validators.append({
                                    "name": item.name,
                                    "type": dec_name,
                                    "fields": fields,
                                    "line": item.lineno
                                })

                break  # Found the class, stop searching

    except (IOError, OSError, SyntaxError):
        pass

    return validators


def extract_data_models(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract Pydantic, dataclass, and TypedDict models from analysis results.

    Returns list of data models with their fields and types.
    """
    models = []
    seen_models = set()  # Track to avoid duplicates

    structure = results.get("structure", {})
    files = structure.get("files", {})

    for filepath, data in files.items():
        classes = data.get("classes", [])

        for cls in classes:
            is_data_model = False
            model_type = None
            cls_name = cls.get("name", "Unknown")

            # Skip duplicates (same class name in different paths)
            filename = Path(filepath).name
            key = f"{filename}:{cls_name}"
            if key in seen_models:
                continue

            # Check base classes
            bases = cls.get("bases", [])
            for base in bases:
                if base in DATA_MODEL_BASES or any(b in base for b in DATA_MODEL_BASES):
                    is_data_model = True
                    model_type = "Pydantic" if "BaseModel" in base else "TypedDict"
                    break

            # Check decorators
            decorators = cls.get("decorators", [])
            for dec in decorators:
                if any(d in dec for d in DATA_MODEL_DECORATORS):
                    is_data_model = True
                    model_type = "dataclass"
                    break

            if is_data_model:
                seen_models.add(key)

                # Determine domain category from filepath and class name
                path_lower = filepath.lower()
                name_lower = cls_name.lower()

                if "agent" in path_lower or name_lower.endswith("agent"):
                    domain = "Agents"
                elif "api" in path_lower or "handler" in path_lower or "endpoint" in path_lower:
                    domain = "API"
                elif "config" in name_lower or "settings" in name_lower:
                    domain = "Config"
                elif "request" in name_lower or "response" in name_lower:
                    domain = "API"
                elif "model" in path_lower or "schema" in path_lower:
                    domain = "Models"
                elif "workflow" in path_lower or "task" in path_lower:
                    domain = "Workflows"
                else:
                    # Use parent directory as domain
                    parts = filepath.replace("\\", "/").split("/")
                    if len(parts) >= 2:
                        domain = parts[-2].title()
                    else:
                        domain = "Other"

                # Extract Pydantic-specific features if applicable
                field_constraints = {}
                validators = []
                if model_type == "Pydantic":
                    field_constraints = _extract_field_constraints(filepath, cls_name)
                    validators = _extract_validators(filepath, cls_name)

                models.append({
                    "name": cls_name,
                    "file": filepath,
                    "line": cls.get("start_line", cls.get("line", 0)),
                    "type": model_type,
                    "bases": bases,
                    "fields": cls.get("fields", []),
                    "field_constraints": field_constraints,
                    "validators": validators,
                    "methods": [m.get("name") for m in cls.get("methods", [])],
                    "domain": domain
                })

    # Sort by domain, then by name
    models.sort(key=lambda x: (x["domain"], x["name"]))

    return models


# =============================================================================
# Entry Point Detection
# =============================================================================

ENTRY_POINT_FILES = {"main.py", "cli.py", "__main__.py", "app.py", "run.py", "server.py"}
ENTRY_POINT_FUNCTIONS = {"main", "cli", "run", "app", "serve"}


def detect_entry_points(results: Dict[str, Any], target_dir: str = ".") -> List[Dict[str, Any]]:
    """
    Detect entry points in the codebase.

    Looks for:
    - Files named main.py, cli.py, __main__.py, etc.
    - Functions named main(), cli(), run()
    - if __name__ == "__main__" blocks
    """
    entry_points = []
    seen_files = set()

    structure = results.get("structure", {})
    files = structure.get("files", {})

    # Get project name from target directory
    project_name = Path(target_dir).name

    for filepath, data in files.items():
        filename = Path(filepath).name

        # Check if file is an entry point by name
        if filename in ENTRY_POINT_FILES:
            usage = f"python {filepath}"
            if filename == "__main__.py":
                usage = f"python -m {project_name}"
            elif filename == "cli.py":
                usage = f"python -m {project_name}" if "__main__.py" in [Path(f).name for f in files] else f"python {filepath}"

            entry_points.append({
                "entry_point": filename,
                "file": filepath,
                "usage": usage,
                "type": "file"
            })
            seen_files.add(filepath)

        # Check for entry point functions
        functions = data.get("functions", [])
        for func in functions:
            func_name = func.get("name", "")
            if func_name in ENTRY_POINT_FUNCTIONS and filepath not in seen_files:
                entry_points.append({
                    "entry_point": f"{func_name}()",
                    "file": filepath,
                    "usage": f"python {filepath}",
                    "type": "function"
                })

    return entry_points


# =============================================================================
# CLI Arguments Extraction
# =============================================================================

def _extract_argparse_args(tree: ast.AST) -> List[Dict[str, Any]]:
    """
    Extract arguments from argparse.ArgumentParser.add_argument() calls.

    Returns list of argument definitions.
    """
    arguments = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Look for .add_argument() calls
            if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                arg_info = {"source": "argparse"}

                # Get argument name from first positional arg
                if node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        arg_info["name"] = first_arg.value

                # Extract keyword arguments
                for kw in node.keywords:
                    if kw.arg == "help":
                        if isinstance(kw.value, ast.Constant):
                            arg_info["help"] = kw.value.value
                    elif kw.arg == "required":
                        if isinstance(kw.value, ast.Constant):
                            arg_info["required"] = kw.value.value
                    elif kw.arg == "default":
                        arg_info["default"] = _get_env_default_value(kw.value)
                    elif kw.arg == "type":
                        if isinstance(kw.value, ast.Name):
                            arg_info["type"] = kw.value.id

                if "name" in arg_info:
                    # Determine if required (positional args or explicit required=True)
                    if "required" not in arg_info:
                        name = arg_info["name"]
                        arg_info["required"] = not name.startswith("-")
                    arguments.append(arg_info)

    return arguments


def _extract_click_args(tree: ast.AST) -> List[Dict[str, Any]]:
    """
    Extract arguments from @click.option() and @click.argument() decorators.

    Returns list of argument definitions.
    """
    arguments = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    func = decorator.func
                    # Check for click.option or click.argument
                    if isinstance(func, ast.Attribute):
                        if func.attr in ("option", "argument"):
                            is_option = func.attr == "option"
                            arg_info = {
                                "source": "click",
                                "required": not is_option  # arguments are required by default
                            }

                            # Get name from first positional arg
                            if decorator.args:
                                first_arg = decorator.args[0]
                                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                                    arg_info["name"] = first_arg.value

                            # Extract keyword arguments
                            for kw in decorator.keywords:
                                if kw.arg == "help":
                                    if isinstance(kw.value, ast.Constant):
                                        arg_info["help"] = kw.value.value
                                elif kw.arg == "required":
                                    if isinstance(kw.value, ast.Constant):
                                        arg_info["required"] = kw.value.value
                                elif kw.arg == "default":
                                    arg_info["default"] = _get_env_default_value(kw.value)
                                elif kw.arg == "type":
                                    if isinstance(kw.value, ast.Name):
                                        arg_info["type"] = kw.value.id

                            if "name" in arg_info:
                                arguments.append(arg_info)

    return arguments


def _extract_typer_args(tree: ast.AST) -> List[Dict[str, Any]]:
    """
    Extract arguments from typer.Option() and typer.Argument() in function signatures.

    Example: def main(name: str = typer.Argument(...), verbose: bool = typer.Option(False))

    Returns list of argument definitions.
    """
    arguments = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check function parameters for typer.Option/typer.Argument defaults
            for arg in node.args.args + node.args.kwonlyargs:
                # Skip 'self' and 'cls'
                if arg.arg in ("self", "cls"):
                    continue

                # Check for typer.Option() or typer.Argument() in defaults
                # We need to find the default for this argument
                pass  # Defaults are paired with args differently

            # Match defaults to arguments
            all_args = node.args.args + node.args.kwonlyargs
            defaults = []

            # Regular defaults (right-aligned with args)
            num_required = len(node.args.args) - len(node.args.defaults)
            for i, arg in enumerate(node.args.args):
                if i >= num_required:
                    defaults.append((arg, node.args.defaults[i - num_required]))
                else:
                    defaults.append((arg, None))

            # Keyword-only defaults
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                defaults.append((arg, default))

            for arg, default in defaults:
                if arg.arg in ("self", "cls"):
                    continue

                if default and isinstance(default, ast.Call):
                    # Check if it's typer.Option() or typer.Argument()
                    func = default.func
                    if isinstance(func, ast.Attribute):
                        if func.attr in ("Option", "Argument"):
                            is_option = func.attr == "Option"
                            arg_info = {
                                "source": "typer",
                                "name": f"--{arg.arg.replace('_', '-')}" if is_option else arg.arg,
                                "required": not is_option
                            }

                            # Get type annotation
                            if arg.annotation:
                                if isinstance(arg.annotation, ast.Name):
                                    arg_info["type"] = arg.annotation.id
                                elif isinstance(arg.annotation, ast.Subscript):
                                    try:
                                        arg_info["type"] = ast.unparse(arg.annotation)
                                    except:
                                        pass

                            # Extract keyword arguments from typer call
                            for kw in default.keywords:
                                if kw.arg == "help":
                                    if isinstance(kw.value, ast.Constant):
                                        arg_info["help"] = kw.value.value

                            # First positional arg is often the default value
                            if default.args and is_option:
                                arg_info["default"] = _get_env_default_value(default.args[0])

                            arguments.append(arg_info)

    return arguments


def extract_cli_arguments(entry_points: List[Dict[str, Any]], structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract CLI arguments from entry point files.

    Supports:
    - argparse: ArgumentParser.add_argument()
    - click: @click.option(), @click.argument()
    - typer: typer.Option(), typer.Argument()

    Returns list of entry points with their CLI arguments.
    """
    results = []

    for entry in entry_points:
        filepath = entry.get("file", "")
        if not filepath:
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)

            # Extract arguments from all supported frameworks
            argparse_args = _extract_argparse_args(tree)
            click_args = _extract_click_args(tree)
            typer_args = _extract_typer_args(tree)

            all_args = argparse_args + click_args + typer_args

            if all_args:
                results.append({
                    "file": filepath,
                    "entry_point": entry.get("entry_point", ""),
                    "usage": entry.get("usage", ""),
                    "arguments": all_args
                })

        except (IOError, OSError, SyntaxError):
            continue

    return results


# =============================================================================
# Logic Map Generation
# =============================================================================

class LogicMapGenerator:
    """
    Generates control flow logic maps from Python AST.

    Symbols:
    - -> : Conditional branch
    - * : Loop iteration
    - ! : Exception handling
    - {X} : State mutation
    - [X] : Side effect
    - <X> : External input
    """

    SIDE_EFFECT_PATTERNS = {
        'db': ['db.save', 'db.commit', 'session.commit', 'cursor.execute',
               '.insert(', '.update(', '.delete('],
        'api': ['requests.', 'httpx.', '.post(', '.put(', '.patch(', 'fetch('],
        'file': ['file.write', '.write(', 'json.dump', 'pickle.dump'],
        'email': ['send_email', 'send_mail', 'notify('],
        'cache': ['cache.set', 'redis.set', 'cache.invalidate'],
    }

    SAFE_PATTERNS = ['.get(', 'isinstance', 'hasattr', 'getattr', 'len(', 'str(', 'int(']

    INPUT_PATTERNS = ['request.', 'input(', 'args.', 'params.', 'payload.']

    def __init__(self, source: str, detail_level: int = 2):
        self.source = source
        self.detail_level = detail_level
        self.tree = None

    def parse(self) -> bool:
        """Parse the source code."""
        try:
            self.tree = ast.parse(self.source)
            return True
        except SyntaxError:
            return False

    def generate_logic_map(self, method_name: str) -> Optional[Dict[str, Any]]:
        """Generate a logic map for a specific method."""
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

        logic_map = {
            "method": method_name,
            "line": method_node.lineno,
            "flow": [],
            "side_effects": [],
            "state_mutations": [],
            "conditions": [],
        }

        self._analyze_node(method_node, logic_map)

        return logic_map

    def _analyze_node(self, node: ast.AST, logic_map: Dict, depth: int = 0):
        """Recursively analyze AST nodes to build logic map."""
        prefix = "  " * depth

        for child in ast.iter_child_nodes(node):
            # Conditionals
            if isinstance(child, ast.If):
                condition = self._get_condition_text(child.test)
                logic_map["conditions"].append(condition)
                logic_map["flow"].append(f"{prefix}-> {condition}?")
                self._analyze_node(child, logic_map, depth + 1)

            # Loops
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                target = self._node_to_text(child.target)
                iter_name = self._node_to_text(child.iter)
                logic_map["flow"].append(f"{prefix}* for {target} in {iter_name}:")
                self._analyze_node(child, logic_map, depth + 1)

            elif isinstance(child, ast.While):
                condition = self._get_condition_text(child.test)
                logic_map["flow"].append(f"{prefix}* while {condition}:")
                self._analyze_node(child, logic_map, depth + 1)

            # Function calls - check for side effects
            elif isinstance(child, ast.Call):
                call_text = self._get_call_text(child)
                side_effect = self._detect_side_effect(call_text)
                if side_effect:
                    logic_map["side_effects"].append(side_effect)
                    logic_map["flow"].append(f"{prefix}[{side_effect}]")
                elif self._is_external_input(call_text):
                    logic_map["flow"].append(f"{prefix}<{call_text}>")

            # Assignments - check for state mutations
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Attribute):
                        if isinstance(target.value, ast.Name) and target.value.id == "self":
                            mutation = f"self.{target.attr}"
                            logic_map["state_mutations"].append(mutation)
                            logic_map["flow"].append(f"{prefix}{{{mutation}}}")

            # Return statements
            elif isinstance(child, ast.Return):
                if child.value:
                    ret_text = self._node_to_text(child.value)
                    logic_map["flow"].append(f"{prefix}-> Return({ret_text})")
                else:
                    logic_map["flow"].append(f"{prefix}-> Return")

            # Exception handling
            elif isinstance(child, ast.Try):
                logic_map["flow"].append(f"{prefix}try:")
                self._analyze_node(child, logic_map, depth + 1)
                for handler in child.handlers:
                    exc_type = "Exception"
                    if handler.type and hasattr(handler.type, "id"):
                        exc_type = handler.type.id
                    logic_map["flow"].append(f"{prefix}! except {exc_type}")

            else:
                self._analyze_node(child, logic_map, depth)

    def _get_condition_text(self, node: ast.AST) -> str:
        """Extract readable text from a condition node."""
        if isinstance(node, ast.Compare):
            left = self._node_to_text(node.left)
            ops = {
                ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
                ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
                ast.In: "in", ast.NotIn: "not in"
            }
            op_str = ops.get(type(node.ops[0]), "?")
            right = self._node_to_text(node.comparators[0])
            return f"{left} {op_str} {right}"
        elif isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            values = [self._get_condition_text(v) for v in node.values]
            return f" {op} ".join(values)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"not {self._get_condition_text(node.operand)}"
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
            if isinstance(node.value, str) and len(node.value) > 20:
                return "..."
            return repr(node.value) if isinstance(node.value, str) else str(node.value)
        elif isinstance(node, ast.Subscript):
            return f"{self._node_to_text(node.value)}[...]"
        return "..."

    def _get_call_text(self, node: ast.Call) -> str:
        """Get text representation of a function call."""
        func_name = self._node_to_text(node.func)
        return f"{func_name}(...)"

    def _detect_side_effect(self, call_text: str) -> Optional[str]:
        """Detect if a call has side effects."""
        call_lower = call_text.lower()

        for safe in self.SAFE_PATTERNS:
            if safe in call_lower:
                return None

        for category, patterns in self.SIDE_EFFECT_PATTERNS.items():
            for pattern in patterns:
                if pattern in call_lower:
                    return f"{category.upper()}: {call_text}"
        return None

    def _is_external_input(self, call_text: str) -> bool:
        """Check if a call represents external input."""
        call_lower = call_text.lower()
        return any(pattern in call_lower for pattern in self.INPUT_PATTERNS)


def _extract_function_docstring(source: str, func_name: str) -> Optional[str]:
    """Extract docstring for a function."""
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                    docstring = node.body[0].value.value
                    # Return first sentence only
                    first_line = docstring.split('\n')[0].strip()
                    return first_line if first_line else None
        return None
    except SyntaxError:
        return None


def _generate_heuristic_summary(source: str, func_name: str) -> str:
    """Generate heuristic summary from AST patterns."""
    try:
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                # Count patterns
                loop_count = 0
                try_count = 0
                conditional_count = 0
                return_count = 0
                early_returns = False

                for child in ast.walk(node):
                    if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                        loop_count += 1
                    elif isinstance(child, ast.Try):
                        try_count += 1
                    elif isinstance(child, ast.If):
                        conditional_count += 1
                    elif isinstance(child, ast.Return):
                        return_count += 1
                        # Check if return is inside an If (early return pattern)
                        for parent in ast.walk(node):
                            if isinstance(parent, ast.If):
                                for if_child in ast.walk(parent):
                                    if child == if_child:
                                        early_returns = True

                # Build summary parts
                parts = []
                if loop_count > 0:
                    parts.append(f"Iterates over {loop_count} collection{'s' if loop_count > 1 else ''}")
                if conditional_count > 0:
                    parts.append(f"{conditional_count} decision branch{'es' if conditional_count > 1 else ''}")
                if try_count > 0:
                    parts.append(f"handles {try_count} exception type{'s' if try_count > 1 else ''}")
                if return_count > 1 and early_returns:
                    parts.append("returns early on error")
                elif return_count == 1:
                    parts.append("single return point")

                if parts:
                    return ". ".join(parts) + "."
                return ""
        return ""
    except SyntaxError:
        return ""


def generate_logic_maps(results: Dict[str, Any], n: int = 10) -> List[Dict[str, Any]]:
    """
    Generate logic maps for the top N complex functions.

    Includes docstrings and heuristic summaries for better context.

    Returns list of logic maps for hotspot functions.
    """
    logic_maps = []
    seen = set()  # Track to avoid duplicates

    hotspots = results.get("hotspots", [])
    structure = results.get("structure", {})
    files = structure.get("files", {})

    for hs in hotspots:
        if len(logic_maps) >= n:
            break

        filepath = hs.get("file", "")
        func_name = hs.get("function", "")

        if not filepath or not func_name:
            continue

        # Skip duplicates (same function name in different paths)
        basename = Path(filepath).name
        key = f"{basename}:{func_name}"
        if key in seen:
            continue
        seen.add(key)

        # Try to read the file and generate logic map
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()

            generator = LogicMapGenerator(source)
            if generator.parse():
                logic_map = generator.generate_logic_map(func_name)
                if logic_map:
                    logic_map["file"] = filepath
                    logic_map["complexity"] = hs.get("complexity", 0)
                    # Add docstring and heuristic summary
                    logic_map["docstring"] = _extract_function_docstring(source, func_name)
                    logic_map["heuristic"] = _generate_heuristic_summary(source, func_name)
                    logic_maps.append(logic_map)
        except (IOError, OSError):
            continue

    return logic_maps


# =============================================================================
# Import Verification
# =============================================================================

def verify_imports(results: Dict[str, Any], target_dir: str) -> Dict[str, Any]:
    """
    Verify that imports can be resolved.

    Returns verification results with passed, failed, and warnings.
    """
    verification = {
        "passed": 0,
        "failed": 0,
        "broken": [],
        "warnings": []
    }

    imports = results.get("imports", {})
    external_deps = imports.get("external_deps", [])
    graph = imports.get("graph", {})

    # Build set of all known internal modules
    internal_modules = set(graph.keys())

    # Check each module's imports
    for module, mod_data in graph.items():
        # Handle both dict format {'imports': [...]} and list format [...]
        if isinstance(mod_data, dict):
            module_imports = mod_data.get("imports", [])
        else:
            module_imports = mod_data if isinstance(mod_data, list) else []

        for imp in module_imports:
            # Internal imports are generally OK
            if imp in internal_modules:
                verification["passed"] += 1
            elif imp in external_deps:
                verification["passed"] += 1
            else:
                # Could be a relative import or missing
                verification["warnings"].append({
                    "module": module,
                    "import": imp,
                    "issue": "Cannot verify - may be dynamic or conditional"
                })

    return verification


# =============================================================================
# Layer Details
# =============================================================================

def get_layer_details(results: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get detailed layer information including import counts.

    Returns layers with modules and their import metrics.
    """
    imports = results.get("imports", {})
    layers = imports.get("layers", {})
    graph = imports.get("graph", {})

    detailed_layers = {}

    for layer_name, modules in layers.items():
        detailed_modules = []
        for mod in modules:
            if isinstance(mod, dict):
                mod_name = mod.get("module", mod.get("name", str(mod)))
            else:
                mod_name = mod

            # Get module data from graph - handles both dict and list formats
            mod_data = graph.get(mod_name, {})
            if isinstance(mod_data, dict):
                imported_by_count = len(mod_data.get("imported_by", []))
                imports_count = len(mod_data.get("imports", []))
            else:
                # Fallback for list format
                imported_by_count = 0
                imports_count = len(mod_data) if isinstance(mod_data, list) else 0

            detailed_modules.append({
                "module": mod_name,
                "imported_by": imported_by_count,
                "imports": imports_count
            })

        # Sort by imported_by count
        detailed_modules.sort(key=lambda x: x["imported_by"], reverse=True)
        detailed_layers[layer_name] = detailed_modules

    return detailed_layers


# =============================================================================
# Architecture Prose Generation
# =============================================================================

def generate_prose(results: Dict[str, Any], project_name: str = "Project") -> str:
    """
    Generate natural language architecture overview.

    Detects patterns like agents, workflows, APIs, CLIs and generates prose.
    """
    summary = results.get("summary", {})
    imports = results.get("imports", {})
    layers = imports.get("layers", {})

    # Detect architecture patterns
    patterns = []
    pattern_details = []

    structure = results.get("structure", {})
    files = structure.get("files", {})

    # Check for agents
    agent_files = [f for f in files if "agent" in f.lower()]
    if agent_files:
        patterns.append("agent-based architecture")
        agent_count = len(agent_files)
        pattern_details.append(f"**{agent_count} agent modules** for autonomous task execution")

    # Check for workflows
    workflow_files = [f for f in files if any(w in f.lower() for w in ["workflow", "pipeline", "orchestrat"])]
    if workflow_files:
        patterns.append("workflow orchestration")
        workflow_count = len(workflow_files)
        pattern_details.append(f"**{workflow_count} workflow modules** for process coordination")

    # Check for API
    api_files = [f for f in files if any(a in f.lower() for a in ["api", "handler", "endpoint", "route"])]
    if api_files:
        patterns.append("REST/HTTP API")
        api_count = len(api_files)
        pattern_details.append(f"**{api_count} API handlers** for external integration")

    # Check for CLI
    cli_files = [f for f in files if any(c in f.lower() for c in ["cli", "command", "argparse"])]
    if cli_files:
        patterns.append("command-line interface")
        cli_count = len(cli_files)
        pattern_details.append(f"**{cli_count} CLI modules** for user interaction")

    # Check for data models
    model_files = [f for f in files if any(m in f.lower() for m in ["model", "schema", "entity"])]
    if model_files:
        model_count = len(model_files)
        pattern_details.append(f"**{model_count} data model definitions**")

    # Check for tests
    test_files = [f for f in files if "test" in f.lower()]
    if test_files:
        test_count = len(test_files)
        pattern_details.append(f"**{test_count} test modules** for validation")

    # Build prose
    total_files = summary.get("total_files", 0)
    total_functions = summary.get("total_functions", 0)
    total_classes = summary.get("total_classes", 0)

    layer_counts = {name: len(mods) for name, mods in layers.items()}

    prose_parts = [f"**{project_name}** is a Python application"]

    if patterns:
        prose_parts.append(f" with {', '.join(patterns[:3])}")

    prose_parts.append(f". The codebase contains **{total_files}** Python files")
    prose_parts.append(f" with **{total_functions}** functions and **{total_classes}** classes")

    if layer_counts:
        prose_parts.append(f", organized across {len(layer_counts)} architectural layers")
        layer_str = ", ".join(f"{count} {name}" for name, count in layer_counts.items() if count > 0)
        if layer_str:
            prose_parts.append(f" ({layer_str})")

    prose_parts.append(".\n\n")

    # Add pattern details
    if pattern_details:
        prose_parts.append("**Key Components:**\n")
        for detail in pattern_details[:6]:
            prose_parts.append(f"- {detail}\n")

    return "".join(prose_parts)


# =============================================================================
# State Mutations
# =============================================================================

def extract_state_mutations(results: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Extract state mutations (self.X = Y assignments) from complex functions.

    Returns dict mapping function names to list of mutated attributes.
    """
    mutations = {}

    hotspots = results.get("hotspots", [])[:20]
    structure = results.get("structure", {})
    files = structure.get("files", {})

    for hs in hotspots:
        filepath = hs.get("file", "")
        func_name = hs.get("function", "")

        if not filepath or not func_name:
            continue

        # Try to read and parse file
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)

            # Find the function
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == func_name:
                        func_mutations = []
                        for child in ast.walk(node):
                            if isinstance(child, ast.Assign):
                                for target in child.targets:
                                    if isinstance(target, ast.Attribute):
                                        if isinstance(target.value, ast.Name) and target.value.id == "self":
                                            func_mutations.append(f"self.{target.attr}")

                        if func_mutations:
                            key = f"{Path(filepath).name}:{func_name}"
                            mutations[key] = list(set(func_mutations))
                        break
        except (IOError, OSError, SyntaxError):
            continue

    return mutations


# =============================================================================
# Verification Commands
# =============================================================================

def generate_verify_commands(results: Dict[str, Any], project_name: str = "project") -> List[str]:
    """
    Generate verification commands for the project.

    Template-based generation based on detected features.
    """
    commands = []

    # Import check
    commands.append(f"# Check import health")
    commands.append(f"python -c \"import {project_name}; print('OK')\"")
    commands.append("")

    # Test command
    tests = results.get("tests", {})
    if tests.get("test_file_count", 0) > 0:
        commands.append("# Run tests")
        commands.append("pytest tests/ -x -q")
        commands.append("")

    # CLI help
    entry_points = detect_entry_points(results)
    if any(ep.get("entry_point") in ("cli.py", "__main__.py") for ep in entry_points):
        commands.append("# CLI help")
        commands.append(f"python -m {project_name} --help")

    return commands


# =============================================================================
# Inline Skeleton Formatting
# =============================================================================

def _extract_class_docstring(filepath: str, class_name: str, start_line: int) -> Optional[str]:
    """Extract docstring for a class from source file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                # Get docstring
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                    docstring = node.body[0].value.value
                    # Return first sentence only
                    first_sentence = docstring.split('.')[0].strip()
                    if first_sentence:
                        return first_sentence + "."
                return None
    except (IOError, OSError, SyntaxError):
        pass
    return None


def _extract_init_signature(filepath: str, class_name: str) -> Optional[str]:
    """Extract __init__ method signature from source file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        # Build signature string
                        args = []
                        for arg in item.args.args:
                            if arg.arg == "self":
                                continue
                            arg_str = arg.arg
                            if arg.annotation:
                                try:
                                    arg_str += f": {ast.unparse(arg.annotation)}"
                                except:
                                    pass
                            args.append(arg_str)

                        # Add defaults for keyword-only args
                        for arg in item.args.kwonlyargs:
                            arg_str = arg.arg
                            if arg.annotation:
                                try:
                                    arg_str += f": {ast.unparse(arg.annotation)}"
                                except:
                                    pass
                            args.append(arg_str)

                        return f"def __init__(self, {', '.join(args)})"
                return None
    except (IOError, OSError, SyntaxError):
        pass
    return None


def _get_instance_var_repr(node: ast.AST) -> str:
    """Get string representation of an instance variable value."""
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        if isinstance(node.value, str):
            if len(node.value) > 25:
                return f'"{node.value[:22]}..."'
            return f'"{node.value}"'
        return repr(node.value)
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.List):
        if not node.elts:
            return "[]"
        return "[...]"
    elif isinstance(node, ast.Dict):
        if not node.keys:
            return "{}"
        return "{...}"
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return f"{node.func.id}(...)"
        elif isinstance(node.func, ast.Attribute):
            return f"{node.func.attr}(...)"
        return "..."
    elif isinstance(node, ast.Attribute):
        # e.g., self.other_var or config.value
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return "..."


def _extract_instance_vars(filepath: str, class_name: str) -> List[Dict[str, Any]]:
    """
    Extract instance variables (self.x = y) from __init__ method.

    Returns list of instance variables with their assigned values.
    """
    instance_vars = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                # Find __init__ method
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        # Walk through __init__ body to find self.x = y assignments
                        for stmt in ast.walk(item):
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Attribute):
                                        if isinstance(target.value, ast.Name) and target.value.id == "self":
                                            var_name = target.attr
                                            var_value = _get_instance_var_repr(stmt.value)
                                            instance_vars.append({
                                                "name": var_name,
                                                "value": var_value,
                                                "line": stmt.lineno
                                            })
                            # Also handle augmented assignments (self.x += y) - rare but possible
                            elif isinstance(stmt, ast.AugAssign):
                                if isinstance(stmt.target, ast.Attribute):
                                    if isinstance(stmt.target.value, ast.Name) and stmt.target.value.id == "self":
                                        var_name = stmt.target.attr
                                        instance_vars.append({
                                            "name": var_name,
                                            "value": "...",  # Can't determine initial value
                                            "line": stmt.lineno
                                        })
                        break  # Found __init__, stop searching
                break  # Found class, stop searching

    except (IOError, OSError, SyntaxError):
        pass

    # Deduplicate by name (keep first occurrence)
    seen = set()
    unique_vars = []
    for var in instance_vars:
        if var["name"] not in seen:
            seen.add(var["name"])
            unique_vars.append(var)

    return unique_vars


def format_inline_skeletons(results: Dict[str, Any], n: int = 10) -> List[Dict[str, Any]]:
    """
    Get top N critical classes for inline skeleton display.

    Prioritizes classes using architectural importance scoring:
    - Import weight (how many modules import this class's file)
    - Method complexity (total complexity of methods)
    - Base class significance (Agent, Model, etc. get bonus)

    Includes docstrings (first sentence) and __init__ signatures for context.
    """
    structure = results.get("structure", {})
    files = structure.get("files", {})
    imports = results.get("imports", {})
    graph = imports.get("graph", {})

    # Build file import weight map
    file_import_weight = {}
    for mod_name, mod_data in graph.items():
        if isinstance(mod_data, dict):
            imported_by_count = len(mod_data.get("imported_by", []))
        else:
            imported_by_count = 0
        # Map module name to import count
        file_import_weight[mod_name] = imported_by_count

    # Base class patterns that indicate architectural importance
    IMPORTANT_BASES = {
        "Agent": 30, "BaseAgent": 30,
        "BaseModel": 20, "Model": 15,
        "BaseExecutor": 25, "Executor": 20,
        "BaseProcessor": 20, "Processor": 15,
        "BaseHandler": 15, "Handler": 10,
        "ABC": 15,  # Abstract base classes
        "Protocol": 15,  # Protocol classes
    }

    # Collect all classes with metadata, tracking full paths to avoid duplicates
    seen_paths = set()
    all_classes = []
    for filepath, data in files.items():
        # Get import weight for this file
        # Convert filepath to module format for lookup
        path_parts = filepath.replace("\\", "/").split("/")
        for i, part in enumerate(path_parts):
            if part in ("kosmos", "src", "lib"):
                mod_path = ".".join(path_parts[i:]).replace(".py", "")
                break
        else:
            mod_path = Path(filepath).stem

        import_weight = file_import_weight.get(mod_path, 0)

        for cls in data.get("classes", []):
            cls_name = cls.get("name", "Unknown")
            # Use full path to avoid duplicates
            full_id = f"{filepath}:{cls_name}"
            if full_id in seen_paths:
                continue
            seen_paths.add(full_id)

            # Calculate base class bonus
            bases = cls.get("bases", [])
            base_bonus = 0
            for base in bases:
                for pattern, bonus in IMPORTANT_BASES.items():
                    if pattern in base:
                        base_bonus = max(base_bonus, bonus)
                        break

            # Calculate complexity from methods
            methods = cls.get("methods", [])
            method_complexity = sum(m.get("complexity", 1) for m in methods)
            method_count = len(methods)

            # Calculate importance score
            # Import weight: 0-100+ scaled to 0-30
            # Base bonus: 0-30
            # Method count: 0-50+ scaled to 0-20
            # Method complexity: 0-200+ scaled to 0-20
            score = (
                min(import_weight, 100) * 0.3 +  # Import weight (max 30)
                base_bonus +                       # Base class bonus (max 30)
                min(method_count, 50) * 0.4 +     # Method count (max 20)
                min(method_complexity, 200) * 0.1  # Complexity (max 20)
            )

            # Extract docstring from structure or source file
            docstring = cls.get("docstring")
            if not docstring:
                docstring = _extract_class_docstring(filepath, cls_name, cls.get("start_line", 0))

            # Extract __init__ signature
            init_sig = _extract_init_signature(filepath, cls_name)

            # Extract instance variables from __init__
            instance_vars = _extract_instance_vars(filepath, cls_name)

            all_classes.append({
                "name": cls_name,
                "file": filepath,
                "line": cls.get("start_line", cls.get("line", 0)),
                "bases": bases,
                "methods": methods,
                "fields": cls.get("fields", []),
                "decorators": cls.get("decorators", []),
                "method_count": method_count,
                "importance_score": round(score, 2),
                "docstring": docstring,
                "init_signature": init_sig,
                "instance_vars": instance_vars
            })

    # Sort by importance score descending
    all_classes.sort(key=lambda x: x["importance_score"], reverse=True)

    # Remove internal score from output
    for cls in all_classes:
        cls.pop("importance_score", None)

    return all_classes[:n]


# =============================================================================
# Full Signatures Formatting
# =============================================================================

def format_signatures(results: Dict[str, Any], n: int = 10) -> List[Dict[str, Any]]:
    """
    Get full signatures for top N hotspot functions.

    Includes parameter types, return types, and docstrings.
    """
    signatures = []

    hotspots = results.get("hotspots", [])[:n]
    structure = results.get("structure", {})
    files = structure.get("files", {})

    for hs in hotspots:
        filepath = hs.get("file", "")
        func_name = hs.get("function", "")

        file_data = files.get(filepath, {})
        functions = file_data.get("functions", [])

        for func in functions:
            if func.get("name") == func_name:
                signatures.append({
                    "name": func_name,
                    "file": filepath,
                    "line": func.get("start_line", func.get("line", 0)),
                    "signature": func.get("signature", ""),
                    "args": func.get("args", []),
                    "returns": func.get("returns"),
                    "docstring": func.get("docstring"),
                    "is_async": func.get("is_async", False),
                    "complexity": hs.get("complexity", 0)
                })
                break

    # Remove duplicates (same file and function)
    seen = set()
    unique_signatures = []
    for sig in signatures:
        key = f"{sig['file']}:{sig['name']}"
        if key not in seen:
            seen.add(key)
            unique_signatures.append(sig)

    return unique_signatures


# =============================================================================
# Side Effects Detail
# =============================================================================

def get_side_effects_detail(results: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get side effects organized by file and function.

    Returns detailed side effect information per function.
    """
    detail = defaultdict(list)

    side_effects = results.get("side_effects", {})
    by_type = side_effects.get("by_type", {})

    # Reorganize by file
    for effect_type, effects in by_type.items():
        for effect in effects:
            filepath = effect.get("file", "")
            if filepath:
                detail[filepath].append({
                    "type": effect_type,
                    "call": effect.get("call", ""),
                    "line": effect.get("line", 0),
                    "function": effect.get("function", "unknown")
                })

    # Sort effects within each file by line
    for filepath in detail:
        detail[filepath].sort(key=lambda x: x["line"])

    return dict(detail)


# =============================================================================
# Hidden Coupling (Git Coupling)
# =============================================================================

def get_hidden_coupling(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Get files that change together without import relationship.

    Returns list of coupled file pairs with change counts.
    """
    git = results.get("git", {})
    coupling = git.get("coupling", [])

    # The data is already in the correct format
    return coupling


# =============================================================================
# External Dependencies
# =============================================================================

def get_external_dependencies(results: Dict[str, Any]) -> List[str]:
    """
    Get list of external (third-party) dependencies.

    Returns sorted list of external package names.
    """
    imports = results.get("imports", {})
    external_deps = imports.get("external_deps", [])

    # Sort alphabetically
    return sorted(external_deps)


# =============================================================================
# Environment Variables (AST-based with defaults)
# =============================================================================

def _get_string_value(node: ast.AST) -> Optional[str]:
    """Extract string value from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_env_default_value(node: ast.AST) -> Optional[str]:
    """Get string representation of env var default value."""
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        if isinstance(node.value, str):
            if len(node.value) > 30:
                return f'"{node.value[:27]}..."'
            return f'"{node.value}"'
        return repr(node.value)
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Call):
        func_name = node.func.id if isinstance(node.func, ast.Name) else "..."
        return f"{func_name}(...)"
    return "..."


def _is_getenv_call(node: ast.Call) -> bool:
    """Check if a Call node is os.getenv() or os.environ.get()."""
    # os.getenv(...)
    if isinstance(node.func, ast.Attribute):
        if node.func.attr == "getenv":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                return True
        # os.environ.get(...)
        if node.func.attr == "get":
            if isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr == "environ":
                    if isinstance(node.func.value.value, ast.Name):
                        if node.func.value.value.id == "os":
                            return True
            # environ.get(...) - for `from os import environ`
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "environ":
                return True
    return False


def _extract_env_vars_from_file_ast(filepath: str) -> List[Dict[str, Any]]:
    """
    Extract environment variables from a file using AST parsing.

    Captures:
    - Variable name
    - Default value (if any)
    - Whether it's required (no default)
    - Line number
    """
    env_vars = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_getenv_call(node):
                if node.args:
                    var_name = _get_string_value(node.args[0])
                    if var_name:
                        default = None
                        # Check for second positional argument (default value)
                        if len(node.args) > 1:
                            default = _get_env_default_value(node.args[1])
                        # Check for 'default' keyword argument
                        else:
                            for kw in node.keywords:
                                if kw.arg == "default":
                                    default = _get_env_default_value(kw.value)
                                    break

                        env_vars.append({
                            "variable": var_name,
                            "default": default,
                            "required": default is None,
                            "file": filepath,
                            "line": node.lineno
                        })

            # Also detect os.environ["VAR"] and os.environ["VAR"] = ...
            elif isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Attribute):
                    if node.value.attr == "environ":
                        var_name = _get_string_value(node.slice)
                        if var_name:
                            env_vars.append({
                                "variable": var_name,
                                "default": None,
                                "required": True,  # Direct access is always required
                                "file": filepath,
                                "line": node.lineno
                            })

    except (IOError, OSError, SyntaxError):
        pass

    return env_vars


def get_environment_variables(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract environment variables using AST parsing with default values.

    Uses AST analysis to capture:
    - Variable names from os.getenv(), os.environ.get(), os.environ[]
    - Default values (second argument to getenv/get)
    - Whether variable is required (no default = required)

    Returns list of environment variables with file locations and defaults.
    """
    env_vars = []
    seen = set()  # Track (var_name, file) to avoid duplicates

    structure = results.get("structure", {})
    files = structure.get("files", {})

    # Prioritize config files, then scan all files
    priority_files = []
    other_files = []

    for filepath in files.keys():
        fname = Path(filepath).name.lower()
        if any(kw in fname for kw in ["config", "env", "settings", "setup", "provider"]):
            priority_files.append(filepath)
        else:
            other_files.append(filepath)

    # Scan priority files first, then others
    all_files = priority_files + other_files

    for filepath in all_files:
        file_env_vars = _extract_env_vars_from_file_ast(filepath)
        for env_var in file_env_vars:
            key = (env_var["variable"], env_var["file"])
            if key not in seen:
                seen.add(key)
                env_vars.append(env_var)

    # Deduplicate by variable name (keep first occurrence with most info)
    final_vars = {}
    for ev in env_vars:
        var_name = ev["variable"]
        if var_name not in final_vars:
            final_vars[var_name] = ev
        else:
            # Keep the one with a default value if available
            existing = final_vars[var_name]
            if existing["default"] is None and ev["default"] is not None:
                final_vars[var_name] = ev

    # Sort by required (required first), then by name
    result = sorted(final_vars.values(), key=lambda x: (not x["required"], x["variable"]))

    return result


# =============================================================================
# Linter Rules Extraction
# =============================================================================

def _parse_toml_value(value: str) -> Any:
    """
    Parse a simple TOML value.

    Handles strings, integers, booleans, and simple lists.
    """
    value = value.strip()

    # Boolean
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Integer
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)

    # String (with quotes)
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Simple list
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = []
        for item in inner.split(","):
            item = item.strip()
            if (item.startswith('"') and item.endswith('"')) or \
               (item.startswith("'") and item.endswith("'")):
                items.append(item[1:-1])
            else:
                items.append(item)
        return items

    return value


def _parse_simple_toml(content: str) -> Dict[str, Any]:
    """
    Parse a simple TOML file without external dependencies.

    Only handles basic key-value pairs and sections.
    For complex TOML, use tomllib on Python 3.11+.
    """
    result = {}
    current_section = None
    current_section_data = {}

    for line in content.split("\n"):
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            # Save previous section
            if current_section:
                result[current_section] = current_section_data

            # Start new section
            section_name = line[1:-1].strip()
            # Handle nested sections like [tool.ruff]
            current_section = section_name
            current_section_data = {}
            continue

        # Key-value pair
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = _parse_toml_value(value)

            if current_section:
                current_section_data[key] = value
            else:
                result[key] = value

    # Save last section
    if current_section:
        result[current_section] = current_section_data

    return result


def extract_linter_rules(target_dir: str) -> Dict[str, Any]:
    """
    Extract linter rules from project configuration files.

    Checks for:
    - pyproject.toml (ruff, black, isort settings)
    - ruff.toml
    - .flake8
    - setup.cfg

    Returns dict with:
    - linter: str - detected linter name
    - config_file: str - source config file
    - rules: dict - extracted rules
    - banned_imports: list - imports that should be avoided
    """
    target_path = Path(target_dir)
    result = {
        "linter": None,
        "config_file": None,
        "rules": {},
        "banned_imports": [],
        "required_imports": []
    }

    # Try pyproject.toml first (most common)
    pyproject = target_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")

            # Try tomllib on Python 3.11+
            try:
                import tomllib
                data = tomllib.loads(content)
            except ImportError:
                # Fall back to simple parser
                data = _parse_simple_toml(content)

            # Check for ruff configuration
            ruff_config = None
            if "tool.ruff" in data:
                ruff_config = data["tool.ruff"]
                result["linter"] = "ruff"
            elif "tool" in data and isinstance(data["tool"], dict):
                if "ruff" in data["tool"]:
                    ruff_config = data["tool"]["ruff"]
                    result["linter"] = "ruff"

            if ruff_config:
                result["config_file"] = "pyproject.toml"
                if "line-length" in ruff_config:
                    result["rules"]["line_length"] = ruff_config["line-length"]
                if "select" in ruff_config:
                    result["rules"]["select"] = ruff_config["select"]
                if "ignore" in ruff_config:
                    result["rules"]["ignore"] = ruff_config["ignore"]

            # Check for black configuration
            black_config = None
            if "tool.black" in data:
                black_config = data["tool.black"]
            elif "tool" in data and isinstance(data["tool"], dict):
                if "black" in data["tool"]:
                    black_config = data["tool"]["black"]

            if black_config:
                if not result["linter"]:
                    result["linter"] = "black"
                    result["config_file"] = "pyproject.toml"
                if "line-length" in black_config:
                    result["rules"]["line_length"] = black_config["line-length"]
                if "target-version" in black_config:
                    result["rules"]["target_version"] = black_config["target-version"]

            # Check for isort configuration
            isort_config = None
            if "tool.isort" in data:
                isort_config = data["tool.isort"]
            elif "tool" in data and isinstance(data["tool"], dict):
                if "isort" in data["tool"]:
                    isort_config = data["tool"]["isort"]

            if isort_config:
                result["rules"]["import_sorting"] = "isort"
                if "profile" in isort_config:
                    result["rules"]["isort_profile"] = isort_config["profile"]

        except Exception:
            pass

    # Try ruff.toml
    ruff_toml = target_path / "ruff.toml"
    if ruff_toml.exists() and not result["linter"]:
        try:
            content = ruff_toml.read_text(encoding="utf-8")
            data = _parse_simple_toml(content)

            result["linter"] = "ruff"
            result["config_file"] = "ruff.toml"

            if "line-length" in data:
                result["rules"]["line_length"] = data["line-length"]
            if "select" in data:
                result["rules"]["select"] = data["select"]

        except Exception:
            pass

    # Try .flake8
    flake8 = target_path / ".flake8"
    if flake8.exists() and not result["linter"]:
        try:
            content = flake8.read_text(encoding="utf-8")

            result["linter"] = "flake8"
            result["config_file"] = ".flake8"

            # Parse INI-style config
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("max-line-length"):
                    try:
                        result["rules"]["line_length"] = int(line.split("=")[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("ignore"):
                    result["rules"]["ignore"] = line.split("=")[1].strip()

        except Exception:
            pass

    # Extract common banned patterns based on rules
    if result["rules"]:
        select = result["rules"].get("select", [])
        if isinstance(select, list):
            # E501 = line too long, T20x = print statements banned
            if any("T20" in s for s in select):
                result["banned_imports"].append("print() - use logging instead")
            # UP = pyupgrade rules
            if any("UP" in s for s in select):
                result["rules"]["pyupgrade"] = True

    return result


# =============================================================================
# Hazard Glob Patterns
# =============================================================================

def derive_hazard_patterns(hazards: List[Dict[str, Any]], target_dir: str = ".") -> List[Dict[str, Any]]:
    """
    Derive glob patterns from hazard file paths.

    Groups files by parent directory and creates patterns like:
    - artifacts/** (if multiple files in artifacts/)
    - logs/*.log (if multiple .log files in logs/)
    - specific/path/large_file.json (if only one file)

    Returns list of patterns with file counts and estimated tokens.
    """
    from collections import defaultdict

    if not hazards:
        return []

    target_path = Path(target_dir).resolve()

    # Group hazards by parent directory
    dir_files = defaultdict(list)

    for hazard in hazards:
        filepath = hazard.get("file", "")
        tokens = hazard.get("tokens", 0)

        try:
            # Make path relative to target
            file_path = Path(filepath)
            if file_path.is_absolute():
                try:
                    rel_path = file_path.relative_to(target_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            parent = str(rel_path.parent)
            filename = rel_path.name
            extension = rel_path.suffix

            dir_files[parent].append({
                "file": str(rel_path),
                "filename": filename,
                "extension": extension,
                "tokens": tokens
            })
        except Exception:
            continue

    # Generate patterns
    patterns = []

    for dir_path, files in dir_files.items():
        if len(files) == 1:
            # Single file - use specific path
            f = files[0]
            patterns.append({
                "pattern": f["file"],
                "file_count": 1,
                "total_tokens": f["tokens"],
                "type": "file"
            })
        else:
            # Multiple files - try to group by extension or use directory pattern
            extensions = defaultdict(list)
            for f in files:
                extensions[f["extension"]].append(f)

            # If same extension, use *.ext pattern
            if len(extensions) == 1:
                ext = list(extensions.keys())[0]
                total_tokens = sum(f["tokens"] for f in files)
                if dir_path == ".":
                    pattern = f"*{ext}" if ext else "*"
                else:
                    pattern = f"{dir_path}/*{ext}" if ext else f"{dir_path}/*"
                patterns.append({
                    "pattern": pattern,
                    "file_count": len(files),
                    "total_tokens": total_tokens,
                    "type": "extension"
                })
            else:
                # Mixed extensions - use directory/** pattern
                total_tokens = sum(f["tokens"] for f in files)
                if dir_path == ".":
                    pattern = "**/*"
                else:
                    pattern = f"{dir_path}/**"
                patterns.append({
                    "pattern": pattern,
                    "file_count": len(files),
                    "total_tokens": total_tokens,
                    "type": "directory"
                })

    # Sort by total tokens descending
    patterns.sort(key=lambda x: x["total_tokens"], reverse=True)

    # Format tokens for display
    for p in patterns:
        tokens = p["total_tokens"]
        if tokens >= 1000:
            p["tokens_display"] = f"~{tokens // 1000}K tokens"
        else:
            p["tokens_display"] = f"~{tokens} tokens"

    return patterns


# =============================================================================
# Directory Hazards
# =============================================================================

# Common directories that waste context when reading codebases
DIRECTORY_HAZARDS = {
    "__pycache__": "Python bytecode cache - always skip",
    ".git": "Git internals - use git commands instead",
    "node_modules": "NPM packages - skip unless debugging deps",
    ".venv": "Python virtual environment - skip",
    "venv": "Python virtual environment - skip",
    ".env": "Environment directory - skip",
    "dist": "Build output - skip unless debugging builds",
    "build": "Build output - skip unless debugging builds",
    ".eggs": "Python egg cache - skip",
    "*.egg-info": "Package metadata - skip",
    "artifacts": "Generated artifacts - skip unless debugging",
    "outputs": "Generated outputs - skip unless debugging",
    ".pytest_cache": "Pytest cache - skip",
    ".mypy_cache": "MyPy cache - skip",
    ".tox": "Tox environments - skip",
    "htmlcov": "Coverage reports - skip",
    ".coverage": "Coverage data - skip",
}


def get_directory_hazards(target_dir: str) -> List[Dict[str, Any]]:
    """
    Detect directories that should be skipped to avoid wasting context.

    Args:
        target_dir: Target directory to scan

    Returns:
        List of hazardous directories found with recommendations.
    """
    hazards = []
    target_path = Path(target_dir)

    for pattern, recommendation in DIRECTORY_HAZARDS.items():
        if "*" in pattern:
            # Glob pattern
            matches = list(target_path.glob(pattern))
            for match in matches:
                if match.is_dir():
                    hazards.append({
                        "directory": str(match.relative_to(target_path)),
                        "recommendation": recommendation
                    })
        else:
            # Exact match - check root and one level deep
            for search_path in [target_path / pattern, *target_path.glob(f"*/{pattern}")]:
                if search_path.is_dir():
                    hazards.append({
                        "directory": str(search_path.relative_to(target_path)),
                        "recommendation": recommendation
                    })
                    break  # Only include once per pattern

    # Sort by directory name
    hazards.sort(key=lambda x: x["directory"])

    return hazards


# =============================================================================
# Prompt & Persona Map
# =============================================================================

# Common patterns for finding agent prompts/personas
PROMPT_PATTERNS = [
    "SYSTEM_PROMPT", "PERSONA", "INSTRUCTIONS", "AGENT_PROMPT",
    "system_prompt", "persona", "instructions", "agent_prompt",
    "PROMPT_TEMPLATE", "DEFAULT_PROMPT", "BASE_PROMPT"
]


def find_agent_prompts(target_dir: str, results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Find agent prompts and personas in the codebase.

    Scans for:
    - .prompt, .txt files in prompts/ directories
    - Large string constants (>500 chars) in agent files
    - Variables matching SYSTEM_PROMPT, persona, instructions patterns

    Args:
        target_dir: Target directory to scan
        results: Analysis results (for structure info)

    Returns:
        List of persona maps with agent name, prompt summary, and source.
    """
    personas = []
    seen_agents = set()
    target_path = Path(target_dir)

    # Method 1: Scan for prompt files
    prompt_dirs = ["prompts", "prompt", "templates", "agents/prompts"]
    for prompt_dir in prompt_dirs:
        prompt_path = target_path / prompt_dir
        if prompt_path.exists():
            for file in prompt_path.glob("**/*"):
                if file.suffix in (".txt", ".prompt", ".md") and file.is_file():
                    try:
                        content = file.read_text(encoding="utf-8")[:2000]
                        # Extract first paragraph as summary
                        first_para = content.split("\n\n")[0].strip()
                        if len(first_para) > 50:
                            agent_name = file.stem.replace("_", " ").title()
                            if agent_name not in seen_agents:
                                seen_agents.add(agent_name)
                                personas.append({
                                    "agent": agent_name,
                                    "summary": first_para[:200] + ("..." if len(first_para) > 200 else ""),
                                    "source": str(file.relative_to(target_path)),
                                    "type": "file"
                                })
                    except (IOError, OSError):
                        continue

    # Method 2: Scan agent files for large string constants
    structure = results.get("structure", {})
    files = structure.get("files", {})

    for filepath, data in files.items():
        if "agent" not in filepath.lower():
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)

            # Look for string assignments to prompt-like variables
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_name = target.id
                            # Check if it matches prompt patterns
                            if any(pattern in var_name for pattern in PROMPT_PATTERNS):
                                if (isinstance(node.value, ast.Constant) and
                                    isinstance(node.value.value, str) and
                                    len(node.value.value) > 100):
                                    prompt_text = node.value.value
                                    # Extract first paragraph
                                    first_para = prompt_text.split("\n\n")[0].strip()
                                    agent_name = Path(filepath).stem.replace("_", " ").title()
                                    if agent_name not in seen_agents:
                                        seen_agents.add(agent_name)
                                        personas.append({
                                            "agent": agent_name,
                                            "summary": first_para[:200] + ("..." if len(first_para) > 200 else ""),
                                            "source": f"{Path(filepath).name}:{var_name}",
                                            "type": "constant"
                                        })

                # Also check for class attributes in agent classes
                elif isinstance(node, ast.ClassDef):
                    if any(base in str(node.bases) for base in ["Agent", "BaseAgent"]):
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name):
                                        var_name = target.id
                                        if any(pattern in var_name for pattern in PROMPT_PATTERNS):
                                            if (isinstance(item.value, ast.Constant) and
                                                isinstance(item.value.value, str) and
                                                len(item.value.value) > 100):
                                                prompt_text = item.value.value
                                                first_para = prompt_text.split("\n\n")[0].strip()
                                                agent_name = node.name.replace("Agent", "")
                                                if agent_name not in seen_agents:
                                                    seen_agents.add(agent_name)
                                                    personas.append({
                                                        "agent": agent_name,
                                                        "summary": first_para[:200] + ("..." if len(first_para) > 200 else ""),
                                                        "source": f"{Path(filepath).name}:{node.name}.{var_name}",
                                                        "type": "class"
                                                    })

        except (IOError, OSError, SyntaxError):
            continue

    # Sort by agent name
    personas.sort(key=lambda x: x["agent"])

    return personas

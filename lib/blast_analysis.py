"""
Repo X-Ray: Blast Radius Analysis

Computes the impact of changing any file by traversing the import graph
and call graph to find transitive dependents. Answers: "If I change
this file, what else might break?"

Combines two signal sources:
- Import graph (imported_by edges from import_analysis)
- Call graph (reverse_lookup from call_analysis)

Usage:
    from blast_analysis import analyze_blast_radius

    blast = analyze_blast_radius(import_results, call_results)
"""

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# Blast Radius Computation
# =============================================================================

def _build_reverse_import_graph(import_results: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Build a mapping from module stem -> set of modules that import it."""
    graph = import_results.get("graph", {})
    reverse = {}
    for module_name, info in graph.items():
        reverse.setdefault(module_name, set())
        for dep in info.get("imported_by", []):
            reverse.setdefault(module_name, set()).add(dep)
    return reverse


def _build_reverse_call_graph(call_results: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Build a mapping from module stem -> set of modules that call into it.

    Uses cross_module_calls to find which modules contain call sites
    to functions defined in each target module.
    """
    reverse = {}
    cross_module = call_results.get("cross_module_calls", call_results.get("cross_module", {}))

    for func_name, data in cross_module.items():
        # Extract the target module from the qualified function name
        target_module = func_name.split(".")[0] if "." in func_name else ""
        if not target_module:
            continue

        for site in data.get("call_sites", []):
            caller_file = site.get("file", "")
            caller_module = Path(caller_file).stem
            if caller_module and caller_module != target_module:
                reverse.setdefault(target_module, set()).add(caller_module)

    return reverse


def _compute_file_blast_radius(
    target_module: str,
    reverse_imports: Dict[str, Set[str]],
    reverse_calls: Dict[str, Set[str]],
    max_hops: int = 5,
) -> Dict[str, Any]:
    """BFS through combined reverse import + call graph from a target module.

    Returns the set of transitively affected modules and hop distances.
    """
    visited = {}  # module -> hop distance
    queue = deque([(target_module, 0)])

    while queue:
        module, hops = queue.popleft()
        if module in visited or hops > max_hops:
            continue
        visited[module] = hops

        # Follow both import and call reverse edges
        dependents = set()
        dependents.update(reverse_imports.get(module, set()))
        dependents.update(reverse_calls.get(module, set()))

        for dep in dependents:
            if dep not in visited:
                queue.append((dep, hops + 1))

    # Remove the target itself from affected count
    visited.pop(target_module, None)

    return {
        "affected_modules": visited,
        "affected_count": len(visited),
        "max_hop_distance": max(visited.values()) if visited else 0,
    }


def _classify_risk(affected_count: int, total_modules: int) -> str:
    """Classify blast radius risk level."""
    if total_modules == 0:
        return "isolated"
    ratio = affected_count / total_modules
    if ratio >= 0.5 or affected_count >= 10:
        return "critical"
    elif ratio >= 0.25 or affected_count >= 5:
        return "high"
    elif affected_count >= 2:
        return "moderate"
    return "isolated"


# =============================================================================
# Public API
# =============================================================================

def analyze_blast_radius(
    import_results: Dict[str, Any],
    call_results: Dict[str, Any],
    git_results: Optional[Dict[str, Any]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Compute blast radius for every module in the codebase.

    Args:
        import_results: Output from analyze_imports()
        call_results: Output from analyze_calls()
        git_results: Optional git results (for co-modification cross-reference)
        verbose: Print progress

    Returns:
        {
            "files": [
                {
                    "module": str,
                    "affected_count": int,
                    "risk": "isolated"|"moderate"|"high"|"critical",
                    "affected_modules": [{"module": str, "hops": int}],
                    "max_hops": int,
                }
            ],
            "summary": {
                "critical_count": int,
                "high_count": int,
                "average_affected": float,
            }
        }
    """
    graph = import_results.get("graph", {})
    if not graph:
        return {"files": [], "summary": {"critical_count": 0, "high_count": 0, "average_affected": 0.0}}

    reverse_imports = _build_reverse_import_graph(import_results)
    reverse_calls = _build_reverse_call_graph(call_results) if call_results else {}
    total_modules = len(graph)

    # Build co-modification set for cross-referencing (optional)
    co_modified_pairs = set()
    if git_results:
        for pair in git_results.get("coupling", []):
            file_a = pair.get("file_a", "")
            file_b = pair.get("file_b", "")
            if file_a and file_b:
                a_stem = Path(file_a).stem
                b_stem = Path(file_b).stem
                co_modified_pairs.add((a_stem, b_stem))
                co_modified_pairs.add((b_stem, a_stem))

    files = []
    total_affected = 0

    for module_name in graph:
        result = _compute_file_blast_radius(module_name, reverse_imports, reverse_calls)
        affected_count = result["affected_count"]
        risk = _classify_risk(affected_count, total_modules)
        total_affected += affected_count

        # Build affected list with hop distances, sorted by hops
        affected_list = sorted(
            [
                {"module": mod, "hops": hops}
                for mod, hops in result["affected_modules"].items()
            ],
            key=lambda x: x["hops"],
        )

        entry = {
            "module": module_name,
            "affected_count": affected_count,
            "risk": risk,
            "affected_modules": affected_list[:15],  # Limit output size
            "max_hops": result["max_hop_distance"],
        }

        # Flag undertesting if affected by import/call graph but never co-modified in git
        if co_modified_pairs and affected_list:
            never_co_modified = [
                m["module"] for m in affected_list
                if (module_name, m["module"]) not in co_modified_pairs
            ]
            if never_co_modified:
                entry["undertested_dependents"] = never_co_modified[:5]

        files.append(entry)

    # Sort by affected_count descending
    files.sort(key=lambda x: x["affected_count"], reverse=True)

    critical_count = sum(1 for f in files if f["risk"] == "critical")
    high_count = sum(1 for f in files if f["risk"] == "high")
    avg_affected = total_affected / total_modules if total_modules else 0.0

    return {
        "files": files[:20],  # Top 20 highest-impact files
        "summary": {
            "critical_count": critical_count,
            "high_count": high_count,
            "average_affected": round(avg_affected, 1),
        },
    }

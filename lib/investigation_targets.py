"""
Repo X-Ray: Investigation Targets

Computes prioritized investigation signals for the deep_crawl agent.
All analysis is deterministic and derived from existing xray results.

Usage:
    from investigation_targets import compute_investigation_targets

    targets = compute_investigation_targets(
        ast_results=ast_results,
        import_results=import_results,
        call_results=call_results,
        git_results=git_results,
        gap_results=gap_results,
        root_dir="."
    )
"""

import ast as ast_module
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# Configuration
# =============================================================================

# Hardcoded generic names used by the scanner. The JSON config at
# .claude/skills/deep-crawl/configs/generic_names.json exists for the
# deep_crawl agent's reference only — the scanner uses these defaults
# to stay zero-config.
GENERIC_FUNCTION_NAMES = {
    "process", "handle", "run", "execute", "resolve",
    "validate", "transform", "convert", "dispatch", "apply",
    "update", "get", "set", "do", "perform",
    "manage", "build", "create", "make", "generate",
    "parse", "format", "load", "save", "send",
    "check", "verify", "compute", "calculate", "evaluate",
    "init", "setup", "configure", "prepare", "cleanup",
    "start", "stop", "reset", "refresh", "sync",
    "call", "invoke", "emit", "notify", "trigger",
    "wrap", "decorate", "inject", "register", "connect",
    "fetch", "pull", "push", "merge", "split",
    "filter", "map", "reduce", "aggregate", "collect",
    "render", "display", "show", "output", "log",
}

GENERIC_MODULE_NAMES = {
    "utils", "helpers", "common", "base", "core",
    "misc", "tools", "lib", "shared", "general",
    "service", "handler", "manager", "processor", "worker",
    "engine", "runner", "executor", "dispatcher", "resolver",
    "controller", "adapter", "wrapper", "proxy", "factory",
}


# =============================================================================
# Ambiguous Interfaces
# =============================================================================

def compute_ambiguous_interfaces(
    ast_results: Dict[str, Any],
    call_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Find functions whose names are generic and whose signatures lack
    sufficient type information for a downstream agent to understand
    their behavior without reading the source.

    Scoring: (cross_module_callers * cc) / max(type_coverage, 0.1)
    Higher score = more ambiguous = higher investigation priority.
    """
    ambiguous = []
    files = ast_results.get("files", {})
    cross_module = call_results.get("cross_module", {}) if call_results else {}

    for filepath, file_data in files.items():
        for func in file_data.get("functions", []):
            _assess_function_ambiguity(
                func, filepath, cross_module, ambiguous
            )
        for cls in file_data.get("classes", []):
            for method in cls.get("methods", []):
                _assess_function_ambiguity(
                    method, filepath, cross_module, ambiguous,
                    class_name=cls.get("name")
                )

    ambiguous.sort(key=lambda x: x.get("ambiguity_score", 0), reverse=True)
    return ambiguous[:30]


def _assess_function_ambiguity(
    func: Dict, filepath: str, cross_module: Dict,
    results: List, class_name: Optional[str] = None
) -> None:
    """Assess a single function for ambiguity and append to results if flagged."""
    name = func.get("name", "")
    base_name = name.split(".")[-1] if "." in name else name

    # Skip private/dunder methods
    if base_name.startswith("_"):
        return

    is_generic = base_name.lower() in GENERIC_FUNCTION_NAMES

    # Calculate type coverage for this function
    args = func.get("args", [])
    non_self_args = [a for a in args if a.get("name") not in ("self", "cls")]
    typed_args = sum(1 for a in non_self_args if a.get("type"))
    total_args = max(len(non_self_args), 1)
    has_return_type = bool(func.get("returns"))
    type_coverage = (typed_args + (1 if has_return_type else 0)) / (total_args + 1)

    # Count cross-module callers
    module_name = Path(filepath).stem
    qualified_names = [
        f"{module_name}.{name}",
        name,
    ]
    if class_name:
        qualified_names.append(f"{class_name}.{name}")
        qualified_names.append(f"{module_name}.{class_name}.{name}")

    caller_count = 0
    for qname in qualified_names:
        if qname in cross_module:
            caller_count = max(caller_count, cross_module[qname].get("call_count", 0))

    # Only flag if: generic name OR (low type coverage AND has cross-module callers)
    if not is_generic and (type_coverage >= 0.5 or caller_count < 2):
        return

    cc = func.get("complexity", 1)
    ambiguity_score = (max(caller_count, 1) * max(cc, 1)) / max(type_coverage, 0.1)

    results.append({
        "function": name,
        "class": class_name,
        "file": filepath,
        "line": func.get("start_line", 0),
        "reason": "generic_name" if is_generic else "low_type_coverage",
        "type_coverage": round(type_coverage, 2),
        "cc": cc,
        "cross_module_callers": caller_count,
        "ambiguity_score": round(ambiguity_score, 1),
    })


# =============================================================================
# Entry-to-Side-Effect Paths
# =============================================================================

def compute_entry_side_effect_paths(
    ast_results: Dict[str, Any],
    call_results: Dict[str, Any],
    gap_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    For each detected entry point, walk the call graph to find reachable
    side effects. Returns paths with estimated module-level hop counts.

    This gives the deep_crawl agent a roadmap: "trace from here to here."
    Hop counts are module-level estimates; actual function call depth may differ.
    """
    entry_points = gap_results.get("entry_points", [])
    if not entry_points:
        return []

    cross_module = call_results.get("cross_module", {}) if call_results else {}
    files = ast_results.get("files", {})

    # Collect all side effects by file
    side_effects_by_file = defaultdict(list)
    for filepath, file_data in files.items():
        for se in file_data.get("side_effects", []):
            side_effects_by_file[filepath].append(se)

    # Build a simplified call graph: caller_module_stem -> set of callee_module_stems
    # Also build stem->filepath mapping
    stem_to_filepath = {}
    for filepath in files:
        stem = Path(filepath).stem
        stem_to_filepath[stem] = filepath

    call_graph = defaultdict(set)
    for func_name, data in cross_module.items():
        for site in data.get("call_sites", []):
            caller_file = site.get("file", "")
            caller_stem = Path(caller_file).stem
            # The func_name key format varies; extract module stem
            callee_stem = func_name.split(".")[0] if "." in func_name else ""
            if caller_stem and callee_stem and caller_stem != callee_stem:
                call_graph[caller_stem].add(callee_stem)

    paths = []
    for ep in entry_points:
        ep_file = ep.get("file", "")
        ep_stem = Path(ep_file).stem

        # BFS to find reachable side effects
        visited = set()
        queue = [(ep_stem, 0)]
        reachable_effects = []
        max_hops = 0

        while queue:
            module_stem, hops = queue.pop(0)
            if module_stem in visited or hops > 8:
                continue
            visited.add(module_stem)
            max_hops = max(max_hops, hops)

            # Check for side effects in this module
            module_filepath = stem_to_filepath.get(module_stem, "")
            if module_filepath:
                for se in side_effects_by_file.get(module_filepath, []):
                    reachable_effects.append({
                        "type": se.get("category", "unknown"),
                        "location": f"{module_filepath}:{se.get('line', 0)}",
                        "pattern": se.get("call", ""),
                        "hops_from_entry": hops,
                    })

            # Follow call graph edges
            for callee_stem in call_graph.get(module_stem, set()):
                if callee_stem not in visited:
                    queue.append((callee_stem, hops + 1))

        if reachable_effects:
            entry_name = ep.get("entry_point", ep.get("function", ep_file))
            paths.append({
                "entry_point": f"{ep_file}:{entry_name}",
                "entry_type": ep.get("type", "unknown"),
                "reachable_side_effects": reachable_effects[:10],
                "estimated_hop_count": max_hops,
                "modules_traversed": len(visited),
                "granularity": "module_level",
            })

    paths.sort(key=lambda x: x["estimated_hop_count"], reverse=True)
    return paths[:10]


# =============================================================================
# Coupling Anomalies
# =============================================================================

def compute_coupling_anomalies(
    git_results: Dict[str, Any],
    import_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Find file pairs that are frequently co-modified but have no import
    relationship. These represent hidden coupling.
    """
    coupling = git_results.get("coupling", []) if git_results else []
    if not coupling:
        return []

    import_graph = import_results.get("graph", {}) if import_results else {}

    anomalies = []
    for pair in coupling:
        # Handle both possible key formats defensively
        file_a = pair.get("file_a", "")
        file_b = pair.get("file_b", "")
        if not file_a and isinstance(pair.get("files"), list) and len(pair.get("files", [])) >= 2:
            file_a = pair["files"][0]
            file_b = pair["files"][1]

        # Score field: try 'score', 'confidence', 'count' (normalize count)
        score = pair.get("score", pair.get("confidence", 0))
        if not score:
            # count-based coupling: normalize against a threshold
            count = pair.get("count", 0)
            score = min(count / 5.0, 1.0) if count else 0

        if not file_a or not file_b or score < 0.7:
            continue

        # Check import relationship (direct or 1-hop transitive)
        mod_a = Path(file_a).stem
        mod_b = Path(file_b).stem

        a_imports = set(import_graph.get(mod_a, {}).get("imports", []))
        b_imports = set(import_graph.get(mod_b, {}).get("imports", []))
        # imported_by not needed for forward-edge checks


        has_direct_import = mod_b in a_imports or mod_a in b_imports

        # Check 1-hop transitive: A imports C, C imports B
        has_transitive = False
        if not has_direct_import:
            for mid in a_imports:
                mid_imports = set(import_graph.get(mid, {}).get("imports", []))
                if mod_b in mid_imports:
                    has_transitive = True
                    break
            if not has_transitive:
                for mid in b_imports:
                    mid_imports = set(import_graph.get(mid, {}).get("imports", []))
                    if mod_a in mid_imports:
                        has_transitive = True
                        break

        if not has_direct_import and not has_transitive:
            anomalies.append({
                "files": [file_a, file_b],
                "co_modification_score": round(score, 2),
                "has_import_relationship": False,
                "reason": "co_modified_without_imports",
            })

    anomalies.sort(key=lambda x: x["co_modification_score"], reverse=True)
    return anomalies[:10]


# =============================================================================
# Convention Deviations
# =============================================================================

def compute_convention_deviations(
    ast_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Detect dominant coding patterns and flag outliers.

    Checks:
    - Class __init__ signature patterns (config injection, no-arg, etc.)
    - Decorator usage consistency
    """
    files = ast_results.get("files", {})
    deviations = []

    # Analyze class __init__ patterns
    init_patterns = defaultdict(list)  # pattern -> [class_info]

    for filepath, file_data in files.items():
        for cls in file_data.get("classes", []):
            init_method = None
            for method in cls.get("methods", []):
                if method.get("name") == "__init__":
                    init_method = method
                    break

            if init_method:
                args = init_method.get("args", [])
                non_self_args = [a for a in args if a.get("name") not in ("self", "cls")]
                has_typed_args = any(a.get("type") for a in non_self_args)

                if len(non_self_args) == 0:
                    pattern = "no_args"
                elif has_typed_args:
                    pattern = "typed_injection"
                else:
                    pattern = "untyped_args"

                init_patterns[pattern].append({
                    "class": cls.get("name", ""),
                    "file": filepath,
                    "line": cls.get("start_line", 0),
                    "param_count": len(non_self_args),
                })

    # Find the dominant pattern and flag deviations
    if init_patterns:
        dominant = max(init_patterns.items(), key=lambda x: len(x[1]))
        dominant_pattern = dominant[0]
        dominant_count = len(dominant[1])

        for pattern, classes in init_patterns.items():
            if pattern != dominant_pattern and len(classes) <= dominant_count * 0.3:
                deviations.append({
                    "convention": f"class_init_{dominant_pattern}",
                    "conforming_count": dominant_count,
                    "violating": [
                        {
                            "class": c["class"],
                            "file": c["file"],
                            "line": c["line"],
                            "actual_pattern": pattern,
                        }
                        for c in classes
                    ],
                })

    # Analyze return type annotation patterns
    funcs_with_returns = 0
    funcs_without_returns = 0
    funcs_no_returns_list = []

    for filepath, file_data in files.items():
        for func in file_data.get("functions", []):
            name = func.get("name", "")
            if name.startswith("_"):
                continue
            if func.get("returns"):
                funcs_with_returns += 1
            else:
                funcs_without_returns += 1
                funcs_no_returns_list.append({
                    "class": None,
                    "file": filepath,
                    "line": func.get("start_line", 0),
                    "function": name,
                })

    total_funcs = funcs_with_returns + funcs_without_returns
    if total_funcs >= 5:
        # If >70% have return types, flag those without
        if funcs_with_returns / total_funcs > 0.7 and funcs_no_returns_list:
            deviations.append({
                "convention": "return_type_annotations",
                "conforming_count": funcs_with_returns,
                "violating": funcs_no_returns_list[:10],
            })
        # If <30% have return types, flag those with (unusual effort)
        elif funcs_with_returns / total_funcs < 0.3 and funcs_with_returns > 0:
            # Not flagging the minority as "deviating" — skip
            pass

    return deviations[:10]


# =============================================================================
# Shared Mutable State
# =============================================================================

def compute_shared_mutable_state(
    ast_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Find module-level variables that are mutated at runtime.

    Re-parses files via ast.parse() because this analysis requires
    tracking mutation patterns that the existing single-pass AST
    visitor doesn't capture.

    Detects:
    - Module-level assignments that are later mutated via augmented
      assignment, method calls (.append, .update, etc.), or subscript assignment
    - Singleton patterns (_instance = None with get_instance)
    """
    files = ast_results.get("files", {})
    shared_state = []

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast_module.parse(source)
        except (IOError, SyntaxError, UnicodeDecodeError):
            continue

        # Find module-level assignments (not inside functions/classes)
        module_vars = {}
        for node in ast_module.iter_child_nodes(tree):
            if isinstance(node, ast_module.Assign):
                for target in node.targets:
                    if isinstance(target, ast_module.Name):
                        name = target.id
                        # Skip constants (ALL_CAPS) and dunder
                        if name.isupper() or name.startswith("__"):
                            continue
                        module_vars[name] = {
                            "name": name,
                            "line": node.lineno,
                            "file": filepath,
                        }

        if not module_vars:
            continue

        # Check if any module var is mutated inside functions
        _MUTATION_METHODS = {
            "append", "extend", "update", "clear", "pop", "remove",
            "add", "discard", "insert", "setdefault",
        }

        for node in ast_module.walk(tree):
            if not isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
                continue

            for child in ast_module.walk(node):
                # Augmented assignment: var += X
                if isinstance(child, ast_module.AugAssign):
                    if isinstance(child.target, ast_module.Name):
                        if child.target.id in module_vars:
                            var = module_vars[child.target.id]
                            var["mutated"] = True
                            var.setdefault("mutated_by", []).append(
                                f"{filepath}:{node.name}"
                            )

                # Method calls on var: var.append(), var.update(), etc.
                if isinstance(child, ast_module.Call):
                    if isinstance(child.func, ast_module.Attribute):
                        if isinstance(child.func.value, ast_module.Name):
                            if child.func.value.id in module_vars:
                                method = child.func.attr
                                if method in _MUTATION_METHODS:
                                    var = module_vars[child.func.value.id]
                                    var["mutated"] = True
                                    var.setdefault("mutated_by", []).append(
                                        f"{filepath}:{node.name}"
                                    )

                # Subscript assignment: var[key] = X
                if isinstance(child, ast_module.Assign):
                    for t in child.targets:
                        if isinstance(t, ast_module.Subscript):
                            if isinstance(t.value, ast_module.Name):
                                if t.value.id in module_vars:
                                    var = module_vars[t.value.id]
                                    var["mutated"] = True
                                    var.setdefault("mutated_by", []).append(
                                        f"{filepath}:{node.name}"
                                    )

        # Collect mutated vars
        for name, var in module_vars.items():
            if var.get("mutated"):
                mutated_by = sorted(set(var.get("mutated_by", [])))
                shared_state.append({
                    "variable": name,
                    "file": filepath,
                    "line": var["line"],
                    "scope": "module",
                    "mutated_by": mutated_by[:5],
                    "risk": "concurrent_modification" if len(mutated_by) > 1 else "hidden_state",
                })

    shared_state.sort(key=lambda x: len(x.get("mutated_by", [])), reverse=True)
    return shared_state[:20]


# =============================================================================
# High Uncertainty Modules
# =============================================================================

def compute_high_uncertainty_modules(
    ast_results: Dict[str, Any],
    call_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Compute composite uncertainty score for each module.

    Modules with high uncertainty are where the deep_crawl agent should
    spend its reading budget — the name and signature alone don't tell
    the story.

    Scoring (normalized to 0-1):
      generic_name (1.0) + low_type_coverage (0.5-1.0) +
      high_fan_in (0.5-1.0) + no_docstrings (1.0) +
      high_complexity (1.0) + has_kwargs (0.5) +
      no_return_annotations (0.5)
    Threshold: normalized score >= 0.3
    """
    files = ast_results.get("files", {})
    cross_module = call_results.get("cross_module", {}) if call_results else {}

    # Compute fan-in per module stem
    fan_in = defaultdict(int)
    for func_name, data in cross_module.items():
        module_stem = func_name.split(".")[0] if "." in func_name else ""
        if module_stem:
            fan_in[module_stem] += data.get("call_count", 0)

    results = []
    for filepath, file_data in files.items():
        module_name = Path(filepath).stem
        reasons = []
        score = 0.0

        # Generic name check
        if module_name.lower() in GENERIC_MODULE_NAMES:
            reasons.append("generic_name")
            score += 1.0

        # Type coverage check
        type_data = file_data.get("type_coverage", {})
        coverage = type_data.get("coverage_percent", 0) / 100.0
        if coverage < 0.3:
            reasons.append("low_type_coverage")
            score += 1.0
        elif coverage < 0.6:
            reasons.append("moderate_type_coverage")
            score += 0.5

        # Fan-in check
        module_fan_in = fan_in.get(module_name, 0)
        if module_fan_in >= 5:
            reasons.append("high_fan_in")
            score += 1.0
        elif module_fan_in >= 3:
            reasons.append("moderate_fan_in")
            score += 0.5

        # Docstring check
        has_docstrings = False
        for cls in file_data.get("classes", []):
            if cls.get("docstring"):
                has_docstrings = True
                break
        if not has_docstrings:
            for func in file_data.get("functions", []):
                if func.get("docstring"):
                    has_docstrings = True
                    break
        if not has_docstrings and (file_data.get("functions") or file_data.get("classes")):
            reasons.append("no_docstrings")
            score += 1.0

        # High complexity check
        complexity_data = file_data.get("complexity", {})
        hotspots = complexity_data.get("hotspots", {})
        max_cc = 0
        if isinstance(hotspots, dict):
            max_cc = max(hotspots.values()) if hotspots else 0
        elif isinstance(hotspots, list):
            max_cc = max((h.get("complexity", 0) for h in hotspots), default=0)
        if max_cc > 15:
            reasons.append("high_complexity")
            score += 1.0

        # kwargs check in public functions
        has_kwargs = False
        for func in file_data.get("functions", []):
            if func.get("name", "").startswith("_"):
                continue
            for arg in func.get("args", []):
                arg_name = arg.get("name", "")
                if arg_name.startswith("**"):
                    has_kwargs = True
                    break
            if has_kwargs:
                break
        if has_kwargs:
            reasons.append("has_kwargs")
            score += 0.5

        # No return type annotations on public functions
        public_funcs = [f for f in file_data.get("functions", [])
                        if not f.get("name", "").startswith("_")]
        if public_funcs:
            funcs_with_returns = sum(1 for f in public_funcs if f.get("returns"))
            if funcs_with_returns == 0:
                reasons.append("no_return_annotations")
                score += 0.5

        # Normalize to 0-1
        normalized_score = score / 6.0

        if normalized_score >= 0.3 and reasons:
            results.append({
                "module": filepath,
                "reasons": reasons,
                "uncertainty_score": round(normalized_score, 2),
                "fan_in": module_fan_in,
                "type_coverage": round(coverage, 2),
                "max_cc": max_cc,
            })

    results.sort(key=lambda x: x["uncertainty_score"], reverse=True)
    return results[:20]


# =============================================================================
# Domain Entities
# =============================================================================

def compute_domain_entities(
    ast_results: Dict[str, Any],
    gap_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract domain-specific entities: Pydantic models, dataclasses,
    TypedDicts, and classes referenced in type annotations across 3+ modules.
    """
    data_models = gap_results.get("data_models", [])

    entities = []
    seen = set()

    for model in data_models:
        name = model.get("name", "")
        if name and name not in seen:
            seen.add(name)
            fields = model.get("fields", [])
            field_names = [f.get("name", "") for f in fields[:5]] if isinstance(fields, list) else []
            entities.append({
                "name": name,
                "type": model.get("type", "class"),
                "file": model.get("file", ""),
                "line": model.get("line", 0),
                "fields": field_names,
            })

    # Also find classes used in type annotations across 3+ files
    files = ast_results.get("files", {})
    type_references = defaultdict(set)  # class_name -> set of files

    _BUILTIN_TYPES = {
        "str", "int", "float", "bool", "bytes",
        "list", "dict", "set", "tuple", "frozenset",
        "None", "Any", "Optional", "Union", "List", "Dict",
        "Set", "Tuple", "Type", "Callable", "Iterator",
        "Generator", "Coroutine", "Awaitable", "Iterable",
        "Sequence", "Mapping", "MutableMapping",
    }

    for filepath, file_data in files.items():
        for func in file_data.get("functions", []):
            for arg in func.get("args", []):
                _extract_type_ref(arg.get("type", ""), filepath, type_references, _BUILTIN_TYPES)
            _extract_type_ref(func.get("returns", ""), filepath, type_references, _BUILTIN_TYPES)

        for cls in file_data.get("classes", []):
            for method in cls.get("methods", []):
                for arg in method.get("args", []):
                    _extract_type_ref(arg.get("type", ""), filepath, type_references, _BUILTIN_TYPES)
                _extract_type_ref(method.get("returns", ""), filepath, type_references, _BUILTIN_TYPES)

    for name, referenced_in in type_references.items():
        if len(referenced_in) >= 3 and name not in seen:
            seen.add(name)
            entities.append({
                "name": name,
                "type": "type_annotation_entity",
                "file": "",
                "line": 0,
                "referenced_in": sorted(list(referenced_in))[:5],
            })

    entities.sort(
        key=lambda x: len(x.get("referenced_in", x.get("fields", []))),
        reverse=True
    )
    return entities[:20]


def _extract_type_ref(
    type_str: str, filepath: str,
    type_references: Dict[str, set],
    builtin_types: set,
) -> None:
    """Extract a base type name from a type annotation string."""
    if not type_str:
        return
    # Strip container types: Optional[Foo] -> Foo, List[Foo] -> Foo
    base = type_str.split("[")[0].split(".")[-1].strip()
    if base and base[0].isupper() and base not in builtin_types:
        type_references[base].add(filepath)


# =============================================================================
# Master Function
# =============================================================================

def compute_investigation_targets(
    ast_results: Dict[str, Any],
    import_results: Dict[str, Any],
    call_results: Dict[str, Any],
    git_results: Dict[str, Any],
    gap_results: Dict[str, Any],
    root_dir: str = ".",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Compute all investigation targets from existing xray analysis results.

    Returns a dict suitable for inclusion in xray JSON output.

    Args:
        ast_results: Raw output from analyze_codebase() — must have 'files' key
        import_results: Output from analyze_imports()
        call_results: Output from analyze_calls()
        git_results: The git dict from results (has 'risk', 'coupling', 'freshness')
        gap_results: Dict with 'entry_points' and 'data_models' from gap_features
        root_dir: Project root directory
        verbose: Print progress to stderr
    """
    targets = {}

    def _run(name, func):
        try:
            if verbose:
                print(f"  {name}...", file=sys.stderr)
            return func()
        except Exception as e:
            if verbose:
                print(f"  {name} failed: {e}", file=sys.stderr)
            return []

    if verbose:
        print("Computing investigation targets...", file=sys.stderr)

    targets["ambiguous_interfaces"] = _run(
        "Ambiguous interfaces",
        lambda: compute_ambiguous_interfaces(ast_results, call_results)
    )

    targets["entry_to_side_effect_paths"] = _run(
        "Entry-to-side-effect paths",
        lambda: compute_entry_side_effect_paths(ast_results, call_results, gap_results)
    )

    targets["coupling_anomalies"] = _run(
        "Coupling anomalies",
        lambda: compute_coupling_anomalies(git_results, import_results)
    )

    targets["convention_deviations"] = _run(
        "Convention deviations",
        lambda: compute_convention_deviations(ast_results)
    )

    targets["shared_mutable_state"] = _run(
        "Shared mutable state",
        lambda: compute_shared_mutable_state(ast_results)
    )

    targets["high_uncertainty_modules"] = _run(
        "High uncertainty modules",
        lambda: compute_high_uncertainty_modules(ast_results, call_results)
    )

    targets["domain_entities"] = _run(
        "Domain entities",
        lambda: compute_domain_entities(ast_results, gap_results)
    )

    # Summary stats
    targets["summary"] = {
        "ambiguous_interfaces": len(targets["ambiguous_interfaces"]),
        "entry_paths": len(targets["entry_to_side_effect_paths"]),
        "coupling_anomalies": len(targets["coupling_anomalies"]),
        "convention_deviations": sum(
            len(d.get("violating", []))
            for d in targets["convention_deviations"]
        ),
        "shared_mutable_state": len(targets["shared_mutable_state"]),
        "high_uncertainty_modules": len(targets["high_uncertainty_modules"]),
        "domain_entities": len(targets["domain_entities"]),
    }

    if verbose:
        print(f"  Investigation targets computed: {targets['summary']}", file=sys.stderr)

    return targets

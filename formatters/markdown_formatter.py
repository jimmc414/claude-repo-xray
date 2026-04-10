"""
Repo X-Ray: Markdown Output Formatter

Formats analysis results as human/AI-readable Markdown.
Supports gap analysis features for enhanced output.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add lib directory to path for gap_features import
FORMATTER_DIR = Path(__file__).parent
LIB_DIR = FORMATTER_DIR.parent / "lib"
sys.path.insert(0, str(LIB_DIR))


def _class_header(name, bases, line, code_lang):
    if code_lang == "typescript":
        ext = f" extends {', '.join(bases)}" if bases else ""
        return f"class {name}{ext} {{ // L{line}"
    bases_str = f"({', '.join(bases)})" if bases else ""
    return f"class {name}{bases_str}:  # L{line}"


def _method_sig(name, is_async, code_lang):
    prefix = "async " if is_async else ""
    if code_lang == "typescript":
        return f"    {prefix}{name}(...)"
    return f"    {prefix}def {name}(...)"


def _comment(text, code_lang):
    return f"    // {text}" if code_lang == "typescript" else f"    # {text}"


def _self_prefix(code_lang):
    return "this." if code_lang == "typescript" else "self."


def _build_display_names(all_paths):
    """Compute shortest unique path suffix for each file path.

    Unique basenames → basename only.
    Colliding basenames → walk parent segments until unique.
    If >3 segments needed → parent/.../name form.
    """
    from collections import defaultdict
    by_basename = defaultdict(list)
    for p in all_paths:
        if p:
            by_basename[Path(p).name].append(p)

    result = {}
    for basename, paths in by_basename.items():
        if len(paths) == 1:
            result[paths[0]] = basename
            continue
        for full_path in paths:
            parts = Path(full_path).parts
            for depth in range(2, len(parts) + 1):
                suffix = parts[-depth:]
                if sum(1 for p in paths if Path(p).parts[-min(depth, len(Path(p).parts)):] == suffix) == 1:
                    result[full_path] = suffix[0] + "/.../" + suffix[-1] if depth > 3 else "/".join(suffix)
                    break
            else:
                result[full_path] = full_path
    return result


def format_markdown(
    results: Dict[str, Any],
    project_name: Optional[str] = None,
    gap_features: Optional[Dict[str, Any]] = None
) -> str:
    """
    Format analysis results as Markdown.

    Args:
        results: Analysis results dictionary
        project_name: Optional project name for title
        gap_features: Optional dict of gap feature flags

    Returns:
        Markdown string
    """
    lines = []
    metadata = results.get("metadata", {})
    summary = results.get("summary", {})
    gap = gap_features or {}

    # Build disambiguation map for monorepo-safe display names
    # Normalize paths: strip target_dir prefix to dedup absolute/relative forms
    _target_dir = str(gap.get("target_dir", ""))
    _td_prefix = (_target_dir + "/") if _target_dir and not _target_dir.endswith("/") else _target_dir

    def _norm(p):
        if _td_prefix and p.startswith(_td_prefix):
            return p[len(_td_prefix):]
        return p

    _all_paths = set()
    for fp in results.get("structure", {}).get("files", {}).keys():
        if fp:
            _all_paths.add(_norm(fp))
    for r in results.get("git", {}).get("risk", []):
        _all_paths.add(_norm(r.get("file", "")))
    for bucket in ("active", "aging", "stale", "dormant"):
        for f in results.get("git", {}).get("freshness", {}).get(bucket, []):
            p = f.get("file", "") if isinstance(f, dict) else str(f) if f else ""
            if p:
                _all_paths.add(_norm(p))
    for fc in results.get("git", {}).get("function_churn", []):
        _all_paths.add(_norm(fc.get("file", "")))
    for cc in results.get("git", {}).get("coupling_clusters", []):
        for f in cc.get("files", []):
            _all_paths.add(_norm(f))
    for v in results.get("git", {}).get("velocity", []):
        _all_paths.add(_norm(v.get("file", "")))
    for hs in results.get("hotspots", []):
        _all_paths.add(_norm(hs.get("file", "")))
    for effects in results.get("side_effects", {}).get("by_type", {}).values():
        for e in effects:
            _all_paths.add(_norm(e.get("file", "")))
    for fp in results.get("security_concerns", {}).keys():
        _all_paths.add(_norm(fp))
    for fp in results.get("sql_strings", {}).keys():
        _all_paths.add(_norm(fp))
    for fp in results.get("silent_failures", {}).keys():
        _all_paths.add(_norm(fp))
    for dm in results.get("deprecation_markers", []):
        _all_paths.add(_norm(dm.get("file", "")))
    for av in results.get("async_patterns", {}).get("violations", []):
        _all_paths.add(_norm(av.get("file", "")))
    inv = results.get("investigation_targets", {})
    for m in inv.get("high_uncertainty_modules", []):
        _all_paths.add(_norm(m.get("module", "")))
    for a in inv.get("coupling_anomalies", []):
        for f in a.get("files", []):
            _all_paths.add(_norm(f))
    for s in inv.get("shared_mutable_state", []):
        _all_paths.add(_norm(s.get("file", "")))
    _all_paths.discard("")
    _dn_map = _build_display_names(list(_all_paths))

    def dn(path):
        """Display name with monorepo disambiguation."""
        if not path:
            return ""
        return _dn_map.get(_norm(path), Path(path).name)

    # Language-aware code fence and file label
    lang = metadata.get("language", "python")
    code_lang = "typescript" if lang in ("typescript", "mixed") else "python"
    file_label = {"python": "Python files", "typescript": "Source files", "mixed": "Source files"}.get(lang, "Source files")

    # Header
    name = project_name or Path(metadata.get("target_directory", ".")).name
    lines.append(f"# Codebase Analysis: {name}")
    lines.append("")
    lines.append(f"Generated: {metadata.get('generated_at', 'N/A')} | "
                 f"Preset: {metadata.get('preset', 'full')} | "
                 f"Files: {summary.get('total_files', 0)}")
    lines.append("")

    # Summary Table
    lines.append("## Summary")
    lines.append("")

    # GitHub About (if enabled)
    if gap.get("github_about"):
        try:
            from gap_features import get_github_about
            target_dir = gap.get("target_dir", ".")
            about = get_github_about(target_dir)
            if about.get("description"):
                lines.append(f"> **About:** {about['description']}")
                lines.append("")
            if about.get("topics"):
                topics = ", ".join(about["topics"][:10])
                lines.append(f"> **Topics:** {topics}")
                lines.append("")
            if about.get("error"):
                lines.append(f"> *{about['error']}*")
                lines.append("")
        except Exception:
            pass

    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| {file_label} | {summary.get('total_files', 0)} |")
    lines.append(f"| Total lines | {summary.get('total_lines', 0):,} |")
    lines.append(f"| Functions | {summary.get('total_functions', 0)} |")
    lines.append(f"| Classes | {summary.get('total_classes', 0)} |")
    if summary.get("type_coverage"):
        lines.append(f"| Type coverage | {summary.get('type_coverage', 0)}% |")
    if summary.get("total_tokens"):
        lines.append(f"| Est. tokens | {summary.get('total_tokens', 0):,} |")
    lines.append("")

    # ==========================================================================
    # GAP ANALYSIS FEATURES
    # ==========================================================================

    # Prose - Natural language architecture overview
    if gap.get("prose"):
        try:
            from gap_features import generate_prose
            prose = generate_prose(results, name)
            lines.append("## Architecture Overview")
            lines.append("")
            lines.append(prose)
            lines.append("")
        except Exception:
            pass

    # Mermaid Diagram
    if gap.get("mermaid"):
        try:
            from gap_features import generate_mermaid_diagram
            imports = results.get("imports", {})
            if imports:
                # Include call data for data flow annotations if enabled
                call_data = results.get("calls") if gap.get("data_flow") else None
                mermaid = generate_mermaid_diagram(imports, call_data)
                lines.append("## Architecture Diagram")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to read:** FOUNDATION modules are at the bottom (no dependencies).")
                    lines.append("> CORE modules build on foundation. ORCHESTRATION modules coordinate others.")
                    lines.append("> Arrows show import direction. Dotted arrows (<-.->) indicate circular dependencies.")
                    lines.append("")
                lines.append(mermaid)
                lines.append("")
        except Exception:
            pass

    # Priority Scores - Split into Architectural Pillars and Maintenance Hotspots
    if gap.get("priority_scores"):
        try:
            from gap_features import get_architectural_pillars, get_maintenance_hotspots

            # Architectural Pillars - files that many modules depend on
            pillars = get_architectural_pillars(results, 10)
            if pillars:
                lines.append("## Architectural Pillars")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** These are the most-imported files in the codebase. Changes here")
                    lines.append("> ripple outward, so understand them first. High import counts indicate core")
                    lines.append("> abstractions that many modules depend on.")
                    lines.append("")
                lines.append("*Foundation files that many modules depend on - understand these first:*")
                lines.append("")
                lines.append("| # | File | Imported By | Key Dependents |")
                lines.append("|---|------|-------------|----------------|")
                for i, p in enumerate(pillars, 1):
                    dependents = ", ".join(p.get("imported_by", [])[:3])
                    if len(p.get("imported_by", [])) > 3:
                        dependents += "..."
                    lines.append(f"| {i} | `{dn(p.get('file', ''))}` | {p.get('imported_by_count', 0)} modules | {dependents} |")
                lines.append("")

            # Maintenance Hotspots - files with high risk/churn
            hotspots = get_maintenance_hotspots(results, 10)
            if hotspots:
                lines.append("## Maintenance Hotspots")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** These files have high git churn, hotfix frequency, or author entropy.")
                    lines.append("> They represent areas of instability. Be extra careful when modifying these files")
                    lines.append("> and consider adding tests before changes.")
                    lines.append("")
                lines.append("*Files with high churn/risk - handle with care:*")
                lines.append("")
                lines.append("| # | File | Risk | Factors |")
                lines.append("|---|------|------|---------|")
                for i, h in enumerate(hotspots, 1):
                    lines.append(f"| {i} | `{dn(h.get('file', ''))}` | {h.get('risk_score', 0):.2f} | {h.get('reason', '')} |")
                lines.append("")
        except Exception:
            pass

    # Entry Points
    if gap.get("entry_points"):
        try:
            from gap_features import detect_entry_points, extract_cli_arguments
            target_dir = gap.get("target_dir", ".")
            entry_pts = detect_entry_points(results, target_dir)
            if entry_pts:
                lines.append("## Entry Points")
                lines.append("")
                lines.append("| Entry Point | File | Usage |")
                lines.append("|-------------|------|-------|")
                for ep in entry_pts[:10]:
                    # Convert absolute path to relative for portability
                    filepath = ep.get('file', '')
                    usage = ep.get('usage', '')
                    try:
                        rel_path = "./" + str(Path(filepath).relative_to(target_dir))
                        rel_usage = usage.replace(str(target_dir), ".").replace("\\", "/")
                    except ValueError:
                        rel_path = "./" + dn(filepath)
                        rel_usage = usage
                    lines.append(f"| `{ep.get('entry_point', '')}` | {rel_path} | `{rel_usage}` |")
                lines.append("")

                # CLI Arguments — TS scanner data takes precedence
                ts_cli = results.get("cli")
                if ts_cli and ts_cli.get("framework"):
                    lines.append("### CLI Arguments")
                    lines.append("")
                    lines.append(f"**Framework:** {ts_cli['framework']}")
                    lines.append("")
                    if ts_cli.get("options"):
                        lines.append("| Option | Description |")
                        lines.append("|--------|-------------|")
                        for opt in ts_cli["options"][:15]:
                            lines.append(f"| `{opt.get('flag', '')}` | {opt.get('description', '-') or '-'} |")
                        lines.append("")
                    if ts_cli.get("commands"):
                        lines.append("**Commands:**")
                        for cmd in ts_cli["commands"][:10]:
                            desc = cmd.get("description", "") or ""
                            lines.append(f"- `{cmd['name']}` — {desc}")
                        lines.append("")
                elif gap.get("cli_arguments"):
                    structure = results.get("structure", {})
                    cli_args = extract_cli_arguments(entry_pts, structure)
                    if cli_args:
                        lines.append("### CLI Arguments")
                        lines.append("")
                        for entry in cli_args[:5]:
                            entry_name = dn(entry.get('file', ''))
                            lines.append(f"**{entry_name}:**")
                            lines.append("")
                            lines.append("| Argument | Required | Default | Help |")
                            lines.append("|----------|----------|---------|------|")
                            for arg in entry.get("arguments", [])[:10]:
                                arg_name = arg.get("name", "")
                                required = "Yes" if arg.get("required") else "No"
                                default = arg.get("default", "-") or "-"
                                help_text = arg.get("help", "-") or "-"
                                if len(help_text) > 50:
                                    help_text = help_text[:47] + "..."
                                lines.append(f"| `{arg_name}` | {required} | {default} | {help_text} |")
                            lines.append("")
        except Exception:
            pass

    # Inline Skeletons
    inline_n = gap.get("inline_skeletons")
    if inline_n and inline_n > 0:
        try:
            from gap_features import format_inline_skeletons
            skeletons = format_inline_skeletons(results, inline_n)
            if skeletons:
                lines.append("## Critical Classes")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** These classes are ranked by architectural importance: import weight,")
                    lines.append("> base class significance (Agent, Model, etc.), and method complexity. The skeleton")
                    lines.append("> shows the class interface without implementation details.")
                    lines.append("")
                lines.append(f"*Top {len(skeletons)} classes by architectural importance:*")
                lines.append("")
                for cls in skeletons:
                    bases = f"({', '.join(cls.get('bases', []))})" if cls.get('bases') else ""
                    lines.append(f"### {cls['name']}{bases} ({dn(cls.get('file', ''))}:{cls.get('line', 0)})")
                    lines.append("")
                    # Show docstring if available
                    if cls.get("docstring"):
                        lines.append(f"> {cls['docstring']}")
                        lines.append("")
                    lines.append(f"```{code_lang}")
                    lines.append(_class_header(cls['name'], cls.get('bases', []), cls.get('line', 0), code_lang))
                    # Show __init__/constructor signature first if available
                    if cls.get("init_signature"):
                        lines.append(f"    {cls['init_signature']}")
                        lines.append("")

                    # Show instance variables from __init__ (if enabled)
                    instance_vars = cls.get("instance_vars", [])
                    if instance_vars and gap.get("instance_vars"):
                        lines.append(_comment("Instance variables:", code_lang))
                        sp = _self_prefix(code_lang)
                        for iv in instance_vars[:8]:
                            iv_name = iv.get("name", "")
                            iv_value = iv.get("value", "...")
                            lines.append(f"    {sp}{iv_name} = {iv_value}")
                        if len(instance_vars) > 8:
                            lines.append(_comment(f"... and {len(instance_vars) - 8} more", code_lang))
                        lines.append("")

                    for field in cls.get("fields", [])[:5]:
                        field_name = field.get("name", "")
                        field_type = field.get("type", "")
                        if field_type:
                            lines.append(f"    {field_name}: {field_type}")
                        else:
                            lines.append(f"    {field_name}")
                    # Show methods (skip __init__/constructor since we showed it above)
                    init_names = {"__init__", "constructor"}
                    methods_shown = 0
                    for method in cls.get("methods", []):
                        method_name = method.get("name", "")
                        if method_name in init_names:
                            continue  # Already shown
                        if methods_shown >= 10:
                            break
                        lines.append(_method_sig(method_name, method.get("is_async"), code_lang))
                        methods_shown += 1
                    remaining = cls.get("method_count", 0) - methods_shown - (1 if cls.get("init_signature") else 0)
                    if remaining > 0:
                        lines.append(_comment(f"... and {remaining} more methods", code_lang))
                    lines.append("```")
                    lines.append("")
        except Exception:
            pass

    # Data Models
    if gap.get("data_models"):
        try:
            from gap_features import extract_data_models
            from collections import defaultdict
            models = extract_data_models(results)
            if models:
                lines.append("## Data Models")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** Data models define the structure of data flowing through the system.")
                    lines.append("> They're grouped by domain: API models, Config, Agents, etc. Understanding these")
                    lines.append("> helps you know what data shapes to expect when calling functions.")
                    lines.append("")
                lines.append(f"*{len(models)} Pydantic/dataclass models found:*")
                lines.append("")

                # Group models by domain
                models_by_domain = defaultdict(list)
                for model in models:
                    models_by_domain[model.get("domain", "Other")].append(model)

                # Show models grouped by domain
                models_shown = 0
                for domain in sorted(models_by_domain.keys()):
                    if models_shown >= 15:
                        break
                    domain_models = models_by_domain[domain]
                    lines.append(f"### {domain}")
                    lines.append("")
                    for model in domain_models:
                        if models_shown >= 15:
                            lines.append(f"*...and {len(models) - models_shown} more models*")
                            break
                        bases = f"({', '.join(model.get('bases', []))})" if model.get('bases') else ""
                        model_type = model.get("type", "")
                        lines.append(f"**{model['name']}** [{model_type}] ({dn(model.get('file', ''))})")
                        lines.append("")

                        # Show field constraints if enabled and available
                        field_constraints = model.get("field_constraints", {})
                        if field_constraints and gap.get("pydantic_validators"):
                            lines.append("| Field | Type | Constraints |")
                            lines.append("|-------|------|-------------|")
                            for field in model.get("fields", [])[:8]:
                                field_name = field.get("name", "")
                                field_type = field.get("type", "")
                                constraints = field_constraints.get(field_name, {})
                                # Format constraints
                                constraint_strs = []
                                for k, v in constraints.items():
                                    if k != "type":
                                        constraint_strs.append(f"{k}={v}")
                                constraint_text = ", ".join(constraint_strs) if constraint_strs else "-"
                                lines.append(f"| `{field_name}` | {field_type} | {constraint_text} |")
                            lines.append("")
                        else:
                            lines.append(f"```{code_lang}")
                            lines.append(_class_header(model['name'], model.get('bases', []), model.get('line', 0), code_lang))
                            for field in model.get("fields", [])[:8]:
                                field_name = field.get("name", "")
                                field_type = field.get("type", "")
                                if field_type:
                                    lines.append(f"    {field_name}: {field_type}")
                                else:
                                    lines.append(f"    {field_name}")
                            lines.append("```")
                            lines.append("")

                        # Show validators if enabled and available
                        validators = model.get("validators", [])
                        if validators and gap.get("pydantic_validators"):
                            validator_names = [f'`{v.get("name", "")}`' for v in validators[:5]]
                            lines.append(f"*Validators:* {', '.join(validator_names)}")
                            lines.append("")
                        models_shown += 1
        except Exception:
            pass

    # Hazards (Large Files and Directories)
    if gap.get("hazards"):
        try:
            from gap_features import detect_hazards, get_directory_hazards, derive_hazard_patterns
            file_hazards = detect_hazards(results)
            target_dir = gap.get("target_dir", ".")
            dir_hazards = get_directory_hazards(target_dir)

            if file_hazards or dir_hazards:
                lines.append("## Context Hazards")
                lines.append("")

                # Show glob patterns if enabled
                if file_hazards and gap.get("hazard_patterns"):
                    patterns = derive_hazard_patterns(file_hazards, target_dir)
                    if patterns:
                        lines.append("### Patterns to Exclude")
                        lines.append("")
                        lines.append("*Use these glob patterns to skip large files:*")
                        lines.append("")
                        for p in patterns[:10]:
                            lines.append(f"- `{p.get('pattern', '')}` ({p.get('file_count', 0)} files, {p.get('tokens_display', '')})")
                        lines.append("")

                # File hazards
                if file_hazards:
                    lines.append("### Large Files")
                    lines.append("")
                    lines.append("*DO NOT read these files directly - use skeleton view:*")
                    lines.append("")
                    lines.append("| Tokens | File | Recommendation |")
                    lines.append("|--------|------|----------------|")
                    for h in file_hazards[:10]:
                        lines.append(f"| {h.get('tokens', 0):,} | `{dn(h.get('file', ''))}` | {h.get('recommendation', '')} |")
                    lines.append("")

                # Directory hazards
                if dir_hazards:
                    lines.append("### Skip Directories")
                    lines.append("")
                    lines.append("*These directories waste context - always skip:*")
                    lines.append("")
                    for dh in dir_hazards[:15]:
                        lines.append(f"- `{dh.get('directory', '')}/` - {dh.get('recommendation', '')}")
                    lines.append("")
        except Exception:
            pass

    # Logic Maps
    logic_n = gap.get("logic_maps")
    if logic_n and logic_n > 0:
        try:
            from gap_features import generate_logic_maps
            maps = generate_logic_maps(results, logic_n)
            if maps:
                lines.append("## Logic Maps")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to read:** These are control flow visualizations for complex functions.")
                    lines.append("> `->` = conditional branch, `*` = loop, `try:` = exception handling,")
                    lines.append("> `!` = except handler, `[X]` = side effect, `{X}` = state mutation.")
                    lines.append("> CC (Cyclomatic Complexity) indicates the number of independent paths.")
                    lines.append("")
                lines.append("*Control flow visualization for complex functions:*")
                lines.append("")
                for lm in maps:
                    lines.append(f"### {lm.get('method', '')}() - {dn(lm.get('file', ''))}:{lm.get('line', 0)} (CC:{lm.get('complexity', 0)})")
                    lines.append("")
                    # Show docstring if available
                    if lm.get("docstring"):
                        lines.append(f"> {lm['docstring']}")
                        lines.append("")
                    # Show heuristic summary if available
                    if lm.get("heuristic"):
                        lines.append(f"**Summary:** {lm['heuristic']}")
                        lines.append("")
                    lines.append("```")
                    for flow_line in lm.get("flow", [])[:30]:
                        lines.append(flow_line)
                    if len(lm.get("flow", [])) > 30:
                        lines.append(f"... ({len(lm['flow']) - 30} more lines)")
                    lines.append("```")
                    if lm.get("side_effects"):
                        lines.append(f"**Side Effects:** {', '.join(lm['side_effects'][:5])}")
                    if lm.get("state_mutations"):
                        lines.append(f"**State Mutations:** {', '.join(lm['state_mutations'][:5])}")
                    lines.append("")

                # Add Logic Map Legend at the end
                lines.append("### Logic Map Legend")
                lines.append("")
                lines.append("```")
                lines.append("->    : Control flow / conditional branch")
                lines.append("*     : Loop iteration (for/while)")
                lines.append("try:  : Try block start")
                lines.append("!     : Exception handler (except)")
                lines.append("[X]   : Side effect (DB, API, file I/O)")
                lines.append("{X}   : State mutation")
                lines.append("```")
                lines.append("")
        except Exception:
            pass

    # Method Signatures
    if gap.get("signatures"):
        try:
            from gap_features import format_signatures
            sigs = format_signatures(results, 10)
            if sigs:
                lines.append("## Method Signatures (Hotspots)")
                lines.append("")
                for sig in sigs:
                    lines.append(f"### {sig.get('name', '')}() - {dn(sig.get('file', ''))}:{sig.get('line', 0)}")
                    lines.append("")
                    # Build signature
                    async_prefix = "async " if sig.get("is_async") else ""
                    args_list = []
                    for arg in sig.get("args", []):
                        arg_str = arg.get("name", "")
                        if arg.get("type"):
                            arg_str += f": {arg['type']}"
                        if arg.get("default"):
                            arg_str += f" = {arg['default']}"
                        args_list.append(arg_str)
                    args_str = ", ".join(args_list)
                    ret = f" -> {sig['returns']}" if sig.get("returns") else ""
                    lines.append(f"```{code_lang}")
                    if code_lang == "typescript":
                        lines.append(f"{async_prefix}function {sig['name']}({args_str}){ret}")
                    else:
                        lines.append(f"{async_prefix}def {sig['name']}({args_str}){ret}")
                    lines.append("```")
                    if sig.get("docstring"):
                        lines.append(f"> {sig['docstring'][:200]}")
                    lines.append("")
        except Exception:
            pass

    # State Mutations
    if gap.get("state_mutations"):
        try:
            from gap_features import extract_state_mutations
            mutations = extract_state_mutations(results)
            if mutations:
                lines.append("## State Mutations")
                lines.append("")
                lines.append("*Attribute modifications in complex functions:*")
                lines.append("")
                for func_name, muts in list(mutations.items())[:15]:
                    lines.append(f"### {func_name}")
                    for m in muts[:10]:
                        lines.append(f"- `{m}`")
                    lines.append("")
        except Exception:
            pass

    # Persona Map (Agent Prompts)
    if gap.get("persona_map"):
        try:
            from gap_features import find_agent_prompts
            target_dir = gap.get("target_dir", ".")
            personas = find_agent_prompts(target_dir, results)
            if personas:
                lines.append("## Persona Map")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** Agent-based systems are driven by prompts that define behavior.")
                    lines.append("> This section shows discovered agent personas and their core instructions.")
                    lines.append("> Understanding these prompts helps you predict how agents will respond.")
                    lines.append("")
                lines.append("*Agent prompts and personas discovered in the codebase:*")
                lines.append("")
                for persona in personas[:10]:
                    agent = persona.get("agent", "Unknown")
                    summary = persona.get("summary", "")
                    source = persona.get("source", "")
                    ptype = persona.get("type", "")
                    lines.append(f"### {agent}")
                    lines.append("")
                    lines.append(f"**Source:** `{source}` ({ptype})")
                    lines.append("")
                    if summary:
                        lines.append(f"> {summary}")
                    lines.append("")
        except Exception:
            pass

    # Side Effects Detail
    if gap.get("side_effects_detail"):
        try:
            from gap_features import get_side_effects_detail
            detail = get_side_effects_detail(results)
            if detail:
                lines.append("## Side Effects (Detailed)")
                lines.append("")
                for filepath, effects in list(detail.items())[:10]:
                    lines.append(f"### {dn(filepath)}")
                    lines.append("")
                    lines.append("| Line | Type | Call |")
                    lines.append("|------|------|------|")
                    for e in effects[:10]:
                        lines.append(f"| {e.get('line', 0)} | {e.get('type', '')} | `{e.get('call', '')}` |")
                    lines.append("")
        except Exception:
            pass

    # Import Verification
    if gap.get("verify_imports"):
        try:
            from gap_features import verify_imports
            target_dir = gap.get("target_dir", ".")
            verification = verify_imports(results, target_dir)
            lines.append("## Import Verification")
            lines.append("")
            lines.append(f"**Summary:** {verification.get('passed', 0)} passed, {verification.get('failed', 0)} failed")
            lines.append("")
            broken = verification.get("broken", [])
            if broken:
                lines.append("### Broken Imports")
                for b in broken[:10]:
                    lines.append(f"- `{b.get('import', '')}` in `{b.get('module', '')}`")
                lines.append("")
            warnings = verification.get("warnings", [])
            if warnings:
                lines.append("### Warnings")
                for w in warnings[:10]:
                    lines.append(f"- `{w.get('module', '')}`: {w.get('issue', '')}")
                lines.append("")
        except Exception:
            pass

    # Verification Commands
    if gap.get("verify_commands"):
        try:
            from gap_features import generate_verify_commands
            commands = generate_verify_commands(results, name)
            if commands:
                lines.append("## Quick Verification")
                lines.append("")
                lines.append("```bash")
                for cmd in commands:
                    lines.append(cmd)
                lines.append("```")
                lines.append("")
        except Exception:
            pass

    # ==========================================================================
    # END GAP ANALYSIS FEATURES
    # ==========================================================================

    # Investigation Targets (for Deep Crawl)
    if gap.get("investigation_targets"):
        inv = results.get("investigation_targets", {})
        if inv and any(inv.get(k) for k in (
            "high_uncertainty_modules", "ambiguous_interfaces",
            "entry_to_side_effect_paths", "coupling_anomalies",
            "shared_mutable_state", "convention_deviations", "domain_entities",
        )):
            lines.append("## Investigation Targets (for Deep Crawl)")
            lines.append("")

            # High-uncertainty modules
            hum = inv.get("high_uncertainty_modules", [])
            if hum:
                items = ", ".join(
                    f"{dn(m['module'])} ({m['uncertainty_score']})"
                    for m in hum[:6]
                )
                lines.append(f"**High-uncertainty modules ({len(hum)}):** {items}")
                lines.append("")

            # Ambiguous interfaces
            ai = inv.get("ambiguous_interfaces", [])
            if ai:
                # Group by function name
                from collections import Counter
                name_counts = Counter(a["function"] for a in ai)
                items = ", ".join(
                    f"{name}() in {count} modules" if count > 1 else f"{name}()"
                    for name, count in name_counts.most_common(6)
                )
                lines.append(f"**Ambiguous interfaces ({len(ai)}):** {items}")
                lines.append("")

            # Entry-to-side-effect paths
            esp = inv.get("entry_to_side_effect_paths", [])
            if esp:
                items_list = []
                for p in esp[:5]:
                    entry = dn(p["entry_point"].split(":")[0]) if ":" in p["entry_point"] else p["entry_point"]
                    effects = ", ".join(set(
                        se["type"] for se in p.get("reachable_side_effects", [])
                    ))
                    items_list.append(
                        f"{entry} → {p['estimated_hop_count']} module hops → {effects}"
                    )
                lines.append(f"**Traced entry→side-effect paths ({len(esp)}):** " + "; ".join(items_list))
                lines.append("  *(Note: hop counts are module-level estimates; actual function call depth may differ)*")
                lines.append("")

            # Coupling anomalies
            ca = inv.get("coupling_anomalies", [])
            if ca:
                items = ", ".join(
                    f"{dn(a['files'][0])} ↔ {dn(a['files'][1])} "
                    f"(no imports, {int(a['co_modification_score']*100)}% co-modified)"
                    for a in ca[:4]
                )
                lines.append(f"**Coupling anomalies ({len(ca)}):** {items}")
                lines.append("")

            # Shared mutable state
            sms = inv.get("shared_mutable_state", [])
            if sms:
                items = ", ".join(
                    f"{s['variable']} in {dn(s['file'])}"
                    for s in sms[:5]
                )
                lines.append(f"**Shared mutable state ({len(sms)}):** {items}")
                lines.append("")

            # Convention deviations
            cd = inv.get("convention_deviations", [])
            if cd:
                items = ", ".join(
                    f"{d['convention']} ({len(d.get('violating', []))} violations)"
                    for d in cd[:4]
                )
                lines.append(f"**Convention deviations ({len(cd)}):** {items}")
                lines.append("")

            # Domain entities
            de = inv.get("domain_entities", [])
            if de:
                items = ", ".join(e["name"] for e in de[:8])
                lines.append(f"**Domain entities ({len(de)}):** {items}")
                lines.append("")

    # Priority Files (if available) - only show if not using gap priority_scores
    priority_files = results.get("priority_files", [])
    if priority_files and not gap.get("priority_scores"):
        lines.append("## Priority Files")
        lines.append("")
        lines.append("*Start here when working on this codebase:*")
        lines.append("")
        lines.append("| # | File | Score | Reasons |")
        lines.append("|---|------|-------|---------|")
        for i, pf in enumerate(priority_files[:10], 1):
            reasons = ", ".join(pf.get("reasons", []))
            lines.append(f"| {i} | `{pf.get('file', '')}` | {pf.get('score', 0):.2f} | {reasons} |")
        lines.append("")

    # Complexity Hotspots
    hotspots = results.get("hotspots", [])
    if hotspots:
        lines.append("## Complexity Hotspots")
        lines.append("")
        lines.append("*Functions with highest cyclomatic complexity:*")
        lines.append("")
        lines.append("| CC | Function | File |")
        lines.append("|----|----------|------|")

        # Deduplicate by function+short_path combo to avoid showing duplicate copies
        seen_combos = set()
        for hs in hotspots:
            if len(seen_combos) >= 10:
                break

            full_path = hs.get('file', '')
            func_name = hs.get('function', '')

            short_path = dn(full_path)

            # Deduplicate by function name + short path (skip duplicate file copies)
            combo = f"{func_name}:{short_path}"
            if combo in seen_combos:
                continue
            seen_combos.add(combo)

            lines.append(f"| {hs.get('complexity', 0)} | `{func_name}` | {short_path} |")
        lines.append("")

    # Import Analysis
    imports = results.get("imports", {})
    if imports:
        lines.append("## Import Analysis")
        lines.append("")

        # Layers - prefer tiers (topological) over layers (heuristic)
        raw_tiers = imports.get("tiers", {})
        if raw_tiers and any(raw_tiers.get(k) for k in ("foundation", "core", "orchestration")):
            layers = raw_tiers
            layer_heading = "### Architectural Tiers"
        else:
            layers = imports.get("layers", {})
            layer_heading = "### Architectural Layers"
        if layers:
            lines.append(layer_heading)
            lines.append("")

            # Check if layer_details is enabled
            if gap.get("layer_details"):
                try:
                    from gap_features import get_layer_details
                    detailed_layers = get_layer_details(results)
                    for layer_name, modules in detailed_layers.items():
                        if modules:
                            lines.append(f"**{layer_name.upper()}** ({len(modules)} modules)")
                            lines.append("")
                            lines.append("| Module | Imported By | Imports |")
                            lines.append("|--------|-------------|---------|")
                            for mod in modules[:10]:
                                mod_name = mod.get("module", "")
                                imported_by = mod.get("imported_by", 0)
                                imports_count = mod.get("imports", 0)
                                lines.append(f"| `{mod_name}` | {imported_by} | {imports_count} |")
                            if len(modules) > 10:
                                lines.append(f"| *...and {len(modules) - 10} more* | | |")
                            lines.append("")
                except Exception:
                    # Fallback to simple display
                    for layer_name, modules in layers.items():
                        if modules:
                            lines.append(f"**{layer_name.upper()}** ({len(modules)} modules)")
                            lines.append("")
                            for mod in modules[:5]:
                                lines.append(f"- `{mod}`")
                            if len(modules) > 5:
                                lines.append(f"- *...and {len(modules) - 5} more*")
                            lines.append("")
            else:
                # Simple display without details
                for layer_name, modules in layers.items():
                    if modules:
                        lines.append(f"**{layer_name.upper()}** ({len(modules)} modules)")
                        lines.append("")
                        for mod in modules[:5]:
                            lines.append(f"- `{mod}`")
                        if len(modules) > 5:
                            lines.append(f"- *...and {len(modules) - 5} more*")
                        lines.append("")

        # Circular Dependencies
        circular = imports.get("circular", [])
        if circular:
            lines.append("### Circular Dependencies")
            lines.append("")
            for a, b in circular[:5]:
                lines.append(f"- `{a}` <-> `{b}`")
            lines.append("")

        # Orphans
        orphans = imports.get("orphans", [])
        if orphans:
            lines.append("### Orphan Candidates")
            lines.append("")
            lines.append("*Files with no importers (may be entry points or dead code):*")
            lines.append("")
            seen_orphan_names = set()
            for orphan in orphans[:10]:
                if isinstance(orphan, dict):
                    orphan_path = orphan.get('file', orphan.get('module', ''))
                else:
                    orphan_path = str(orphan)
                # Show relative path or module name for portability
                if "/" in orphan_path or "\\" in orphan_path:
                    orphan_display = dn(orphan_path)
                else:
                    orphan_display = orphan_path
                if orphan_display in seen_orphan_names:
                    continue
                seen_orphan_names.add(orphan_display)
                lines.append(f"- `{orphan_display}`")
                if len(seen_orphan_names) >= 5:
                    break
            lines.append("")

        # External Dependencies
        try:
            from gap_features import get_external_dependencies
            external = get_external_dependencies(results)
            if external:
                lines.append("### External Dependencies")
                lines.append("")
                lines.append(f"*{len(external)} third-party packages:*")
                lines.append("")
                # Display in columns for readability
                lines.append(", ".join(f"`{dep}`" for dep in external[:30]))
                if len(external) > 30:
                    lines.append(f"*...and {len(external) - 30} more*")
                lines.append("")
        except Exception:
            pass

        # Barrel Files (TypeScript re-export hubs)
        barrel_files = imports.get("barrel_files", [])
        if barrel_files:
            lines.append("### Barrel Files")
            lines.append("")
            lines.append("*`index.ts` re-export hubs (high export count, minimal logic):*")
            lines.append("")
            lines.append("| File | Re-exports | Logic Lines | Sources |")
            lines.append("|------|------------|-------------|---------|")
            for bf in barrel_files[:10]:
                sources = ", ".join(f"`{s}`" for s in bf.get("reexported_from", [])[:5])
                if len(bf.get("reexported_from", [])) > 5:
                    sources += f", +{len(bf['reexported_from']) - 5} more"
                lines.append(f"| `{dn(bf.get('file', ''))}` | {bf.get('reexport_count', 0)} | {bf.get('logic_lines', 0)} | {sources} |")
            lines.append("")

    # TS Type System Overview (only for TypeScript/mixed projects)
    if lang in ("typescript", "mixed"):
        structure_files = results.get("structure", {}).get("files", {})
        all_interfaces = []
        all_type_aliases = []
        all_enums = []
        for fp, fdata in structure_files.items():
            for iface in fdata.get("ts_interfaces", []):
                all_interfaces.append({**iface, "file": fp})
            for ta in fdata.get("ts_type_aliases", []):
                all_type_aliases.append({**ta, "file": fp})
            for en in fdata.get("ts_enums", []):
                all_enums.append({**en, "file": fp})

        if all_interfaces or all_type_aliases or all_enums:
            lines.append("## Type System Overview")
            lines.append("")

            # Exported interfaces (top 20 by member count)
            exported_ifaces = [i for i in all_interfaces if i.get("exported")]
            if exported_ifaces:
                exported_ifaces.sort(key=lambda x: len(x.get("members", [])), reverse=True)
                lines.append("### Key Interfaces")
                lines.append("| Interface | Members | Extends | File |")
                lines.append("|-----------|---------|---------|------|")
                for iface in exported_ifaces[:20]:
                    members = len(iface.get("members", []))
                    extends = ", ".join(iface.get("extends", [])) or "-"
                    lines.append(f"| `{iface['name']}` | {members} | {extends} | {dn(iface['file'])} |")
                lines.append("")

            # Union/intersection types (discriminated unions are architecturally important)
            union_types = [t for t in all_type_aliases if t.get("type_kind") in ("union", "intersection") and t.get("exported")]
            if union_types:
                lines.append("### Union/Intersection Types")
                lines.append("| Type | Kind | File |")
                lines.append("|------|------|------|")
                for t in union_types[:15]:
                    lines.append(f"| `{t['name']}` | {t['type_kind']} | {dn(t['file'])} |")
                lines.append("")

            # Enums
            exported_enums = [e for e in all_enums if e.get("exported")]
            if exported_enums:
                lines.append("### Enums")
                lines.append("| Enum | Members | Const | File |")
                lines.append("|------|---------|-------|------|")
                for e in exported_enums[:15]:
                    lines.append(f"| `{e['name']}` | {len(e.get('members', []))} | {'yes' if e.get('is_const') else 'no'} | {dn(e['file'])} |")
                lines.append("")

    # TS Type Safety signals
    ts_specific = results.get("ts_specific", {})
    if ts_specific:
        any_d = ts_specific.get("any_density", {})
        if any(any_d.values()):
            lines.append("## Type Safety")
            lines.append("")
            lines.append("| Signal | Count |")
            lines.append("|--------|-------|")
            if any_d.get("explicit_any"):
                lines.append(f"| `any` type annotations | {any_d['explicit_any']} |")
            if any_d.get("as_any_assertions"):
                lines.append(f"| `as any` assertions | {any_d['as_any_assertions']} |")
            if any_d.get("ts_ignore_count"):
                lines.append(f"| `@ts-ignore` directives | {any_d['ts_ignore_count']} |")
            if any_d.get("ts_expect_error_count"):
                lines.append(f"| `@ts-expect-error` directives | {any_d['ts_expect_error_count']} |")
            lines.append("")

            mod_sys = ts_specific.get("module_system")
            if mod_sys:
                lines.append(f"Module system: **{mod_sys}**")
                lines.append("")

    # API Routes
    routes = results.get("routes", {})
    if routes:
        route_list = routes.get("routes", [])
        route_summary = routes.get("summary", {})
        if route_list:
            lines.append("## API Routes")
            lines.append("")
            fw = route_summary.get("frameworks_detected", [])
            fw_note = f" ({', '.join(fw)})" if fw else ""
            lines.append(f"*{route_summary.get('total_routes', len(route_list))} routes detected{fw_note}*")
            lines.append("")
            lines.append("| Method | Path | Handler | File |")
            lines.append("|--------|------|---------|------|")
            for r in route_list[:30]:
                lines.append(f"| {r.get('method', '?')} | `{r.get('path', '')}` | `{r.get('handler', '')}` | {dn(r.get('file', ''))}:{r.get('line', 0)} |")
            lines.append("")

    # Cross-Module Calls
    calls = results.get("calls", {})
    if calls:
        most_called = calls.get("most_called", [])
        if most_called:
            lines.append("## Cross-Module Calls")
            lines.append("")
            lines.append("*Most called functions across modules:*")
            lines.append("")
            lines.append("| Function | Call Sites | Modules |")
            lines.append("|----------|------------|---------|")
            for mc in most_called[:10]:
                lines.append(f"| `{mc.get('function', '')}` | {mc.get('call_sites', 0)} | {mc.get('modules', 0)} |")
            lines.append("")

    # Git Analysis
    git = results.get("git", {})
    if git:
        lines.append("## Git History Analysis")
        lines.append("")
        if gap.get("explain"):
            lines.append("> **How to use:** Git analysis reveals patterns invisible in code alone. High-risk files")
            lines.append("> have frequent changes (churn), bug fixes (hotfixes), or many authors (entropy).")
            lines.append("> Hidden coupling shows files that change together without import relationships.")
            lines.append("")

        # Risk
        risk = git.get("risk", [])
        if risk:
            lines.append("### High-Risk Files")
            lines.append("")
            lines.append("*Files with high churn, hotfixes, or author entropy:*")
            lines.append("")
            lines.append("| Risk | File | Factors |")
            lines.append("|------|------|---------|")
            for r in risk[:5]:
                factors = f"churn:{r.get('churn', 0)} hotfix:{r.get('hotfixes', 0)} authors:{r.get('authors', 0)}"
                lines.append(f"| {r.get('risk_score', 0):.2f} | `{dn(r.get('file', ''))}` | {factors} |")
            lines.append("")

        # Freshness
        freshness = git.get("freshness", {})
        if freshness:
            lines.append("### Freshness")
            lines.append("")
            active_files = freshness.get("active", [])
            aging_files = freshness.get("aging", [])
            stale_files = freshness.get("stale", [])
            dormant_files = freshness.get("dormant", [])
            lines.append(f"- **Active** (< 30 days): {len(active_files)} files")
            lines.append(f"- **Aging** (30-90 days): {len(aging_files)} files")
            lines.append(f"- **Stale** (90-180 days): {len(stale_files)} files")
            lines.append(f"- **Dormant** (> 180 days): {len(dormant_files)} files")
            lines.append("")

            # Show outliers for aging/stale/dormant files
            def get_file_info(f):
                if isinstance(f, dict):
                    return dn(f.get("file", "")), f.get("days", 0)
                return dn(f) if f else "", 0

            # Build commit count lookup from risk data
            risk_data = git.get("risk", [])
            commit_counts = {}
            for r in risk_data:
                fname = dn(r.get("file", ""))
                commit_counts[fname] = r.get("churn", 0)

            # Show most concerning files (stale and dormant first)
            outliers = []
            for f in dormant_files[:5]:
                fname, days = get_file_info(f)
                outliers.append((fname, "dormant", days))
            for f in stale_files[:5]:
                fname, days = get_file_info(f)
                outliers.append((fname, "stale", days))
            for f in aging_files[:5]:
                fname, days = get_file_info(f)
                outliers.append((fname, "aging", days))

            if outliers:
                lines.append("**Notable aging files:**")
                lines.append("")
                lines.append("| File | Status | Age | Commits |")
                lines.append("|------|--------|-----|---------|")
                for fname, status, days in outliers[:10]:
                    if fname:
                        commits = commit_counts.get(fname, "-")
                        lines.append(f"| `{fname}` | {status} | {days}d | {commits} |")
                lines.append("")

        # Hidden Coupling
        try:
            from gap_features import get_hidden_coupling
            coupling = get_hidden_coupling(results)
            if coupling:
                lines.append("### Hidden Coupling")
                lines.append("")
                lines.append("*Files that change together (without import relationship):*")
                lines.append("")
                lines.append("| File A | File B | Co-changes |")
                lines.append("|--------|--------|------------|")
                for c in coupling[:10]:
                    lines.append(f"| `{dn(c.get('file_a', ''))}` | `{dn(c.get('file_b', ''))}` | {c.get('count', 0)} |")
                lines.append("")
        except Exception:
            pass

        # Function-Level Hotspots
        function_churn = git.get("function_churn", [])
        if function_churn:
            lines.append("### Function-Level Hotspots")
            lines.append("")
            lines.append("*Most volatile functions (by commit frequency):*")
            lines.append("")
            lines.append("| Risk | Function | File | Commits | Hotfixes |")
            lines.append("|------|----------|------|---------|----------|")
            for fc in function_churn[:10]:
                lines.append(f"| {fc.get('risk_score', 0):.2f} | `{fc.get('function', '')}` | {dn(fc.get('file', ''))} | {fc.get('commits', 0)} | {fc.get('hotfixes', 0)} |")
            lines.append("")

        # Change Clusters
        coupling_clusters = git.get("coupling_clusters", [])
        if coupling_clusters:
            lines.append("### Change Clusters")
            lines.append("")
            lines.append("*Files that form change groups (modify one → check all):*")
            lines.append("")
            lines.append("| Cluster | Files | Co-changes |")
            lines.append("|---------|-------|------------|")
            for cc in coupling_clusters[:10]:
                file_list = ", ".join(f"`{dn(f)}`" for f in cc.get("files", []))
                lines.append(f"| {cc.get('cluster_id', 0) + 1} | {file_list} | {cc.get('total_cochanges', 0)} |")
            lines.append("")

        # Velocity Trends
        velocity = git.get("velocity", [])
        if velocity:
            # Only show non-stable trends (accelerating/decelerating are the actionable ones)
            notable = [v for v in velocity if v.get("trend") != "stable"]
            if notable:
                lines.append("### Velocity Trends")
                lines.append("")
                lines.append("*Files with accelerating or decelerating churn:*")
                lines.append("")
                lines.append("| File | Trend | Monthly |")
                lines.append("|------|-------|---------|")
                for v in notable[:10]:
                    monthly = v.get("monthly_commits", [])
                    lines.append(f"| `{dn(v.get('file', ''))}` | {v.get('trend', '')} | {monthly} |")
                lines.append("")
            # If all stable, show top files by volume
            elif velocity:
                lines.append("### Velocity Trends")
                lines.append("")
                lines.append("*All active files show stable churn velocity.*")
                lines.append("")

    # Side Effects
    side_effects = results.get("side_effects", {})
    if side_effects:
        by_type = side_effects.get("by_type", {})
        if by_type:
            lines.append("## Side Effects")
            lines.append("")
            lines.append("*Functions with external I/O operations:*")
            lines.append("")
            for effect_type, effects in by_type.items():
                if effects:
                    lines.append(f"### {effect_type.upper()}")
                    for e in effects[:5]:
                        lines.append(f"- `{e.get('call', '')}` in {dn(e.get('file', ''))}:{e.get('line', 0)}")
                    lines.append("")

    # Security Concerns
    security_concerns = results.get("security_concerns", {})
    if security_concerns and gap.get("security_concerns", True):
        all_concerns = []
        for filepath, concerns in security_concerns.items():
            for c in concerns:
                all_concerns.append({**c, "file": filepath})
        if all_concerns:
            lines.append("## Security Concerns")
            lines.append("")
            lines.append("*Code injection vectors detected (exec/eval/compile):*")
            lines.append("")
            for c in all_concerns:
                lines.append(f"- **{c.get('call', '')}()** in `{dn(c.get('file', ''))}:{c.get('line', 0)}`")
            lines.append("")

    # SQL String Literals
    sql_strings = results.get("sql_strings", {})
    if sql_strings and gap.get("db_query_patterns", True):
        all_sql = []
        for filepath, queries in sql_strings.items():
            for q in queries:
                all_sql.append({**q, "file": filepath})
        if all_sql:
            lines.append("## Database Queries (String Literals)")
            lines.append("")
            lines.append("| Query | Location |")
            lines.append("|-------|----------|")
            for q in all_sql[:15]:
                query_text = q.get("query", "")[:60]
                lines.append(f"| `{query_text}` | {dn(q.get('file', ''))}:{q.get('line', 0)} |")
            lines.append("")

    # Environment Variables
    try:
        from gap_features import get_environment_variables
        env_vars = get_environment_variables(results)
        if env_vars:
            lines.append("## Environment Variables")
            lines.append("")
            lines.append("*Environment variables used in the codebase:*")
            lines.append("")

            # Check if env_defaults feature is enabled (new format with defaults)
            if gap.get("env_defaults") and env_vars and "default" in env_vars[0]:
                lines.append("| Variable | Default | Required | Location |")
                lines.append("|----------|---------|----------|----------|")
                for ev in env_vars[:20]:
                    default = ev.get("default", "-") or "-"
                    fallback = ev.get("fallback_type", "none")
                    if ev.get("required"):
                        required = "**Yes**"
                    elif fallback == "or_fallback":
                        required = "No (or fallback)"
                    else:
                        required = "No"
                    location = f"{dn(ev.get('file', ''))}:{ev.get('line', 0)}"
                    lines.append(f"| `{ev.get('variable', '')}` | {default} | {required} | {location} |")
            else:
                # Fallback to old format
                lines.append("| Variable | File | Line |")
                lines.append("|----------|------|------|")
                for ev in env_vars[:20]:
                    lines.append(f"| `{ev.get('variable', '')}` | {dn(ev.get('file', ''))} | {ev.get('line', 0)} |")
            lines.append("")
    except Exception:
        pass

    # Test Coverage
    tests = results.get("tests", {})
    if tests and tests.get("test_file_count", 0) > 0:
        lines.append("## Test Coverage")
        lines.append("")
        lines.append(f"**{tests.get('test_file_count', 0)}** test files, "
                     f"**~{tests.get('test_function_count', 0)}** test functions")
        lines.append("")

        # Coverage by type
        coverage_by_type = tests.get("coverage_by_type", {})
        if coverage_by_type:
            lines.append("| Type | Files |")
            lines.append("|------|-------|")
            for test_type, count in sorted(coverage_by_type.items(), key=lambda x: -x[1]):
                lines.append(f"| `{test_type}/` | {count} |")
            lines.append("")

        # Tested/Untested
        tested = tests.get("tested_dirs", [])
        untested = tests.get("untested_dirs", [])
        if tested:
            lines.append(f"**Tested:** {', '.join(f'`{d}`' for d in tested[:8])}")
        if untested:
            lines.append(f"**Untested:** {', '.join(f'`{d}`' for d in untested[:8])}")
        lines.append("")

    # Technical Debt
    tech_debt = results.get("tech_debt", {})
    if tech_debt:
        markers = tech_debt.get("summary", {}).get("by_type", {})
        if markers:
            lines.append("## Technical Debt")
            lines.append("")
            total = sum(markers.values())
            lines.append(f"**{total}** markers found:")
            lines.append("")
            for marker_type, count in sorted(markers.items(), key=lambda x: -x[1]):
                lines.append(f"- **{marker_type}**: {count}")
            lines.append("")

    # Silent Failures
    silent_failures = results.get("silent_failures", {})
    if silent_failures and gap.get("silent_failures", True):
        all_failures = []
        for filepath, failures in silent_failures.items():
            for f in failures:
                all_failures.append({**f, "file": filepath})
        if all_failures:
            lines.append("## Silent Failures")
            lines.append("")
            lines.append("*Exception handlers that may hide errors:*")
            lines.append("")
            lines.append("| Pattern | Exception Type | Location |")
            lines.append("|---------|---------------|----------|")
            for sf in all_failures[:20]:
                pattern = sf.get("pattern", "-")
                except_type = sf.get("except_type", "-")
                lines.append(f"| {pattern} | {except_type} | `{dn(sf.get('file', ''))}:{sf.get('line', 0)}` |")
            lines.append("")

    # Deprecated APIs
    deprecation_markers = results.get("deprecation_markers", [])
    if deprecation_markers and gap.get("deprecation_markers", True):
        lines.append("## Deprecated APIs")
        lines.append("")
        lines.append("*Functions, classes, or code marked as deprecated:*")
        lines.append("")
        for dm in deprecation_markers[:20]:
            source = dm.get("source", dm.get("kind", "decorator"))
            name = dm.get("name", "")
            if name:
                lines.append(f"- `{name}` ({source}) — {dn(dm.get('file', ''))}:{dm.get('line', 0)}")
            else:
                text = dm.get("text", "")
                lines.append(f"- {text} ({source}) — {dn(dm.get('file', ''))}:{dm.get('line', 0)}")
        lines.append("")

    # Decorators
    decorators = results.get("decorators", {})
    if decorators:
        inventory = decorators.get("inventory", decorators)
        if inventory and isinstance(inventory, dict):
            lines.append("## Decorator Usage")
            lines.append("")
            sorted_decs = sorted(inventory.items(), key=lambda x: -x[1])[:10]
            for dec, count in sorted_decs:
                lines.append(f"- `@{dec}`: {count}")
            lines.append("")

    # Async Patterns
    async_patterns = results.get("async_patterns", {})
    if async_patterns and async_patterns.get("async_functions", 0) > 0:
        lines.append("## Async Patterns")
        lines.append("")
        lines.append(f"- Async functions: {async_patterns.get('async_functions', 0)}")
        lines.append(f"- Sync functions: {async_patterns.get('sync_functions', 0)}")
        lines.append(f"- Async for loops: {async_patterns.get('async_for_loops', 0)}")
        lines.append(f"- Async context managers: {async_patterns.get('async_context_managers', 0)}")
        lines.append("")

        # Async Violations subsection
        violations = async_patterns.get("violations", [])
        if violations and gap.get("async_violations", True):
            lines.append("### Async/Sync Violations")
            lines.append("")
            lines.append("*Blocking calls detected inside async functions:*")
            lines.append("")
            for v in violations[:15]:
                lines.append(f"- **{v.get('violation_type', '')}**: `{v.get('call', '')}` in `{v.get('function', '')}` — {dn(v.get('file', ''))}:{v.get('line', 0)}")
            lines.append("")

    # Test Example (Rosetta Stone)
    if gap.get("test_example"):
        try:
            # Prefer TS scanner's test_example if present
            example = tests.get("test_example") if tests else None
            if not example:
                from test_analysis import get_test_example
                target_dir = gap.get("target_dir", ".")
                example = get_test_example(target_dir, max_lines=50)
            if example:
                lines.append("## Testing Idioms")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** Use this test as a template for writing new tests.")
                    lines.append("> It demonstrates the mocking and assertion patterns used in this codebase.")
                    lines.append("")
                patterns = example.get("patterns", [])
                if patterns:
                    lines.append(f"**Patterns used:** {', '.join(f'`{p}`' for p in patterns)}")
                    lines.append("")
                lines.append(f"**Example:** `{example.get('file', '')}` ({example.get('line_count', 0)} lines)")
                lines.append("")
                lines.append(f"```{code_lang}")
                lines.append(example.get("content", ""))
                lines.append("```")
                lines.append("")
        except Exception:
            pass

    # Project Idioms — TS config rules take precedence over Python linter extraction
    config_rules = results.get("config_rules")
    if config_rules:
        ts_config = config_rules.get("typescript")
        eslint_config = config_rules.get("eslint")
        prettier_config = config_rules.get("prettier")
        if ts_config or eslint_config or prettier_config:
            lines.append("## Project Idioms")
            lines.append("")
            if gap.get("explain"):
                lines.append("> **How to use:** Follow these rules to ensure your code passes CI.")
                lines.append("")
            if ts_config:
                strict_label = "strict mode" if ts_config.get("strict") else "non-strict"
                lines.append(f"**TypeScript:** {strict_label} (from `{ts_config.get('config_file', 'tsconfig.json')}`)")
                flags = ts_config.get("flags", {})
                if flags:
                    lines.append("")
                    lines.append("| Flag | Value |")
                    lines.append("|------|-------|")
                    for flag, val in sorted(flags.items()):
                        lines.append(f"| {flag} | {val} |")
                lines.append("")
            if eslint_config:
                fw = f" (extends {eslint_config['framework']})" if eslint_config.get("framework") else ""
                lines.append(f"**ESLint:** `{eslint_config.get('config_file', '')}`{fw}")
                lines.append("")
            if prettier_config:
                lines.append(f"**Prettier:** `{prettier_config.get('config_file', '')}`")
                lines.append("")
    elif gap.get("linter_rules"):
        try:
            from gap_features import extract_linter_rules
            target_dir = gap.get("target_dir", ".")
            linter = extract_linter_rules(target_dir)
            if linter.get("linter"):
                lines.append("## Project Idioms")
                lines.append("")
                if gap.get("explain"):
                    lines.append("> **How to use:** Follow these rules to ensure your code passes CI.")
                    lines.append("> The linter configuration defines the coding style for this project.")
                    lines.append("")
                lines.append(f"**Linter:** {linter['linter']} (from `{linter.get('config_file', '')}`)")
                lines.append("")

                rules = linter.get("rules", {})
                if rules:
                    lines.append("| Rule | Value |")
                    lines.append("|------|-------|")
                    for rule, value in rules.items():
                        if isinstance(value, list):
                            value = ", ".join(str(v) for v in value[:5])
                        lines.append(f"| {rule} | {value} |")
                    lines.append("")

                banned = linter.get("banned_imports", [])
                if banned:
                    lines.append("**Banned patterns:**")
                    for b in banned[:5]:
                        lines.append(f"- {b}")
                    lines.append("")
        except Exception:
            pass

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by Repo X-Ray v{results.get('metadata', {}).get('tool_version', '2.0.0')}*")

    return "\n".join(lines)


def format_skeleton_markdown(
    ast_results: Dict[str, Any],
    max_files: int = 20
) -> str:
    """
    Format code skeleton as Markdown.

    Args:
        ast_results: AST analysis results
        max_files: Maximum number of files to include

    Returns:
        Markdown string with code skeletons
    """
    lines = []
    lines.append("# Code Skeleton")
    lines.append("")

    files = ast_results.get("files", {})

    for i, (filepath, data) in enumerate(files.items()):
        if i >= max_files:
            lines.append(f"*...and {len(files) - max_files} more files*")
            break

        lines.append(f"## {Path(filepath).name}")
        lines.append("")
        lines.append(f"*{filepath}*")
        lines.append("")

        # Classes
        for cls in data.get("classes", []):
            bases = f"({', '.join(cls.get('bases', []))})" if cls.get('bases') else ""
            lines.append(f"### class {cls['name']}{bases}")
            if cls.get("docstring"):
                lines.append(f"> {cls['docstring']}")

            for method in cls.get("methods", []):
                args = ", ".join(a.get("name", "") for a in method.get("args", []))
                ret = f" -> {method['returns']}" if method.get("returns") else ""
                async_prefix = "async " if method.get("is_async") else ""
                lines.append(f"- `{async_prefix}def {method['name']}({args}){ret}`")

            lines.append("")

        # Functions
        for func in data.get("functions", []):
            args = ", ".join(a.get("name", "") for a in func.get("args", []))
            ret = f" -> {func['returns']}" if func.get("returns") else ""
            async_prefix = "async " if func.get("is_async") else ""
            lines.append(f"### `{async_prefix}def {func['name']}({args}){ret}`")
            if func.get("docstring"):
                lines.append(f"> {func['docstring']}")
            lines.append("")

    return "\n".join(lines)

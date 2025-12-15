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
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Python files | {summary.get('total_files', 0)} |")
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
                mermaid = generate_mermaid_diagram(imports)
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
                    lines.append(f"| {i} | `{Path(p.get('file', '')).name}` | {p.get('imported_by_count', 0)} modules | {dependents} |")
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
                    lines.append(f"| {i} | `{Path(h.get('file', '')).name}` | {h.get('risk_score', 0):.2f} | {h.get('reason', '')} |")
                lines.append("")
        except Exception:
            pass

    # Entry Points
    if gap.get("entry_points"):
        try:
            from gap_features import detect_entry_points
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
                        rel_path = "./" + Path(filepath).name
                        rel_usage = usage
                    lines.append(f"| `{ep.get('entry_point', '')}` | {rel_path} | `{rel_usage}` |")
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
                    lines.append(f"### {cls['name']}{bases} ({Path(cls.get('file', '')).name}:{cls.get('line', 0)})")
                    lines.append("")
                    # Show docstring if available
                    if cls.get("docstring"):
                        lines.append(f"> {cls['docstring']}")
                        lines.append("")
                    lines.append("```python")
                    lines.append(f"class {cls['name']}{bases}:  # L{cls.get('line', 0)}")
                    # Show __init__ signature first if available
                    if cls.get("init_signature"):
                        lines.append(f"    {cls['init_signature']}")
                        lines.append("")
                    for field in cls.get("fields", [])[:5]:
                        field_name = field.get("name", "")
                        field_type = field.get("type", "")
                        if field_type:
                            lines.append(f"    {field_name}: {field_type}")
                        else:
                            lines.append(f"    {field_name}")
                    # Show methods (skip __init__ since we showed it above)
                    methods_shown = 0
                    for method in cls.get("methods", []):
                        method_name = method.get("name", "")
                        if method_name == "__init__":
                            continue  # Already shown
                        if methods_shown >= 10:
                            break
                        is_async = "async " if method.get("is_async") else ""
                        lines.append(f"    {is_async}def {method_name}(...)")
                        methods_shown += 1
                    remaining = cls.get("method_count", 0) - methods_shown - (1 if cls.get("init_signature") else 0)
                    if remaining > 0:
                        lines.append(f"    # ... and {remaining} more methods")
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
                        lines.append(f"**{model['name']}** [{model_type}] ({Path(model.get('file', '')).name})")
                        lines.append("")
                        lines.append("```python")
                        lines.append(f"class {model['name']}{bases}:  # L{model.get('line', 0)}")
                        for field in model.get("fields", [])[:8]:
                            field_name = field.get("name", "")
                            field_type = field.get("type", "")
                            if field_type:
                                lines.append(f"    {field_name}: {field_type}")
                            else:
                                lines.append(f"    {field_name}")
                        lines.append("```")
                        lines.append("")
                        models_shown += 1
        except Exception:
            pass

    # Hazards (Large Files and Directories)
    if gap.get("hazards"):
        try:
            from gap_features import detect_hazards, get_directory_hazards
            file_hazards = detect_hazards(results)
            target_dir = gap.get("target_dir", ".")
            dir_hazards = get_directory_hazards(target_dir)

            if file_hazards or dir_hazards:
                lines.append("## Context Hazards")
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
                        lines.append(f"| {h.get('tokens', 0):,} | `{Path(h.get('file', '')).name}` | {h.get('recommendation', '')} |")
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
                    lines.append(f"### {lm.get('method', '')}() - {Path(lm.get('file', '')).name}:{lm.get('line', 0)} (CC:{lm.get('complexity', 0)})")
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
                    lines.append(f"### {sig.get('name', '')}() - {Path(sig.get('file', '')).name}:{sig.get('line', 0)}")
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
                    lines.append("```python")
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
                    lines.append(f"### {Path(filepath).name}")
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

            # Show last 2-3 path components for context (e.g., "cli/main.py" not just "main.py")
            path_parts = Path(full_path).parts
            if len(path_parts) >= 3:
                short_path = "/".join(path_parts[-3:])
            elif len(path_parts) >= 2:
                short_path = "/".join(path_parts[-2:])
            else:
                short_path = Path(full_path).name

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

        # Layers - enhanced with layer_details if enabled
        layers = imports.get("layers", {})
        if layers:
            lines.append("### Architectural Layers")
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
            for orphan in orphans[:5]:
                orphan_path = orphan.get('file', orphan.get('module', ''))
                # Show relative path or module name for portability
                if "/" in orphan_path or "\\" in orphan_path:
                    orphan_display = Path(orphan_path).name
                else:
                    orphan_display = orphan_path
                lines.append(f"- `{orphan_display}`")
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
                lines.append(f"| {r.get('risk_score', 0):.2f} | `{Path(r.get('file', '')).name}` | {factors} |")
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
                    return Path(f.get("file", "")).name, f.get("days", 0)
                return Path(f).name if f else "", 0

            # Build commit count lookup from risk data
            risk_data = git.get("risk", [])
            commit_counts = {}
            for r in risk_data:
                fname = Path(r.get("file", "")).name
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
                    lines.append(f"| `{Path(c.get('file_a', '')).name}` | `{Path(c.get('file_b', '')).name}` | {c.get('count', 0)} |")
                lines.append("")
        except Exception:
            pass

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
                        lines.append(f"- `{e.get('call', '')}` in {Path(e.get('file', '')).name}:{e.get('line', 0)}")
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
            lines.append("| Variable | File | Line |")
            lines.append("|----------|------|------|")
            for ev in env_vars[:20]:
                lines.append(f"| `{ev.get('variable', '')}` | {Path(ev.get('file', '')).name} | {ev.get('line', 0)} |")
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

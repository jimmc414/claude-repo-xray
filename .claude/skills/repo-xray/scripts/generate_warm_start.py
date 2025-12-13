#!/usr/bin/env python3
"""
Repo X-Ray: WARM_START.md Generator

Generates a complete WARM_START.md onboarding document for any Python repository.
Combines all analysis tools into a single automated workflow.

Usage:
    python generate_warm_start.py /path/to/repo
    python generate_warm_start.py /path/to/repo -o WARM_START.md
    python generate_warm_start.py /path/to/repo --json
    python generate_warm_start.py /path/to/repo -v

Features:
    - Single command generates complete documentation
    - Pattern-based architecture detection
    - Confidence markers for optional Claude enhancement
    - Hybrid approach: automation + intelligent fallback
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SKILL_ROOT))

# Import from sibling modules
from dependency_graph import (
    build_dependency_graph,
    identify_layers,
    generate_mermaid,
    find_orphans,
    auto_detect_root_package,
)
from git_analysis import (
    analyze_risk,
    analyze_coupling,
    analyze_freshness,
    get_tracked_files,
)
from mapper import (
    map_directory,
    load_ignore_patterns,
    estimate_tokens,
    format_tokens,
)
from lib.ast_utils import get_skeleton


# =============================================================================
# Project Detection
# =============================================================================

def detect_project_name(directory: str) -> str:
    """Detect project name from pyproject.toml, setup.py, or directory name."""
    # Try pyproject.toml
    pyproject = Path(directory) / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Try setup.py
    setup_py = Path(directory) / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text()
            match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Fall back to directory name
    return Path(directory).resolve().name


def detect_source_dir(directory: str) -> str:
    """Detect the main source directory."""
    project_name = detect_project_name(directory)

    # Common patterns
    candidates = [
        project_name,
        "src",
        f"src/{project_name}",
        "lib",
    ]

    for candidate in candidates:
        path = Path(directory) / candidate
        if path.exists() and path.is_dir():
            # Check if it has Python files
            if list(path.glob("*.py")) or list(path.glob("**/*.py")):
                return candidate

    return "."


# =============================================================================
# Data Collection
# =============================================================================

def collect_all_data(directory: str, verbose: bool = False) -> Dict[str, Any]:
    """Run all analyses and collect structured data."""
    if verbose:
        print("Collecting repository data...", file=sys.stderr)

    project_name = detect_project_name(directory)
    source_dir = detect_source_dir(directory)

    # Get ignore patterns
    ignore_dirs, ignore_exts, ignore_files = load_ignore_patterns()

    if verbose:
        print(f"  Project: {project_name}", file=sys.stderr)
        print(f"  Source dir: {source_dir}", file=sys.stderr)

    # Map directory for token estimates
    if verbose:
        print("  Running mapper...", file=sys.stderr)
    map_result = map_directory(directory, ignore_dirs, ignore_exts, ignore_files)

    # Build dependency graph
    if verbose:
        print("  Building dependency graph...", file=sys.stderr)
    graph = build_dependency_graph(directory, auto_detect=True)
    layers = identify_layers(graph)
    mermaid = generate_mermaid(graph)
    orphans = find_orphans(graph)

    # Get the detected root package (for imports)
    root_package = graph.get("root_package", "")
    if not root_package:
        # Try to infer from module names
        modules = graph.get("modules", {})
        if modules:
            first_module = list(modules.keys())[0]
            root_package = first_module.split(".")[0] if "." in first_module else first_module

    # Git analysis
    if verbose:
        print("  Analyzing git history...", file=sys.stderr)
    files = get_tracked_files(directory)
    risk = analyze_risk(directory, files) if files else []
    coupling = analyze_coupling(directory) if files else []
    freshness = analyze_freshness(directory, files) if files else {"active": [], "aging": [], "stale": [], "dormant": []}

    # Detect entry points and critical classes
    if verbose:
        print("  Detecting entry points...", file=sys.stderr)
    entry_points = detect_entry_points(directory, graph, layers, root_package)

    if verbose:
        print("  Extracting critical classes...", file=sys.stderr)
    critical_classes = extract_critical_classes(directory, graph, layers)
    data_models = extract_data_models(directory, graph, layers)

    return {
        "project_name": project_name,
        "root_package": root_package,
        "source_dir": source_dir,
        "timestamp": datetime.now().strftime("%Y-%m-%d"),
        "token_budget": map_result["total_tokens"],
        "file_count": map_result["file_count"],
        "large_files": map_result["large_files"],
        "graph": graph,
        "layers": layers,
        "mermaid": mermaid,
        "orphans": orphans,
        "risk": risk,
        "coupling": coupling,
        "freshness": freshness,
        "entry_points": entry_points,
        "critical_classes": critical_classes,
        "data_models": data_models,
    }


# =============================================================================
# Entry Point Detection
# =============================================================================

def detect_entry_points(directory: str, graph: Dict, layers: Dict, root_package: str = "") -> List[Dict]:
    """Find CLI and API entry points."""
    entry_points = []
    modules = graph.get("modules", {})

    # Directories to skip for entry point detection (utility/test scripts)
    skip_dirs = {".claude", "tests", "test", "examples", "scripts", "tools", "utils", "alembic"}

    def should_skip_file(filepath: str) -> bool:
        """Check if file is in a directory we should skip."""
        path_parts = filepath.replace("\\", "/").lower().split("/")
        return any(skip_dir in path_parts for skip_dir in skip_dirs)

    # Common entry point patterns
    entry_patterns = ["main.py", "cli.py", "__main__.py", "app.py", "wsgi.py", "asgi.py"]

    for module_name, info in modules.items():
        filepath = info.get("file", "")
        filename = os.path.basename(filepath)

        # Skip files in test/utility directories
        if should_skip_file(filepath):
            continue

        # Check filename patterns - prioritize if in root package
        if filename in entry_patterns:
            # Skip if we already have this filename from another location
            existing_filenames = [os.path.basename(e.get("file", "")) for e in entry_points]
            if filename in existing_filenames:
                continue

            # Higher priority if in detected root package
            is_in_root = root_package and root_package in module_name
            entry_points.append({
                "module": module_name,
                "file": filepath,
                "type": "cli" if "cli" in filename.lower() else "main",
                "description": f"Entry point ({filename})",
                "priority": 1 if is_in_root else 2,
            })
            continue

        # Check for if __name__ == "__main__" - only for root package files
        if filepath and os.path.exists(filepath):
            # Only check __main__ for files in root package or workflow directories
            is_relevant = (
                (root_package and root_package in module_name) or
                "workflow" in module_name.lower() or
                "cli" in module_name.lower()
            )
            if not is_relevant:
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'if __name__ ==' in content or 'if __name__==' in content:
                    if module_name not in [e["module"] for e in entry_points]:
                        entry_points.append({
                            "module": module_name,
                            "file": filepath,
                            "type": "script",
                            "description": "Has __main__ block",
                            "priority": 3,
                        })
            except Exception:
                pass

    # Sort by priority (lower is better)
    entry_points.sort(key=lambda x: x.get("priority", 99))

    # Add top orchestration modules with workflow/research/main in name
    workflow_keywords = ["workflow", "research", "main", "app", "run"]
    for module_name in layers.get("orchestration", []):
        if any(kw in module_name.lower() for kw in workflow_keywords):
            if module_name not in [e["module"] for e in entry_points]:
                info = modules.get(module_name, {})
                entry_points.append({
                    "module": module_name,
                    "file": info.get("file", ""),
                    "type": "orchestration",
                    "description": "Orchestration layer",
                    "priority": 4,
                })

    # Remove priority field before returning
    for ep in entry_points:
        ep.pop("priority", None)

    return entry_points[:10]  # Limit to 10


# =============================================================================
# Critical Class Extraction
# =============================================================================

def extract_critical_classes(directory: str, graph: Dict, layers: Dict) -> List[Dict]:
    """Extract skeleton code for critical classes."""
    critical = []
    modules = graph.get("modules", {})

    # Get top modules from orchestration and core layers
    top_modules = (
        layers.get("orchestration", [])[:5] +
        layers.get("core", [])[:3]
    )

    for module_name in top_modules:
        info = modules.get(module_name, {})
        filepath = info.get("file", "")

        if filepath and os.path.exists(filepath):
            try:
                skeleton, orig_tokens, skel_tokens = get_skeleton(filepath)
                if skeleton and skel_tokens > 10:  # Has meaningful content
                    # Extract just the class definitions
                    classes = extract_classes_from_skeleton(skeleton)
                    if classes:
                        critical.append({
                            "module": module_name,
                            "file": filepath,
                            "skeleton": skeleton,
                            "classes": classes,
                            "orig_tokens": orig_tokens,
                            "skel_tokens": skel_tokens,
                        })
            except Exception:
                pass

    return critical[:8]  # Limit


def extract_classes_from_skeleton(skeleton: str) -> List[str]:
    """Extract class names from skeleton text."""
    classes = []
    for line in skeleton.split('\n'):
        if line.strip().startswith('class ') and ':' in line:
            match = re.match(r'class\s+(\w+)', line.strip())
            if match:
                classes.append(match.group(1))
    return classes


def extract_data_models(directory: str, graph: Dict, layers: Dict) -> List[Dict]:
    """Extract Pydantic/dataclass models."""
    models = []
    modules = graph.get("modules", {})

    # Look for model files in foundation layer
    model_keywords = ["model", "schema", "types", "entities"]

    for module_name in layers.get("foundation", []) + layers.get("core", []):
        if any(kw in module_name.lower() for kw in model_keywords):
            info = modules.get(module_name, {})
            filepath = info.get("file", "")

            if filepath and os.path.exists(filepath):
                try:
                    skeleton, _, skel_tokens = get_skeleton(filepath)
                    if skeleton and skel_tokens > 10:
                        classes = extract_classes_from_skeleton(skeleton)
                        if classes:
                            models.append({
                                "module": module_name,
                                "file": filepath,
                                "skeleton": skeleton,
                                "classes": classes,
                            })
                except Exception:
                    pass

    return models[:5]  # Limit


# =============================================================================
# Architecture Overview Generation
# =============================================================================

def generate_architecture_overview(data: Dict) -> Tuple[str, float]:
    """
    Generate prose description from detected patterns.
    Returns (overview_text, confidence_score).
    """
    layers = data["layers"]
    project = data["project_name"]

    # Count modules per layer
    orch_count = len(layers.get("orchestration", []))
    core_count = len(layers.get("core", []))
    found_count = len(layers.get("foundation", []))

    # Detect architectural patterns
    all_modules = (
        layers.get("orchestration", []) +
        layers.get("core", []) +
        layers.get("foundation", [])
    )
    all_modules_lower = [m.lower() for m in all_modules]

    has_agents = any("agent" in m for m in all_modules_lower)
    has_workflow = any("workflow" in m for m in all_modules_lower)
    has_api = any("api" in m for m in all_modules_lower)
    has_models = any("model" in m for m in all_modules_lower)
    has_cli = any("cli" in m for m in all_modules_lower)
    has_db = any("db" in m or "database" in m for m in all_modules_lower)
    has_execution = any("execut" in m or "runner" in m for m in all_modules_lower)

    # Calculate confidence based on detected patterns
    patterns_found = sum([has_agents, has_workflow, has_api, has_models, has_cli, has_db, has_execution])
    confidence = min(0.9, 0.4 + (patterns_found * 0.1))

    # Build description
    overview = f"**{project}** is a Python application"

    descriptors = []
    if has_agents:
        descriptors.append("agent-based architecture")
    if has_workflow:
        descriptors.append("workflow orchestration")
    if has_api:
        descriptors.append("API endpoints")
    if has_execution:
        descriptors.append("code execution capabilities")

    if descriptors:
        overview += " with " + ", ".join(descriptors[:2])

    overview += ".\n\n"

    # Layer summary
    overview += f"The codebase contains {orch_count + core_count + found_count} modules organized in three architectural layers:\n\n"
    overview += f"- **Foundation** ({found_count} modules): Core utilities, configuration, data models\n"
    overview += f"- **Core** ({core_count} modules): Business logic and domain services\n"
    overview += f"- **Orchestration** ({orch_count} modules): High-level coordination and entry points\n"

    # Key patterns
    overview += "\n**Key architectural patterns:**\n"

    if has_agents:
        overview += "- **Agent Architecture** - Specialized agents handle different concerns\n"
    if has_workflow:
        overview += "- **Workflow Orchestration** - Coordinated multi-step processes\n"
    if has_models:
        overview += "- **Data Models** - Pydantic/dataclass models for validation\n"
    if has_cli:
        overview += "- **CLI Interface** - Command-line entry points\n"
    if has_api:
        overview += "- **API Layer** - HTTP/REST endpoints\n"
    if has_db:
        overview += "- **Data Persistence** - Database integration\n"

    if not any([has_agents, has_workflow, has_models, has_cli, has_api, has_db]):
        overview += "- Standard Python package structure\n"
        confidence = 0.5

    return overview, confidence


# =============================================================================
# Formatting Functions
# =============================================================================

def format_token_budget(tokens: int) -> str:
    """Format token budget string."""
    if tokens >= 1000000:
        return f"~{tokens / 1000000:.1f}M tokens"
    elif tokens >= 1000:
        return f"~{tokens / 1000:.0f}K tokens"
    return f"~{tokens} tokens"


def format_entry_points_table(entry_points: List[Dict]) -> str:
    """Format entry points as markdown table."""
    if not entry_points:
        return "*No entry points detected*"

    lines = ["| Class/Module | File | Description |", "|--------------|------|-------------|"]
    for ep in entry_points:
        module = ep["module"].split(".")[-1]
        file = os.path.basename(ep["file"]) if ep["file"] else "-"
        desc = ep["description"]
        lines.append(f"| `{module}` | `{file}` | {desc} |")

    return "\n".join(lines)


def format_core_components(critical_classes: List[Dict]) -> str:
    """Format critical classes with skeleton code."""
    if not critical_classes:
        return "*Use skeleton.py to extract critical class interfaces*"

    output = []
    for item in critical_classes[:3]:  # Top 3
        module = item["module"]
        filepath = item["file"]
        skeleton = item["skeleton"]

        # Truncate skeleton if too long
        lines = skeleton.split('\n')
        if len(lines) > 30:
            skeleton = '\n'.join(lines[:30]) + "\n# ... (truncated)"

        output.append(f"**{module}** (`{os.path.basename(filepath)}`)")
        output.append("```python")
        output.append(skeleton)
        output.append("```")
        output.append("")

    return "\n".join(output)


def format_data_models(data_models: List[Dict]) -> str:
    """Format data models section."""
    if not data_models:
        return "*No Pydantic/dataclass models detected*"

    output = []
    for item in data_models[:2]:  # Top 2
        module = item["module"]
        classes = item["classes"]
        skeleton = item["skeleton"]

        # Truncate
        lines = skeleton.split('\n')
        if len(lines) > 25:
            skeleton = '\n'.join(lines[:25]) + "\n# ... (truncated)"

        output.append(f"**{module}** (classes: {', '.join(classes[:5])})")
        output.append("```python")
        output.append(skeleton)
        output.append("```")
        output.append("")

    return "\n".join(output)


def format_layers_table(layers: Dict, layer_name: str, graph: Dict) -> str:
    """Format a layer as markdown table."""
    modules = layers.get(layer_name, [])
    if not modules:
        return "*None detected*"

    graph_modules = graph.get("modules", {})

    lines = ["| Module | Imported By | Imports |", "|--------|-------------|---------|"]
    for module in modules[:10]:
        info = graph_modules.get(module, {})
        imported_by = len(info.get("imported_by", []))
        imports = len(info.get("imports", []))
        short_name = module.split(".")[-1] if "." in module else module
        lines.append(f"| `{short_name}` | {imported_by} | {imports} |")

    return "\n".join(lines)


def format_risk_table(risk: List[Dict]) -> str:
    """Format risk analysis as markdown table."""
    if not risk:
        return "*No risk data available (no git history or no commits in analysis period)*"

    lines = ["| File | Risk | Churn | Hotfixes | Authors |", "|------|------|-------|----------|---------|"]
    for r in risk[:10]:
        file = r["file"]
        lines.append(f"| {file} | {r['risk_score']:.2f} | {r['churn']} | {r['hotfixes']} | {r['authors']} |")

    return "\n".join(lines)


def format_coupling_table(coupling: List[Dict]) -> str:
    """Format coupling analysis."""
    if not coupling:
        return "*No significant coupling pairs detected in recent history.*\n\nThis indicates clean module boundaries - files are generally modified independently."

    lines = ["| File A | File B | Co-changes |", "|--------|--------|------------|"]
    for c in coupling[:10]:
        lines.append(f"| {c['file_a']} | {c['file_b']} | {c['count']} |")

    return "\n".join(lines)


def format_orphan_table(orphans: List[Dict]) -> str:
    """Format orphan files table."""
    if not orphans:
        return "*No orphan files detected*"

    lines = ["| File | Confidence | Notes |", "|------|------------|-------|"]
    for o in orphans[:10]:
        lines.append(f"| {o['file']} | {o['confidence']:.2f} | {o['notes']} |")

    return "\n".join(lines)


def format_dormant_table(freshness: Dict) -> str:
    """Format dormant files table."""
    dormant = freshness.get("dormant", [])
    if not dormant:
        return "*No dormant files detected - all files active within 180 days*"

    lines = ["| File | Days Since Change |", "|------|-------------------|"]
    for d in dormant[:10]:
        lines.append(f"| {d['file']} | {d['days']} |")

    return "\n".join(lines)


def format_freshness_summary(freshness: Dict) -> str:
    """Format freshness summary table."""
    return f"""| Category | File Count | Description |
|----------|------------|-------------|
| Active | {len(freshness.get('active', []))} | Changed in last 30 days |
| Aging | {len(freshness.get('aging', []))} | Changed 30-90 days ago |
| Stale | {len(freshness.get('stale', []))} | Changed 90-180 days ago |
| Dormant | {len(freshness.get('dormant', []))} | Not changed in 180+ days |"""


def format_hazard_files(large_files: List[Dict]) -> str:
    """Format large files table."""
    if not large_files:
        return "*No unusually large files detected*"

    lines = ["| Tokens | File | Note |", "|--------|------|------|"]
    for f in large_files[:10]:
        note = "Use skeleton view" if f["tokens"] > 20000 else "Consider skeleton"
        lines.append(f"| {f['formatted']} | `{f['path']}` | {note} |")

    return "\n".join(lines)


# =============================================================================
# Template Rendering
# =============================================================================

def load_template() -> str:
    """Load the WARM_START template."""
    template_path = SKILL_ROOT / "templates" / "warm_start.md.template"
    if template_path.exists():
        return template_path.read_text()

    # Fallback minimal template
    return """# {PROJECT_NAME}: Developer Warm Start

> Generated: {TIMESTAMP}
> Token budget: {TOKEN_BUDGET}

## Architecture Overview
{ARCHITECTURE_OVERVIEW}

## Architecture Layers
{FOUNDATION_MODULES_TABLE}

## Risk Assessment
{RISK_FILES_TABLE}
"""


def _get_best_entry_class(data: Dict) -> str:
    """Get the best entry point class name for data flow diagram."""
    # Priority order for keywords (most specific first)
    keyword_priority = [
        ["research_loop", "research_workflow"],  # Highest priority
        ["workflow", "research"],
        ["main", "app"],
    ]

    # Check orchestration layer first (more likely to have the main workflow)
    for keywords in keyword_priority:
        for module in data.get("layers", {}).get("orchestration", []):
            if any(kw in module.lower() for kw in keywords):
                return module.split(".")[-1]

    # Check entry points
    for keywords in keyword_priority:
        for ep in data.get("entry_points", []):
            module = ep.get("module", "")
            if any(kw in module.lower() for kw in keywords):
                return module.split(".")[-1]

    # Fall back to first entry point or "Main"
    if data.get("entry_points"):
        return data["entry_points"][0]["module"].split(".")[-1]

    return "Main"


def render_template(data: Dict) -> str:
    """Fill all template placeholders with collected data."""
    template = load_template()

    # Generate architecture overview with confidence
    arch_overview, confidence = generate_architecture_overview(data)

    # Add confidence marker if below threshold
    if confidence < 0.7:
        arch_overview = f"<!-- CONFIDENCE: {confidence:.1f} - Pattern-based generation, may benefit from enhancement -->\n\n{arch_overview}\n\n<!-- /CONFIDENCE -->"

    # Build replacements
    replacements = {
        "{PROJECT_NAME}": data["project_name"],
        "{TIMESTAMP}": data["timestamp"],
        "{TOKEN_BUDGET}": format_token_budget(data["token_budget"]),
        "{SOURCE_DIR}": data["source_dir"],
        "{FOCUS_AREA}": "core",

        # Section 1
        "{MERMAID_DIAGRAM}": f"```mermaid\n{data['mermaid']}\n```",
        "{WORKFLOW_MERMAID_DIAGRAM}": "*Use `dependency_graph.py --focus workflow` for a focused view*",

        # Section 2
        "{ARCHITECTURE_OVERVIEW}": arch_overview,

        # Section 3
        "{ENTRY_POINTS_TABLE}": format_entry_points_table(data["entry_points"]),
        "{CORE_COMPONENTS}": format_core_components(data["critical_classes"]),
        "{DATA_MODELS}": format_data_models(data["data_models"]),
        "{EXECUTOR_CLASSES_TABLE}": "*Use skeleton.py to find Executor/Runner classes*",

        # Section 4 - Data flow (use best entry point or orchestration module)
        "{ENTRY_POINT_CLASS}": _get_best_entry_class(data),
        "{MAIN_METHOD}": "run",
        "{STATE_OR_CONTEXT_SETUP}": "Initialize state/context",
        "{CORE_PROCESSING_STEP}": "Core processing",
        "{SUB_COMPONENT}": "Sub-components",
        "{VALIDATION_OR_ANALYSIS}": "Validation/Analysis",
        "{OUTPUT_OR_RESULT}": "Generate output",

        # Section 5 - Use root_package for valid Python imports
        "{CLI_COMMANDS}": f"```bash\n# Run the main entry point\npython -m {data['root_package'] or data['project_name'].replace('-', '_')}\n```",
        "{PYTHON_API}": f"```python\nfrom {data['root_package'] or data['project_name'].replace('-', '_')} import main\n# See entry points above for specific imports\n```",
        "{KEY_IMPORTS}": f"```python\nfrom {data['root_package'] or data['project_name'].replace('-', '_')} import *\n```",

        # Section 6
        "{HAZARD_DIRECTORIES}": "- `__pycache__/`, `.git/`, `venv/`, `node_modules/`\n- `artifacts/`, `data/`, `logs/`",
        "{HAZARD_FILES}": format_hazard_files(data["large_files"]),
        "{HAZARD_EXTENSIONS}": "`.pyc`, `.pkl`, `.log`, `.jsonl`, `.csv`, `.h5`",

        # Section 7 - Use root_package for valid Python
        "{HEALTH_CHECK_COMMAND}": f"python -m {data['root_package'] or data['project_name'].replace('-', '_')} --help",
        "{TEST_COMMAND}": "pytest tests/ -x -q",
        "{IMPORT_VERIFICATION}": f'python -c "import {data["root_package"] or data["project_name"].replace("-", "_")}; print(\'OK\')"',

        # Section 9
        "{FOUNDATION_MODULES_TABLE}": format_layers_table(data["layers"], "foundation", data["graph"]),
        "{CORE_MODULES_TABLE}": format_layers_table(data["layers"], "core", data["graph"]),
        "{ORCHESTRATION_MODULES_TABLE}": format_layers_table(data["layers"], "orchestration", data["graph"]),

        # Section 10
        "{RISK_FILES_TABLE}": format_risk_table(data["risk"]),

        # Section 11
        "{COUPLING_TABLE}": format_coupling_table(data["coupling"]),

        # Section 12
        "{ORPHAN_TABLE}": format_orphan_table(data["orphans"]),
        "{DORMANT_TABLE}": format_dormant_table(data["freshness"]) + "\n\n### Freshness Summary\n" + format_freshness_summary(data["freshness"]),
    }

    # Apply replacements
    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value))

    return result


# =============================================================================
# Debug Output
# =============================================================================

def write_debug_output(data: Dict, output_dir: Path):
    """Write debug data for validation and troubleshooting."""
    output_dir.mkdir(exist_ok=True)

    # Prepare serializable data (remove non-serializable graph internals)
    debug_data = {
        "project_name": data["project_name"],
        "source_dir": data["source_dir"],
        "timestamp": data["timestamp"],
        "token_budget": data["token_budget"],
        "file_count": data["file_count"],
        "layers": data["layers"],
        "mermaid": data["mermaid"],
        "risk": data["risk"],
        "coupling": data["coupling"],
        "freshness": data["freshness"],
        "orphans": data["orphans"],
        "large_files": data["large_files"],
        "entry_points": data["entry_points"],
        "critical_classes": [
            {"module": c["module"], "file": c["file"], "classes": c["classes"]}
            for c in data.get("critical_classes", [])
        ],
        "data_models": [
            {"module": m["module"], "file": m["file"], "classes": m["classes"]}
            for m in data.get("data_models", [])
        ],
    }

    # Add graph module info for debugging
    if "graph" in data:
        debug_data["graph_modules"] = {
            k: {"imports": v["imports"], "imported_by": v["imported_by"]}
            for k, v in data["graph"].get("modules", {}).items()
        }

    # Write full raw data
    (output_dir / "raw_data.json").write_text(
        json.dumps(debug_data, indent=2, default=str)
    )

    # Write section-by-section data
    sections = {
        "section_01_context": {
            "mermaid": data["mermaid"],
            "layer_counts": {k: len(v) for k, v in data["layers"].items()}
        },
        "section_02_overview": {
            "project_name": data["project_name"],
            "layers": data["layers"],
            "total_modules": sum(len(v) for v in data["layers"].values())
        },
        "section_03_classes": {
            "entry_points": data["entry_points"],
            "critical_classes": [c["module"] for c in data.get("critical_classes", [])],
            "data_models": [m["module"] for m in data.get("data_models", [])]
        },
        "section_06_hazards": {
            "large_files": data["large_files"],
            "file_count": data["file_count"],
            "token_budget": data["token_budget"]
        },
        "section_09_layers": {
            "foundation": data["layers"].get("foundation", []),
            "core": data["layers"].get("core", []),
            "orchestration": data["layers"].get("orchestration", []),
            "leaf": data["layers"].get("leaf", [])
        },
        "section_10_risk": {
            "risk_entries": len(data["risk"]),
            "files": data["risk"][:10] if data["risk"] else []
        },
        "section_11_coupling": {
            "coupling_pairs": len(data["coupling"]),
            "pairs": data["coupling"][:10] if data["coupling"] else []
        },
        "section_12_deadcode": {
            "orphans": data["orphans"],
            "freshness": data["freshness"]
        }
    }

    for name, content in sections.items():
        (output_dir / f"{name}.json").write_text(
            json.dumps(content, indent=2, default=str)
        )

    print(f"Debug data written to {output_dir}/")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate WARM_START.md for a Python repository"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Repository directory to analyze (default: current)"
    )
    parser.add_argument(
        "-o", "--output",
        default="WARM_START.md",
        help="Output file path (default: WARM_START.md)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw data as JSON instead of markdown"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress messages"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Output raw section data to WARM_START_debug/ directory"
    )

    args = parser.parse_args()

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Collect all data
    try:
        data = collect_all_data(args.directory, verbose=args.verbose)
    except Exception as e:
        print(f"Error collecting data: {e}", file=sys.stderr)
        sys.exit(1)

    # Write debug output if requested
    if args.debug:
        debug_dir = Path(args.output).parent / "WARM_START_debug"
        write_debug_output(data, debug_dir)

    # Output
    if args.json:
        # JSON output (remove non-serializable items)
        output_data = {k: v for k, v in data.items() if k != "graph"}
        output_data["layers"] = data["layers"]
        print(json.dumps(output_data, indent=2, default=str))
    else:
        # Render template
        if args.verbose:
            print("Rendering template...", file=sys.stderr)

        result = render_template(data)

        # Write output
        output_path = Path(args.output)
        output_path.write_text(result)

        print(f"Generated {args.output}")
        print(f"  Project: {data['project_name']}")
        print(f"  Files analyzed: {data['file_count']}")
        print(f"  Total tokens: {format_token_budget(data['token_budget'])}")


if __name__ == "__main__":
    main()

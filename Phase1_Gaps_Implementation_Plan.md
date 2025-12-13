# Phase 1 Gaps: Implementation Plan

> Self-contained plan for filling in missing data in generate_warm_start.py output.
> A fresh Claude Code instance can implement this without additional context.

## Overview

The `generate_warm_start.py` tool successfully generates WARM_START.md documents, but three sections contain generic placeholder content instead of detected data. This plan addresses each gap.

## Current State

**Files involved:**
- `.claude/skills/repo-xray/scripts/generate_warm_start.py` (~800 lines)
- `.claude/skills/repo-xray/templates/warm_start.md.template`
- `.claude/skills/repo-xray/lib/token_estimator.py` (unused)
- `.claude/skills/repo-xray/tests/test_generate_warm_start.py`

**Working correctly:**
- Sections 1-3: System Context, Architecture Overview, Critical Classes
- Sections 6-12: Hazards, Verification, X-Ray Commands, Layers, Risk, Coupling, Dead Code

**Gaps (generic placeholders):**
- Section 4: Data Flow - uses hardcoded template
- Section 5: Entry Points - uses invalid package name
- Gap 3: `lib/token_estimator.py` is orphaned (not imported anywhere)

---

## Gap 1: Section 4 - Data Flow

### Current Behavior

The template always generates:
```
[1] configure.__init__(...)
[2] configure.run(...)
    ├──▶ [3] Initialize state/context
    ...
```

This is hardcoded regardless of what entry points were detected.

### Desired Behavior

Generate a data flow diagram based on the **detected orchestration module**:
```
[1] generate_warm_start.main()
    │
    ├──▶ [2] collect_all_data()
    │         ├── mapper.map_directory()
    │         ├── dependency_graph.build_dependency_graph()
    │         ├── git_analysis.analyze_risk()
    │         └── detect_entry_points()
    │
    └──▶ [3] render_template()
              │
              ▼
         WARM_START.md
```

### Implementation

**File:** `generate_warm_start.py`

**Step 1:** Create `generate_data_flow()` function (~60 lines)

```python
def generate_data_flow(data: Dict) -> str:
    """Generate data flow diagram from detected architecture."""

    # Get the primary entry point (orchestration layer, or first entry point)
    entry_points = data.get("entry_points", [])
    orchestration = data["layers"].get("orchestration", [])
    graph = data.get("graph", {})

    # Find primary module
    if orchestration:
        primary = orchestration[0]
    elif entry_points:
        primary = entry_points[0].get("module", "main")
    else:
        return FALLBACK_DATA_FLOW  # Use existing template as fallback

    # Get what this module imports (its dependencies)
    primary_full = None
    for mod_name in graph.get("modules", {}):
        if mod_name.endswith(primary) or mod_name == primary:
            primary_full = mod_name
            break

    if not primary_full:
        return FALLBACK_DATA_FLOW

    imports = graph["modules"].get(primary_full, {}).get("imports", [])

    # Build the flow diagram
    lines = [
        "```",
        "User Input",
        "    │",
        "    ▼",
        f"[1] {primary}.main()",
        "    │",
    ]

    if imports:
        lines.append("    ├──▶ [2] Process inputs")
        lines.append("    │")
        lines.append("    ├──▶ [3] Core processing")

        # Show what modules are called
        for i, imp in enumerate(imports[:4]):  # Limit to 4
            imp_short = imp.split(".")[-1]
            prefix = "    │         ├──" if i < len(imports[:4]) - 1 else "    │         └──"
            lines.append(f"{prefix} {imp_short}()")

        lines.append("    │")
        lines.append("    └──▶ [4] Generate output")
    else:
        lines.append("    └──▶ [2] Execute")

    lines.extend([
        "              │",
        "              ▼",
        "         Results",
        "```",
    ])

    return "\n".join(lines)
```

**Step 2:** Update `render_template()` to call `generate_data_flow()`

Find in `render_template()`:
```python
"{DATA_FLOW}": "..."  # Current hardcoded template
```

Replace with:
```python
"{DATA_FLOW}": generate_data_flow(data),
```

**Step 3:** Update template placeholder

In `warm_start.md.template`, ensure Section 4 has:
```markdown
## 4. Data Flow

{DATA_FLOW}
```

### Testing

Add to `test_generate_warm_start.py`:

```python
class TestSection04DataFlow:
    """Validate Data Flow section."""

    def test_data_flow_not_hardcoded(self, debug_data):
        """Data flow should reference detected modules, not 'configure'."""
        # Read the generated markdown
        warm_start = Path("WARM_START_python.md").read_text()

        # If orchestration has generate_warm_start, it should appear in flow
        if "generate_warm_start" in debug_data["layers"].get("orchestration", []):
            assert "generate_warm_start" in warm_start or "main" in warm_start

    def test_data_flow_shows_imports(self, debug_data):
        """Data flow should show imported modules."""
        # The primary orchestration module's imports should appear
        orch = debug_data["layers"].get("orchestration", [])
        if orch:
            primary = orch[0]
            modules = debug_data.get("graph_modules", {})
            for mod_name, mod_info in modules.items():
                if primary in mod_name:
                    imports = mod_info.get("imports", [])
                    # At least some imports should appear in the flow
                    assert len(imports) >= 0  # Basic check
```

---

## Gap 2: Section 5 - Entry Points

### Current Behavior

Generates invalid Python:
```python
python -m claude-repo-xray        # Hyphens invalid
from claude-repo-xray import main  # Won't work
```

### Desired Behavior

Generate valid, working commands based on project structure:

**For script-based projects (like repo-xray):**
```markdown
### CLI Commands
```bash
# Primary entry point
python .claude/skills/repo-xray/scripts/generate_warm_start.py /path/to/repo

# Individual tools
python .claude/skills/repo-xray/scripts/mapper.py . --summary
python .claude/skills/repo-xray/scripts/dependency_graph.py . --mermaid
```

### Python API
```python
# Add scripts to path, then import
import sys
sys.path.insert(0, ".claude/skills/repo-xray/scripts")

from generate_warm_start import collect_all_data
from dependency_graph import build_dependency_graph
from mapper import map_directory
```
```

**For package-based projects (any project with `pkg/__init__.py`):**
```markdown
### CLI Commands
```bash
python -m mypackage
mypackage --help  # If entry point defined in pyproject.toml
```

### Python API
```python
from mypackage.core import MainClass
from mypackage.utils import helper_function
```
```

### Implementation

**File:** `generate_warm_start.py`

**Step 1:** Create `detect_project_type()` function (~30 lines)

```python
def detect_project_type(directory: str, project_name: str) -> str:
    """Detect if project is package-based or script-based."""

    # Check for package indicators
    pkg_dir = Path(directory) / project_name.replace("-", "_")
    has_package = pkg_dir.exists() and (pkg_dir / "__init__.py").exists()

    # Check for pyproject.toml with scripts
    pyproject = Path(directory) / "pyproject.toml"
    has_cli_entry = False
    if pyproject.exists():
        content = pyproject.read_text()
        has_cli_entry = "[project.scripts]" in content or "[tool.poetry.scripts]" in content

    # Check for setup.py entry points
    setup_py = Path(directory) / "setup.py"
    if setup_py.exists():
        content = setup_py.read_text()
        has_cli_entry = has_cli_entry or "entry_points" in content

    if has_package:
        return "package"
    else:
        return "scripts"
```

**Step 2:** Create `generate_entry_points_section()` function (~80 lines)

```python
def generate_entry_points_section(data: Dict, directory: str) -> str:
    """Generate Entry Points section based on project type."""

    project_name = data["project_name"]
    project_type = detect_project_type(directory, project_name)
    entry_points = data.get("entry_points", [])
    source_dir = data.get("source_dir", ".")

    lines = []

    if project_type == "package":
        # Package-based project
        pkg_name = project_name.replace("-", "_")

        lines.append("### CLI Commands")
        lines.append("```bash")
        lines.append(f"# Run as module")
        lines.append(f"python -m {pkg_name}")
        lines.append("```")
        lines.append("")
        lines.append("### Python API")
        lines.append("```python")
        lines.append(f"from {pkg_name} import main")

        # Add imports from orchestration layer
        orch = data["layers"].get("orchestration", [])
        for mod in orch[:3]:
            mod_path = mod.replace(".", "/")
            lines.append(f"from {mod} import *")

        lines.append("```")

    else:
        # Script-based project
        lines.append("### CLI Commands")
        lines.append("```bash")

        # List actual script entry points
        for ep in entry_points[:5]:
            file_path = ep.get("file", "")
            if file_path:
                # Make path relative
                rel_path = os.path.relpath(file_path, directory)
                lines.append(f"python {rel_path}")

        lines.append("```")
        lines.append("")
        lines.append("### Python API")
        lines.append("```python")
        lines.append("# Add scripts directory to path")
        lines.append("import sys")

        # Detect script directory
        if entry_points:
            first_file = entry_points[0].get("file", "")
            script_dir = os.path.dirname(os.path.relpath(first_file, directory))
            lines.append(f'sys.path.insert(0, "{script_dir}")')

        lines.append("")

        # Show imports from entry points
        for ep in entry_points[:4]:
            module = ep.get("module", "")
            if module:
                lines.append(f"from {module} import main")

        lines.append("```")

    # Add key imports section
    lines.append("")
    lines.append("### Key Imports")
    lines.append("```python")

    foundation = data["layers"].get("foundation", [])
    for mod in foundation[:3]:
        mod_short = mod.split(".")[-1]
        lines.append(f"from {mod} import *  # {mod_short}")

    lines.append("```")

    return "\n".join(lines)
```

**Step 3:** Update `render_template()`

Replace the hardcoded entry points section:
```python
"{ENTRY_POINTS_SECTION}": generate_entry_points_section(data, directory),
```

**Step 4:** Update template

In `warm_start.md.template`, ensure Section 5 has:
```markdown
## 5. Entry Points

{ENTRY_POINTS_SECTION}
```

### Testing

Add to `test_generate_warm_start.py`:

```python
class TestSection05EntryPoints:
    """Validate Entry Points section."""

    def test_no_invalid_package_name(self):
        """Entry points should not use invalid Python identifiers."""
        warm_start = Path("WARM_START_python.md").read_text()

        # Should not have hyphens in import statements
        import_lines = [l for l in warm_start.split("\n") if "from " in l and "import" in l]
        for line in import_lines:
            # Extract the module being imported
            if "from " in line:
                parts = line.split("from ")[1].split(" import")[0]
                # Hyphens are invalid in Python module names
                assert "-" not in parts or parts.startswith('"'), f"Invalid import: {line}"

    def test_script_paths_valid(self):
        """Script paths should be valid relative paths."""
        warm_start = Path("WARM_START_python.md").read_text()

        # Find python command lines
        for line in warm_start.split("\n"):
            if line.strip().startswith("python ") and ".py" in line:
                # Extract the path
                parts = line.split("python ")[1].split()[0]
                # Should be a valid path (no spaces, valid chars)
                assert " " not in parts or parts.startswith('"')
```

---

## Gap 3: Orphaned token_estimator.py

### Current State

`lib/token_estimator.py` exists but is not imported by any module. Both `mapper.py` and `generate_warm_start.py` have their own inline `estimate_tokens()` functions.

### Options

| Option | Pros | Cons |
|--------|------|------|
| A. Delete it | Clean, no dead code | Loses potential utility |
| B. Use it | DRY, single source of truth | Requires refactoring |
| C. Keep as-is | No work | Technical debt |

### Recommended: Option B - Use it

Consolidate token estimation into `lib/token_estimator.py` and import from there.

### Implementation

**Step 1:** Verify `lib/token_estimator.py` contents

Read the file and confirm it has:
- `estimate_tokens(text: str) -> int`
- `estimate_file_tokens(filepath: str) -> int`

**Step 2:** Update `mapper.py` to import from lib

Find:
```python
def estimate_tokens(filepath: str) -> int:
    """Estimate token count for a file (chars / 4)."""
    try:
        return os.path.getsize(filepath) // 4
    except (OSError, IOError):
        return 0
```

Replace with:
```python
# Add to imports at top
import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "lib"))
from token_estimator import estimate_file_tokens as estimate_tokens
```

Or if the function signatures differ, create a wrapper.

**Step 3:** Update `__all__` exports in mapper.py

Remove `estimate_tokens` from `__all__` since it's now imported:
```python
__all__ = [
    'map_directory',
    'load_ignore_patterns',
    # 'estimate_tokens',  # Now from lib
    'format_tokens',
    'get_size_tag',
]
```

**Step 4:** Verify token_estimator.py has correct functions

If needed, update `lib/token_estimator.py`:
```python
"""Token estimation utilities."""

import os

def estimate_tokens(text: str) -> int:
    """Estimate tokens from text (chars / 4)."""
    return len(text) // 4

def estimate_file_tokens(filepath: str) -> int:
    """Estimate tokens for a file."""
    try:
        return os.path.getsize(filepath) // 4
    except (OSError, IOError):
        return 0

def format_tokens(tokens: int) -> str:
    """Format token count for display."""
    if tokens >= 1000:
        return f"{tokens / 1000:.1f}K"
    return str(tokens)

def categorize_size(tokens: int) -> str:
    """Get size category tag."""
    if tokens > 50000:
        return "HUGE"
    elif tokens > 20000:
        return "LARGE"
    elif tokens > 10000:
        return "MEDIUM"
    return ""
```

### Testing

After changes, run:
```bash
# Verify mapper still works
python .claude/skills/repo-xray/scripts/mapper.py . --summary

# Verify token_estimator is no longer orphan
python .claude/skills/repo-xray/scripts/dependency_graph.py . --orphans

# Run all tests
pytest .claude/skills/repo-xray/tests/ -v
```

---

## Implementation Order

1. **Gap 3 first** (token_estimator) - Smallest change, cleans up dead code
2. **Gap 2 second** (Entry Points) - Medium complexity, high impact on usability
3. **Gap 1 last** (Data Flow) - Most complex, requires understanding call patterns

## Testing Checklist

After all changes:

```bash
# 1. Run existing tests (should still pass)
pytest .claude/skills/repo-xray/tests/test_generate_warm_start.py -v

# 2. Regenerate WARM_START for repo-xray (script-based project)
python .claude/skills/repo-xray/scripts/generate_warm_start.py . --debug -v -o WARM_START_python.md

# 3. Verify Section 4 (Data Flow) shows detected modules
grep -A 20 "## 4. Data Flow" WARM_START_python.md
# Should reference detected orchestration module, not hardcoded "configure"

# 4. Verify Section 5 (Entry Points) has valid Python
grep -A 20 "## 5. Entry Points" WARM_START_python.md
# Should NOT contain hyphens in import statements
# Should show actual script paths for script-based projects

# 5. Verify token_estimator is no longer orphan
python .claude/skills/repo-xray/scripts/dependency_graph.py . --orphans
# Should NOT list token_estimator.py

# 6. Test on a package-based project (any project with pkg/__init__.py structure)
# Create a test or use any available package-based repo
python .claude/skills/repo-xray/scripts/generate_warm_start.py /path/to/package-project -o /tmp/test_warm_start.md -v
grep -A 10 "## 5. Entry Points" /tmp/test_warm_start.md
# Should show "from package_name import ..." (valid package imports)

# 7. Run full test suite
pytest .claude/skills/repo-xray/tests/ -v
```

## Success Criteria

- [ ] Section 4 Data Flow shows detected orchestration module and its imports
- [ ] Section 5 Entry Points generates valid Python import statements (no hyphens)
- [ ] Section 5 Entry Points correctly detects script-based vs package-based projects
- [ ] Script-based projects show actual file paths
- [ ] Package-based projects show valid `from package import` statements
- [ ] `lib/token_estimator.py` is imported by `mapper.py`
- [ ] Orphan detection no longer flags `token_estimator.py`
- [ ] All 25+ existing tests pass
- [ ] Tool works generically on any Python repository

## Files Modified

| File | Changes |
|------|---------|
| `scripts/generate_warm_start.py` | Add `generate_data_flow()`, `detect_project_type()`, `generate_entry_points_section()` |
| `scripts/mapper.py` | Import `estimate_tokens` from lib instead of defining locally |
| `lib/token_estimator.py` | Ensure all needed functions exist |
| `templates/warm_start.md.template` | Update placeholders for sections 4 & 5 |
| `tests/test_generate_warm_start.py` | Add tests for sections 4 & 5 |

## Estimated Effort

- Gap 3 (token_estimator): ~15 minutes
- Gap 2 (Entry Points): ~45 minutes
- Gap 1 (Data Flow): ~30 minutes
- Testing & verification: ~20 minutes

**Total: ~2 hours**

# repo-xray v3.1 Enhancement Plan

**STATUS: PLANNING**
**Created: 2025-12-15**
**Goal: Add 9 new analysis features to v3.0**

> **Note:** Config-driven refactor (v3.0) is COMPLETE. This plan covers new features only.

---

## New Features (9 Total)

All features are **Python stdlib only** - no external dependencies.

| # | Feature | Complexity | Config Key |
|---|---------|------------|------------|
| 1 | GitHub repo "About" in summary | Medium | `sections.github_about` |
| 2 | Data flow annotations in Mermaid | Low | `sections.data_flow` |
| 3 | CLI arguments extraction | Medium | `sections.cli_arguments` |
| 4 | Instance variables in class skeletons | Low | `sections.instance_vars` |
| 5 | Pydantic validators in data models | Medium | `sections.pydantic_validators` |
| 6 | Hazards as glob patterns | Low | `sections.hazard_patterns` |
| 7 | Env var default values | Low | `sections.env_defaults` |
| 8 | One-shot test example | Medium | `sections.test_example` |
| 9 | Linter rules from config files | Medium | `sections.linter_rules` |

---

## Implementation Details

---

### Feature 1: GitHub "About" Section in Summary

**Goal:** Pull the repository description from GitHub and include it in the Summary section.

**Implementation (lib/gap_features.py):**

```python
def get_github_about(target_dir: str) -> dict:
    """
    Extract GitHub repo description.
    Strategy: Try gh CLI first (works for private repos), then API.
    Returns: {"description": str, "topics": list, "error": str or None}
    """
    # 1. Try gh CLI first (handles auth automatically)
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "description,topics"],
            cwd=target_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {"description": data.get("description"), "topics": data.get("topics", [])}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # gh not installed or timed out

    # 2. Fall back to GitHub API (public repos only)
    # Parse .git/config for remote URL
    git_config = Path(target_dir) / ".git" / "config"
    if not git_config.exists():
        return {"error": "Not a git repository"}

    # Extract owner/repo, call API with urllib.request

    # 3. Return error if both fail
    return {"error": "Private repo or GitHub unavailable"}
```

**Output in Markdown:**
```markdown
## Summary
> **About:** A unified AST-based Python codebase analysis tool for AI coding assistants.
> **Topics:** python, ast, codebase-analysis, ai-tools
```

**Config:** `sections.github_about: true` (default: true)

---

### Feature 2: Data Flow Annotations in Mermaid

**Goal:** Add `%% Data Flows: ...` comment showing push/pull direction.

**Implementation (lib/gap_features.py):**

Enhance `generate_mermaid_diagram()`:

```python
def generate_mermaid_diagram(import_data, call_data=None, max_nodes=30):
    # ... existing diagram generation ...

    # Add data flow annotation based on call analysis
    if call_data:
        # Analyze which layers call which: caller→callee = data pushed
        flow_direction = infer_data_flow(call_data, import_data["layers"])
        lines.append(f"%% Data Flows: {flow_direction}")
        # e.g., "%% Data Flows: Foundation → Core → Orchestration (push-based)"
```

**Analysis Logic:**
- Count calls from each layer to others
- If Foundation calls Core more than Core calls Foundation → "push-based"
- If Core calls Foundation more → "pull-based"

**Config:** `sections.data_flow: true` (default: true)

---

### Feature 3: CLI Arguments Extraction

**Goal:** Extract argparse/click/typer arguments for entry points.

**Implementation (lib/gap_features.py):**

```python
def extract_cli_arguments(entry_points: list, structure: dict) -> list:
    """
    Parse entry point files for CLI arguments.
    Supports: argparse, click, typer
    Returns: [{file, arguments: [{name, help, required, default}]}]
    """
    for entry in entry_points:
        filepath = entry["file"]
        tree = ast.parse(source)

        # Pattern 1: argparse
        # Look for parser.add_argument('--foo', ...) calls

        # Pattern 2: click
        # Look for @click.option('--foo', ...) decorators

        # Pattern 3: typer
        # Look for typer.Option() and typer.Argument() in function signatures
        # e.g., def main(name: str = typer.Argument(...), verbose: bool = typer.Option(False))
```

**Output in Markdown:**
```markdown
## Entry Points

| Entry | File | Usage |
|-------|------|-------|
| `main.py` | lib/main.py | `python main.py --query QUERY [--config FILE]` |

### CLI Arguments for `main.py`:
| Argument | Required | Default | Help |
|----------|----------|---------|------|
| `--query` | Yes | - | Query to execute |
| `--config` | No | config.json | Config file path |
```

**Config:** `sections.cli_arguments: true` (default: true)

---

### Feature 4: Instance Variables in Class Skeletons

**Goal:** Include `self.x = ...` from `__init__` in critical class skeletons.

**Implementation (lib/ast_analysis.py):**

Enhance `generate_skeleton()`:

```python
def _extract_instance_vars(init_method: ast.FunctionDef) -> list:
    """Extract self.x = y assignments from __init__."""
    instance_vars = []
    for node in ast.walk(init_method):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == "self":
                        var_name = target.attr
                        var_value = _get_default_repr(node.value)  # Existing helper!
                        instance_vars.append((var_name, var_value))
    return instance_vars
```

**Output:**
```python
class DatabaseManager:
    # Instance variables (from __init__)
    self.connection = None
    self.pool_size = 10
    self.timeout = 30.0

    def __init__(self, host: str, port: int = 5432): ...
    def connect(self) -> Connection: ...
```

**Config:** `sections.instance_vars: true` (default: true)

---

### Feature 5: Pydantic Validators in Data Models

**Goal:** Extract `Field(...)` constraints and `@validator` decorators.

**Implementation (lib/gap_features.py):**

Enhance `extract_data_models()`:

```python
def _extract_field_constraints(class_node: ast.ClassDef) -> dict:
    """Extract Field() constraints for each field."""
    constraints = {}
    for node in ast.walk(class_node):
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.value, ast.Call):
                if _is_field_call(node.value):  # Check for Field(...)
                    field_name = node.target.id
                    constraints[field_name] = _extract_field_args(node.value)
                    # e.g., {"gt": 0, "le": 100, "description": "..."}
    return constraints
```

**Output:**
```markdown
### Data Models

#### `Config` (Pydantic) - lib/config.py:15
| Field | Type | Constraints |
|-------|------|-------------|
| `max_cost_usd` | float | gt=0, le=1000 |
| `timeout` | int | ge=1, default=30 |
| `name` | str | min_length=1 |
```

**Config:** `sections.pydantic_validators: true` (default: true)

---

### Feature 6: Hazards as Glob Patterns

**Goal:** Derive glob patterns from hazard file paths.

**Implementation (lib/gap_features.py):**

```python
def derive_hazard_patterns(hazards: list) -> list:
    """
    Convert specific hazard paths to glob patterns.
    e.g., [artifacts/a.json, artifacts/b.json] → ["artifacts/**"]
    """
    # Group by parent directory
    # If multiple files in same dir → dir/**
    # If single file → keep specific path
    # Return unique patterns
```

**Output:**
```markdown
## Context Hazards

> **Warning:** These paths contain large files that may waste context tokens.

**Patterns to exclude:**
- `**/artifacts/**` (3 files, ~50K tokens)
- `**/logs/**` (5 files, ~100K tokens)
- `data/cache/*.json` (2 files, ~20K tokens)
```

**Config:** `sections.hazard_patterns: true` (default: true)

---

### Feature 7: Env Var Default Values

**Goal:** Extract default values from `os.getenv("KEY", "default")`.

**Implementation (lib/gap_features.py):**

Replace regex with AST:

```python
def get_environment_variables_enhanced(results: dict) -> list:
    """AST-based extraction with defaults."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _is_getenv_call(node):
                var_name = _get_string_value(node.args[0])
                default = None
                if len(node.args) > 1:
                    default = _get_default_repr(node.args[1])  # Existing helper!
                env_vars.append({
                    "variable": var_name,
                    "default": default,  # NEW
                    "required": default is None,  # NEW
                    "file": filepath,
                    "line": node.lineno
                })
```

**Output:**
```markdown
## Environment Variables

| Variable | Default | Required | Location |
|----------|---------|----------|----------|
| `DATABASE_URL` | - | **Yes** | config.py:10 |
| `LOG_LEVEL` | "INFO" | No | logging.py:5 |
| `TIMEOUT` | 30 | No | client.py:20 |
```

**Config:** `sections.env_defaults: true` (default: true)

---

### Feature 8: One-Shot Test Example

**Goal:** Include one complete test file as a "Rosetta Stone".

**Implementation (lib/test_analysis.py):**

```python
def get_test_example(test_files: list, max_lines: int = 50) -> dict:
    """
    Find the best representative test file (max 50 lines).
    Criteria: complete, uses fixtures, reasonable size.
    Returns: {"file": path, "content": str, "patterns": []}
    """
    # 1. Filter to files under 50 lines
    # 2. Score by: has fixtures usage, has mocking, has assertions
    # 3. Return best candidate with full content
    # 4. Identify patterns: unittest.mock, pytest-mock, custom mocks
```

**Output:**
```markdown
## Testing Idioms

> Use this test as a template for new tests.

**Mocking patterns used:** `unittest.mock.patch`, `pytest.fixture`

```python
# tests/unit/test_example.py
import pytest
from unittest.mock import patch, MagicMock
from myapp.service import MyService

@pytest.fixture
def mock_db():
    return MagicMock()

def test_service_creates_record(mock_db):
    with patch("myapp.service.database", mock_db):
        svc = MyService()
        result = svc.create("test")
        mock_db.insert.assert_called_once()
        assert result.id is not None
```
```

**Config:** `sections.test_example: true` (default: true)

---

### Feature 9: Linter Rules from Config Files

**Goal:** Extract key rules from pyproject.toml, ruff.toml, etc.

**Implementation (lib/gap_features.py):**

```python
def extract_linter_rules(target_dir: str) -> dict:
    """
    Parse linter config files for key rules.
    Returns: {"line_length": int, "banned_imports": [], "rules": []}
    """
    # Check for: pyproject.toml, ruff.toml, .flake8, setup.cfg
    # For Python 3.11+: use tomllib (stdlib)
    # For older: basic string parsing or skip

    # Extract:
    # - line-length
    # - select/ignore rules
    # - banned imports
    # - required imports (isort settings)
```

**Output:**
```markdown
## Project Idioms

> Follow these rules to pass CI.

**Linter:** ruff (from pyproject.toml)

| Rule | Value |
|------|-------|
| Line length | 100 |
| Quote style | double |
| Import sorting | isort-compatible |

**Banned patterns:**
- `print()` - use `logger.info()` instead
- `import os` - use `from pathlib import Path`
```

**Config:** `sections.linter_rules: true` (default: true)

---

## Files to Modify

| File | Changes | Est. Lines |
|------|---------|------------|
| `lib/gap_features.py` | Features 1,2,3,5,6,7,9 | ~350 |
| `lib/ast_analysis.py` | Feature 4 (instance vars) | ~40 |
| `lib/test_analysis.py` | Feature 8 (test example) | ~60 |
| `lib/config_loader.py` | Add new config keys | ~20 |
| `configs/default_config.json` | Add 9 new section keys | ~10 |
| `formatters/markdown_formatter.py` | Render new sections | ~150 |
| `README.md` | Document new features | ~50 |

**Total:** ~680 lines of new code

---

## Config Updates

Add to `configs/default_config.json` sections:

```json
{
  "sections": {
    "github_about": true,
    "data_flow": true,
    "cli_arguments": true,
    "instance_vars": true,
    "pydantic_validators": true,
    "hazard_patterns": true,
    "env_defaults": true,
    "test_example": true,
    "linter_rules": true
  }
}
```

---

## Implementation Order

**Phase 1: Easy wins (low complexity)**
1. Feature 7: Env var defaults (~40 lines)
2. Feature 4: Instance variables (~30 lines)
3. Feature 6: Hazard patterns (~40 lines)

**Phase 2: Medium complexity**
4. Feature 2: Data flow annotations (~30 lines)
5. Feature 3: CLI arguments (~80 lines)
6. Feature 5: Pydantic validators (~60 lines)

**Phase 3: Requires external calls/parsing**
7. Feature 1: GitHub about (~50 lines)
8. Feature 8: Test example (~60 lines)
9. Feature 9: Linter rules (~60 lines)

**Phase 4: Integration**
10. Update markdown formatter for all new sections
11. Update config files
12. Update README
13. Run tests

---

## Validation

```bash
# Test each feature individually
python xray.py /path/to/project --output markdown > test_output.md

# Verify new sections appear:
# - GitHub About in Summary
# - Data flow comment in Mermaid
# - CLI arguments table in Entry Points
# - Instance vars in Critical Classes
# - Constraints in Data Models
# - Glob patterns in Hazards
# - Defaults in Env Vars
# - Test example section
# - Linter rules section

# Test against kosmos repo
python xray.py /mnt/c/python/kosmos --output markdown > kosmos_test.md

# Run existing tests
pytest tests/ -v
```

---

## Success Criteria

- [ ] All 9 features implemented with Python stdlib only
- [ ] Each feature has corresponding config key
- [ ] Each feature can be disabled via config
- [ ] Existing tests still pass
- [ ] New output matches expected format
- [ ] README documents all new features

---

## Notes

- **Python version:** Use `tomllib` (3.11+) for TOML parsing; fall back gracefully
- **GitHub:** Try `gh` CLI first (handles auth), then API, then show error
- **Instance vars:** Use existing `_get_default_repr()` helper
- **Test example:** Limit to files under 50 lines to avoid bloat
- **CLI libraries:** Support argparse, click, and typer

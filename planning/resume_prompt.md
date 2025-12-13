# Resume Prompt: Investigate and Validate generate_warm_start.py Output

## Context

The `generate_warm_start.py` tool was implemented to automatically generate WARM_START.md documents. Initial testing revealed:

| Repository | Files | Expected Size | Actual Size | Issue |
|------------|-------|---------------|-------------|-------|
| kosmos | 2,653 | ~15KB | 18KB | OK |
| repo-xray | 29 | ~10KB | ~8KB | Smaller than expected |

The repo-xray output is suspiciously small, suggesting some sections may be sparse or missing detail.

## Investigation Goals

1. **Audit each section** - Verify all 12 sections have appropriate content
2. **Compare with manual versions** - Identify gaps vs warm_start_v4.md
3. **Add raw data output** - Output section data alongside rendered markdown
4. **Create validation tests** - Independently verify each section's accuracy

## Files to Investigate

### Primary
- `/mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/scripts/generate_warm_start.py`
- `/mnt/c/python/claude-repo-xray/WARM_START_generated.md` (the sparse output)

### Reference
- `/mnt/c/python/kosmos/warm_start_v4.md` (manual, comprehensive)
- `/mnt/c/python/kosmos/WARM_START_generated.md` (automated)

## Section-by-Section Audit Checklist

### Section 1: System Context
- [ ] Mermaid diagram has nodes for all layers
- [ ] Edges show actual dependencies
- [ ] Compare node count: manual vs generated

### Section 2: Architecture Overview
- [ ] Project name detected correctly
- [ ] Architectural patterns identified (agents, workflow, api, etc.)
- [ ] Module counts accurate
- [ ] Confidence marker present if low confidence

### Section 3: Critical Classes
- [ ] Entry points detected (main.py, cli.py, __main__.py)
- [ ] Core components have skeleton code (not just table)
- [ ] Data models extracted with Pydantic fields
- [ ] Compare detail level with manual version

### Section 4: Data Flow
- [ ] Entry point class populated (not placeholder)
- [ ] Flow steps reflect actual architecture
- [ ] Compare with manual data flow

### Section 5: Entry Points
- [ ] CLI commands detected from cli.py
- [ ] Python API examples accurate
- [ ] Key imports from foundation layer

### Section 6: Context Hazards
- [ ] Large files table populated
- [ ] Hazard directories listed
- [ ] Extensions to skip listed

### Section 7: Quick Verification
- [ ] Health check command uses project name
- [ ] Test command appropriate
- [ ] Import verification uses correct package

### Section 8: X-Ray Commands
- [ ] Source directory correct
- [ ] Focus area appropriate
- [ ] Token budget table present

### Section 9: Architecture Layers
- [ ] Foundation table has modules with import counts
- [ ] Core table populated
- [ ] Orchestration table populated
- [ ] Compare counts with dependency_graph.py output

### Section 10: Risk Assessment
- [ ] Risk table has files with scores
- [ ] Factors (churn, hotfixes, authors) present
- [ ] Compare with git_analysis.py --risk output

### Section 11: Hidden Coupling
- [ ] Coupling pairs listed (or "none found" message)
- [ ] Compare with git_analysis.py --coupling output

### Section 12: Potential Dead Code
- [ ] Orphan files table populated
- [ ] Dormant files or "none" message
- [ ] Freshness summary table present
- [ ] Compare with dependency_graph.py --orphans

## Implementation Tasks

### 1. Add Raw Data Output Mode

Modify `generate_warm_start.py` to support `--debug` flag that outputs:

```bash
python generate_warm_start.py /path/to/repo --debug
```

Output structure:
```
WARM_START.md           # The rendered document
WARM_START_data.json    # Raw data for all sections
WARM_START_sections/    # Individual section data
  section_01_context.json
  section_02_overview.json
  section_03_classes.json
  ...
  section_12_deadcode.json
```

### 2. Create Validation Tests

Create `/mnt/c/python/claude-repo-xray/.claude/skills/repo-xray/tests/test_generate_warm_start.py`:

```python
"""Tests for generate_warm_start.py output validation."""

import pytest
import json
from pathlib import Path

class TestSection01Context:
    """Validate System Context section."""

    def test_mermaid_has_subgraphs(self, generated_data):
        """Mermaid should have ORCHESTRATION, CORE, FOUNDATION subgraphs."""
        mermaid = generated_data["mermaid"]
        assert "subgraph ORCHESTRATION" in mermaid
        assert "subgraph CORE" in mermaid
        assert "subgraph FOUNDATION" in mermaid

    def test_mermaid_has_edges(self, generated_data):
        """Mermaid should have dependency edges."""
        mermaid = generated_data["mermaid"]
        assert "-->" in mermaid  # Has at least one edge

class TestSection02Overview:
    """Validate Architecture Overview section."""

    def test_project_name_detected(self, generated_data):
        """Project name should be detected."""
        assert generated_data["project_name"]
        assert generated_data["project_name"] != "."

    def test_module_counts_accurate(self, generated_data):
        """Module counts should match actual modules."""
        layers = generated_data["layers"]
        total = (
            len(layers.get("orchestration", [])) +
            len(layers.get("core", [])) +
            len(layers.get("foundation", []))
        )
        assert total > 0

class TestSection03Classes:
    """Validate Critical Classes section."""

    def test_entry_points_detected(self, generated_data):
        """Should detect at least one entry point."""
        assert len(generated_data["entry_points"]) > 0

    def test_critical_classes_have_skeleton(self, generated_data):
        """Critical classes should have skeleton code."""
        for cls in generated_data["critical_classes"]:
            assert cls.get("skeleton")
            assert len(cls["skeleton"]) > 50  # Not empty

class TestSection09Layers:
    """Validate Architecture Layers section."""

    def test_foundation_not_empty(self, generated_data):
        """Foundation layer should have modules."""
        assert len(generated_data["layers"].get("foundation", [])) > 0

    def test_layers_match_graph(self, generated_data):
        """Layer modules should exist in graph."""
        graph_modules = set(generated_data["graph"]["modules"].keys())
        for layer in ["foundation", "core", "orchestration"]:
            for module in generated_data["layers"].get(layer, []):
                assert module in graph_modules

class TestSection10Risk:
    """Validate Risk Assessment section."""

    def test_risk_scores_valid(self, generated_data):
        """Risk scores should be between 0 and 1."""
        for r in generated_data["risk"]:
            assert 0 <= r["risk_score"] <= 1

    def test_risk_factors_present(self, generated_data):
        """Risk entries should have all factors."""
        for r in generated_data["risk"]:
            assert "churn" in r
            assert "hotfixes" in r
            assert "authors" in r

class TestSection12DeadCode:
    """Validate Potential Dead Code section."""

    def test_orphans_have_confidence(self, generated_data):
        """Orphan entries should have confidence scores."""
        for o in generated_data["orphans"]:
            assert "confidence" in o
            assert 0 <= o["confidence"] <= 1

    def test_freshness_categories_present(self, generated_data):
        """Freshness should have all categories."""
        freshness = generated_data["freshness"]
        assert "active" in freshness
        assert "aging" in freshness
        assert "stale" in freshness
        assert "dormant" in freshness
```

### 3. Fix Identified Issues

Based on audit findings, fix issues in:
- `generate_warm_start.py` - Main generator
- `format_*` functions - Section formatters
- Data collection functions - If missing data

## Testing Commands

```bash
# Generate output with debug data
python .claude/skills/repo-xray/scripts/generate_warm_start.py /mnt/c/python/claude-repo-xray --debug -v

# Run validation tests
pytest .claude/skills/repo-xray/tests/test_generate_warm_start.py -v

# Compare section outputs manually
diff <(python git_analysis.py /mnt/c/python/claude-repo-xray --risk) \
     <(grep -A20 "## 10. Risk Assessment" WARM_START_generated.md)
```

## Success Criteria

- [ ] All 12 sections have appropriate content (not sparse)
- [ ] Raw data JSON available for each section
- [ ] Validation tests pass for both repos (kosmos, repo-xray)
- [ ] Generated output comparable to manual warm_start_v4.md
- [ ] Debug mode outputs section-by-section data

## Notes

- The repo-xray codebase is small (29 files) so some sections will naturally have less content
- Focus on ensuring sections aren't *missing* data, not just smaller
- The hybrid approach means Claude can enhance sparse sections if needed

"""Tests for generate_warm_start.py output validation.

Run with: pytest .claude/skills/repo-xray/tests/test_generate_warm_start.py -v

Prerequisites:
    Run generate_warm_start.py with --debug flag first:
    python .claude/skills/repo-xray/scripts/generate_warm_start.py . --debug
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from dependency_graph import build_dependency_graph, identify_layers, detect_source_root


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def repo_root():
    """Get the repository root directory."""
    # Navigate from tests/ to repo root
    return Path(__file__).parent.parent.parent.parent.parent


@pytest.fixture(scope="module")
def debug_data(repo_root):
    """Load generated debug data for repo-xray."""
    data_path = repo_root / "WARM_START_debug" / "raw_data.json"
    if not data_path.exists():
        pytest.skip(
            "Debug data not generated. Run: "
            "python .claude/skills/repo-xray/scripts/generate_warm_start.py . --debug"
        )
    return json.loads(data_path.read_text())


@pytest.fixture(scope="module")
def graph_data(repo_root):
    """Build a fresh dependency graph for testing."""
    return build_dependency_graph(str(repo_root), auto_detect=True)


@pytest.fixture(scope="module")
def layers_data(graph_data):
    """Get layer classification from graph."""
    return identify_layers(graph_data)


# =============================================================================
# Test Source Root Detection
# =============================================================================

class TestSourceRootDetection:
    """Test that source root is correctly detected."""

    def test_detects_nested_source_root(self, repo_root):
        """Should detect .claude/skills/repo-xray/scripts as source root."""
        source_root = detect_source_root(str(repo_root))
        assert source_root is not None
        assert "scripts" in source_root or "repo-xray" in source_root

    def test_source_root_contains_python_files(self, repo_root):
        """Detected source root should contain Python files."""
        source_root = detect_source_root(str(repo_root))
        if source_root:
            py_files = list(Path(source_root).glob("*.py"))
            assert len(py_files) > 0


# =============================================================================
# Test Module Detection
# =============================================================================

class TestModuleDetection:
    """Test that all modules are detected."""

    def test_all_scripts_detected(self, graph_data):
        """All script files should be detected as modules."""
        expected = {
            "configure", "dependency_graph", "generate_warm_start",
            "git_analysis", "mapper", "skeleton"
        }
        modules = set(m.split(".")[-1] for m in graph_data["modules"])
        missing = expected - modules
        assert not missing, f"Missing modules: {missing}"

    def test_lib_modules_detected(self, graph_data):
        """Library modules should be detected."""
        module_names = list(graph_data["modules"].keys())
        lib_modules = [m for m in module_names if "ast_utils" in m or "token_estimator" in m]
        assert len(lib_modules) >= 1, "Should detect lib modules"

    def test_module_names_clean(self, graph_data):
        """Module names should not start with dots."""
        for module_name in graph_data["modules"]:
            assert not module_name.startswith("."), f"Module name starts with dot: {module_name}"

    def test_imports_detected(self, graph_data):
        """Modules should have detected imports."""
        # generate_warm_start imports from dependency_graph, git_analysis, mapper, lib.ast_utils
        gen_modules = [m for m in graph_data["modules"] if "generate_warm_start" in m]
        assert gen_modules, "generate_warm_start module should exist"

        gen_module = gen_modules[0]
        imports = graph_data["modules"][gen_module]["imports"]
        assert len(imports) >= 3, f"generate_warm_start should have 3+ imports, got {len(imports)}"


# =============================================================================
# Test Layer Classification
# =============================================================================

class TestLayerClassification:
    """Test architectural layer assignment."""

    def test_not_all_leaf(self, layers_data):
        """Modules shouldn't all be in leaf layer."""
        leaf_count = len(layers_data.get("leaf", []))
        total = sum(len(v) for v in layers_data.values())
        ratio = leaf_count / total if total > 0 else 1
        assert ratio < 0.8, f"Too many modules in leaf layer: {leaf_count}/{total}"

    def test_has_foundation(self, layers_data):
        """Should have foundation layer modules."""
        foundation = layers_data.get("foundation", [])
        assert len(foundation) > 0, "Should have foundation modules"

    def test_has_core_or_orchestration(self, layers_data):
        """Should have core and/or orchestration layer modules."""
        core = layers_data.get("core", [])
        orchestration = layers_data.get("orchestration", [])
        assert len(core) + len(orchestration) > 0, "Should have core or orchestration modules"

    def test_generate_warm_start_is_orchestration(self, layers_data):
        """generate_warm_start should be in orchestration layer."""
        orch = layers_data.get("orchestration", [])
        gen_modules = [m for m in orch if "generate_warm_start" in m]
        assert gen_modules, "generate_warm_start should be in orchestration layer"


# =============================================================================
# Test Debug Output Structure
# =============================================================================

class TestDebugOutput:
    """Test that debug output has correct structure."""

    def test_raw_data_has_required_fields(self, debug_data):
        """raw_data.json should have all required fields."""
        required = [
            "project_name", "timestamp", "layers", "mermaid",
            "risk", "coupling", "freshness", "orphans", "entry_points"
        ]
        for field in required:
            assert field in debug_data, f"Missing field: {field}"

    def test_layers_structure(self, debug_data):
        """Layers should have expected structure."""
        layers = debug_data["layers"]
        for layer in ["foundation", "core", "orchestration"]:
            assert layer in layers, f"Missing layer: {layer}"
            assert isinstance(layers[layer], list), f"Layer {layer} should be a list"

    def test_entry_points_not_empty(self, debug_data):
        """Should have detected entry points."""
        entry_points = debug_data.get("entry_points", [])
        assert len(entry_points) > 0, "Should have entry points"


# =============================================================================
# Test Section 9: Architecture Layers
# =============================================================================

class TestSection09Layers:
    """Validate Architecture Layers section."""

    def test_foundation_has_modules(self, layers_data):
        """Foundation layer should have modules."""
        assert len(layers_data.get("foundation", [])) > 0

    def test_core_has_modules(self, layers_data):
        """Core layer should have modules."""
        assert len(layers_data.get("core", [])) > 0

    def test_layers_have_imports(self, graph_data):
        """Layer modules should have import relationships."""
        modules = graph_data["modules"]
        has_imports = sum(1 for m in modules.values() if m["imports"])
        assert has_imports > 0, "Some modules should have imports"

    def test_layers_have_imported_by(self, graph_data):
        """Some modules should be imported by others."""
        modules = graph_data["modules"]
        has_imported_by = sum(1 for m in modules.values() if m["imported_by"])
        assert has_imported_by > 0, "Some modules should have imported_by"


# =============================================================================
# Test Section 10: Risk Assessment
# =============================================================================

class TestSection10Risk:
    """Validate Risk Assessment section."""

    def test_has_risk_data(self, debug_data):
        """Should have risk assessment data."""
        risk = debug_data.get("risk", [])
        # Risk data may be empty for very new repos
        assert isinstance(risk, list)

    def test_risk_scores_valid(self, debug_data):
        """Risk scores should be between 0 and 1."""
        for r in debug_data.get("risk", []):
            assert "risk_score" in r
            assert 0 <= r["risk_score"] <= 1, f"Invalid risk score: {r['risk_score']}"

    def test_risk_has_factors(self, debug_data):
        """Risk entries should have contributing factors."""
        for r in debug_data.get("risk", []):
            assert "churn" in r
            assert "hotfixes" in r
            assert "authors" in r


# =============================================================================
# Test Section 12: Potential Dead Code
# =============================================================================

class TestSection12DeadCode:
    """Validate Potential Dead Code section."""

    def test_orphans_structure(self, debug_data):
        """Orphan entries should have correct structure."""
        for o in debug_data.get("orphans", []):
            assert "file" in o
            assert "confidence" in o
            assert 0 <= o["confidence"] <= 1

    def test_freshness_structure(self, debug_data):
        """Freshness data should have correct structure."""
        freshness = debug_data.get("freshness", {})
        expected_categories = ["active", "aging", "stale", "dormant"]
        for cat in expected_categories:
            assert cat in freshness, f"Missing freshness category: {cat}"


# =============================================================================
# Test Mermaid Diagram
# =============================================================================

class TestMermaidDiagram:
    """Test Mermaid diagram generation."""

    def test_has_mermaid(self, debug_data):
        """Should have Mermaid diagram."""
        mermaid = debug_data.get("mermaid", "")
        assert mermaid, "Mermaid diagram should not be empty"
        assert "graph TD" in mermaid

    def test_mermaid_has_subgraphs(self, debug_data):
        """Mermaid should have layer subgraphs."""
        mermaid = debug_data.get("mermaid", "")
        # At least one of these should be present
        has_subgraph = (
            "subgraph ORCHESTRATION" in mermaid or
            "subgraph CORE" in mermaid or
            "subgraph FOUNDATION" in mermaid
        )
        assert has_subgraph, "Mermaid should have layer subgraphs"

    def test_mermaid_has_edges(self, debug_data):
        """Mermaid should have dependency edges."""
        mermaid = debug_data.get("mermaid", "")
        assert "-->" in mermaid, "Mermaid should have dependency edges"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

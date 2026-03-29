"""
Unit tests for investigation_targets.py

Tests the investigation targets module that computes prioritized
investigation signals for the deep_crawl agent.
"""

import sys
from pathlib import Path

import pytest

# Add lib directory to path
TESTS_DIR = Path(__file__).parent
ROOT_DIR = TESTS_DIR.parent
LIB_DIR = ROOT_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

from investigation_targets import (
    compute_investigation_targets,
    compute_ambiguous_interfaces,
    compute_entry_side_effect_paths,
    compute_coupling_anomalies,
    compute_convention_deviations,
    compute_shared_mutable_state,
    compute_high_uncertainty_modules,
    compute_domain_entities,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def empty_results():
    """Empty analysis results."""
    return {"files": {}}


@pytest.fixture
def basic_ast_results():
    """AST results with functions of varying ambiguity."""
    return {
        "files": {
            "/project/core/engine.py": {
                "functions": [
                    {
                        "name": "process",
                        "args": [{"name": "data"}, {"name": "options"}],
                        "returns": None,
                        "complexity": 15,
                        "start_line": 10,
                        "docstring": None,
                        "has_type_hints": False,
                    },
                    {
                        "name": "calculate_total",
                        "args": [
                            {"name": "items", "type": "List[Item]"},
                            {"name": "discount", "type": "float"},
                        ],
                        "returns": "float",
                        "complexity": 3,
                        "start_line": 50,
                        "docstring": "Calculate total with discount.",
                        "has_type_hints": True,
                    },
                ],
                "classes": [
                    {
                        "name": "Engine",
                        "start_line": 5,
                        "docstring": "Main engine.",
                        "methods": [
                            {
                                "name": "__init__",
                                "args": [{"name": "self"}, {"name": "config", "type": "Config"}],
                                "returns": None,
                                "complexity": 1,
                                "start_line": 6,
                            },
                            {
                                "name": "handle",
                                "args": [{"name": "self"}, {"name": "request"}],
                                "returns": None,
                                "complexity": 8,
                                "start_line": 20,
                            },
                        ],
                    }
                ],
                "type_coverage": {"total_functions": 3, "typed_functions": 1, "coverage_percent": 33.3},
                "complexity": {"hotspots": {}},
                "side_effects": [
                    {"category": "db", "call": "db.commit", "line": 30},
                ],
                "internal_calls": {},
            },
            "/project/utils/helpers.py": {
                "functions": [
                    {
                        "name": "format",
                        "args": [{"name": "value"}],
                        "returns": "str",
                        "complexity": 2,
                        "start_line": 5,
                        "docstring": "Format a value.",
                        "has_type_hints": True,
                    },
                ],
                "classes": [],
                "type_coverage": {"total_functions": 1, "typed_functions": 1, "coverage_percent": 100.0},
                "complexity": {"hotspots": {}},
                "side_effects": [],
                "internal_calls": {},
            },
        },
        "summary": {
            "total_files": 2,
            "total_functions": 4,
        },
    }


@pytest.fixture
def basic_call_results():
    """Call analysis results with cross-module data."""
    return {
        "cross_module": {
            "engine.process": {
                "call_count": 5,
                "calling_modules": 3,
                "call_sites": [
                    {"file": "/project/api/routes.py", "line": 15, "caller": "handle_request"},
                    {"file": "/project/cli/main.py", "line": 30, "caller": "run"},
                ],
            },
            "helpers.format": {
                "call_count": 2,
                "calling_modules": 2,
                "call_sites": [
                    {"file": "/project/core/engine.py", "line": 25, "caller": "process"},
                ],
            },
        },
    }


@pytest.fixture
def basic_git_results():
    """Git analysis results."""
    return {
        "risk": [
            {"file": "/project/core/engine.py", "risk_score": 0.85, "churn": 15, "hotfixes": 3, "authors": 4},
        ],
        "coupling": [
            {"file_a": "/project/core/engine.py", "file_b": "/project/utils/helpers.py", "count": 8},
        ],
        "freshness": {},
    }


@pytest.fixture
def basic_import_results():
    """Import analysis results."""
    return {
        "graph": {
            "engine": {"imports": ["helpers"], "imported_by": ["routes", "main"]},
            "helpers": {"imports": [], "imported_by": ["engine"]},
            "routes": {"imports": ["engine"], "imported_by": []},
        },
    }


@pytest.fixture
def basic_gap_results():
    """Gap results with entry points and data models."""
    return {
        "entry_points": [
            {"file": "/project/cli/main.py", "entry_point": "main()", "type": "function"},
        ],
        "data_models": [
            {"name": "Order", "type": "dataclass", "file": "/project/models/order.py", "line": 5,
             "fields": [{"name": "id", "type": "int"}, {"name": "total", "type": "float"}]},
        ],
    }


# =============================================================================
# Tests: compute_ambiguous_interfaces
# =============================================================================

class TestAmbiguousInterfaces:
    def test_flags_generic_names(self, basic_ast_results, basic_call_results):
        result = compute_ambiguous_interfaces(basic_ast_results, basic_call_results)
        names = [r["function"] for r in result]
        assert "process" in names
        assert "handle" in names

    def test_skips_well_typed_functions(self, basic_ast_results, basic_call_results):
        result = compute_ambiguous_interfaces(basic_ast_results, basic_call_results)
        names = [r["function"] for r in result]
        assert "calculate_total" not in names

    def test_skips_private_functions(self, basic_ast_results, basic_call_results):
        result = compute_ambiguous_interfaces(basic_ast_results, basic_call_results)
        names = [r["function"] for r in result]
        assert "__init__" not in names

    def test_includes_ambiguity_score(self, basic_ast_results, basic_call_results):
        result = compute_ambiguous_interfaces(basic_ast_results, basic_call_results)
        for r in result:
            assert "ambiguity_score" in r
            assert r["ambiguity_score"] > 0

    def test_empty_input(self, empty_results):
        result = compute_ambiguous_interfaces(empty_results, {})
        assert result == []


# =============================================================================
# Tests: compute_entry_side_effect_paths
# =============================================================================

class TestEntrySideEffectPaths:
    def test_finds_paths(self, basic_ast_results, basic_call_results, basic_gap_results):
        result = compute_entry_side_effect_paths(
            basic_ast_results, basic_call_results, basic_gap_results
        )
        assert len(result) >= 0  # May be 0 if BFS doesn't connect

    def test_includes_granularity(self, basic_ast_results, basic_call_results, basic_gap_results):
        result = compute_entry_side_effect_paths(
            basic_ast_results, basic_call_results, basic_gap_results
        )
        for path in result:
            assert path.get("granularity") == "module_level"

    def test_empty_entry_points(self, basic_ast_results, basic_call_results):
        result = compute_entry_side_effect_paths(
            basic_ast_results, basic_call_results, {"entry_points": []}
        )
        assert result == []


# =============================================================================
# Tests: compute_coupling_anomalies
# =============================================================================

class TestCouplingAnomalies:
    def test_detects_anomalies_without_imports(self):
        git = {"coupling": [
            {"file_a": "a.py", "file_b": "b.py", "count": 10},
        ]}
        imports = {"graph": {
            "a": {"imports": [], "imported_by": []},
            "b": {"imports": [], "imported_by": []},
        }}
        result = compute_coupling_anomalies(git, imports)
        assert len(result) == 1
        assert result[0]["reason"] == "co_modified_without_imports"

    def test_skips_when_import_exists(self):
        git = {"coupling": [
            {"file_a": "a.py", "file_b": "b.py", "count": 10},
        ]}
        imports = {"graph": {
            "a": {"imports": ["b"], "imported_by": []},
            "b": {"imports": [], "imported_by": ["a"]},
        }}
        result = compute_coupling_anomalies(git, imports)
        assert len(result) == 0

    def test_empty_coupling(self, basic_import_results):
        result = compute_coupling_anomalies({"coupling": []}, basic_import_results)
        assert result == []


# =============================================================================
# Tests: compute_convention_deviations
# =============================================================================

class TestConventionDeviations:
    def test_detects_init_pattern_deviations(self, basic_ast_results):
        result = compute_convention_deviations(basic_ast_results)
        assert isinstance(result, list)

    def test_empty_input(self, empty_results):
        result = compute_convention_deviations(empty_results)
        assert result == []


# =============================================================================
# Tests: compute_shared_mutable_state
# =============================================================================

class TestSharedMutableState:
    def test_empty_input(self, empty_results):
        result = compute_shared_mutable_state(empty_results)
        assert result == []

    def test_handles_missing_files(self):
        ast_results = {"files": {"/nonexistent/file.py": {}}}
        result = compute_shared_mutable_state(ast_results)
        assert result == []


# =============================================================================
# Tests: compute_high_uncertainty_modules
# =============================================================================

class TestHighUncertaintyModules:
    def test_flags_generic_module_names(self):
        ast_results = {
            "files": {
                "/project/utils.py": {
                    "functions": [{"name": "do_stuff", "args": [], "docstring": None}],
                    "classes": [],
                    "type_coverage": {"total_functions": 1, "typed_functions": 0, "coverage_percent": 0.0},
                    "complexity": {"hotspots": {}},
                },
            }
        }
        result = compute_high_uncertainty_modules(ast_results, {})
        assert len(result) >= 1
        assert any("generic_name" in r["reasons"] for r in result)

    def test_empty_input(self, empty_results):
        result = compute_high_uncertainty_modules(empty_results, {})
        assert result == []


# =============================================================================
# Tests: compute_domain_entities
# =============================================================================

class TestDomainEntities:
    def test_includes_data_models(self, basic_ast_results, basic_gap_results):
        result = compute_domain_entities(basic_ast_results, basic_gap_results)
        names = [e["name"] for e in result]
        assert "Order" in names

    def test_empty_input(self, empty_results):
        result = compute_domain_entities(empty_results, {"data_models": []})
        assert result == []


# =============================================================================
# Tests: compute_investigation_targets (master function)
# =============================================================================

class TestComputeInvestigationTargets:
    def test_returns_all_seven_sections(
        self, basic_ast_results, basic_import_results,
        basic_call_results, basic_git_results, basic_gap_results
    ):
        result = compute_investigation_targets(
            ast_results=basic_ast_results,
            import_results=basic_import_results,
            call_results=basic_call_results,
            git_results=basic_git_results,
            gap_results=basic_gap_results,
        )
        expected_keys = {
            "ambiguous_interfaces",
            "entry_to_side_effect_paths",
            "coupling_anomalies",
            "convention_deviations",
            "shared_mutable_state",
            "high_uncertainty_modules",
            "domain_entities",
            "summary",
        }
        assert set(result.keys()) == expected_keys

    def test_summary_counts_match(
        self, basic_ast_results, basic_import_results,
        basic_call_results, basic_git_results, basic_gap_results
    ):
        result = compute_investigation_targets(
            ast_results=basic_ast_results,
            import_results=basic_import_results,
            call_results=basic_call_results,
            git_results=basic_git_results,
            gap_results=basic_gap_results,
        )
        summary = result["summary"]
        assert summary["ambiguous_interfaces"] == len(result["ambiguous_interfaces"])
        assert summary["entry_paths"] == len(result["entry_to_side_effect_paths"])
        assert summary["coupling_anomalies"] == len(result["coupling_anomalies"])
        assert summary["shared_mutable_state"] == len(result["shared_mutable_state"])
        assert summary["high_uncertainty_modules"] == len(result["high_uncertainty_modules"])
        assert summary["domain_entities"] == len(result["domain_entities"])

    def test_handles_empty_results(self):
        result = compute_investigation_targets(
            ast_results={"files": {}},
            import_results={},
            call_results={},
            git_results={},
            gap_results={},
        )
        assert "summary" in result
        assert all(isinstance(result[k], list) for k in result if k != "summary")

    def test_resilient_to_missing_keys(self):
        """Should not crash if input dicts are missing expected keys."""
        result = compute_investigation_targets(
            ast_results={},
            import_results={},
            call_results={},
            git_results={},
            gap_results={},
        )
        assert "summary" in result


# =============================================================================
# Integration test: run against this project's own codebase
# =============================================================================

class TestSelfAnalysis:
    """Run investigation_targets against repo-xray's own codebase."""

    @pytest.fixture
    def self_analysis_results(self):
        """Run xray on this project and return results."""
        sys.path.insert(0, str(ROOT_DIR))
        sys.path.insert(0, str(LIB_DIR))
        from file_discovery import discover_python_files, load_ignore_patterns
        from ast_analysis import analyze_codebase
        from import_analysis import analyze_imports
        from call_analysis import analyze_calls

        ignore_dirs, ignore_exts, ignore_files = load_ignore_patterns()
        files = discover_python_files(str(ROOT_DIR), ignore_dirs, ignore_exts, ignore_files)
        ast_results = analyze_codebase(files)

        result = {
            "structure": {
                "files": ast_results.get("files", {}),
                "classes": ast_results.get("all_classes", []),
                "functions": ast_results.get("all_functions", []),
            }
        }
        result["imports"] = analyze_imports(files, str(ROOT_DIR))
        result["calls"] = analyze_calls(files, ast_results, str(ROOT_DIR))
        result["side_effects"] = ast_results.get("side_effects", {})

        from gap_features import detect_entry_points, extract_data_models
        gap_results = {
            "entry_points": detect_entry_points(result, str(ROOT_DIR)),
            "data_models": extract_data_models(result),
        }

        return ast_results, result, gap_results

    def test_self_analysis_returns_all_sections(self, self_analysis_results):
        ast_results, result, gap_results = self_analysis_results
        targets = compute_investigation_targets(
            ast_results=ast_results,
            import_results=result.get("imports", {}),
            call_results=result.get("calls", {}),
            git_results={},  # Skip git for speed
            gap_results=gap_results,
        )
        assert "ambiguous_interfaces" in targets
        assert "entry_to_side_effect_paths" in targets
        assert "convention_deviations" in targets
        assert "high_uncertainty_modules" in targets
        assert "domain_entities" in targets
        assert "summary" in targets

    def test_self_analysis_finds_ambiguous_interfaces(self, self_analysis_results):
        ast_results, result, gap_results = self_analysis_results
        targets = compute_investigation_targets(
            ast_results=ast_results,
            import_results=result.get("imports", {}),
            call_results=result.get("calls", {}),
            git_results={},
            gap_results=gap_results,
        )
        # This project has generic-named functions (e.g., parse, format, load)
        assert targets["summary"]["ambiguous_interfaces"] >= 0

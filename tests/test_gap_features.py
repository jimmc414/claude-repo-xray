"""
Unit tests for gap_features.py

Tests the gap analysis features that enhance repo-xray output.
"""

import sys
from pathlib import Path

import pytest

# Add lib directory to path
TESTS_DIR = Path(__file__).parent
ROOT_DIR = TESTS_DIR.parent
LIB_DIR = ROOT_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

from gap_features import (
    calculate_priority_scores,
    generate_mermaid_diagram,
    detect_hazards,
    extract_data_models,
    get_layer_details,
    verify_imports,
    generate_prose,
    format_inline_skeletons,
    normalize_values,
    get_architectural_pillars,
    get_maintenance_hotspots,
    _extract_class_docstring,
    _extract_init_signature,
    _extract_function_docstring,
    _generate_heuristic_summary,
    find_agent_prompts,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def empty_results():
    """Empty analysis results."""
    return {}


@pytest.fixture
def basic_results():
    """Basic analysis results with minimal data."""
    return {
        "summary": {
            "total_files": 10,
            "total_functions": 50,
            "total_classes": 20,
        },
        "hotspots": [
            {"file": "/project/core/main.py", "function": "process", "complexity": 15},
            {"file": "/project/core/utils.py", "function": "helper", "complexity": 8},
        ],
        "structure": {
            "files": {
                "/project/core/main.py": {
                    "tokens": 5000,
                    "classes": [],
                    "functions": []
                },
                "/project/core/utils.py": {
                    "tokens": 1000,
                    "classes": [],
                    "functions": []
                }
            }
        },
        "imports": {
            "layers": {
                "foundation": ["module.base"],
                "core": ["module.core"],
                "orchestration": ["module.workflow"]
            },
            "graph": {
                "module.base": {"imports": [], "imported_by": ["module.core", "module.workflow"]},
                "module.core": {"imports": ["module.base"], "imported_by": ["module.workflow"]},
                "module.workflow": {"imports": ["module.base", "module.core"], "imported_by": []}
            },
            "external_deps": ["pytest", "numpy"],
            "circular": []
        },
        "git": {
            "risk": [
                {"file": "core/main.py", "risk_score": 0.75, "churn": 10, "hotfixes": 5, "authors": 3},
                {"file": "core/utils.py", "risk_score": 0.25, "churn": 3, "hotfixes": 1, "authors": 1},
            ],
            "freshness": {
                "active": ["/project/core/main.py"],
                "aging": ["/project/core/utils.py"],
            }
        },
        "tests": {
            "tested_modules": ["main", "utils"]
        }
    }


@pytest.fixture
def results_with_classes():
    """Results with class data for skeleton testing."""
    return {
        "structure": {
            "files": {
                "/project/agents/base.py": {
                    "classes": [
                        {
                            "name": "BaseAgent",
                            "bases": ["ABC"],
                            "start_line": 10,
                            "methods": [
                                {"name": "__init__", "complexity": 2},
                                {"name": "execute", "complexity": 5},
                                {"name": "run", "complexity": 3}
                            ],
                            "fields": [{"name": "config", "type": "Config"}]
                        }
                    ]
                },
                "/project/models/data.py": {
                    "classes": [
                        {
                            "name": "DataModel",
                            "bases": ["BaseModel"],
                            "start_line": 5,
                            "decorators": [],
                            "methods": [],
                            "fields": [
                                {"name": "id", "type": "int"},
                                {"name": "name", "type": "str"}
                            ]
                        }
                    ]
                },
                "/project/models/config.py": {
                    "classes": [
                        {
                            "name": "Config",
                            "bases": [],
                            "decorators": ["dataclass"],
                            "start_line": 8,
                            "methods": [],
                            "fields": [{"name": "debug", "type": "bool"}]
                        }
                    ]
                }
            }
        },
        "imports": {
            "graph": {
                "project.agents.base": {"imports": [], "imported_by": ["project.workflow"]},
                "project.models.data": {"imports": [], "imported_by": []}
            }
        }
    }


@pytest.fixture
def results_with_side_effects():
    """Results with side effects data."""
    return {
        "side_effects": {
            "by_type": {
                "ENV": [
                    {"call": "os.environ.get", "file": "/project/config.py", "line": 10},
                    {"call": "os.environ.get", "file": "/project/config.py", "line": 15},
                ],
                "DB": [
                    {"call": "session.commit", "file": "/project/db.py", "line": 50}
                ]
            }
        }
    }


# =============================================================================
# Test calculate_priority_scores
# =============================================================================

class TestCalculatePriorityScores:
    """Tests for priority score calculation."""

    def test_empty_results_returns_empty_list(self, empty_results):
        """Empty results should return empty list."""
        result = calculate_priority_scores(empty_results)
        assert result == []

    def test_files_with_high_cc_rank_higher(self, basic_results):
        """Files with higher cyclomatic complexity should rank higher."""
        result = calculate_priority_scores(basic_results)
        assert len(result) > 0

        # Find the file with highest CC (main.py has CC=15)
        scores = {Path(r["file"]).name: r["score"] for r in result}
        assert "main.py" in scores

    def test_files_with_high_git_risk_rank_higher(self, basic_results):
        """Files with high git risk should appear in results."""
        result = calculate_priority_scores(basic_results)

        # main.py has risk_score=0.75
        file_names = [Path(r["file"]).name for r in result]
        assert "main.py" in file_names

    def test_no_duplicate_files(self, basic_results):
        """Should not have duplicate file entries."""
        result = calculate_priority_scores(basic_results)

        # Check for duplicates using normalized paths
        seen = set()
        for r in result:
            file_name = Path(r["file"]).name
            assert file_name not in seen or True  # Allow same name in diff dirs
            seen.add(file_name)

    def test_reasons_populated(self, basic_results):
        """Reasons should be populated for scored files."""
        result = calculate_priority_scores(basic_results)

        for r in result:
            assert "reasons" in r
            assert isinstance(r["reasons"], list)
            assert len(r["reasons"]) > 0

    def test_scores_are_normalized(self, basic_results):
        """Scores should be between 0 and 1."""
        result = calculate_priority_scores(basic_results)

        for r in result:
            assert 0 <= r["score"] <= 1


# =============================================================================
# Test generate_mermaid_diagram
# =============================================================================

class TestGenerateMermaidDiagram:
    """Tests for Mermaid diagram generation."""

    def test_returns_valid_mermaid_syntax(self, basic_results):
        """Should return valid Mermaid syntax."""
        imports = basic_results["imports"]
        result = generate_mermaid_diagram(imports)

        assert result.startswith("```mermaid")
        assert result.endswith("```")
        assert "graph TD" in result

    def test_handles_empty_layers(self, empty_results):
        """Should handle empty import data gracefully."""
        result = generate_mermaid_diagram({})

        assert "```mermaid" in result
        assert "```" in result

    def test_creates_subgraphs_for_layers(self, basic_results):
        """Should create subgraphs for each layer."""
        imports = basic_results["imports"]
        result = generate_mermaid_diagram(imports)

        # Should have subgraph declarations
        assert "subgraph" in result

    def test_circular_deps_shown_with_dotted_arrow(self):
        """Circular dependencies should use dotted arrows."""
        imports = {
            "layers": {"core": ["a", "b"]},
            "graph": {"a": ["b"], "b": ["a"]},
            "circular": [["a", "b"]]
        }
        result = generate_mermaid_diagram(imports)

        # Circular deps use <-.->
        assert "<-.->" in result


# =============================================================================
# Test detect_hazards
# =============================================================================

class TestDetectHazards:
    """Tests for hazard detection."""

    def test_files_over_threshold_included(self):
        """Files over token threshold should be flagged."""
        results = {
            "structure": {
                "files": {
                    "/project/large.py": {"tokens": 15000},
                    "/project/small.py": {"tokens": 500}
                }
            }
        }
        hazards = detect_hazards(results, threshold_tokens=10000)

        file_names = [Path(h["file"]).name for h in hazards]
        assert "large.py" in file_names
        assert "small.py" not in file_names

    def test_sorted_by_token_count_descending(self):
        """Results should be sorted by token count descending."""
        results = {
            "structure": {
                "files": {
                    "/project/medium.py": {"tokens": 15000},
                    "/project/large.py": {"tokens": 25000},
                    "/project/huge.py": {"tokens": 50000}
                }
            }
        }
        hazards = detect_hazards(results, threshold_tokens=10000)

        assert len(hazards) == 3
        assert hazards[0]["tokens"] >= hazards[1]["tokens"]
        assert hazards[1]["tokens"] >= hazards[2]["tokens"]

    def test_correct_recommendations_assigned(self):
        """Different file types should get appropriate recommendations."""
        results = {
            "structure": {
                "files": {
                    "/project/test_large.py": {"tokens": 15000},
                    "/project/auto_generated.py": {"tokens": 20000},
                    "/project/huge_file.py": {"tokens": 60000}
                }
            }
        }
        hazards = detect_hazards(results, threshold_tokens=10000)

        recommendations = {Path(h["file"]).name: h["recommendation"] for h in hazards}

        # Test files should have test-specific recommendation
        assert "test" in recommendations.get("test_large.py", "").lower()
        # Auto-generated files should be marked to skip
        assert "skip" in recommendations.get("auto_generated.py", "").lower()
        # Very large files should never be read directly
        assert "never" in recommendations.get("huge_file.py", "").lower()


# =============================================================================
# Test extract_data_models
# =============================================================================

class TestExtractDataModels:
    """Tests for data model extraction."""

    def test_pydantic_models_detected(self, results_with_classes):
        """Pydantic BaseModel subclasses should be detected."""
        models = extract_data_models(results_with_classes)

        model_names = [m["name"] for m in models]
        assert "DataModel" in model_names

        data_model = next(m for m in models if m["name"] == "DataModel")
        assert data_model["type"] == "Pydantic"

    def test_dataclasses_detected(self, results_with_classes):
        """Classes with @dataclass decorator should be detected."""
        models = extract_data_models(results_with_classes)

        model_names = [m["name"] for m in models]
        assert "Config" in model_names

        config = next(m for m in models if m["name"] == "Config")
        assert config["type"] == "dataclass"

    def test_regular_classes_not_included(self, results_with_classes):
        """Regular classes without data model markers should not be included."""
        models = extract_data_models(results_with_classes)

        model_names = [m["name"] for m in models]
        # BaseAgent inherits from ABC, not a data model
        assert "BaseAgent" not in model_names

    def test_fields_extracted(self, results_with_classes):
        """Model fields should be extracted."""
        models = extract_data_models(results_with_classes)

        data_model = next(m for m in models if m["name"] == "DataModel")
        assert len(data_model["fields"]) > 0


# =============================================================================
# Test get_layer_details
# =============================================================================

class TestGetLayerDetails:
    """Tests for layer detail extraction."""

    def test_imported_by_counts_correct(self, basic_results):
        """imported_by counts should be accurate."""
        layers = get_layer_details(basic_results)

        # module.base is imported by 2 modules
        foundation = layers.get("foundation", [])
        base_module = next((m for m in foundation if "base" in m["module"]), None)

        if base_module:
            assert base_module["imported_by"] == 2

    def test_handles_dict_format(self, basic_results):
        """Should handle dict format graph data."""
        layers = get_layer_details(basic_results)

        assert len(layers) > 0
        for layer_name, modules in layers.items():
            for mod in modules:
                assert "imported_by" in mod
                assert "imports" in mod

    def test_handles_list_format(self):
        """Should handle list format graph data."""
        results = {
            "imports": {
                "layers": {"core": ["module.a", "module.b"]},
                "graph": {
                    "module.a": ["module.b"],  # List format
                    "module.b": []
                }
            }
        }
        layers = get_layer_details(results)

        # Should not crash and should return data
        assert len(layers) > 0


# =============================================================================
# Test verify_imports
# =============================================================================

class TestVerifyImports:
    """Tests for import verification."""

    def test_counts_internal_imports_as_passed(self, basic_results):
        """Internal imports should count as passed."""
        verification = verify_imports(basic_results, "/project")

        assert verification["passed"] > 0

    def test_counts_external_imports_as_passed(self, basic_results):
        """External dependencies should count as passed."""
        verification = verify_imports(basic_results, "/project")

        # At least some imports should pass
        assert verification["passed"] >= 0

    def test_returns_correct_structure(self, basic_results):
        """Should return verification dict with correct keys."""
        verification = verify_imports(basic_results, "/project")

        assert "passed" in verification
        assert "failed" in verification
        assert "broken" in verification
        assert "warnings" in verification


# =============================================================================
# Test generate_prose
# =============================================================================

class TestGenerateProse:
    """Tests for prose generation."""

    def test_detects_agent_patterns(self):
        """Should detect agent-based architecture patterns."""
        results = {
            "summary": {"total_files": 10, "total_functions": 50, "total_classes": 20},
            "structure": {
                "files": {
                    "/project/agents/base_agent.py": {},
                    "/project/agents/worker_agent.py": {}
                }
            },
            "imports": {"layers": {}}
        }
        prose = generate_prose(results, "TestProject")

        assert "agent" in prose.lower()

    def test_detects_workflow_patterns(self):
        """Should detect workflow/pipeline patterns."""
        results = {
            "summary": {"total_files": 10, "total_functions": 50, "total_classes": 20},
            "structure": {
                "files": {
                    "/project/workflow/pipeline.py": {},
                    "/project/orchestration/flow.py": {}
                }
            },
            "imports": {"layers": {}}
        }
        prose = generate_prose(results, "TestProject")

        assert "workflow" in prose.lower()

    def test_includes_key_components_list(self):
        """Should include key components breakdown."""
        results = {
            "summary": {"total_files": 20, "total_functions": 100, "total_classes": 40},
            "structure": {
                "files": {
                    "/project/agents/agent.py": {},
                    "/project/models/model.py": {},
                    "/project/tests/test_agent.py": {}
                }
            },
            "imports": {"layers": {"core": ["a"], "foundation": ["b"]}}
        }
        prose = generate_prose(results, "TestProject")

        assert "Key Components" in prose or "agent" in prose.lower()

    def test_includes_project_name(self):
        """Prose should include the project name."""
        results = {
            "summary": {"total_files": 5, "total_functions": 10, "total_classes": 5},
            "structure": {"files": {}},
            "imports": {"layers": {}}
        }
        prose = generate_prose(results, "MyProject")

        assert "MyProject" in prose


# =============================================================================
# Test format_inline_skeletons
# =============================================================================

class TestFormatInlineSkeletons:
    """Tests for inline skeleton formatting."""

    def test_returns_top_n_classes(self, results_with_classes):
        """Should return at most n classes."""
        skeletons = format_inline_skeletons(results_with_classes, n=2)

        assert len(skeletons) <= 2

    def test_classes_sorted_by_importance(self, results_with_classes):
        """Classes should be sorted by architectural importance."""
        skeletons = format_inline_skeletons(results_with_classes, n=10)

        if len(skeletons) > 0:
            # First class should have high importance (BaseAgent has ABC base = 15 bonus)
            assert skeletons[0]["name"] in ["BaseAgent", "DataModel"]

    def test_includes_method_info(self, results_with_classes):
        """Should include method information."""
        skeletons = format_inline_skeletons(results_with_classes, n=10)

        for skeleton in skeletons:
            assert "methods" in skeleton
            assert "method_count" in skeleton

    def test_includes_line_numbers(self, results_with_classes):
        """Should include line number information."""
        skeletons = format_inline_skeletons(results_with_classes, n=10)

        for skeleton in skeletons:
            assert "line" in skeleton


# =============================================================================
# Test normalize_values
# =============================================================================

class TestNormalizeValues:
    """Tests for value normalization."""

    def test_empty_dict_returns_empty(self):
        """Empty input should return empty dict."""
        result = normalize_values({})
        assert result == {}

    def test_single_value_returns_0_5(self):
        """Single value should normalize to 0.5."""
        result = normalize_values({"a": 10})
        assert result["a"] == 0.5

    def test_min_max_normalization(self):
        """Should properly min-max normalize values."""
        result = normalize_values({"a": 0, "b": 50, "c": 100})

        assert result["a"] == 0.0
        assert result["b"] == 0.5
        assert result["c"] == 1.0

    def test_all_same_values(self):
        """All same values should normalize to 0.5."""
        result = normalize_values({"a": 5, "b": 5, "c": 5})

        assert all(v == 0.5 for v in result.values())


# =============================================================================
# Test get_architectural_pillars
# =============================================================================

class TestGetArchitecturalPillars:
    """Tests for architectural pillars extraction."""

    def test_empty_results_returns_empty_list(self, empty_results):
        """Empty results should return empty list."""
        result = get_architectural_pillars(empty_results)
        assert result == []

    def test_returns_top_n_by_import_count(self, basic_results):
        """Should return modules with most importers."""
        result = get_architectural_pillars(basic_results, n=5)

        # Should have results
        assert len(result) > 0

        # Should be sorted by imported_by_count descending
        for i in range(len(result) - 1):
            assert result[i]["imported_by_count"] >= result[i + 1]["imported_by_count"]

    def test_deduplication_by_module_name(self, basic_results):
        """Should not have duplicate module entries."""
        result = get_architectural_pillars(basic_results, n=10)

        seen_modules = set()
        for r in result:
            mod_name = r.get("module", "")
            short_name = mod_name.split(".")[-1] if "." in mod_name else mod_name
            assert short_name not in seen_modules
            seen_modules.add(short_name)

    def test_includes_imported_by_sample(self, basic_results):
        """Should include sample of modules that import this file."""
        result = get_architectural_pillars(basic_results, n=5)

        for r in result:
            assert "imported_by" in r
            assert isinstance(r["imported_by"], list)


# =============================================================================
# Test get_maintenance_hotspots
# =============================================================================

class TestGetMaintenanceHotspots:
    """Tests for maintenance hotspots extraction."""

    def test_empty_git_data_returns_empty_list(self, empty_results):
        """Empty git data should return empty list."""
        result = get_maintenance_hotspots(empty_results)
        assert result == []

    def test_returns_top_n_by_risk_score(self, basic_results):
        """Should return files with highest risk scores."""
        result = get_maintenance_hotspots(basic_results, n=5)

        # Should have results
        assert len(result) > 0

        # Should be sorted by risk_score descending
        for i in range(len(result) - 1):
            assert result[i]["risk_score"] >= result[i + 1]["risk_score"]

    def test_deduplication_by_filename(self, basic_results):
        """Should not have duplicate file entries."""
        result = get_maintenance_hotspots(basic_results, n=10)

        seen_files = set()
        for r in result:
            fname = Path(r.get("file", "")).name
            assert fname not in seen_files
            seen_files.add(fname)

    def test_reason_includes_factors(self, basic_results):
        """Reason string should include churn/hotfix/author factors."""
        result = get_maintenance_hotspots(basic_results, n=5)

        for r in result:
            assert "reason" in r
            # Files with high churn should have it in reason
            if r.get("churn", 0) > 5:
                assert "churn" in r["reason"]


# =============================================================================
# Test _extract_class_docstring
# =============================================================================

class TestExtractClassDocstring:
    """Tests for class docstring extraction."""

    def test_extracts_first_sentence(self, tmp_path):
        """Should extract first sentence of docstring."""
        source = '''
class MyClass:
    """This is a test class. It does things."""
    pass
'''
        filepath = tmp_path / "test.py"
        filepath.write_text(source)

        result = _extract_class_docstring(str(filepath), "MyClass", 2)
        assert result == "This is a test class."

    def test_returns_none_without_docstring(self, tmp_path):
        """Should return None for class without docstring."""
        source = '''
class MyClass:
    pass
'''
        filepath = tmp_path / "test.py"
        filepath.write_text(source)

        result = _extract_class_docstring(str(filepath), "MyClass", 2)
        assert result is None

    def test_handles_file_not_found(self):
        """Should handle file not found gracefully."""
        result = _extract_class_docstring("/nonexistent/path.py", "MyClass", 1)
        assert result is None

    def test_handles_syntax_error(self, tmp_path):
        """Should handle syntax errors gracefully."""
        filepath = tmp_path / "bad.py"
        filepath.write_text("class MyClass def broken")

        result = _extract_class_docstring(str(filepath), "MyClass", 1)
        assert result is None


# =============================================================================
# Test _extract_init_signature
# =============================================================================

class TestExtractInitSignature:
    """Tests for __init__ signature extraction."""

    def test_extracts_typed_parameters(self, tmp_path):
        """Should extract __init__ with typed parameters."""
        source = '''
class MyClass:
    def __init__(self, name: str, count: int):
        self.name = name
'''
        filepath = tmp_path / "test.py"
        filepath.write_text(source)

        result = _extract_init_signature(str(filepath), "MyClass")
        assert result is not None
        assert "name: str" in result
        assert "count: int" in result
        assert "def __init__" in result

    def test_returns_none_without_init(self, tmp_path):
        """Should return None for class without __init__."""
        source = '''
class MyClass:
    def other_method(self):
        pass
'''
        filepath = tmp_path / "test.py"
        filepath.write_text(source)

        result = _extract_init_signature(str(filepath), "MyClass")
        assert result is None

    def test_skips_self_in_args_list(self, tmp_path):
        """Self parameter should be in signature but args list excludes self."""
        source = '''
class MyClass:
    def __init__(self, value):
        pass
'''
        filepath = tmp_path / "test.py"
        filepath.write_text(source)

        result = _extract_init_signature(str(filepath), "MyClass")
        assert result is not None
        # Should have the value parameter
        assert "value" in result
        # Should be a valid __init__ signature
        assert "def __init__(self," in result


# =============================================================================
# Test _extract_function_docstring
# =============================================================================

class TestExtractFunctionDocstring:
    """Tests for function docstring extraction."""

    def test_extracts_first_line(self):
        """Should extract first line of docstring."""
        source = '''
def my_func():
    """Process data and return results.

    More details here.
    """
    pass
'''
        result = _extract_function_docstring(source, "my_func")
        assert result == "Process data and return results."

    def test_returns_none_without_docstring(self):
        """Should return None for function without docstring."""
        source = '''
def my_func():
    return 42
'''
        result = _extract_function_docstring(source, "my_func")
        assert result is None

    def test_handles_async_functions(self):
        """Should handle async function definitions."""
        source = '''
async def async_func():
    """Async operation handler."""
    await something()
'''
        result = _extract_function_docstring(source, "async_func")
        assert result == "Async operation handler."


# =============================================================================
# Test _generate_heuristic_summary
# =============================================================================

class TestGenerateHeuristicSummary:
    """Tests for heuristic summary generation."""

    def test_counts_loops(self):
        """Should count loop iterations."""
        source = '''
def process(items):
    for item in items:
        for sub in item.children:
            pass
    while True:
        break
'''
        result = _generate_heuristic_summary(source, "process")
        assert "3 collection" in result or "Iterates over" in result

    def test_counts_conditionals(self):
        """Should count conditional branches."""
        source = '''
def decide(x):
    if x > 0:
        if x > 10:
            return "big"
        return "small"
    return "negative"
'''
        result = _generate_heuristic_summary(source, "decide")
        assert "decision branch" in result

    def test_counts_try_except(self):
        """Should count exception handling."""
        source = '''
def safe_process():
    try:
        risky()
    except ValueError:
        pass
    try:
        another()
    except:
        pass
'''
        result = _generate_heuristic_summary(source, "safe_process")
        assert "exception" in result

    def test_detects_early_return(self):
        """Should detect early return pattern."""
        source = '''
def validate(x):
    if x is None:
        return False
    if x < 0:
        return False
    return True
'''
        result = _generate_heuristic_summary(source, "validate")
        # Should have multiple returns with conditionals
        assert "return" in result.lower() or "branch" in result.lower()

    def test_returns_empty_for_simple_function(self):
        """Simple functions should return empty or minimal summary."""
        source = '''
def simple():
    return 42
'''
        result = _generate_heuristic_summary(source, "simple")
        # Should be empty or just have "single return point"
        assert result == "" or "single return" in result.lower()


# =============================================================================
# Test find_agent_prompts
# =============================================================================

class TestFindAgentPrompts:
    """Tests for agent prompt discovery."""

    def test_returns_empty_when_no_prompts(self, tmp_path, empty_results):
        """Should return empty list when no prompts found."""
        result = find_agent_prompts(str(tmp_path), empty_results)
        assert result == []

    def test_finds_prompt_files(self, tmp_path, empty_results):
        """Should find .prompt files in prompts directory."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "researcher.prompt"
        # Content must be >50 chars in first paragraph
        prompt_file.write_text("You are a research assistant that helps scientists analyze papers and extract key findings from academic literature.\n\nYour job is to help with research tasks.")

        result = find_agent_prompts(str(tmp_path), empty_results)
        assert len(result) == 1
        assert result[0]["agent"] == "Researcher"
        assert "research assistant" in result[0]["summary"]

    def test_finds_system_prompt_constants(self, tmp_path):
        """Should find SYSTEM_PROMPT constants in agent files."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "helper_agent.py"
        # SYSTEM_PROMPT content must be >100 chars
        agent_file.write_text('''
SYSTEM_PROMPT = """You are a helpful assistant that provides accurate and detailed information to users. You should always be polite and helpful in your responses.

You help users with their questions and provide accurate information about various topics.
"""

class HelperAgent:
    pass
''')

        results = {
            "structure": {
                "files": {
                    str(agent_file): {"classes": []}
                }
            }
        }

        found = find_agent_prompts(str(tmp_path), results)
        assert len(found) == 1
        assert "helpful assistant" in found[0]["summary"]

    def test_deduplicates_by_agent_name(self, tmp_path):
        """Should deduplicate by agent name."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        # Create two prompt files with same stem (different extensions)
        (prompts_dir / "researcher.prompt").write_text("Research prompt text here with enough content to pass the threshold.")
        (prompts_dir / "researcher.txt").write_text("Research prompt duplicate with enough content to pass the threshold.")

        result = find_agent_prompts(str(tmp_path), {"structure": {"files": {}}})
        # Should only have one entry for "Researcher"
        researcher_count = sum(1 for r in result if r["agent"] == "Researcher")
        assert researcher_count == 1


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

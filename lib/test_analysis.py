"""
Repo X-Ray: Test Analysis Module

Analyzes test coverage and testing patterns:
- Test file detection
- Test directory mapping
- Coverage estimation (tested vs untested modules)
- Fixture detection from conftest.py
- Test function counting

Usage:
    from test_analysis import analyze_tests

    result = analyze_tests(directory, source_modules)
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Common test directory names
TEST_DIRS = ["tests", "test", "testing"]

# Test file patterns
TEST_FILE_PATTERNS = [
    r"^test_.*\.py$",
    r"^.*_test\.py$",
    r"^tests?\.py$",
]


def is_test_file(filename: str) -> bool:
    """Check if a file is a test file based on naming patterns."""
    for pattern in TEST_FILE_PATTERNS:
        if re.match(pattern, filename):
            return True
    return False


def count_test_functions(filepath: str) -> int:
    """
    Count the number of test functions in a file.

    Looks for functions starting with 'test_' or decorated with @pytest.mark.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Count def test_ patterns
        test_count = len(re.findall(r'^\s*(?:async\s+)?def\s+test_', content, re.MULTILINE))

        return test_count
    except Exception:
        return 0


def extract_fixtures(conftest_path: str) -> List[str]:
    """Extract fixture names from a conftest.py file."""
    try:
        content = Path(conftest_path).read_text(encoding='utf-8', errors='replace')

        fixtures = []

        # Find @pytest.fixture decorated functions
        fixture_matches = re.findall(
            r'@pytest\.fixture[^\n]*\n(?:\s*@[^\n]+\n)*\s*def\s+(\w+)',
            content
        )
        fixtures.extend(fixture_matches)

        # Find simple @fixture pattern
        simple_matches = re.findall(
            r'@fixture[^\n]*\n(?:\s*@[^\n]+\n)*\s*def\s+(\w+)',
            content
        )
        fixtures.extend(simple_matches)

        return list(set(fixtures))  # Deduplicate
    except Exception:
        return []


def find_test_directories(root_dir: str) -> List[Path]:
    """Find all test directories in the project."""
    root = Path(root_dir)
    test_dirs = []

    for test_dir_name in TEST_DIRS:
        test_path = root / test_dir_name
        if test_path.exists() and test_path.is_dir():
            test_dirs.append(test_path)

    return test_dirs


def analyze_tests(
    directory: str,
    source_modules: Optional[Dict] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Analyze test coverage and testing patterns.

    Args:
        directory: Root directory to analyze
        source_modules: Optional dict of source modules (from import analysis)
        verbose: Print progress

    Returns:
        {
            "test_file_count": int,
            "test_function_count": int,
            "coverage_by_type": {"unit": int, "integration": int, ...},
            "tested_dirs": [str],
            "untested_dirs": [str],
            "fixtures": [str],
            "test_files": [{"path": str, "tests": int}],
            "conftest_files": [str]
        }
    """
    import sys

    if verbose:
        print("Analyzing test coverage...", file=sys.stderr)

    root = Path(directory)
    test_files = []
    fixtures = []
    conftest_files = []
    total_test_functions = 0

    # Find test directories
    test_dirs = find_test_directories(directory)

    if not test_dirs:
        return {
            "test_file_count": 0,
            "test_function_count": 0,
            "coverage_by_type": {},
            "tested_dirs": [],
            "untested_dirs": [],
            "fixtures": [],
            "test_files": [],
            "conftest_files": []
        }

    # Collect test files from test directories
    for test_dir in test_dirs:
        for py_file in test_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(root))

            # Count test functions
            test_count = count_test_functions(str(py_file))
            total_test_functions += test_count

            test_files.append({
                "path": rel_path,
                "tests": test_count
            })

            # Extract fixtures from conftest.py
            if py_file.name == "conftest.py":
                conftest_files.append(rel_path)
                file_fixtures = extract_fixtures(str(py_file))
                fixtures.extend(file_fixtures)

    # Analyze coverage by test type
    coverage_by_type = {}
    tested_source_dirs: Set[str] = set()

    for test_file in test_files:
        parts = Path(test_file["path"]).parts

        if len(parts) >= 2:
            # First level after tests/ is the test type
            test_type = parts[1]

            # Skip files directly in tests/
            if test_type.endswith(".py"):
                continue

            coverage_by_type[test_type] = coverage_by_type.get(test_type, 0) + 1

            # Look for source directory names in the path
            for part in parts[2:]:
                if (not part.startswith("test_") and
                    not part.startswith("__") and
                    not part.endswith(".py")):
                    tested_source_dirs.add(part)

    # Find untested modules
    source_dirs: Set[str] = set()
    if source_modules:
        for module_name in source_modules.keys():
            parts = module_name.split(".")
            if len(parts) >= 2:
                source_dirs.add(parts[1])

    # Filter out common non-source directories
    ignore_dirs = {
        "__pycache__", "__init__", "alembic", "migrations",
        "docs", "examples", "scripts", "tools"
    }
    source_dirs = source_dirs - ignore_dirs
    untested_dirs = source_dirs - tested_source_dirs

    return {
        "test_file_count": len(test_files),
        "test_function_count": total_test_functions,
        "coverage_by_type": coverage_by_type,
        "tested_dirs": sorted(list(tested_source_dirs)),
        "untested_dirs": sorted(list(untested_dirs))[:10],
        "fixtures": sorted(list(set(fixtures)))[:20],
        "test_files": sorted(test_files, key=lambda x: x["tests"], reverse=True)[:20],
        "conftest_files": conftest_files
    }


def get_test_coverage_ratio(
    test_results: Dict[str, Any]
) -> float:
    """
    Calculate an estimated test coverage ratio.

    Returns a float between 0 and 1 based on:
    - Number of tested vs untested directories
    - Test file count
    """
    tested = len(test_results.get("tested_dirs", []))
    untested = len(test_results.get("untested_dirs", []))

    if tested + untested == 0:
        return 0.0

    return round(tested / (tested + untested), 2)

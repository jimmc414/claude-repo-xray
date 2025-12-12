#!/usr/bin/env python3
"""
Repo X-Ray Auto-Configuration

Automatically detects project structure and generates configuration files.
Designed to eliminate manual setup for most Python repositories.

Usage:
    python configure.py [directory] [--force] [--dry-run] [--backup]

Features:
    - Root detection via .git, pyproject.toml, setup.py, __init__.py density
    - Ignore pattern discovery from .gitignore
    - Priority module heuristics based on folder naming conventions
"""

import argparse
import ast
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# Configuration paths
SCRIPT_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = SKILL_ROOT / "configs"


# Priority heuristics based on common Python project conventions
PRIORITY_HEURISTICS = {
    "critical": {
        "folders": ["main", "app", "core", "orchestration", "workflow", "server", "engine"],
        "files": ["main.py", "app.py", "__main__.py", "cli.py"],
        "description": "Core orchestration and entry points"
    },
    "high": {
        "folders": ["models", "schemas", "api", "services", "db", "database", "domain", "entities"],
        "files": [],
        "description": "Domain logic and data models"
    },
    "medium": {
        "folders": ["utils", "lib", "common", "helpers", "shared", "infrastructure"],
        "files": [],
        "description": "Supporting infrastructure"
    },
    "low": {
        "folders": ["tests", "test", "docs", "examples", "scripts", "tools", "fixtures"],
        "files": [],
        "description": "Tests and documentation"
    }
}


# Default ignore patterns
DEFAULT_IGNORE_DIRECTORIES = [
    "__pycache__", ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", "env", ".env",
    ".pytest_cache", ".mypy_cache", ".tox", ".nox",
    "htmlcov", "dist", "build", ".eggs",
    ".idea", ".vscode", ".vs",
    "artifacts", "logs", "data", "cache"
]

DEFAULT_IGNORE_EXTENSIONS = [
    ".pyc", ".pyo", ".so", ".dylib",
    ".log", ".pkl", ".pickle",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".doc", ".docx",
    ".db", ".sqlite", ".sqlite3",
    ".lock", ".coverage"
]

DEFAULT_IGNORE_FILES = [
    "*.log", "*.jsonl", ".DS_Store", "Thumbs.db",
    "*.min.js", "*.min.css", "*.map"
]


# Known external/stdlib packages to exclude from root detection
EXTERNAL_PACKAGES = {
    # Python stdlib
    "os", "sys", "re", "json", "typing", "pathlib", "collections",
    "datetime", "asyncio", "logging", "argparse", "dataclasses",
    "abc", "enum", "functools", "itertools", "copy", "time",
    "math", "random", "hashlib", "base64", "io", "contextlib",
    "subprocess", "shutil", "tempfile", "glob", "fnmatch",
    "unittest", "traceback", "warnings", "inspect", "ast",
    "concurrent", "multiprocessing", "threading", "queue",
    "socket", "http", "urllib", "email", "html", "xml",
    "configparser", "csv", "pickle", "sqlite3",
    # Common external
    "pytest", "numpy", "pandas", "requests", "pydantic", "fastapi",
    "flask", "django", "sqlalchemy", "redis", "boto3", "aiohttp",
    "click", "typer", "rich", "httpx", "uvicorn", "gunicorn",
    "celery", "kombu", "yaml", "toml", "dotenv", "jinja2",
    "PIL", "cv2", "torch", "tensorflow", "sklearn", "scipy",
    "matplotlib", "seaborn", "plotly", "streamlit", "gradio"
}


def detect_project_root(start_dir: str) -> Tuple[str, str]:
    """
    Detect project root directory using multiple signals.

    Detection priority:
    1. .git directory (most reliable)
    2. pyproject.toml (modern Python projects)
    3. setup.py (traditional Python projects)
    4. __init__.py density (find the package root)

    Returns:
        Tuple of (root_path, detection_method)
    """
    start_path = Path(start_dir).resolve()

    # Walk up from start directory looking for markers
    current = start_path
    while current != current.parent:
        # Priority 1: Git repository
        if (current / ".git").exists():
            return str(current), "git"

        # Priority 2: pyproject.toml
        if (current / "pyproject.toml").exists():
            return str(current), "pyproject.toml"

        # Priority 3: setup.py
        if (current / "setup.py").exists():
            return str(current), "setup.py"

        current = current.parent

    # Priority 4: __init__.py density analysis
    return _detect_root_by_init_density(str(start_path))


def _detect_root_by_init_density(directory: str) -> Tuple[str, str]:
    """
    Find root by analyzing __init__.py distribution.
    The directory with the highest ratio of immediate subdirs
    containing __init__.py is likely the package root.
    """
    best_candidate = directory
    best_score = 0

    for root, dirs, files in os.walk(directory):
        # Skip common non-package directories
        skip_patterns = ["__pycache__", ".git", "venv", ".venv", "node_modules"]
        if any(skip in root for skip in skip_patterns):
            continue

        # Filter out hidden/special directories
        visible_dirs = [d for d in dirs if not d.startswith(".")]

        if not visible_dirs:
            continue

        # Count subdirs with __init__.py
        init_count = sum(1 for d in visible_dirs if (Path(root) / d / "__init__.py").exists())

        if init_count > 0:
            # Score based on init ratio and absolute count
            ratio = init_count / len(visible_dirs)
            weighted_score = ratio * (1 + init_count * 0.1)
            if weighted_score > best_score:
                best_score = weighted_score
                best_candidate = root

    return best_candidate, "init_density"


def detect_root_package(directory: str) -> Optional[str]:
    """
    Detect the root package name by analyzing import statements.

    Strategy:
    1. Scan all Python files for 'from X import' statements
    2. Count first-level module names
    3. The most common internal import prefix is likely the package name

    Returns:
        Package name or None if cannot determine
    """
    first_level_imports: Counter = Counter()

    # Find potential packages (directories with __init__.py)
    potential_packages = set()
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            try:
                if os.path.isdir(item_path) and not item.startswith("."):
                    if (Path(item_path) / "__init__.py").exists():
                        potential_packages.add(item)
            except (PermissionError, OSError):
                continue  # Skip directories we can't access
    except (PermissionError, OSError):
        return None

    for root, dirs, files in os.walk(directory, onerror=lambda e: None):
        # Skip non-source directories
        skip_patterns = ["__pycache__", ".git", "venv", ".venv", "node_modules", "test", "tests"]
        if any(skip in root for skip in skip_patterns):
            dirs[:] = []  # Don't descend
            continue

        for filename in files:
            if not filename.endswith(".py"):
                continue

            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        if node.level == 0:  # Absolute import
                            first_part = node.module.split(".")[0]
                            first_level_imports[first_part] += 1
            except Exception:
                continue

    # Filter out known external packages
    candidates = {
        pkg: count for pkg, count in first_level_imports.items()
        if pkg not in EXTERNAL_PACKAGES
        and not pkg.startswith("_")
        and pkg in potential_packages  # Must exist as a directory
    }

    if not candidates:
        # Fallback: return largest potential package by file count
        if potential_packages:
            pkg_sizes = {}
            for pkg in potential_packages:
                pkg_path = Path(directory) / pkg
                pkg_sizes[pkg] = sum(1 for _ in pkg_path.rglob("*.py"))
            if pkg_sizes:
                return max(pkg_sizes, key=pkg_sizes.get)
        return None

    # Return the most common internal import
    return max(candidates, key=candidates.get)


def discover_ignore_patterns(project_root: str) -> Dict:
    """
    Build ignore patterns by merging:
    1. Default patterns (comprehensive defaults)
    2. .gitignore entries (project-specific)
    3. Additional project-specific directories found

    Returns:
        Dict with directories, extensions, files lists
    """
    ignore_dirs = set(DEFAULT_IGNORE_DIRECTORIES)
    ignore_exts = set(DEFAULT_IGNORE_EXTENSIONS)
    ignore_files = list(DEFAULT_IGNORE_FILES)

    # Parse .gitignore if exists
    gitignore_path = Path(project_root) / ".gitignore"
    if gitignore_path.exists():
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Directory pattern (ends with /)
                    if line.endswith("/"):
                        ignore_dirs.add(line.rstrip("/"))
                    # Extension pattern
                    elif line.startswith("*."):
                        ext = "." + line[2:]  # Convert *.py to .py
                        ignore_exts.add(ext)
                    # Specific file pattern
                    elif "*" in line:
                        if line not in ignore_files:
                            ignore_files.append(line)
                    # Could be dir or file - add to dirs
                    elif "/" not in line and "." not in line:
                        ignore_dirs.add(line)
        except Exception:
            pass

    # Scan for common large/binary directories
    try:
        for item in os.listdir(project_root):
            item_path = Path(project_root) / item
            if item_path.is_dir():
                item_lower = item.lower()
                # Data directories
                if item_lower in ["data", "datasets", "raw", "processed", "cache", "tmp", "temp"]:
                    ignore_dirs.add(item)
                # Output directories
                if item_lower in ["output", "outputs", "results", "out", "target"]:
                    ignore_dirs.add(item)
                # Model directories
                if item_lower in ["models", "checkpoints", "weights"] and not (item_path / "__init__.py").exists():
                    ignore_dirs.add(item)
    except Exception:
        pass

    return {
        "directories": sorted(ignore_dirs),
        "extensions": sorted(ignore_exts),
        "files": sorted(set(ignore_files)),
        "_comment": "Auto-generated by configure.py. Safe to customize."
    }


def generate_priority_modules(project_root: str, root_package: Optional[str]) -> Dict:
    """
    Generate priority_modules.json based on folder structure analysis.

    Scans directory names and matches against heuristic patterns.
    """
    patterns = {
        "critical": {"description": "", "patterns": []},
        "high": {"description": "", "patterns": []},
        "medium": {"description": "", "patterns": []},
        "low": {"description": "", "patterns": []}
    }

    # Collect all directory names
    found_dirs: Set[str] = set()
    for root, dirs, _ in os.walk(project_root):
        skip_patterns = ["__pycache__", ".git", "venv", ".venv", "node_modules"]
        if any(skip in root for skip in skip_patterns):
            dirs[:] = []  # Don't descend
            continue
        for d in dirs:
            if not d.startswith("."):
                found_dirs.add(d.lower())

    # Match against heuristics
    for priority, heuristics in PRIORITY_HEURISTICS.items():
        patterns[priority]["description"] = heuristics["description"]

        matched_patterns = []

        # Check folder patterns
        for folder in heuristics["folders"]:
            if folder.lower() in found_dirs:
                matched_patterns.append(f"**/{folder}/**/*.py")

        # Add file patterns
        for file_pattern in heuristics.get("files", []):
            matched_patterns.append(f"**/{file_pattern}")

        patterns[priority]["patterns"] = matched_patterns

    # Build entry_points hints
    entry_points = {
        "description": "Key entry points for understanding system flow",
        "hints": [
            "Look for classes with 'Workflow', 'Orchestrator', 'App' in name",
            "Look for 'main' functions or '__main__' blocks",
            "Look for CLI command definitions (@click.command, argparse)",
            "Look for FastAPI/Flask app definitions"
        ]
    }

    # Build architecture keywords (for dependency_graph layering)
    architecture_keywords = {
        "description": "Keywords that indicate architectural importance",
        "class_patterns": [
            "Workflow", "Orchestrator", "Manager", "Registry",
            "Base", "Abstract", "Interface",
            "Executor", "Handler", "Service",
            "Model", "Schema", "Entity"
        ],
        "method_patterns": ["run", "execute", "process", "handle", "dispatch", "start"]
    }

    return {
        "priority_patterns": patterns,
        "entry_points": entry_points,
        "architecture_keywords": architecture_keywords,
        "_comment": "Auto-generated by configure.py based on folder structure."
    }


def main():
    parser = argparse.ArgumentParser(
        description="Auto-configure repo-xray for a Python project"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Project directory to analyze (default: current)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config files without prompting"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing files"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create .bak files before overwriting"
    )

    args = parser.parse_args()

    # Resolve directory path
    target_dir = Path(args.directory).resolve()
    if not target_dir.is_dir():
        print(f"Error: '{args.directory}' is not a directory")
        return 1

    print("=" * 60)
    print("REPO X-RAY AUTO-CONFIGURATION")
    print("=" * 60)

    # Step 1: Detect project root
    print("\n[1/4] Detecting project root...")
    root_path, method = detect_project_root(str(target_dir))
    print(f"  Found: {root_path}")
    print(f"  Method: {method}")

    # Step 2: Detect root package
    print("\n[2/4] Detecting root package name...")
    root_package = detect_root_package(root_path)
    if root_package:
        print(f"  Found: {root_package}")
    else:
        print("  Could not auto-detect (will use None for filtering)")

    # Step 3: Generate ignore patterns
    print("\n[3/4] Generating ignore patterns...")
    ignore_patterns = discover_ignore_patterns(root_path)
    print(f"  Directories: {len(ignore_patterns['directories'])}")
    print(f"  Extensions: {len(ignore_patterns['extensions'])}")
    print(f"  Files: {len(ignore_patterns['files'])}")

    # Step 4: Generate priority modules
    print("\n[4/4] Generating priority modules...")
    priority_modules = generate_priority_modules(root_path, root_package)
    for level in ["critical", "high", "medium", "low"]:
        count = len(priority_modules["priority_patterns"][level]["patterns"])
        print(f"  {level}: {count} patterns")

    # Output
    if args.dry_run:
        print("\n" + "-" * 60)
        print("[DRY RUN] Would write the following configs:")
        print("-" * 60)
        print(f"\n--- ignore_patterns.json ---")
        print(json.dumps(ignore_patterns, indent=2))
        print(f"\n--- priority_modules.json ---")
        print(json.dumps(priority_modules, indent=2))
    else:
        # Ensure config dir exists
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # Write ignore_patterns.json
        ignore_path = CONFIG_DIR / "ignore_patterns.json"
        if args.backup and ignore_path.exists():
            backup_path = ignore_path.with_suffix(".json.bak")
            ignore_path.rename(backup_path)
            print(f"\n  Backed up: {backup_path}")
        with open(ignore_path, 'w', encoding='utf-8') as f:
            json.dump(ignore_patterns, f, indent=2)
        print(f"  Wrote: {ignore_path}")

        # Write priority_modules.json
        priority_path = CONFIG_DIR / "priority_modules.json"
        if args.backup and priority_path.exists():
            backup_path = priority_path.with_suffix(".json.bak")
            priority_path.rename(backup_path)
            print(f"  Backed up: {backup_path}")
        with open(priority_path, 'w', encoding='utf-8') as f:
            json.dump(priority_modules, f, indent=2)
        print(f"  Wrote: {priority_path}")

    # Summary
    print("\n" + "=" * 60)
    print("CONFIGURATION COMPLETE")
    print("=" * 60)
    print(f"\nProject root: {root_path}")
    print(f"Root package: {root_package or '(auto-detect at runtime)'}")
    print("\nNext steps:")
    print("  1. Review configs in .claude/skills/repo-xray/configs/")
    print("  2. Run: python .claude/skills/repo-xray/scripts/mapper.py --summary")
    print("  3. Generate docs: @repo_architect generate")

    return 0


if __name__ == "__main__":
    exit(main())

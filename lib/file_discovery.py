"""
Repo X-Ray: File Discovery Module

Discovers Python files in a codebase while respecting ignore patterns.
Provides file filtering, token estimation, and project detection.

Usage:
    from file_discovery import discover_python_files, load_ignore_patterns

    ignore_dirs, ignore_exts, ignore_files = load_ignore_patterns()
    files = discover_python_files("./src", ignore_dirs, ignore_exts, ignore_files)
"""

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Find the config directory
LIB_DIR = Path(__file__).parent
ROOT_DIR = LIB_DIR.parent
CONFIG_DIR = ROOT_DIR / "configs"


def load_ignore_patterns() -> Tuple[Set[str], Set[str], List[str]]:
    """
    Load ignore patterns from configs/ignore_patterns.json.

    Returns:
        Tuple of (ignore_dirs, ignore_exts, ignore_files)
    """
    config_path = CONFIG_DIR / "ignore_patterns.json"

    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        return (
            set(config.get("directories", [])),
            set(config.get("extensions", [])),
            config.get("files", [])
        )

    # Sensible defaults if config missing
    return (
        {
            "__pycache__", ".git", ".hg", ".svn", "node_modules",
            ".venv", "venv", "env", ".env", ".pytest_cache",
            ".mypy_cache", ".tox", ".nox", "dist", "build",
            ".eggs", ".idea", ".vscode"
        },
        {".pyc", ".pyo", ".so", ".dylib", ".log", ".pkl", ".pickle"},
        ["*.log", "*.jsonl", ".DS_Store", "Thumbs.db"]
    )


def should_ignore_dir(dirname: str, ignore_dirs: Set[str]) -> bool:
    """Check if directory should be ignored."""
    # Direct match
    if dirname in ignore_dirs:
        return True

    # Pattern match (for things like "*.egg-info")
    for pattern in ignore_dirs:
        if fnmatch.fnmatch(dirname, pattern):
            return True

    return False


def should_ignore_file(filename: str, ignore_exts: Set[str], ignore_files: List[str]) -> bool:
    """Check if file should be ignored."""
    ext = Path(filename).suffix
    if ext in ignore_exts:
        return True

    for pattern in ignore_files:
        if fnmatch.fnmatch(filename, pattern):
            return True

    return False


def discover_python_files(
    root_dir: str,
    ignore_dirs: Optional[Set[str]] = None,
    ignore_exts: Optional[Set[str]] = None,
    ignore_files: Optional[List[str]] = None
) -> List[str]:
    """
    Discover all Python files in a directory, respecting ignore patterns.

    Args:
        root_dir: Root directory to scan
        ignore_dirs: Directory names to skip
        ignore_exts: File extensions to skip
        ignore_files: File patterns to skip

    Returns:
        List of absolute paths to Python files, sorted
    """
    if ignore_dirs is None or ignore_exts is None or ignore_files is None:
        ignore_dirs, ignore_exts, ignore_files = load_ignore_patterns()

    files = []

    for root, dirs, filenames in os.walk(root_dir):
        # Filter directories in-place (modifies the walk)
        dirs[:] = [d for d in dirs if not should_ignore_dir(d, ignore_dirs)]

        for filename in filenames:
            # Only Python files
            if not filename.endswith('.py'):
                continue

            # Check ignore patterns
            if should_ignore_file(filename, ignore_exts, ignore_files):
                continue

            filepath = os.path.join(root, filename)
            files.append(os.path.abspath(filepath))

    return sorted(files)


def estimate_tokens(filepath: str) -> int:
    """
    Estimate token count for a file.

    Uses the heuristic: ~4 characters per token for code.

    Args:
        filepath: Path to the file

    Returns:
        Estimated token count
    """
    try:
        return os.path.getsize(filepath) // 4
    except (OSError, IOError):
        return 0


def estimate_tokens_from_text(text: str) -> int:
    """
    Estimate token count for a string.

    Args:
        text: The text to estimate

    Returns:
        Estimated token count
    """
    return len(text) // 4


def format_tokens(tokens: int) -> str:
    """
    Format token count for display.

    Args:
        tokens: Token count

    Returns:
        Formatted string (e.g., "1.2K", "45K")
    """
    if tokens >= 1000:
        return f"{tokens / 1000:.1f}K"
    return str(tokens)


def get_size_category(tokens: int) -> str:
    """
    Categorize file size by token count.

    Args:
        tokens: Estimated token count

    Returns:
        Size category string
    """
    if tokens > 50000:
        return "HUGE"
    elif tokens > 20000:
        return "LARGE"
    elif tokens > 10000:
        return "MEDIUM"
    elif tokens > 5000:
        return "SMALL"
    else:
        return "TINY"


def detect_project_name(directory: str) -> str:
    """
    Detect project name from pyproject.toml, setup.py, or directory name.

    Args:
        directory: Project root directory

    Returns:
        Detected project name
    """
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
    """
    Detect the main source directory.

    Looks for common patterns: src/, lib/, <project_name>/, etc.

    Args:
        directory: Project root directory

    Returns:
        Relative path to source directory
    """
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


def get_file_stats(files: List[str]) -> Dict:
    """
    Get aggregate statistics for a list of files.

    Args:
        files: List of file paths

    Returns:
        Dict with file_count, total_tokens, total_lines, size_breakdown
    """
    total_tokens = 0
    total_lines = 0
    size_breakdown = {"HUGE": 0, "LARGE": 0, "MEDIUM": 0, "SMALL": 0, "TINY": 0}

    for filepath in files:
        tokens = estimate_tokens(filepath)
        total_tokens += tokens
        size_breakdown[get_size_category(tokens)] += 1

        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                total_lines += sum(1 for _ in f)
        except Exception:
            pass

    return {
        "file_count": len(files),
        "total_tokens": total_tokens,
        "total_lines": total_lines,
        "size_breakdown": size_breakdown
    }


def group_files_by_directory(files: List[str], root_dir: str) -> Dict[str, List[str]]:
    """
    Group files by their parent directory.

    Args:
        files: List of absolute file paths
        root_dir: Root directory for relative paths

    Returns:
        Dict mapping directory paths to files in that directory
    """
    root_path = Path(root_dir).resolve()
    groups = {}

    for filepath in files:
        path = Path(filepath)
        rel_dir = str(path.parent.relative_to(root_path))
        if rel_dir == ".":
            rel_dir = "(root)"

        if rel_dir not in groups:
            groups[rel_dir] = []
        groups[rel_dir].append(filepath)

    return groups

#!/usr/bin/env python3
"""
Repo Investigator: Import Verifier

Two-tier verification:
- Safe mode (AST-only): Checks syntax and local file references
- Strict mode (Runtime): Actually imports the module

Features:
- Prioritize untested modules for verification
- Directory scanning mode
- Detailed verification reports

Usage:
    python verify.py <path> [options]

Examples:
    python verify.py src/core/workflow.py --mode safe
    python verify.py mypackage.core.workflow --mode strict
    python verify.py src/ --prioritize-untested --warm-start-debug ./WARM_START_debug
"""
import argparse
import ast
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Tuple, List, Dict, Optional


# Standard library modules (subset for quick checking)
STDLIB_MODULES = {
    'os', 'sys', 're', 'json', 'typing', 'pathlib', 'collections',
    'datetime', 'asyncio', 'logging', 'argparse', 'dataclasses',
    'abc', 'enum', 'functools', 'itertools', 'copy', 'time',
    'math', 'random', 'hashlib', 'base64', 'io', 'contextlib',
    'subprocess', 'shutil', 'tempfile', 'glob', 'fnmatch',
    'unittest', 'traceback', 'warnings', 'inspect', 'ast',
    'concurrent', 'multiprocessing', 'threading', 'queue',
    'http', 'urllib', 'socket', 'ssl', 'email', 'html', 'xml',
    'sqlite3', 'pickle', 'csv', 'configparser', 'struct', 'codecs',
    'textwrap', 'string', 'secrets', 'operator', 'heapq', 'bisect',
    'weakref', 'types', 'pprint', 'reprlib', 'difflib', 'atexit',
    'sched', 'signal', 'mmap', 'ctypes', 'zipfile', 'tarfile',
    'gzip', 'bz2', 'lzma', 'zipimport', 'pkgutil', 'importlib',
    'tokenize', 'keyword', 'linecache', 'dis', 'pickletools',
    'symtable', 'token', 'tabnanny', 'pyclbr', 'py_compile',
    'compileall', 'code', 'codeop', 'pdb', 'profile', 'timeit',
    'trace', 'tracemalloc', 'gc', 'site', 'sysconfig', 'builtins',
    'uuid', 'decimal', 'fractions', 'numbers', 'cmath', 'statistics'
}


def check_safe(filepath: str, verbose: bool = False) -> Tuple[bool, str, List[str]]:
    """
    AST-based verification (no execution).

    Checks:
    1. File exists and is readable
    2. File parses as valid Python
    3. Imported modules appear to exist locally

    Returns:
        Tuple of (success, message, warnings)
    """
    warnings = []

    if verbose:
        print(f"Checking {filepath}...", file=sys.stderr)

    # Check file exists
    if not os.path.exists(filepath):
        return False, "File not found", warnings

    # Read and parse
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"Syntax error: {e}", warnings
    except Exception as e:
        return False, f"Read error: {e}", warnings

    # Check imports
    cwd = os.getcwd()
    missing = []
    external = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split('.')[0]
                if mod in STDLIB_MODULES:
                    continue
                if not _module_exists_locally(mod, cwd):
                    if _is_likely_external(mod):
                        external.append(alias.name)
                    else:
                        missing.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue  # Skip relative imports (harder to verify)
            if node.module:
                mod = node.module.split('.')[0]
                if mod in STDLIB_MODULES:
                    continue
                if not _module_exists_locally(mod, cwd):
                    if _is_likely_external(mod):
                        external.append(node.module)
                    else:
                        missing.append(node.module)

    if missing:
        warnings.append(f"Potential missing imports: {', '.join(missing[:5])}")
    if external:
        warnings.append(f"External dependencies: {', '.join(external[:5])}")

    return True, "AST Valid", warnings


def _module_exists_locally(module_name: str, cwd: str) -> bool:
    """Check if a module exists as a local file or package."""
    # Check as file
    if os.path.exists(os.path.join(cwd, f"{module_name}.py")):
        return True

    # Check as package
    pkg_path = os.path.join(cwd, module_name)
    if os.path.isdir(pkg_path) and os.path.exists(os.path.join(pkg_path, "__init__.py")):
        return True

    # Check in common source directories
    for src_dir in ['src', 'lib', 'app']:
        src_path = os.path.join(cwd, src_dir)
        if os.path.exists(os.path.join(src_path, f"{module_name}.py")):
            return True
        pkg_path = os.path.join(src_path, module_name)
        if os.path.isdir(pkg_path) and os.path.exists(os.path.join(pkg_path, "__init__.py")):
            return True

    return False


def _is_likely_external(module_name: str) -> bool:
    """Check if a module is likely an external package (e.g., from PyPI)."""
    # Common external packages
    external_packages = {
        'pydantic', 'fastapi', 'flask', 'django', 'sqlalchemy', 'requests',
        'numpy', 'pandas', 'scipy', 'matplotlib', 'seaborn', 'sklearn',
        'torch', 'tensorflow', 'keras', 'transformers', 'pytest', 'click',
        'typer', 'rich', 'httpx', 'aiohttp', 'celery', 'redis', 'boto3',
        'anthropic', 'openai', 'langchain', 'llama_index', 'tiktoken'
    }
    return module_name.lower() in external_packages


def check_strict(module_path: str, verbose: bool = False) -> Tuple[bool, str]:
    """
    Runtime import verification.

    Actually imports the module to verify all dependencies resolve.
    WARNING: This executes module-level code.

    Returns:
        Tuple of (success, message)
    """
    if verbose:
        print(f"Importing {module_path}...", file=sys.stderr)

    # Convert file path to module path if needed
    if module_path.endswith('.py'):
        module_path = module_path[:-3]
    module_name = module_path.replace(os.sep, '.').replace('/', '.')

    # Clean up module name
    if module_name.startswith('.'):
        module_name = module_name[1:]

    try:
        # Add current directory to path
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())

        # Attempt import
        importlib.import_module(module_name)
        return True, "Import Successful"

    except ImportError as e:
        return False, f"ImportError: {e}"
    except Exception as e:
        return False, f"Runtime error: {type(e).__name__}: {e}"


def load_untested_modules(warm_start_debug_path: str, verbose: bool = False) -> List[str]:
    """Load list of untested module directories from WARM_START_debug."""
    try:
        debug_dir = Path(warm_start_debug_path)
        test_data_path = debug_dir / "section_13_test_coverage.json"
        if test_data_path.exists():
            test_data = json.loads(test_data_path.read_text())
            untested = test_data.get("untested_dirs", [])
            if verbose:
                print(f"Loaded {len(untested)} untested directories", file=sys.stderr)
            return untested
    except Exception as e:
        if verbose:
            print(f"Warning: Could not load test coverage: {e}", file=sys.stderr)
    return []


def scan_directory(
    directory: str,
    ignore_dirs: set = None,
    prioritize_untested: bool = False,
    untested_dirs: List[str] = None,
    verbose: bool = False
) -> List[str]:
    """
    Scan directory for Python files.

    If prioritize_untested is True, returns untested files first.
    """
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', 'node_modules', '.venv', 'env', '.claude', 'tests', 'test'}

    files = []
    untested_files = []
    tested_files = []

    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, directory)

                if prioritize_untested and untested_dirs:
                    # Check if file is in an untested directory
                    is_untested = any(rel_path.startswith(d) for d in untested_dirs)
                    if is_untested:
                        untested_files.append(filepath)
                    else:
                        tested_files.append(filepath)
                else:
                    files.append(filepath)

    if prioritize_untested:
        # Untested files first
        files = untested_files + tested_files
        if verbose:
            print(f"Found {len(untested_files)} untested, {len(tested_files)} tested files", file=sys.stderr)
    elif verbose:
        print(f"Found {len(files)} Python files to verify", file=sys.stderr)

    return files


def verify_directory(
    directory: str,
    mode: str = "safe",
    prioritize_untested: bool = False,
    warm_start_debug: Optional[str] = None,
    verbose: bool = False
) -> List[Dict]:
    """Verify all Python files in a directory."""
    results = []

    untested_dirs = []
    if prioritize_untested and warm_start_debug:
        untested_dirs = load_untested_modules(warm_start_debug, verbose)

    files = scan_directory(
        directory,
        prioritize_untested=prioritize_untested,
        untested_dirs=untested_dirs,
        verbose=verbose
    )

    for filepath in files:
        rel_path = os.path.relpath(filepath, directory)

        if mode == "safe":
            ok, msg, warnings = check_safe(filepath, verbose)
            results.append({
                "file": rel_path,
                "status": "OK" if ok else "FAIL",
                "message": msg,
                "warnings": warnings,
                "untested": any(rel_path.startswith(d) for d in untested_dirs) if untested_dirs else None
            })
        else:
            ok, msg = check_strict(filepath, verbose)
            results.append({
                "file": rel_path,
                "status": "OK" if ok else "FAIL",
                "message": msg,
                "warnings": [],
                "untested": any(rel_path.startswith(d) for d in untested_dirs) if untested_dirs else None
            })

    return results


def write_debug_output(results: List[Dict], output_dir: str, verbose: bool = False):
    """Write debug output to VERIFY_debug/ directory."""
    debug_path = Path(output_dir)
    debug_path.mkdir(parents=True, exist_ok=True)

    # Write full results
    with open(debug_path / "verification_report.json", 'w') as f:
        json.dump(results, f, indent=2)

    # Write summary
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    untested_fail = sum(1 for r in results if r["status"] == "FAIL" and r.get("untested"))

    summary = {
        "total_files": len(results),
        "passed": ok_count,
        "failed": fail_count,
        "untested_failures": untested_fail,
        "failures": [r for r in results if r["status"] == "FAIL"]
    }
    with open(debug_path / "summary.json", 'w') as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print(f"Debug output written to {debug_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Verify Python imports and dependencies"
    )
    parser.add_argument(
        "path",
        help="File path, module path, or directory to verify"
    )
    parser.add_argument(
        "--mode",
        choices=["safe", "strict"],
        default="safe",
        help="Verification mode (default: safe)"
    )
    parser.add_argument(
        "--prioritize-untested",
        action="store_true",
        help="Verify untested modules first (requires --warm-start-debug)"
    )
    parser.add_argument(
        "--warm-start-debug",
        metavar="PATH",
        help="Path to WARM_START_debug/ for test coverage data"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress messages"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write debug output to VERIFY_debug/"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    path = args.path
    is_directory = os.path.isdir(path)
    is_file = path.endswith('.py') or (os.path.exists(path) and not is_directory)

    # Handle directory verification
    if is_directory:
        results = verify_directory(
            path,
            mode=args.mode,
            prioritize_untested=args.prioritize_untested,
            warm_start_debug=args.warm_start_debug,
            verbose=args.verbose
        )

        if args.debug:
            write_debug_output(results, "VERIFY_debug", args.verbose)

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            # Print summary
            ok_count = sum(1 for r in results if r["status"] == "OK")
            fail_count = len(results) - ok_count

            print(f"Verification Results ({args.mode} mode)")
            print("-" * 60)

            for r in results:
                status = "[OK]" if r["status"] == "OK" else "[FAIL]"
                untested_marker = " [UNTESTED]" if r.get("untested") else ""
                print(f"{status} {r['file']}{untested_marker}")
                if r["warnings"]:
                    for w in r["warnings"]:
                        print(f"     Warning: {w}")
                if r["status"] == "FAIL":
                    print(f"     {r['message']}")

            print("-" * 60)
            print(f"Total: {len(results)} | Passed: {ok_count} | Failed: {fail_count}")

        if fail_count > 0:
            sys.exit(1)
        return

    # Handle single file verification
    if is_file and not os.path.exists(path):
        # Try adding .py
        if os.path.exists(path + '.py'):
            path = path + '.py'

    # Safe mode
    if args.mode == "safe" or is_file:
        if not is_file:
            # Convert module path to file path for safe check
            file_path = path.replace('.', os.sep) + '.py'
        else:
            file_path = path

        ok, msg, warnings = check_safe(file_path, args.verbose)
        if warnings:
            msg = f"{msg} (Warning: {'; '.join(warnings)})"

        if args.json:
            print(json.dumps({
                "file": file_path,
                "status": "OK" if ok else "FAIL",
                "message": msg,
                "warnings": warnings
            }, indent=2))
        else:
            if not ok:
                print(f"[FAIL] {msg}")
                sys.exit(1)
            print(f"[OK] {msg}")

    # Strict mode
    if args.mode == "strict":
        ok, msg = check_strict(path, args.verbose)

        if args.json:
            print(json.dumps({
                "path": path,
                "status": "OK" if ok else "FAIL",
                "message": msg
            }, indent=2))
        else:
            if not ok:
                print(f"[FAIL] {msg}")
                sys.exit(1)
            print(f"[OK] {msg}")


if __name__ == "__main__":
    main()

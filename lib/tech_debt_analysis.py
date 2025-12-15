"""
Repo X-Ray: Technical Debt Analysis Module

Detects technical debt markers in source code:
- TODO comments
- FIXME markers
- HACK indicators
- XXX/BUG/OPTIMIZE markers

Usage:
    from tech_debt_analysis import analyze_tech_debt

    result = analyze_tech_debt(files)
"""

import re
from pathlib import Path
from typing import Any, Dict, List

# Patterns for detecting technical debt markers
TODO_PATTERNS = [
    r'#\s*(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE)\b[:\s]*(.*)$',
]


def analyze_tech_debt(
    files: List[str],
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Detect technical debt markers in source files.

    Args:
        files: List of file paths to analyze
        verbose: Print progress

    Returns:
        {
            "markers": {
                "TODO": [{"file": str, "line": int, "text": str}],
                "FIXME": [...],
                ...
            },
            "by_file": {
                "filepath": [{"type": str, "line": int, "text": str}]
            },
            "summary": {
                "total_count": int,
                "by_type": {"TODO": int, "FIXME": int, ...}
            }
        }
    """
    import sys

    if verbose:
        print("Analyzing technical debt markers...", file=sys.stderr)

    markers = {
        'TODO': [],
        'FIXME': [],
        'HACK': [],
        'XXX': [],
        'BUG': [],
        'OPTIMIZE': [],
    }

    by_file = {}

    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                file_markers = []

                for line_num, line in enumerate(f, 1):
                    for pattern in TODO_PATTERNS:
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            marker_type = match.group(1).upper()
                            text = match.group(2).strip()[:80]  # Limit length

                            if marker_type in markers:
                                entry = {
                                    'file': filepath,
                                    'line': line_num,
                                    'text': text
                                }
                                markers[marker_type].append(entry)

                                file_markers.append({
                                    'type': marker_type,
                                    'line': line_num,
                                    'text': text
                                })

                if file_markers:
                    by_file[filepath] = file_markers

        except Exception:
            continue

    # Calculate summary
    total_count = sum(len(v) for v in markers.values())
    by_type = {k: len(v) for k, v in markers.items() if v}

    # Filter empty marker types
    markers = {k: v for k, v in markers.items() if v}

    return {
        "markers": markers,
        "by_file": by_file,
        "summary": {
            "total_count": total_count,
            "by_type": by_type
        }
    }


def get_priority_debt(
    tech_debt_results: Dict[str, Any],
    limit: int = 10
) -> List[Dict]:
    """
    Get the highest priority technical debt items.

    Priority order: BUG > FIXME > HACK > TODO > OPTIMIZE > XXX

    Returns:
        List of top priority items
    """
    priority_order = ['BUG', 'FIXME', 'HACK', 'TODO', 'OPTIMIZE', 'XXX']
    result = []

    markers = tech_debt_results.get("markers", {})

    for marker_type in priority_order:
        items = markers.get(marker_type, [])
        for item in items[:limit - len(result)]:
            result.append({
                "priority": marker_type,
                "file": item["file"],
                "line": item["line"],
                "text": item["text"]
            })
            if len(result) >= limit:
                return result

    return result


def get_files_with_most_debt(
    tech_debt_results: Dict[str, Any],
    limit: int = 10
) -> List[Dict]:
    """
    Get files with the most technical debt markers.

    Returns:
        List of files sorted by debt count
    """
    by_file = tech_debt_results.get("by_file", {})

    file_counts = [
        {"file": filepath, "count": len(markers), "types": list(set(m["type"] for m in markers))}
        for filepath, markers in by_file.items()
    ]

    return sorted(file_counts, key=lambda x: x["count"], reverse=True)[:limit]

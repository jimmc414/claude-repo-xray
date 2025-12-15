"""
Repo X-Ray: JSON Output Formatter

Formats analysis results as structured JSON.
"""

import json
from datetime import datetime
from typing import Any, Dict, List


def format_json(
    results: Dict[str, Any],
    indent: int = 2,
    include_raw: bool = False
) -> str:
    """
    Format analysis results as JSON.

    Args:
        results: Analysis results dictionary
        indent: JSON indentation level
        include_raw: Include raw data (larger output)

    Returns:
        JSON string
    """
    # Make a copy to avoid modifying original
    output = {
        "metadata": results.get("metadata", {}),
        "summary": results.get("summary", {})
    }

    # Include all sections that have data
    sections = [
        "structure", "complexity", "git", "imports", "calls",
        "side_effects", "tests", "tech_debt", "types",
        "decorators", "author_expertise", "commit_sizes",
        "priority_files"
    ]

    for section in sections:
        if section in results and results[section]:
            output[section] = results[section]

    # Handle nested sections
    if "all_classes" in results:
        output["all_classes"] = results["all_classes"]
    if "all_functions" in results:
        output["all_functions"] = results["all_functions"]
    if "hotspots" in results:
        output["hotspots"] = results["hotspots"]

    return json.dumps(output, indent=indent, default=str)


def format_json_summary(results: Dict[str, Any]) -> str:
    """
    Format a compact JSON summary (for quick overview).

    Returns:
        JSON string with only summary data
    """
    summary = {
        "metadata": {
            "tool_version": results.get("metadata", {}).get("tool_version", "unknown"),
            "generated_at": results.get("metadata", {}).get("generated_at", ""),
            "file_count": results.get("metadata", {}).get("file_count", 0)
        },
        "summary": results.get("summary", {}),
        "top_hotspots": results.get("hotspots", [])[:5],
        "circular_deps": results.get("imports", {}).get("circular", []),
        "high_impact": results.get("calls", {}).get("high_impact", [])[:5],
        "tech_debt_count": results.get("tech_debt", {}).get("summary", {}).get("total_count", 0)
    }

    return json.dumps(summary, indent=2, default=str)


def merge_results(
    results_list: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Merge multiple analysis results (for multi-directory analysis).

    Args:
        results_list: List of analysis result dictionaries

    Returns:
        Merged results dictionary
    """
    if not results_list:
        return {}

    if len(results_list) == 1:
        return results_list[0]

    # Start with the first result as base
    merged = results_list[0].copy()

    # Aggregate summaries
    for results in results_list[1:]:
        summary = results.get("summary", {})
        merged_summary = merged.get("summary", {})

        for key in ["total_files", "total_lines", "total_tokens",
                    "total_functions", "total_classes"]:
            merged_summary[key] = merged_summary.get(key, 0) + summary.get(key, 0)

        merged["summary"] = merged_summary

        # Merge lists
        for key in ["all_classes", "all_functions", "hotspots"]:
            if key in results:
                merged.setdefault(key, []).extend(results[key])

    return merged

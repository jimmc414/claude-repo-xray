#!/usr/bin/env python3
"""Post-hoc enrichment: inject git signals from xray JSON into a DEEP_ONBOARD document.

Usage:
    python tools/enrich_onboard.py \
        --xray output/xray.json \
        --onboard output/DEEP_ONBOARD.md \
        --output output/DEEP_ONBOARD_enriched.md

Idempotent — safe to run multiple times. Only adds blockquotes, never modifies
existing content.
"""

import argparse
import json
import os
import re
import sys


def load_xray(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_risk_lookup(git_data):
    """Build file→risk_score lookup from git.risk."""
    lookup = {}
    for entry in git_data.get("risk", []):
        lookup[entry["file"]] = entry["risk_score"]
    return lookup


def build_churn_lookup(git_data):
    """Build file→[{function, commits, hotfixes, risk_score}] from git.function_churn."""
    lookup = {}
    for entry in git_data.get("function_churn", []):
        f = entry["file"]
        lookup.setdefault(f, []).append(entry)
    # Sort each file's functions by risk_score descending
    for f in lookup:
        lookup[f].sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    return lookup


def build_velocity_lookup(git_data):
    """Build file→trend from git.velocity."""
    lookup = {}
    for entry in git_data.get("velocity", []):
        lookup[entry["file"]] = entry["trend"]
    return lookup


def build_coupling_index(git_data):
    """Build file→cluster from git.coupling_clusters."""
    clusters = git_data.get("coupling_clusters", [])
    index = {}
    for cluster in clusters:
        for f in cluster["files"]:
            index[f] = cluster
    return index


def match_file(module_path, lookup):
    """Match a module path from the DEEP_ONBOARD against xray file lookup.

    Tries exact match first, then basename match. If basename is ambiguous,
    returns the key with the highest associated value (risk score).
    """
    # Exact match
    if module_path in lookup:
        return module_path

    # Try with/without leading path segments
    basename = os.path.basename(module_path)
    candidates = [k for k in lookup if os.path.basename(k) == basename]

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        # Prefer highest value (works for risk_lookup where values are scores)
        return max(candidates, key=lambda k: lookup[k] if isinstance(lookup[k], (int, float)) else 0)

    return None


def format_risk_blockquote(risk_score, churn_entries, trend):
    """Build the > **Git risk:** blockquote string."""
    parts = [f"**Git risk:** {risk_score:.2f}"]

    if churn_entries:
        top3 = churn_entries[:3]
        func_parts = []
        for e in top3:
            desc = f"{e['function']} ({e['commits']} commits"
            if e.get("hotfixes", 0) > 0:
                desc += f", {e['hotfixes']} hotfixes"
            desc += ")"
            func_parts.append(desc)
        parts.append("volatile functions: " + ", ".join(func_parts))

    if trend and trend != "stable":
        parts.append(f"Trend: {trend}")

    return "> " + " — ".join(parts) + "."


def format_coupling_blockquote(hub_file, cluster):
    """Build the > **Hidden coupling:** blockquote string."""
    other_files = [f for f in cluster["files"] if f != hub_file]
    if not other_files:
        return None
    # Show up to 4 other files
    shown = other_files[:4]
    display = ", ".join(shown)
    if len(other_files) > 4:
        display += f", +{len(other_files) - 4} more"
    count = cluster["total_cochanges"]
    return (
        f"> **Hidden coupling:** When modifying {hub_file}, also verify "
        f"{display} — {count} historical co-changes forming a change cluster."
    )


def enrich_s2(lines, risk_lookup, churn_lookup, velocity_lookup):
    """Inject git risk blockquotes into S2 Module Behavioral Index entries."""
    s2_header_re = re.compile(r"^### `(.+?)` -- Detailed Behavioral Analysis")
    injected = 0
    result = []
    i = 0

    while i < len(lines):
        m = s2_header_re.match(lines[i])
        if not m:
            result.append(lines[i])
            i += 1
            continue

        module_path = m.group(1)
        result.append(lines[i])
        i += 1

        # Find the --- separator ending this module entry
        separator_idx = None
        for j in range(i, len(lines)):
            if lines[j].strip() == "---":
                separator_idx = j
                break

        if separator_idx is None:
            continue

        # Copy lines up to separator
        while i < separator_idx:
            result.append(lines[i])
            i += 1

        # Check idempotency — skip if already enriched
        if any("> **Git risk:**" in lines[k] for k in range(separator_idx - 3, separator_idx)):
            result.append(lines[i])  # the ---
            i += 1
            continue

        # Build blockquote
        matched = match_file(module_path, risk_lookup)
        if matched:
            risk_score = risk_lookup[matched]
            churn_entries = churn_lookup.get(matched, [])

            vel_matched = match_file(module_path, velocity_lookup) if velocity_lookup else None
            trend = velocity_lookup.get(vel_matched) if vel_matched else None

            blockquote = format_risk_blockquote(risk_score, churn_entries, trend)

            # Insert blank line + blockquote before ---
            if result and result[-1].strip() != "":
                result.append("")
            result.append(blockquote)
            result.append("")
            injected += 1

        result.append(lines[i])  # the ---
        i += 1

    return result, injected


def enrich_s6(lines, coupling_index):
    """Inject coupling cluster blockquotes into S6 Change Impact Index hub entries."""
    hub_re = re.compile(r"^#### Hub: `(.+?)`")
    boundary_re = re.compile(r"^#{2,4} ")
    injected = 0
    result = []
    i = 0

    while i < len(lines):
        m = hub_re.match(lines[i])
        if not m:
            result.append(lines[i])
            i += 1
            continue

        hub_file = m.group(1)
        result.append(lines[i])
        i += 1

        # Find next section boundary
        boundary_idx = None
        for j in range(i, len(lines)):
            if boundary_re.match(lines[j]):
                boundary_idx = j
                break
        if boundary_idx is None:
            boundary_idx = len(lines)

        # Copy lines up to boundary
        while i < boundary_idx:
            result.append(lines[i])
            i += 1

        # Check idempotency
        check_start = max(0, len(result) - 5)
        if any("> **Hidden coupling:**" in result[k] for k in range(check_start, len(result))):
            continue

        # Find cluster for this hub
        matched = None
        for key in coupling_index:
            if key == hub_file or os.path.basename(key) == os.path.basename(hub_file):
                matched = key
                break

        if matched:
            cluster = coupling_index[matched]
            blockquote = format_coupling_blockquote(hub_file, cluster)
            if blockquote:
                # Insert before boundary
                if result and result[-1].strip() != "":
                    result.append("")
                result.append(blockquote)
                result.append("")
                injected += 1

    return result, injected


def main():
    parser = argparse.ArgumentParser(description="Enrich DEEP_ONBOARD with xray git signals")
    parser.add_argument("--xray", required=True, help="Path to xray JSON output")
    parser.add_argument("--onboard", required=True, help="Path to DEEP_ONBOARD.md")
    parser.add_argument("--output", required=True, help="Path for enriched output")
    args = parser.parse_args()

    xray_data = load_xray(args.xray)
    git_data = xray_data.get("git", {})

    if not git_data or "error" in git_data:
        print(f"Warning: No git data in xray output (got: {git_data})", file=sys.stderr)

    risk_lookup = build_risk_lookup(git_data)
    churn_lookup = build_churn_lookup(git_data)
    velocity_lookup = build_velocity_lookup(git_data)
    coupling_index = build_coupling_index(git_data)

    with open(args.onboard, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    lines, s2_count = enrich_s2(lines, risk_lookup, churn_lookup, velocity_lookup)
    lines, s6_count = enrich_s6(lines, coupling_index)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Enriched: {s2_count} module entries with git risk, "
          f"{s6_count} hub entries with coupling clusters", file=sys.stderr)
    print(f"Output: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()

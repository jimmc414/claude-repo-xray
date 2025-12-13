#!/usr/bin/env python3
"""
Repo X-Ray: Git Analysis

Extracts historical signals from git history:
- Risk scoring (churn, hotfixes, author entropy)
- Co-modification analysis (hidden coupling)
- Freshness tracking (active, aging, stale, dormant)

Usage:
    python git_analysis.py [directory] [options]

Examples:
    python git_analysis.py src/ --risk
    python git_analysis.py src/ --coupling
    python git_analysis.py src/ --freshness
    python git_analysis.py src/ --json
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Optional

# Exports for programmatic use
__all__ = [
    'analyze_risk',
    'analyze_coupling',
    'analyze_freshness',
    'get_tracked_files',
    'run_git',
]


def run_git(cmd: List[str], cwd: str) -> str:
    """Execute a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return result.stdout.strip()
    except subprocess.SubprocessError:
        return ""


def get_tracked_files(cwd: str) -> List[str]:
    """Get list of tracked Python files."""
    raw = run_git(["ls-files", "*.py"], cwd)
    return [f for f in raw.splitlines() if f.strip()]


def analyze_risk(cwd: str, files: List[str], months: int = 6) -> List[Dict]:
    """
    Calculate Risk Score based on:
    - Churn: Number of commits in period (40% weight)
    - Hotfixes: Commits with fix/bug/urgent/revert keywords (40% weight)
    - Author Entropy: Unique authors / total commits (20% weight)

    Higher score = higher risk (more volatile).
    """
    # Parse git log with custom delimiter
    log = run_git(
        ["log", f"--since={months}.months", "--name-only", "--format=COMMIT::%an::%s"],
        cwd
    )

    if not log:
        return []

    stats = defaultdict(lambda: {"commits": 0, "authors": set(), "hotfixes": 0})
    current_author = ""
    is_hotfix = False

    hotfix_keywords = {"fix", "bug", "urgent", "revert", "hotfix", "patch", "emergency"}

    for line in log.splitlines():
        if line.startswith("COMMIT::"):
            parts = line.split("::", 2)
            if len(parts) >= 3:
                current_author = parts[1]
                subject = parts[2].lower()
                is_hotfix = any(kw in subject for kw in hotfix_keywords)
        elif line.strip() and line.endswith(".py"):
            f = line.strip()
            if f in files:
                s = stats[f]
                s["commits"] += 1
                s["authors"].add(current_author)
                if is_hotfix:
                    s["hotfixes"] += 1

    if not stats:
        return []

    # Normalize and calculate risk score
    max_churn = max(s["commits"] for s in stats.values())
    results = []

    for f, s in stats.items():
        churn_norm = s["commits"] / max_churn if max_churn > 0 else 0
        author_score = min(len(s["authors"]), 5) / 5.0
        hotfix_score = min(s["hotfixes"], 3) / 3.0

        # Risk Formula: 40% Churn, 40% Hotfixes, 20% Authors
        risk = (churn_norm * 0.4) + (hotfix_score * 0.4) + (author_score * 0.2)

        if risk > 0.1:
            results.append({
                "file": f,
                "risk_score": round(risk, 2),
                "churn": s["commits"],
                "hotfixes": s["hotfixes"],
                "authors": len(s["authors"])
            })

    return sorted(results, key=lambda x: x["risk_score"], reverse=True)


def analyze_coupling(cwd: str, max_commits: int = 200, min_cooccurrences: int = 3) -> List[Dict]:
    """
    Find files that change together even without import relationships.

    Strategy:
    1. Parse recent commits (name-only)
    2. Build co-occurrence matrix for Python files
    3. Filter to pairs with >= min_cooccurrences
    4. Skip bulk refactors (commits touching >20 files)
    """
    log = run_git(["log", "-n", str(max_commits), "--name-only", "--format=COMMIT"], cwd)

    if not log:
        return []

    commits = []
    current_files = set()

    for line in log.splitlines():
        if line == "COMMIT":
            if current_files:
                commits.append(list(current_files))
            current_files = set()
        elif line.strip().endswith(".py"):
            current_files.add(line.strip())

    if current_files:
        commits.append(list(current_files))

    # Count co-occurrences
    pairs = Counter()
    for files in commits:
        if len(files) > 20:
            continue  # Skip bulk refactors
        files = sorted(files)
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                pairs[(files[i], files[j])] += 1

    results = []
    for (f1, f2), count in pairs.most_common(20):
        if count >= min_cooccurrences:
            results.append({"file_a": f1, "file_b": f2, "count": count})

    return results


def analyze_freshness(cwd: str, files: List[str]) -> Dict[str, List[Dict]]:
    """
    Categorize files by last modification time.

    Categories:
    - Active: <30 days (being maintained)
    - Aging: 30-90 days (may need attention)
    - Stale: 90-180 days (possibly neglected)
    - Dormant: >180 days (stable or abandoned)
    """
    log = run_git(["log", "--name-only", "--format=COMMIT::%ct"], cwd)

    if not log:
        return {"active": [], "aging": [], "stale": [], "dormant": []}

    last_modified = {}
    current_ts = 0

    for line in log.splitlines():
        if line.startswith("COMMIT::"):
            try:
                current_ts = int(line.split("::")[1])
            except (IndexError, ValueError):
                pass
        elif line.strip() and line.endswith(".py"):
            f = line.strip()
            if f not in last_modified:
                last_modified[f] = current_ts

    now = datetime.now().timestamp()
    result = {"active": [], "aging": [], "stale": [], "dormant": []}

    for f in files:
        ts = last_modified.get(f, now)
        days = int((now - ts) / 86400)
        entry = {"file": f, "days": days}

        if days < 30:
            result["active"].append(entry)
        elif days < 90:
            result["aging"].append(entry)
        elif days < 180:
            result["stale"].append(entry)
        else:
            result["dormant"].append(entry)

    # Sort dormant by age (oldest first)
    result["dormant"].sort(key=lambda x: x["days"], reverse=True)

    return result


def print_risk(results: List[Dict]):
    """Print risk analysis in human-readable format."""
    if not results:
        print("No risk data found (no commits in analysis period)")
        return

    print(f"{'RISK':<6} {'FILE':<50} {'FACTORS'}")
    print("-" * 80)
    for r in results[:15]:
        factors = f"churn:{r['churn']} hotfix:{r['hotfixes']} authors:{r['authors']}"
        print(f"{r['risk_score']:<6} {r['file']:<50} {factors}")


def print_coupling(results: List[Dict]):
    """Print coupling analysis in human-readable format."""
    if not results:
        print("No significant coupling found")
        return

    print("\n=== CO-MODIFICATION PAIRS ===")
    print("Files that change together (hidden coupling)")
    print("-" * 60)
    for c in results:
        print(f"{c['count']:<4} {c['file_a']} <-> {c['file_b']}")


def print_freshness(results: Dict[str, List[Dict]]):
    """Print freshness analysis in human-readable format."""
    print("\n=== FRESHNESS ANALYSIS ===")
    for category, label in [
        ("active", "ACTIVE (last 30 days)"),
        ("aging", "AGING (30-90 days)"),
        ("stale", "STALE (90-180 days)"),
        ("dormant", "DORMANT (>180 days)")
    ]:
        items = results.get(category, [])
        print(f"\n{label}: {len(items)} files")

        if category == "dormant" and items:
            print("  Oldest files:")
            for item in items[:5]:
                print(f"    {item['file']} ({item['days']} days)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze git history for risk, coupling, and freshness signals"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyze (default: current)"
    )
    parser.add_argument(
        "--risk",
        action="store_true",
        help="Calculate risk scores from churn, hotfixes, authors"
    )
    parser.add_argument(
        "--coupling",
        action="store_true",
        help="Find files that change together"
    )
    parser.add_argument(
        "--freshness",
        action="store_true",
        help="Categorize files by last modification"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output all analyses as JSON"
    )
    parser.add_argument(
        "--months",
        type=int,
        default=6,
        help="Months of history for risk analysis (default: 6)"
    )

    args = parser.parse_args()

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Check for git repository
    git_dir = os.path.join(args.directory, ".git")
    if not os.path.exists(git_dir):
        # Try parent directories
        check_dir = os.path.abspath(args.directory)
        while check_dir != os.path.dirname(check_dir):
            if os.path.exists(os.path.join(check_dir, ".git")):
                break
            check_dir = os.path.dirname(check_dir)
        else:
            if args.json:
                print("{}")
            else:
                print("Error: Not a git repository", file=sys.stderr)
            sys.exit(1)

    files = get_tracked_files(args.directory)

    if not files:
        if args.json:
            print("{}")
        else:
            print("No Python files found")
        return

    # Run requested analyses
    output = {}

    if args.json or args.risk:
        output["risk"] = analyze_risk(args.directory, files, args.months)

    if args.json or args.coupling:
        output["coupling"] = analyze_coupling(args.directory)

    if args.json or args.freshness:
        output["freshness"] = analyze_freshness(args.directory, files)

    # Output
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        if "risk" in output:
            print_risk(output["risk"])
        if "coupling" in output:
            print_coupling(output["coupling"])
        if "freshness" in output:
            print_freshness(output["freshness"])

        if not (args.risk or args.coupling or args.freshness):
            print("Use --risk, --coupling, --freshness, or --json to select analysis")


if __name__ == "__main__":
    main()

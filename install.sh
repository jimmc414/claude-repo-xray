#!/bin/bash
# Install claude-repo-xray to a target project
#
# Usage:
#   ./install.sh /path/to/project
#   ./install.sh .

set -e

TARGET_DIR="${1:-.}"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' does not exist"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing claude-repo-xray to: $TARGET_DIR"
echo ""

# Create directories
echo "[1/5] Creating .claude directories..."
mkdir -p "$TARGET_DIR/.claude/skills"
mkdir -p "$TARGET_DIR/.claude/agents"

# Copy Pass 1 skill (repo-xray)
echo "[2/5] Copying repo-xray skill (Pass 1: Structural)..."
cp -r "$SCRIPT_DIR/.claude/skills/repo-xray" "$TARGET_DIR/.claude/skills/"

# Copy Pass 2 skill (repo-investigator)
echo "[3/5] Copying repo-investigator skill (Pass 2: Behavioral)..."
cp -r "$SCRIPT_DIR/.claude/skills/repo-investigator" "$TARGET_DIR/.claude/skills/"

# Copy both agents
echo "[4/5] Copying agents..."
cp "$SCRIPT_DIR/.claude/agents/repo_architect.md" "$TARGET_DIR/.claude/agents/"
cp "$SCRIPT_DIR/.claude/agents/repo_investigator.md" "$TARGET_DIR/.claude/agents/"

# Run auto-configuration
echo "[5/5] Running configure.py..."
cd "$TARGET_DIR"
python3 .claude/skills/repo-xray/scripts/configure.py . --backup 2>/dev/null || {
    echo "  Auto-configuration skipped (requires Python 3.8+)"
    echo "  Run manually: python3 .claude/skills/repo-xray/scripts/configure.py ."
}

echo ""
echo "Done. Next steps:"
echo ""
echo "  # Pass 1: Structural analysis"
echo "  python .claude/skills/repo-xray/scripts/generate_warm_start.py . -v"
echo "  # or: @repo_architect generate"
echo ""
echo "  # Pass 2: Behavioral analysis"
echo "  python .claude/skills/repo-investigator/scripts/generate_hot_start.py . -v"
echo "  # or: @repo_investigator"
echo ""
echo "  # Individual tools"
echo "  python .claude/skills/repo-xray/scripts/mapper.py --summary"
echo "  python .claude/skills/repo-xray/scripts/skeleton.py . --priority critical"

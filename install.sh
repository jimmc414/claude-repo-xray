#!/bin/bash
# Install repo-xray to a target project
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

echo "Installing repo-xray to: $TARGET_DIR"
echo ""

# Create directories
echo "[1/4] Creating .claude directories..."
mkdir -p "$TARGET_DIR/.claude/skills"
mkdir -p "$TARGET_DIR/.claude/agents"

# Copy skill
echo "[2/4] Copying skill..."
cp -r "$SCRIPT_DIR/.claude/skills/repo-xray" "$TARGET_DIR/.claude/skills/"

# Copy agent
echo "[3/4] Copying agent..."
cp "$SCRIPT_DIR/.claude/agents/repo_architect.md" "$TARGET_DIR/.claude/agents/"

# Run auto-configuration
echo "[4/4] Running configure.py..."
cd "$TARGET_DIR"
python3 .claude/skills/repo-xray/scripts/configure.py . --backup 2>/dev/null || {
    echo "  Auto-configuration skipped (requires Python 3.8+)"
    echo "  Run manually: python3 .claude/skills/repo-xray/scripts/configure.py ."
}

# Copy example
if [ -f "$SCRIPT_DIR/WARM_START.example.md" ] && [ ! -f "$TARGET_DIR/WARM_START.md" ]; then
    cp "$SCRIPT_DIR/WARM_START.example.md" "$TARGET_DIR/WARM_START.example.md"
    echo "  Copied WARM_START.example.md"
fi

echo ""
echo "Done. Next steps:"
echo "  python .claude/skills/repo-xray/scripts/mapper.py --summary"
echo "  python .claude/skills/repo-xray/scripts/skeleton.py src/ --priority critical"
echo "  @repo_architect generate"

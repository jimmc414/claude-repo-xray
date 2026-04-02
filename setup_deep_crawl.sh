#!/usr/bin/env bash
# Sets up the deep-crawl skill for global availability in Claude Code.
# Run once per machine from the claude-repo-xray repo root.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/.claude/skills/deep-crawl"
SKILL_DST="$HOME/.claude/skills/deep-crawl"

if [ ! -d "$SKILL_SRC" ]; then
    echo "Error: $SKILL_SRC not found. Run this from the claude-repo-xray repo root."
    exit 1
fi

mkdir -p "$HOME/.claude/skills"

if [ -L "$SKILL_DST" ]; then
    EXISTING=$(readlink -f "$SKILL_DST")
    if [ "$EXISTING" = "$(readlink -f "$SKILL_SRC")" ]; then
        echo "Already configured: $SKILL_DST -> $SKILL_SRC"
        exit 0
    fi
    echo "Updating symlink: $SKILL_DST"
    echo "  was: $EXISTING"
    echo "  now: $SKILL_SRC"
    ln -sfn "$SKILL_SRC" "$SKILL_DST"
elif [ -e "$SKILL_DST" ]; then
    echo "Warning: $SKILL_DST exists but is not a symlink. Skipping."
    echo "Remove it manually if you want to link to this repo's skill."
    exit 1
else
    ln -sfn "$SKILL_SRC" "$SKILL_DST"
    echo "Created: $SKILL_DST -> $SKILL_SRC"
fi

echo ""
echo "Deep crawl is now available in all Claude Code sessions."
echo "Usage: cd /path/to/any/python/repo && claude"
echo "  Then: python $SCRIPT_DIR/xray.py . --output both --out /tmp/xray"
echo "  Then: /deep-crawl full"

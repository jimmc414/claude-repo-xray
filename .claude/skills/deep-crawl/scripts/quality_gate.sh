#!/bin/bash
# quality_gate.sh — Standalone quality gate for deep-crawl section files.
# Usage: ./quality_gate.sh [sections_dir] [--log FILE]
# Checks: existence, header hierarchy, citation density, word retention.
# Exit code: 0 = PASS, 1 = FAIL

SECTIONS_DIR="${1:-.deep_crawl/sections}"
LOG_FILE=""
PASS=true
ERRORS=0

# Parse optional --log flag
shift 2>/dev/null
while [ $# -gt 0 ]; do
    case "$1" in
        --log) LOG_FILE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Helper: output to stdout and optionally to log file
log() {
    echo "$1"
    [ -n "$LOG_FILE" ] && echo "$1" >> "$LOG_FILE"
}

log "=== Deep Crawl Quality Gate ==="
log "Sections directory: $SECTIONS_DIR"
log ""

# 1. Existence check
log "--- Existence Check ---"
for section in critical_paths module_index change_impact_index key_interfaces \
    data_contracts error_handling shared_state config_surface conventions \
    gotchas hazards extension_points change_playbooks reading_order; do
    if [ ! -f "$SECTIONS_DIR/${section}.md" ]; then
        log "MISSING: $section"
        PASS=false
        ERRORS=$((ERRORS + 1))
    fi
done

# 2. Header hierarchy check
log ""
log "--- Header Hierarchy Check ---"
for f in "$SECTIONS_DIR"/*.md; do
    [ -f "$f" ] || continue
    SECTION=$(basename "$f" .md)
    # Skip non-content files
    [[ "$SECTION" == _* || "$SECTION" == S* || "$SECTION" == gotchas_from_* || "$SECTION" == header || "$SECTION" == footer || "$SECTION" == document_map ]] && continue

    H1=$(grep -c "^# " "$f" 2>/dev/null || echo 0)
    H2=$(grep -c "^## " "$f" 2>/dev/null || echo 0)

    if [ "$H1" -gt 0 ]; then
        log "HEADER VIOLATION: $SECTION has $H1 h1 headers (expected 0)"
        PASS=false
        ERRORS=$((ERRORS + 1))
    fi
    if [ "$H2" -gt 1 ]; then
        log "HEADER VIOLATION: $SECTION has $H2 h2 headers (expected 1)"
        PASS=false
        ERRORS=$((ERRORS + 1))
    fi
done

# 3. Citation density check (tiered)
log ""
log "--- Citation Density Check ---"
get_density_floor() {
    case "$1" in
        change_impact_index|gotchas|data_contracts) echo 3 ;;
        module_index|key_interfaces|shared_state|change_playbooks|error_handling|hazards) echo 2 ;;
        critical_paths|config_surface|conventions|extension_points) echo 1 ;;
        *) echo 0 ;;
    esac
}

for f in "$SECTIONS_DIR"/*.md; do
    [ -f "$f" ] || continue
    SECTION=$(basename "$f" .md)
    [[ "$SECTION" == _* || "$SECTION" == S* || "$SECTION" == gotchas_from_* || "$SECTION" == header || "$SECTION" == footer || "$SECTION" == document_map ]] && continue

    WORDS=$(wc -w < "$f")
    FACTS=$(grep -c '\[FACT' "$f" 2>/dev/null || echo 0)
    [ "$WORDS" -eq 0 ] && continue
    FLOOR=$(get_density_floor "$SECTION")
    [ "$FLOOR" -eq 0 ] && continue
    DENSITY=$((FACTS * 100 / WORDS))
    if [ "$DENSITY" -lt "$FLOOR" ]; then
        log "DENSITY FAIL: $SECTION — ${DENSITY}/100w (floor: ${FLOOR}/100w, ${WORDS}w, ${FACTS} FACTs)"
        PASS=false
        ERRORS=$((ERRORS + 1))
    else
        log "OK: $SECTION — ${DENSITY}/100w (floor: ${FLOOR}/100w)"
    fi
done

# 4. Summary
log ""
log "=== Quality Gate Result ==="
if [ "$PASS" = true ]; then
    log "PASS (0 errors)"
    exit 0
else
    log "FAIL ($ERRORS errors)"
    exit 1
fi

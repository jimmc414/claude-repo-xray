# Warm Start Engine: Layer Mechanics

What each layer does, how it does it, and what it outputs.

---

## Phase 1: Foundation

### Skeletons

**Input:** Python source files

**Process:** AST parsing to extract:
- Import statements (verbatim)
- Class definitions with base classes and docstrings
- Method/function signatures with full type annotations
- Decorators
- Module-level docstrings
- Constants and type aliases

Implementation bodies replaced with `...` (ellipsis).

**Output:** `.shadow` files with ~85-95% size reduction

**Enables:** Reading 10-20x more files in the same context budget. The AI can "see" the entire API surface of a large codebase at once.

---

### Executive Summary

**Input:** Accumulated knowledge files (risk scores, dictionary, exploration status, recent failures)

**Process:** Synthesizes a briefing document at session start containing:
- Files with risk score >0.7 (watch list)
- Most-imported files (core modules)
- Recently failed operations (avoid repeating)
- Unmapped directories (knowledge gaps)
- Active jargon mappings (vocabulary)

**Output:** Markdown briefing injected into session context

**Enables:** The AI starts with situational awareness rather than cold ignorance. Knows where the high-risk areas are before touching them.

---

### Mini-HUD

**Input:** Current tool invocation context (file being read, search being performed)

**Process:** Lightweight per-turn context injection:
- If reading a file: inject its risk score, last modifier, dependent count
- If searching: inject relevant jargon expansions
- If in unmapped area: inject warning

**Output:** Small context block (<100 tokens) prepended to tool results

**Enables:** Just-in-time context without bloating every response. The AI gets relevant metadata exactly when operating on a file.

---

### Recursive Cartographer

**Input:** Session transcript (files accessed, directories traversed)

**Process:** At session end, extracts:
- Directories that were read from (mark as "explored")
- File paths accessed (update access timestamps)
- Potential jargon candidates (terms that appeared frequently near code paths)

Updates exploration map and queues jargon candidates for future confirmation.

**Output:** Updated `explored/` markers, session log, jargon candidates

**Enables:** Persistent exploration state. Session N+1 knows what session N discovered. Prevents redundant re-exploration.

---

## Phase 2: Git Intelligence

### Risk Scoring

**Input:** Git log for each tracked file

**Process:** Computes weighted risk score from:
- **Churn (30%):** `git log --since="30 days" --oneline <file> | wc -l` normalized
- **Author entropy (20%):** Unique authors / total commits (more authors = coordination risk)
- **Hotfix signal (25%):** Presence of "hotfix", "revert", "urgent" in commit messages
- **Age (10%):** Days since file creation (newer = less proven)
- **Size (15%):** Line count (larger = more surface area)

Scores normalized to 0.0-1.0 range.

**Output:** `risk-scores.json` with per-file scores and contributing factors

**Enables:** Triage. AI knows which files warrant extra caution before the first line is read. High-risk files get more careful treatment.

---

### Co-Modification Analysis

**Input:** Git log with `--name-only` to see files changed per commit

**Process:** Build co-occurrence matrix:
- For each commit, record all file pairs that changed together
- Weight by frequency (files always changed together score higher)
- Filter to statistically significant pairs (>3 co-occurrences)

**Output:** `co_modifications` section in relationships file

**Enables:** Hidden coupling detection. "When you change auth.py, you usually also change session.py" - even if there's no import relationship.

---

## Phase 3: Navigation

### Dictionary Translation

**Input:** User search queries and prompts

**Process:**
- Maintain YAML dictionary mapping business terms to code paths
- On search: expand query terms using dictionary
  - "cart" → also search "CartService", "basket", "checkout"
- On prompt: annotate recognized jargon with code references
  - "fix the cart bug" → "fix the cart bug [see: src/services/CartService.ts]"

Dictionary built incrementally from:
- Explicit user definitions
- Cartographer-discovered candidates
- README/doc mining

**Output:** Expanded search patterns, annotated prompts

**Enables:** Vocabulary bridging. User says "cart", AI searches for "CartService". No manual translation needed.

---

### Toll Booth

**Input:** File path being accessed

**Process:** Check path against exploration status:
- Is this directory marked as "explored"?
- Does it have a README_AI.md?
- Has any file in this area been accessed before?

If all checks fail: flag as unmapped territory.

**Output:** Warning annotation if entering unmapped area

**Enables:** Epistemic boundaries. AI knows when it's operating in well-understood vs. unknown territory. Can signal uncertainty appropriately.

---

## Phase 4: Safety

### Ripple Effect Analysis

**Input:** File about to be modified

**Process:**
- Parse import graph to find all files that import this file (direct dependents)
- Optionally traverse N levels (transitive dependents)
- Count total impact radius
- Flag if dependent count exceeds threshold (e.g., >10 dependents)

**Output:** Warning with dependent list, suggested test scope

**Enables:** Pre-change impact awareness. "This file has 47 dependents. Changes here have wide blast radius." AI can choose to make smaller, safer changes.

---

### Style Correction

**Input:** Code being written to a file

**Process:**
- Sample existing files in same directory to infer local style:
  - Indentation (tabs vs. spaces, width)
  - Quote style (single vs. double)
  - Import organization
  - Trailing commas, line length preferences
- Apply lightweight transformations to match

Does NOT reformat entire file - only normalizes the new code to blend in.

**Output:** Style-corrected code (or original if style unclear)

**Enables:** Consistency. AI-generated code matches project conventions without explicit style guides.

---

## Phase 5: Learning

### Failure Detection

**Input:** Tool results, user corrections

**Process:** Pattern match for failure signals:
- Tool exit codes != 0
- Error messages in output (exception traces, "not found", "permission denied")
- User messages containing corrections ("no, that's wrong", "actually it's X not Y")

Record failures with context:
- What file/operation failed
- What the error was
- Timestamp

**Output:** Failure log, updated knowledge annotations (mark unreliable entries)

**Enables:** Learning from mistakes. If reading file X always fails, future sessions know to avoid or handle specially.

---

### Trust Decay

**Input:** All knowledge entries with timestamps

**Process:** Apply decay function based on age:
- Base confidence: 1.0 at creation
- Decay rate: configurable per knowledge type (git data decays slower than session observations)
- Formula: `confidence = initial * decay_rate ^ days_since_verification`

Entries below threshold (e.g., 0.4) flagged as "verify before using".

**Output:** Updated confidence scores in knowledge files

**Enables:** Staleness awareness. Knowledge from 6 months ago is treated with appropriate skepticism. Prevents acting on outdated information.

---

### Trust Refresh

**Input:** Session activity log (what knowledge was accessed and used successfully)

**Process:**
- If a dictionary entry was used and the AI found the file: refresh to 1.0
- If a risk score guided a careful edit and no errors occurred: refresh
- If user explicitly confirmed something: refresh with "user verified" source

**Output:** Updated confidence scores (refreshed entries)

**Enables:** Self-healing knowledge. Accurate entries stay fresh through use. Stale/wrong entries decay and eventually get replaced.

---

## Phase 6: Dependencies

### Import Graph Building

**Input:** Python files as they're read during normal operation

**Process:** On each file read:
- Parse imports (both `import X` and `from X import Y`)
- Resolve relative imports to absolute paths
- Add edges to dependency graph: `this_file -> imported_file`

Graph builds incrementally - only files actually accessed get parsed.

**Output:** `relationships.yaml` with nodes (files) and edges (imports)

**Enables:** Architectural understanding. "What imports what" reveals module boundaries, core vs. peripheral code, potential circular dependencies.

---

### Orphan Detection

**Input:** Dependency graph + file listing

**Process:**
- Find all Python files in repo
- Filter to those with zero inbound edges (nothing imports them)
- Exclude known entry points (main.py, cli.py, test_*, etc.)
- Remaining files are orphan candidates

Categorize by confidence:
- 0.9+: Definitely orphaned (not an entry point pattern, nothing imports it)
- 0.7-0.9: Likely orphaned (might be dynamically loaded)
- <0.7: Possibly orphaned (unclear usage pattern)

**Output:** `orphans.yaml` with candidates and confidence scores

**Enables:** Dead code identification. Cleanup candidates surfaced without manual auditing.

---

### Freshness Tracking

**Input:** Git log for commit timestamps

**Process:** For each tracked file:
- Get last commit date: `git log -1 --format=%cI -- <file>`
- Calculate days since last modification
- Categorize: active (<30d), aging (30-90d), stale (90-180d), dormant (>180d)

**Output:** `freshness.json` with per-file status

**Enables:** Maintenance awareness. Dormant files may be abandoned. Active files are being maintained. Helps prioritize where to spend attention.

---

## Output Summary

| Layer | Primary Output | Format |
|-------|---------------|--------|
| Skeletons | `skeletons/*.shadow` | Compressed Python |
| Risk | `risk-scores.json` | `{file: {score, factors}}` |
| Dependencies | `relationships.yaml` | Node/edge graph |
| Orphans | `orphans.yaml` | Candidates with confidence |
| Freshness | `freshness.json` | Per-file staleness status |
| Dictionary | `dictionary.yaml` | Term → path mappings |
| Trust | `confidence.json` | Per-entry decay scores |
| Sessions | `sessions/*.json` | Exploration logs |

All outputs are designed to be:
1. **Parseable** - JSON/YAML for machine consumption
2. **Diffable** - Text-based for git tracking
3. **Incremental** - Updated, not regenerated
4. **Portable** - No dependencies on Claude Code specifically

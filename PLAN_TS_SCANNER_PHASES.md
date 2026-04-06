# Plan: TypeScript Scanner — Phases 2A through 2E

## Context

Phase 0 delivered a working TS scanner with 8 signals and 42 tests.
Phase 1 added import analysis, pipeline integration, and real-world validation against ccusage (120 files). The scanner now produces markdown output via `python xray.py /path/to/ts-project`.

**But the output is ~25% of the Python scanner's quality.** A detailed gap analysis identified 18 specific deficiencies across 5 categories. This plan addresses all of them in dependency order, from highest-impact/lowest-effort to lowest-impact/highest-effort.

### Quality Trajectory

| After Phase | Est. Quality | What Changes | Status |
|-------------|-------------|--------------|--------|
| 1 (current) | ~25% | Skeleton, complexity, basic imports, type coverage | Done |
| 2A | ~50% | Pillars work, git works, mermaid works, skeletons look right | Done |
| 2B | ~65% | Silent failures, security, deprecation, side effects, test detection | Done |
| 2C | ~75% | Call graph, topological layers, partial investigation targets | Done |
| 2D | ~85% | Logic maps, git function churn, full investigation targets | Done |
| 2E | ~90% | CLI args, config rules, decorator display, polish, edge cases | Done 2026-04-05 |

---

## Phase 2A — Integration Fixes + Git Analysis

**Goal:** Fix the plumbing so existing data actually renders. This is the highest-ROI phase — most of these gaps exist because the Python formatter/gap_features assume Python-style data shapes, not because the TS scanner lacks the data.

**Quality jump:** ~25% → ~50%

### Task 2A-1: Fix Architectural Pillars dedup

**Problem:** `gap_features.py:203` uses `mod_name.split(".")[-1]` to deduplicate modules. For Python dotted names like `lib.ast_analysis`, this yields `"ast_analysis"`. For TS paths like `apps/ccusage/src/data-loader.ts`, it yields `"ts"` — every file deduplicates to the same key. Only 1 pillar survives.

**File:** `lib/gap_features.py`, function `get_architectural_pillars()` (line 173)

**Fix:**
```python
# Line 203: Replace
short_name = mod_name.split(".")[-1]
# With
if "/" in mod_name:
    short_name = Path(mod_name).stem  # "data-loader" from "apps/.../data-loader.ts"
else:
    short_name = mod_name.split(".")[-1]  # "ast_analysis" from "lib.ast_analysis"
```

Also fix line 211 (filepath matching) to handle both formats:
```python
# The existing mod_name.replace(".", "/") is fine for Python names
# For TS paths (already slash-delimited), the "mod_name in fp" check works
# No change needed here — the first condition catches TS paths
```

**Verification:** `python xray.py /tmp/ccusage 2>/dev/null | grep -A 12 "Architectural Pillars"` should show 10 rows with data-loader.ts, logger.ts, etc.

---

### Task 2A-2: Fix Mermaid safe IDs and layer lookup

**Problem (IDs):** `gap_features.py:577` generates mermaid node IDs with `mod.replace(".", "_")`. TS paths contain `/` which are not replaced, producing invalid mermaid IDs like `apps/ccusage/src/data_loader_ts`.

**Problem (Layers):** `gap_features.py:563` iterates over `["orchestration", "core", "foundation"]`. The TS scanner emits layer names like `"api"`, `"services"`, `"utils"`, `"other"`. Zero overlap → blank diagram.

**File:** `lib/gap_features.py`, function `generate_mermaid_diagram()` (line 543)

**Fix:**
1. Add a `_safe_mermaid_id()` helper that handles both formats:
   ```python
   def _safe_mermaid_id(name):
       """Convert module name to valid mermaid node ID."""
       return re.sub(r'[^a-zA-Z0-9_]', '_', name)
   ```
   Replace all `mod.replace(".", "_").replace("-", "_")` calls with `_safe_mermaid_id(mod)`.

2. Add a `_normalize_layers()` helper that maps TS directory-based layer names to the three tiers the mermaid function expects:
   ```python
   _TIER_MAP = {
       # Foundation: imported by many, imports few
       "utils": "foundation", "types": "foundation", "config": "foundation",
       "models": "foundation", "state": "foundation",
       # Core: business logic
       "services": "core", "middleware": "core", "hooks": "core",
       # Orchestration: imports many, imported by few
       "api": "orchestration", "components": "orchestration", "pages": "orchestration",
       # Tests are excluded from architecture diagrams
       "tests": None,
   }

   def _normalize_layers(layers):
       """Map TS directory-based layers to foundation/core/orchestration tiers."""
       if any(k in ("foundation", "core", "orchestration") for k in layers):
           return layers  # Already Python-style tiers
       tiers = {"foundation": [], "core": [], "orchestration": []}
       for layer_name, modules in layers.items():
           tier = _TIER_MAP.get(layer_name)
           if tier:
               tiers[tier].extend(modules)
           elif layer_name != "tests":
               tiers["core"].extend(modules)  # Unknown → core
       return tiers
   ```
   Call `_normalize_layers(layers)` at the top of `generate_mermaid_diagram()`.

3. Also fix `_safe_mermaid_id()` usage in `_short_name()` helper:
   ```python
   def _short_name(mod_name):
       if "/" in mod_name:
           return Path(mod_name).stem
       return mod_name.split(".")[-1]
   ```

Also fix `_infer_data_flow()` (line 465) which has the same hardcoded layer name issue.

**Verification:** `python xray.py /tmp/ccusage 2>/dev/null | grep -A 30 "mermaid"` should show a populated graph with subgraphs and edges.

---

### Task 2A-3: Make git_analysis.py language-aware

**Problem:** Every function in `git_analysis.py` hardcodes `.py` file extension filters. Six filter points (lines 68, 106, 168, 218, 270, 519) plus the function churn regex (line 364) that only matches Python `def`/`class` keywords.

**File:** `lib/git_analysis.py`

**Fix — Extension filters (6 points):**

Add a module-level constant and helper:
```python
DEFAULT_EXTENSIONS = (".py",)
TS_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

def _matches_extensions(filename, extensions):
    """Check if filename ends with any of the given extensions."""
    return filename.endswith(extensions)
```

Then update each function to accept `extensions: tuple = DEFAULT_EXTENSIONS`:

| Line | Current | Change to |
|------|---------|-----------|
| 68 | `run_git(["ls-files", "*.py"], cwd)` | `run_git(["ls-files"] + [f"*{ext}" for ext in extensions], cwd)` |
| 106 | `line.endswith(".py")` | `_matches_extensions(line, extensions)` |
| 168 | `line.strip().endswith(".py")` | `_matches_extensions(line.strip(), extensions)` |
| 218 | `line.endswith(".py")` | `_matches_extensions(line, extensions)` |
| 270 | `filepath.endswith('.py')` | `_matches_extensions(filepath, extensions)` |
| 519 | `line.endswith(".py")` | `_matches_extensions(line, extensions)` |

**Fix — Function churn regex (line 364):**

The current regex only matches Python function/class definitions:
```python
hunk_re = re.compile(r'^@@ .+ @@\s+(?:(?:async\s+)?def|class)\s+(\w+)')
```

Add a TS-aware variant:
```python
PYTHON_HUNK_RE = re.compile(r'^@@ .+ @@\s+(?:(?:async\s+)?def|class)\s+(\w+)')
TS_HUNK_RE = re.compile(
    r'^@@ .+ @@\s+'
    r'(?:export\s+(?:default\s+)?)?'
    r'(?:(?:async\s+)?function\s+(\w+)'
    r'|class\s+(\w+)'
    r'|(?:const|let|var)\s+(\w+)\s*=)'
)
```

Select the regex based on the extensions parameter.

**Wire into xray.py:**

Update `_augment_with_git()` and `run_analysis()` to pass the right extensions based on detected language:
```python
extensions = TS_EXTENSIONS if language in ("typescript", "mixed") else DEFAULT_EXTENSIONS
tracked_files = get_tracked_files(target, extensions=extensions)
risk = analyze_risk(target, tracked_files, extensions=extensions, verbose=verbose)
# ... same for all other git functions
```

**Verification:** `python xray.py /tmp/ccusage --verbose 2>/dev/null | grep -A 20 "Git History"` should show populated risk, coupling, and freshness sections.

---

### Task 2A-4: Fix class skeleton syntax in formatter

**Problem:** The formatter renders TS class methods using Python-style `def method(...)` syntax instead of TypeScript-style `method(...)`.

**File:** `formatters/markdown_formatter.py`

**Current output:**
```typescript
class TerminalManager:  # L24
    def constructor(...)
    def hideCursor(...)
```

**Expected output:**
```typescript
class TerminalManager {  // L24
    constructor(...)
    hideCursor(...)
```

**Fix:** In the Critical Classes section (~lines 230-270), make the skeleton rendering language-aware:

```python
if code_lang == "typescript":
    lines.append(f"class {cls['name']}{bases} {{  // L{cls.get('line', 0)}")
    # ...
    for method in methods:
        prefix = "async " if method.get("is_async") else ""
        lines.append(f"    {prefix}{method['name']}(...)")
else:
    lines.append(f"class {cls['name']}{bases}:  # L{cls.get('line', 0)}")
    # ... existing Python-style rendering
```

Also fix the method signature section (~line 489-491) to use `function` or bare name instead of `def`.

**Verification:** Class skeletons in output use `{}` braces, `//` comments, and bare method names.

---

### Task 2A-5: Fix orphan deduplication

**Problem:** Orphan display shows duplicates (`eslint.config.js` appears twice because multiple `apps/*/` dirs each have one).

**File:** `formatters/markdown_formatter.py`, orphan rendering section (~line 818)

**Fix:** Deduplicate orphan display names before rendering:
```python
seen_orphan_names = set()
for orphan in orphans[:10]:
    display = ...  # existing logic
    if display not in seen_orphan_names:
        seen_orphan_names.add(display)
        lines.append(f"- `{display}`")
```

**Verification:** No duplicate orphan names in output.

---

### Phase 2A Files Modified

| File | Est. Lines Changed |
|------|-------------------|
| `lib/gap_features.py` | +60 (pillar dedup, mermaid IDs, layer mapping, short names) |
| `lib/git_analysis.py` | +40 (extensions param, TS hunk regex) |
| `xray.py` | +15 (pass extensions to git functions) |
| `formatters/markdown_formatter.py` | +40 (class syntax, method syntax, orphan dedup) |

### Phase 2A Verification

```bash
# 1. Pillars populated
python xray.py /tmp/ccusage 2>/dev/null | grep -c "| .* | .* modules |"
# Expected: 10 rows

# 2. Mermaid has nodes
python xray.py /tmp/ccusage 2>/dev/null | grep -c "subgraph"
# Expected: >= 2

# 3. Git sections populated
python xray.py /tmp/ccusage 2>/dev/null | grep -A 3 "High-Risk Files"
# Expected: table with files

# 4. TS-style class skeletons
python xray.py /tmp/ccusage 2>/dev/null | grep "def constructor"
# Expected: no matches (should use bare "constructor")

# 5. Python tests still pass
python -m pytest tests/ -x -q

# 6. TS tests still pass
cd ts-scanner && npm test
```

---

## Phase 2B — Behavioral Signals (AST Pattern Matching)

**Goal:** Add 5 new signals to the TS scanner's AST walk. These are all pattern-matching on known API calls or syntax patterns — no new analysis architecture needed.

**Quality jump:** ~50% → ~65%

### Task 2B-1: Silent failure detection

**What:** Detect `catch` clauses with empty blocks or trivial handlers (just `console.log`/`console.error`).

**File:** `ts-scanner/src/ast-analysis.ts` — add detection in `walkPass1()`

**Detection patterns:**
```typescript
// In the AST walk, when encountering a CatchClause:
if (ts.isCatchClause(node)) {
    const block = node.block;
    const stmtCount = block.statements.length;
    if (stmtCount === 0) {
        // Empty catch — definitely a silent failure
        result.silent_failures.push({ type: "empty_catch", line: ..., context: "catch with empty block" });
    } else if (stmtCount === 1 && isConsoleCall(block.statements[0])) {
        // Catch that only logs — likely swallowing error
        result.silent_failures.push({ type: "logged_catch", line: ..., context: "catch only logs, does not rethrow" });
    }
}
```

**Estimated size:** ~50 lines in ast-analysis.ts

---

### Task 2B-2: Security concern detection

**What:** Detect dangerous API calls and patterns.

**File:** `ts-scanner/src/ast-analysis.ts`

**Detection patterns:**

| Pattern | TS Expression | Severity |
|---------|--------------|----------|
| `eval()` | `eval(...)` | high |
| `new Function()` | `new Function(...)` | high |
| `innerHTML` assignment | `el.innerHTML = ...` | medium |
| `dangerouslySetInnerHTML` | JSX attribute | medium |
| `child_process.exec` | `exec(...)`, `execSync(...)` | high |
| `document.write` | `document.write(...)` | medium |

**Detection approach:** In the AST walk, check `CallExpression` and `PropertyAccessExpression` nodes against a lookup table of known dangerous patterns.

**Estimated size:** ~60 lines

---

### Task 2B-3: Deprecation marker detection

**What:** Find `@deprecated` JSDoc tags and decorator patterns.

**File:** `ts-scanner/src/ast-analysis.ts`

**Detection approach:** The JSDoc parsing infrastructure already exists (`getJSDocSummary()`). Extend it:
```typescript
function getDeprecationInfo(node: ts.Node): { deprecated: boolean; reason: string | null } {
    const jsDocs = ts.getJSDocCommentsAndTags(node);
    for (const doc of jsDocs) {
        if (ts.isJSDocDeprecatedTag(doc)) {
            return { deprecated: true, reason: doc.comment ? String(doc.comment) : null };
        }
    }
    // Also check for @Deprecated() decorator
    // ...
    return { deprecated: false, reason: null };
}
```

**Estimated size:** ~40 lines

---

### Task 2B-4: Side effect detection

**What:** Identify I/O operations, network calls, process management, and other side effects.

**File:** `ts-scanner/src/ast-analysis.ts`

**Detection patterns:**

| Category | Patterns |
|----------|---------|
| `file_io` | `fs.readFileSync`, `fs.writeFileSync`, `fs.readFile`, `fs.writeFile`, `fs.mkdir`, `fs.rm`, `fs.unlink` |
| `network` | `fetch(`, `axios.`, `http.request`, `http.get`, `https.`, `XMLHttpRequest` |
| `subprocess` | `child_process.exec`, `child_process.spawn`, `execSync`, `spawnSync` |
| `process` | `process.exit`, `process.kill` |
| `console` | `console.log`, `console.error`, `console.warn` |
| `database` | `prisma.`, `.query(`, `.execute(`, `mongoose.`, `knex(`, `sequelize.` |
| `environment` | `process.env` |

**Detection approach:** When visiting `CallExpression` or `PropertyAccessExpression` nodes, check if the expression text matches any known pattern. Record category, call text, and line number.

**Estimated size:** ~150 lines (the pattern table is the bulk)

---

### Task 2B-5: Test file detection

**What:** Identify test files, count test functions, extract testing patterns.

**File:** New file `ts-scanner/src/test-analysis.ts` (~100 lines)

**Detection approach:**
1. Classify files by naming convention: `*.test.ts`, `*.spec.ts`, files in `__tests__/`, `test/`
2. For test files, count `describe()`, `it()`, `test()`, `expect()` calls in the AST
3. Detect test framework from imports (`vitest`, `jest`, `mocha`, `@testing-library/*`)

**Output shape:** Matches Python's `tests` key:
```json
{
    "test_file_count": 15,
    "test_function_count": 87,
    "test_framework": "vitest",
    "test_files": ["src/__tests__/utils.test.ts", ...]
}
```

**Wire into `index.ts`:** Call after file analysis, include in output JSON.

---

### Phase 2B Files Modified/Created

| File | Action | Est. Lines |
|------|--------|-----------|
| `ts-scanner/src/ast-analysis.ts` | Modify — add silent failures, security, deprecation, side effects | +300 |
| `ts-scanner/src/test-analysis.ts` | Create — test file detection and counting | +100 |
| `ts-scanner/src/index.ts` | Modify — wire test analysis into output | +15 |
| `ts-scanner/src/types.ts` | Modify — ensure stub interfaces match new data | +10 |
| `ts-scanner/test/ast-analysis.test.ts` | Modify — add tests for new signals | +80 |
| `ts-scanner/test/test-analysis.test.ts` | Create — tests for test detection | +40 |

### Phase 2B Verification

```bash
# 1. Silent failures detected
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '[.structure.files[] | .silent_failures | length] | add'

# 2. Side effects detected
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.side_effects.by_type | keys'

# 3. Security concerns (may be 0 for clean codebases)
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '[.structure.files[] | .security_concerns | length] | add'

# 4. Test detection
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.tests'

# 5. Deprecation markers
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.deprecation_markers | length'

# 6. End-to-end
python xray.py /tmp/ccusage 2>/dev/null | grep -c "Silent Failure\|Security\|Side Effect"

# 7. All tests pass
cd ts-scanner && npm test
python -m pytest tests/ -x -q
```

---

## Phase 2C — Call Graph + Topological Layering

**Goal:** Add cross-module call analysis and compute architecture tiers from the import graph structure rather than directory names alone. This unlocks partial investigation targets.

**Quality jump:** ~65% → ~75%

### Task 2C-1: Cross-module call analysis

**What:** Track which functions call which functions across module boundaries. Build caller/callee graph with fan-in counts.

**File:** New file `ts-scanner/src/call-analysis.ts` (~350 lines)

**Why this is harder than Python:**

Python call sites are usually `module.function()` — the module name is visible in the call expression. TypeScript destructures imports:
```typescript
import { createUser } from "./user-service"
// ...
createUser(input)  // No module prefix — need to track the import binding
```

**Approach — Import binding table:**

1. During import parsing (or a second pass), build a `Map<string, { sourceFile: string, exportedName: string }>` that maps local names to their source modules.
2. During the AST walk, when encountering a `CallExpression` where the callee is an `Identifier`, look it up in the binding table.
3. For `PropertyAccessExpression` calls like `mod.func()`, check if `mod` is a namespace import (`import * as mod from "./bar"`).

**What this misses (and why that's OK):**
- Re-exported bindings through barrel files (`export { foo } from "./bar"`) — these require transitive resolution. Can be added later with the existing import graph.
- Computed property calls (`obj[methodName]()`) — not statically resolvable. Python misses these too.
- Method calls on imported class instances (`const svc = new UserService(); svc.createUser()`) — requires type inference. Phase 5 (semantic tier) would handle this.

**Estimated coverage:** ~80% of cross-module calls in typical TS codebases. Python scanner gets ~85-90%.

**Output shape:** Matches `CallAnalysis` interface in `types.ts`:
```json
{
    "cross_module": { "user-service.createUser": { "call_count": 3, "call_sites": [...] } },
    "reverse_lookup": { "user-service.createUser": { "caller_count": 2, "impact_rating": "medium", "callers": [...] } },
    "most_called": [...],
    "most_callers": [...],
    "isolated_functions": [...],
    "high_impact": [...],
    "summary": { "total_cross_module_calls": 45, ... }
}
```

---

### Task 2C-2: Topological layer computation

**What:** Compute `foundation`/`core`/`orchestration`/`leaf` tiers from import graph structure, mirroring the Python scanner's `identify_layers()` (import_analysis.py:516).

**File:** `ts-scanner/src/import-analysis.ts` — add to existing module (~80 lines)

**Algorithm (mirrors Python exactly):**
```
For each module:
    ratio = imported_by_count / (imports_count + 1)
    
    if name matches ORCHESTRATION_KEYWORDS: → orchestration
    elif name matches FOUNDATION_KEYWORDS: → foundation
    elif imported_by == 0 and imports == 0: → leaf
    elif ratio > 2: → foundation  (imported far more than it imports)
    elif ratio < 0.5 and imports > 2: → orchestration  (imports many, imported by few)
    else: → core
```

**Keywords to add:**
```typescript
const ORCHESTRATION_KEYWORDS = /\b(app|main|cli|server|index|run|bootstrap|orchestrat|coordinat|workflow|pipeline)\b/i;
const FOUNDATION_KEYWORDS = /\b(util|utils|helper|common|shared|base|config|constants?|types?|interfaces?|lib)\b/i;
```

**Output:** Add a `tiers` field alongside existing `layers` in the import analysis output:
```json
{
    "layers": { "api": [...], "services": [...], ... },
    "tiers": { "foundation": [...], "core": [...], "orchestration": [...], "leaf": [...] }
}
```

The formatter and mermaid generator read `tiers` when available, falling back to `layers`.

---

### Task 2C-3: Partial investigation targets

**What:** Wire the TS scanner data into `investigation_targets.py` so the sub-functions that already work with TS data produce output.

**File:** `xray.py` — modify the TS scanner code path to call `compute_investigation_targets()`

**What works already (from the research):**

| Sub-function | Works with TS? | Needs |
|---|---|---|
| `compute_ambiguous_interfaces` | **YES** | ast_results shape match |
| `compute_coupling_anomalies` | **YES** | git coupling + import graph |
| `compute_convention_deviations` (return types) | **PARTIAL** | ast_results shape match |
| `compute_high_uncertainty_modules` | **MOSTLY** | ast_results + call_results |
| `compute_entry_side_effect_paths` | **PARTIAL** | entry_points + side_effects + call graph |
| `compute_domain_entities` | **PARTIAL** | data_models + type annotations |
| `compute_shared_mutable_state` | **NO** | Uses Python `ast.parse()` — needs TS rewrite |

**Approach:**

1. After invoking the TS scanner, reshape its output to match the `ast_results` structure that `investigation_targets.py` expects. The key mapping:
   ```python
   # TS scanner emits structure.files.{path}.functions[].complexity
   # investigation_targets expects files.{path}.functions[].complexity
   # They're the same shape — just need to wire it
   ```

2. Build `gap_results` with TS-aware entry points and data models:
   - Entry points: already computed by `detect_entry_points()` (updated in Phase 1)
   - Data models: map TS interfaces/type aliases to the `data_models` format:
     ```python
     # TS scanner emits ts_interfaces, ts_type_aliases per file
     # Convert to: {"name": "User", "type": "interface", "file": "...", "fields": [...]}
     ```

3. For `compute_convention_deviations`, add `"constructor"` alongside `"__init__"` in the pattern check.

4. For `compute_shared_mutable_state`, catch the `SyntaxError` silently (it already does) — this sub-function will remain empty for TS until Phase 2D.

5. Expand `_BUILTIN_TYPES` in `compute_domain_entities` to include TS builtins: `Promise`, `Record`, `Partial`, `Required`, `Omit`, `Pick`, `Readonly`, `Array`, `Map`, `Set`.

**Estimated changes:** ~60 lines in `xray.py`, ~20 lines in `investigation_targets.py`, ~10 lines in `gap_features.py`

---

### Phase 2C Files Modified/Created

| File | Action | Est. Lines |
|------|--------|-----------|
| `ts-scanner/src/call-analysis.ts` | Create — cross-module call graph | +350 |
| `ts-scanner/src/import-analysis.ts` | Modify — add topological tier computation | +80 |
| `ts-scanner/src/index.ts` | Modify — wire call analysis, emit tiers | +20 |
| `ts-scanner/test/call-analysis.test.ts` | Create — call graph tests | +120 |
| `xray.py` | Modify — reshape TS data for investigation targets | +60 |
| `lib/investigation_targets.py` | Modify — TS compatibility (constructor, builtins) | +20 |
| `lib/gap_features.py` | Modify — TS data models extraction | +30 |

### Phase 2C Verification

```bash
# 1. Call graph populated
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.calls.summary'

# 2. Topological tiers computed
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.imports.tiers | keys'

# 3. Investigation targets in markdown
python xray.py /tmp/ccusage 2>/dev/null | grep -A 10 "Investigation Targets"

# 4. All tests pass
cd ts-scanner && npm test
python -m pytest tests/ -x -q
```

---

## Phase 2D — Logic Maps + Advanced Git + Full Investigation Targets

**Goal:** Add the most complex remaining signals. These require significant new code but are what separate a "useful summary" from a "comprehensive analysis."

**Quality jump:** ~75% → ~85%

### Task 2D-1: Logic maps (control flow visualization)

**What:** For the top N complex functions, generate a textual control-flow representation showing decision branches, loops, early returns, and exception handling.

**File:** New file `ts-scanner/src/logic-maps.ts` (~400 lines) OR addition to `ast-analysis.ts`

**Algorithm:**
```
Walk function body depth-first:
    IfStatement → "→ <condition>?"
        ThenBranch → indent, recurse
        ElseBranch → "else:" indent, recurse
    SwitchStatement → "→ switch(<expr>)"
        CaseClause → "case <value>:" indent, recurse
    ForStatement/WhileStatement → "→ for/while <condition>:"
    TryStatement → "try:"
        CatchClause → "catch <type>:"
    ReturnStatement → "→ Return(<expr summary>)"
    ThrowStatement → "→ Throw(<expr summary>)"
```

**TS-specific considerations:**
- Optional chaining (`foo?.bar()`) is a hidden branch — should be noted
- Nullish coalescing (`a ?? b`) is a hidden branch
- Type narrowing (`if (typeof x === "string")`) — the condition text is useful context
- `switch` with exhaustive checks (common in TS with union types) — note exhaustiveness

**Output shape:**
```json
{
    "function": "loadTokenUsageEvents",
    "file": "data-loader.ts",
    "line": 187,
    "complexity": 40,
    "summary": "Iterates over 2 collections. 28 decision branches. Handles 3 exception types.",
    "map": "→ options.startDate?\n  → filter by date\n→ for event of events:\n  → event.type === 'usage'?\n    → ..."
}
```

**Honest difficulty:** This is ~400 lines of careful AST traversal. The algorithm itself is straightforward (depth-first walk emitting indented text), but producing *readable* output requires judgment about what to abbreviate. The Python version took several iterations. Budget 1 day.

---

### Task 2D-2: Git function churn for TypeScript

**What:** Detect which functions changed most frequently in git history, using TS-aware hunk header parsing.

**File:** `lib/git_analysis.py`, function `analyze_function_churn()` (line 341)

**Current state:** The hunk regex (line 364) only matches `def`/`class` — Python keywords.

**Fix:** Add TS-aware regex (from Phase 2A-3 — the regex is defined there, this task adds the selection logic):
```python
def analyze_function_churn(cwd, files, extensions=DEFAULT_EXTENSIONS, verbose=False):
    is_ts = any(ext in ('.ts', '.tsx', '.js', '.jsx') for ext in extensions)
    hunk_re = TS_HUNK_RE if is_ts else PYTHON_HUNK_RE
    # ... rest of function uses hunk_re
```

The TS regex needs to handle multiple capture groups (function name can be in group 1, 2, or 3 depending on the construct). Extract with:
```python
match = hunk_re.match(line)
if match:
    func_name = match.group(1) or match.group(2) or match.group(3)
```

**Honest limitation:** Git's built-in hunk context detection for JS/TS is imperfect. Arrow functions assigned to `const` are sometimes missed in hunk headers because git doesn't recognize `const foo = (` as a function boundary. The result will be ~70% as accurate as the Python version for function-level churn. This is a git limitation, not a scanner limitation.

---

### Task 2D-3: Full investigation targets

**What:** With call graph, side effects, and git analysis all working from earlier phases, enable the remaining investigation target sub-functions.

**File:** `xray.py`, `lib/investigation_targets.py`

**Specifically:**

1. `compute_entry_side_effect_paths` — now works because Phase 2B added side effects and Phase 2C added the call graph. The BFS from entry points through the call graph to side-effect-producing functions is language-neutral.

2. `compute_domain_entities` — now works because Phase 2C added TS data model extraction.

3. `compute_shared_mutable_state` — **still won't work** (uses Python `ast.parse()`). Two options:
   - **Option A:** Add a TS-native shared-state detector in the TS scanner that finds module-level `let`/`var` declarations and class static fields. Emit as `shared_mutable_state` in the JSON. Have the investigation targets code read this instead of re-parsing. (~100 lines in TS scanner)
   - **Option B:** Skip it. It's 1 of 7 sub-functions. The other 6 will produce useful output.

**Recommendation:** Option A — it's not much code and module-level mutable state is a genuinely useful signal.

---

### Task 2D-4: Shared mutable state detection (TS-native)

**What:** Detect module-level mutable state — `let`/`var` declarations at module scope, class static mutable fields, singleton patterns.

**File:** `ts-scanner/src/ast-analysis.ts` — add during AST walk

**Detection:**
```typescript
// Module-level let/var (not const)
if (ts.isVariableStatement(node) && ctx.depth === 0) {
    const flags = node.declarationList.flags;
    if (!(flags & ts.NodeFlags.Const)) {
        // This is a module-level let or var — mutable state
        for (const decl of node.declarationList.declarations) {
            result.shared_mutable_state.push({
                name: decl.name.getText(),
                kind: "module_variable",
                line: getLineNumber(decl, ctx.sourceFile),
            });
        }
    }
}
```

**Estimated size:** ~50 lines

---

### Phase 2D Files Modified/Created

| File | Action | Est. Lines |
|------|--------|-----------|
| `ts-scanner/src/logic-maps.ts` | Create — control flow visualization | +400 |
| `ts-scanner/src/ast-analysis.ts` | Modify — shared mutable state detection | +50 |
| `ts-scanner/src/index.ts` | Modify — wire logic maps, shared state | +15 |
| `lib/git_analysis.py` | Modify — TS function churn regex selection | +20 |
| `xray.py` | Modify — wire full investigation targets | +30 |
| `ts-scanner/test/logic-maps.test.ts` | Create — logic map tests | +80 |

### Phase 2D Verification

```bash
# 1. Logic maps generated for top hotspots
python xray.py /tmp/ccusage 2>/dev/null | grep -A 5 "Logic Map\|Summary:"

# 2. Function churn populated
python xray.py /tmp/ccusage 2>/dev/null | grep -A 10 "Function-Level Hotspots"

# 3. Full investigation targets
python xray.py /tmp/ccusage 2>/dev/null | grep -A 20 "Investigation Targets"

# 4. All tests pass
cd ts-scanner && npm test
python -m pytest tests/ -x -q
```

---

## Phase 2E — Polish + Edge Cases

**Goal:** Handle the remaining ~5% of gaps and improve output quality for edge cases.

**Quality jump:** ~85% → ~90%

### Task 2E-1: CLI argument extraction (best-effort)

**What:** Detect common CLI frameworks and extract argument definitions.

**File:** `ts-scanner/src/ast-analysis.ts` or new `ts-scanner/src/cli-analysis.ts`

**Approach — framework detection only (not full argument extraction):**

Full argument extraction across 10+ TS CLI frameworks is fragile and high-maintenance. Instead, take a pragmatic approach:

1. **Detect which framework is used** from import statements:
   ```
   commander → "commander"
   yargs → "yargs"
   meow → "meow"
   cac → "cac"
   gunshi → "gunshi"
   clipanion → "clipanion"
   ```

2. **For commander and yargs (the two most common)**, extract arguments by pattern-matching `.option()` and `.command()` calls. These two frameworks cover ~70% of TS CLI projects.

3. **For others**, report the framework name without argument details. This still provides useful context ("this project uses gunshi for CLI parsing").

**Honest scope:** This will never match Python's argparse extraction quality, because argparse has a single API (`add_argument`) while TS has a dozen frameworks. Getting 70% coverage of the CLI landscape is realistic; 95% is not worth the maintenance burden.

**Estimated size:** ~150 lines for detection + commander/yargs extraction

---

### Task 2E-2: Decorator aggregation in markdown

**What:** The TS scanner collects decorator usage counts but the markdown output doesn't display them.

**File:** `formatters/markdown_formatter.py`

**Fix:** The decorator inventory section already exists in the formatter for Python. Check if it triggers for TS data:
- The TS scanner emits `decorators.inventory` with counts
- The formatter should render it if non-empty
- May just need a gate check fix

**Estimated size:** ~5 lines (likely just a conditional check)

---

### Task 2E-3: Context hazards improvements

**What:** The TS output only shows 1 skip directory (`.git/`). Should also flag `node_modules/`, `dist/`, `.next/`, etc.

**File:** `formatters/markdown_formatter.py` or `lib/gap_features.py` — wherever skip directories are computed

**Fix:** Add TS-standard directories to the skip list when language is TypeScript:
```python
if lang in ("typescript", "mixed"):
    skip_dirs.extend(["node_modules/", "dist/", "build/", ".next/", ".nuxt/", "coverage/"])
```

**Estimated size:** ~10 lines

---

### Task 2E-4: Re-export resolution in import graph

**What:** Barrel files (`index.ts` with `export { foo } from "./bar"`) are common in TS. The import graph currently treats the barrel as the dependency rather than resolving through to the actual source.

**File:** `ts-scanner/src/import-analysis.ts`

**Approach:** After building the initial graph, detect barrel files (files where >50% of exports are re-exports) and optionally add transitive edges. This improves the accuracy of hub module detection and layer classification.

**Estimated size:** ~60 lines

**Honest note:** This is a nice-to-have. The import graph without re-export resolution is still useful — it just over-counts barrel files as hubs and under-counts the actual source modules. For most projects, the impact on output quality is small (~2-3% improvement).

---

### Task 2E-5: Persona map for TS projects

**What:** The persona map detects agent/prompt markdown files in the repository. This is actually language-agnostic — it reads `.md` files, not code.

**File:** `lib/gap_features.py`

**Check:** Verify that `detect_personas()` (or equivalent) runs regardless of language. If it's gated behind Python-specific checks, remove the gate.

**Estimated size:** ~5 lines (likely just removing a conditional)

---

### Phase 2E Files Modified/Created

| File | Action | Est. Lines |
|------|--------|-----------|
| `ts-scanner/src/cli-analysis.ts` | Create — CLI framework detection | +150 |
| `ts-scanner/src/import-analysis.ts` | Modify — re-export resolution | +60 |
| `formatters/markdown_formatter.py` | Modify — decorator display, context hazards | +15 |
| `lib/gap_features.py` | Modify — persona map gate, skip dirs | +15 |

### Phase 2E Verification

```bash
# 1. CLI framework detected
node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.cli_framework'

# 2. Decorator section in output
python xray.py /tmp/ccusage 2>/dev/null | grep -A 5 "Decorator"

# 3. Skip directories
python xray.py /tmp/ccusage 2>/dev/null | grep "node_modules\|dist/"

# 4. All tests pass
cd ts-scanner && npm test
python -m pytest tests/ -x -q
```

---

## Dependency Graph

```
Phase 2A (Integration Fixes + Git)
    ├── 2A-1: Pillar dedup          (standalone)
    ├── 2A-2: Mermaid IDs + layers  (standalone, but improved by 2C-2)
    ├── 2A-3: Git language-aware    (standalone)
    ├── 2A-4: Class skeleton syntax (standalone)
    └── 2A-5: Orphan dedup          (standalone)

Phase 2B (Behavioral Signals)         ← can start in parallel with 2A
    ├── 2B-1: Silent failures       (standalone)
    ├── 2B-2: Security concerns     (standalone)
    ├── 2B-3: Deprecation markers   (standalone)
    ├── 2B-4: Side effects          (standalone, feeds 2D-3)
    └── 2B-5: Test detection        (standalone)

Phase 2C (Call Graph + Layers)        ← depends on 2A (git), 2B (side effects) for full value
    ├── 2C-1: Cross-module calls    (needs import graph from Phase 1)
    ├── 2C-2: Topological layers    (improves 2A-2 mermaid)
    └── 2C-3: Investigation targets (needs 2A-3 git, 2B-4 side effects, 2C-1 calls)

Phase 2D (Advanced Signals)           ← depends on 2B, 2C
    ├── 2D-1: Logic maps            (standalone, needs AST walk infrastructure)
    ├── 2D-2: Git function churn    (needs 2A-3 git extensions)
    ├── 2D-3: Full investigation    (needs 2C-3 partial + 2B-4 side effects + 2C-1 calls)
    └── 2D-4: Shared mutable state  (standalone AST addition)

Phase 2E (Polish)                     ← depends on everything above
    ├── 2E-1: CLI arg extraction    (standalone)
    ├── 2E-2: Decorator display     (standalone)
    ├── 2E-3: Context hazards       (standalone)
    ├── 2E-4: Re-export resolution  (needs Phase 1 import graph)
    └── 2E-5: Persona map           (standalone)
```

---

## Estimated Total Effort

| Phase | Tasks | New Lines | Modified Lines | Calendar Time |
|-------|-------|-----------|----------------|---------------|
| 2A | 5 | ~0 | ~155 | Half day |
| 2B | 5 | ~540 | ~90 | 1 day |
| 2C | 3 | ~550 | ~110 | 2-3 days |
| 2D | 4 | ~550 | ~65 | 2-3 days |
| 2E | 5 | ~225 | ~35 | 1 day |
| **Total** | **22** | **~1,865** | **~455** | **~7-8 days** |

---

## What This Does NOT Cover

- **Semantic tier (Phase 5):** Running `tsc` for full type resolution. This would unlock ~95%+ parity for call graph resolution, re-export handling, and type-aware analysis. Architecturally different — requires creating a TypeScript Program object with full module resolution. Not planned here.

- **Deep crawl TS adaptation (Phase 4):** Modifying the deep-crawl skill to use TS scanner signals. Once Phases 2A-2D are complete, the deep crawl pipeline should work automatically since it reads the same JSON keys. Phase 4 would focus on TS-specific investigation strategies (e.g., "check generic type constraints" or "trace React component prop drilling").

- **Multi-language (mixed) projects:** Currently, `xray.py` runs either the Python scanner or the TS scanner based on `detect_language()`. True mixed-language support (Python + TS in the same repo) would require merging results from both scanners. Deferred.

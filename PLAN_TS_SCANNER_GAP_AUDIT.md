# Gap Audit: TS Scanner Plan vs Actual Python Output

Audited against:
- **Python xray.md** — 953 lines, 35+ sections (from `python xray.py .`)
- **R14 DEEP_ONBOARD.md** — 5,111 lines, 20+ major sections (from deep_crawl of Kosmos, 802 files)
- **R14 CRAWL_PLAN.md** — 46 investigation tasks across 7 priority tiers

## Part 1: xray.md Section-by-Section Audit

Every section from the Python xray.md output, whether it's covered in the plan, and what's missing.

### Already Working (no plan needed)

| Section | TS Status | Notes |
|---------|-----------|-------|
| Summary table | Working | "Source files" label correct, all metrics populated |
| Complexity Hotspots | Working | Top 10 by CC, fully populated |
| Import Verification | Working | 213 passed, 0 failed |
| Quick Verification | Working | Uses `npx tsx` correctly |
| External Dependencies | Working | 42 packages listed |
| Async Patterns | Working | 71 async, 182 sync, 2 async-for |

### Covered in Plan (Phases 2A-2E)

| Section | Plan Phase | Status |
|---------|-----------|--------|
| Architecture Overview (prose) | 2A-2, 2C-2 | Layer counts wrong ("1 architectural layers (120 other)") |
| Architecture Diagram (Mermaid) | 2A-2 | Blank — layer names + safe IDs |
| Architectural Pillars | 2A-1 | Only 1 row — dedup bug |
| Maintenance Hotspots | 2A-3 | Empty — git .py filter |
| Entry Points | Working | Already TS-aware |
| CLI Arguments | 2E-1 | Missing — no CLI framework detection |
| Critical Classes | 2A-4 | Wrong syntax (Python `def` style) |
| Context Hazards | 2E-3 | Only shows .git/, missing node_modules/dist/etc. |
| Logic Maps | 2D-1 | Completely absent |
| Method Signatures (Hotspots) | 2A-4 | Working but wrong `def` syntax |
| Persona Map | 2E-5 | Not triggered — may just need gate check |
| Side Effects (Detailed) | 2B-4 | Stubs only |
| Side Effects (Summary by type) | 2B-4 | Empty |
| Investigation Targets | 2C-3, 2D-3 | Completely absent |
| Architectural Layers | 2A-2, 2C-2 | All in "OTHER" |
| Orphan Candidates | 2A-5 | Working but has duplicates |
| Cross-Module Calls | 2C-1 | Completely absent |
| Git: High-Risk Files | 2A-3 | Empty — .py filter |
| Git: Freshness | 2A-3 | All zeros — .py filter |
| Git: Hidden Coupling | 2A-3 | Empty — .py filter |
| Git: Function-Level Hotspots | 2D-2 | Empty — Python def/class regex |
| Git: Change Clusters | 2A-3 | Empty — .py filter |
| Git: Velocity Trends | 2A-3 | Empty — .py filter |
| Test Coverage | 2B-5 | Missing |
| Silent Failures | 2B-1 | Stubs only |
| Deprecated APIs | 2B-3 | Stubs only |
| Decorator Usage | 2E-2 | Data exists but not rendered |

### NOT IN PLAN — GAPS FOUND

These sections exist in the Python xray.md but are NOT addressed in any phase of the current plan:

#### Gap 1: GitHub About

**Python output:**
```
> **About:** Deterministic Python codebase analysis + LLM-powered deep investigation...
> **Topics:** ai-coding-assistant, ast, claude-code, codebase-analysis...
```

**TS output:** Missing entirely.

**Root cause:** `gap_features.get_github_about()` runs `gh api repos/{owner}/{repo}` to fetch description and topics. It's triggered by `gap.get("github_about")` in the formatter. Should be language-agnostic since it reads GitHub metadata, not code.

**What to check:** Is the `github_about` gap feature enabled when the TS scanner is invoked? Currently `config_to_gap_features()` builds the gap dict from the config, but when the TS scanner path runs, `config_to_gap_features()` is still called normally. The issue may be that `/tmp/ccusage` is a fresh clone without a GitHub remote, or the feature works fine and just needs testing against a project with a remote.

**Action:** Verify. If not working, it's a 5-line fix. **Add to Phase 2A.**

#### Gap 2: Database Query Detection (SQL Strings)

**Python output:**
```
## Database Queries (String Literals)
| Query | Location |
|-------|----------|
| `cursor.execute("SELECT * FROM users")` | test_scanner_enhancements.py:87 |
| `sql = "INSERT INTO logs (msg) VALUES (?)"` | test_scanner_enhancements.py:300 |
```

**TS output:** Stub only (`sql_strings: {}`).

**Root cause:** The TS scanner's `FileAnalysis.sql_strings` array exists but is never populated.

**What to detect in TS:**
- Raw SQL in template literals: `` `SELECT * FROM users WHERE id = ${id}` ``
- Tagged template SQL: `` sql`SELECT * FROM users` `` (common with libraries like `slonik`, `sql-template-strings`)
- String literal SQL: `"SELECT * FROM users"`
- ORM query patterns: `prisma.user.findMany()`, `.createQueryBuilder()`, `knex("users")`

**Honest assessment:** The raw SQL detection (finding SELECT/INSERT/UPDATE/DELETE in string literals and template literals) is straightforward — same regex-on-strings approach as the Python scanner. ORM detection is harder and more fragile. **Start with raw SQL detection, skip ORM patterns.**

**Action:** ~40 lines in ast-analysis.ts. **Add to Phase 2B.**

#### Gap 3: Environment Variable Detection

**Python output (via gap_features section in xray.md, not shown in minimal output but present in full config):**
The Python scanner has `get_environment_variables()` in gap_features.py which calls `_extract_env_vars_from_file_ast()` to find `os.environ["KEY"]`, `os.getenv("KEY", default)` patterns. This feeds:
- The "Environment Variables" section in xray.md
- The "Configuration Surface" section in DEEP_ONBOARD.md (P4.2 in crawl plan)

**TS output:** Not detected at all.

**What to detect in TS:**
- `process.env.KEY_NAME` — property access
- `process.env["KEY_NAME"]` — element access
- `process.env.KEY_NAME ?? "default"` — with nullish coalescing default
- `process.env.KEY_NAME || "default"` — with logical OR default

**Root cause:** No environment variable extraction exists in the TS scanner.

**Honest assessment:** This is a straightforward AST pattern match — find PropertyAccessExpression or ElementAccessExpression on `process.env`, extract the key name and any default value from nullish coalescing. ~60 lines.

**This is important for deep_crawl.** The R14 crawl plan has a dedicated task (P4.9) for "Environment dependencies — os.getenv, os.environ usage". Without env var extraction from xray, the deep_crawl agent has no starting point for this investigation.

**Action:** Add to ts-scanner/src/ast-analysis.ts. **Add to Phase 2B.**

#### Gap 4: Async Violation Detection

**Python output:**
The Python scanner detects patterns like `time.sleep()` in async functions, `requests.get()` in async code. The TS scanner has an `async_violations` stub but doesn't populate it.

**TS output:** Empty array for every file.

**What to detect in TS:**
- Sync I/O in async functions: `fs.readFileSync()`, `fs.writeFileSync()` inside `async function`
- Blocking calls in async context: `child_process.execSync()` inside async
- `XMLHttpRequest` in async code (should use `fetch`)

**Honest assessment:** Detection is conceptually simple — check if the current function is async (tracked in WalkContext), and if a known synchronous API is called. But TS codebases tend to be better about this than Python codebases (TS async patterns are more mature). This signal may produce very few hits for well-written TS code, but when it does fire, it's genuinely useful.

**Action:** ~40 lines in ast-analysis.ts. **Add to Phase 2B.**

#### Gap 5: State Mutation Tracking

**Python output (in xray.md):**
```
## State Mutations
*Module-level state that is modified during runtime:*
| Module | Mutation | Line |
...
```

The Python scanner tracks `self.attr = value` inside methods (instance variable mutations) and module-level variable reassignment. This feeds the "Shared State" section of DEEP_ONBOARD.md.

**TS output:** Not detected.

**What to detect in TS:**
- `this.prop = value` inside methods — instance state mutation
- Module-level `let`/`var` reassignment
- Class static field mutation

**Current plan status:** Phase 2D-4 covers module-level `let`/`var` detection (shared mutable state). But it does NOT cover `this.prop = value` instance mutations, which is the more common and useful signal.

**Action:** Expand 2D-4 to also track `this.X = Y` patterns inside methods. ~30 additional lines.

#### Gap 6: Linter/Config Rule Extraction

**Python output (when enabled):**
The Python scanner has `extract_linter_rules()` in gap_features.py that reads pyproject.toml (ruff, black, isort), flake8, .editorconfig to extract project coding conventions. This feeds the "Conventions" section of DEEP_ONBOARD.md.

**TS output:** Not detected.

**What to detect in TS:**
- `tsconfig.json` strict settings (strict, noImplicitAny, strictNullChecks, etc.)
- ESLint config (eslint.config.js, .eslintrc) — rules, extends, plugins
- Prettier config (.prettierrc, prettier.config.js) — printWidth, semi, singleQuote
- `.editorconfig` — language-agnostic, same detection as Python

**Honest assessment:** This is complex because TS ecosystem config is fragmented. `tsconfig.json` is straightforward JSON parsing. ESLint has migrated from `.eslintrc` (JSON/YAML) to `eslint.config.js` (JS/TS) — parsing JS configs is hard. Prettier config is simpler (usually JSON).

**Pragmatic approach:** Parse `tsconfig.json` strict flags (high value, easy). Report eslint/prettier config file existence without deep parsing (medium value, easy). Skip JS-format config parsing (low ROI for effort).

**Action:** ~80 lines. **Add to Phase 2E** as a new task.

#### Gap 7: Instance Variables in Class Skeletons

**Python output:**
```python
class LogicMapGenerator:  # L1225
    def __init__(self, source: str, detail_level: int)

    # Instance variables:
    self.source = source
    self.detail_level = detail_level
    self.tree = None
```

**TS output:** Class skeletons show methods but no instance variables.

**Root cause:** The Python scanner extracts `self.X = Y` from `__init__` methods. The TS scanner doesn't extract `this.X = Y` from constructors or class field declarations.

**What to detect in TS:**
- Class property declarations: `private users: User[] = []`
- Constructor assignments: `this.userService = new UserService()`
- TypeScript class fields (declared at class body level) — these are richer than Python because they have explicit type annotations and visibility modifiers

**Honest assessment:** TS actually has MORE information here than Python — class fields have explicit types and visibility modifiers. The TS compiler API makes it easy to iterate `ClassDeclaration.members` and find `PropertyDeclaration` nodes.

**Action:** ~40 lines in ast-analysis.ts to extract class fields. **Add to Phase 2B** (it's easy and high-value for class skeletons).

---

## Part 2: DEEP_ONBOARD Section Audit

Every major section from R14 DEEP_ONBOARD.md, and whether the TS scanner will produce enough signals for deep_crawl to generate it.

### Sections that need xray signals

| DEEP_ONBOARD Section | Key xray signals needed | Plan status |
|---------------------|------------------------|-------------|
| **Critical Paths** | entry_points, call_graph, side_effects | 2B-4 (side effects), 2C-1 (call graph) — **COVERED** |
| **Module Behavioral Index** | file list, function signatures, side_effects, complexity | 2B-4 — **COVERED** |
| **Change Impact Index** | import graph (hub modules), git coupling | 2A-1 (pillars), 2A-3 (git) — **COVERED** |
| **Key Interfaces** | class/function signatures with types | Already working — **COVERED** |
| **Data Contracts** | TS interfaces, type aliases, enums | Already in AST output — **COVERED** but see note below |
| **Error Handling Strategy** | silent_failures, exception patterns | 2B-1 — **COVERED** |
| **Shared State** | shared_mutable_state, state_mutations | 2D-4 + Gap 5 expansion — **COVERED after amendment** |
| **Domain Glossary** | LLM-generated from code reading | No scanner signal needed — **N/A** |
| **Configuration Surface** | env vars, config files | **GAP 3 + GAP 6** — needs addition |
| **Conventions** | linter rules, code patterns | **GAP 6** — needs addition |
| **Gotchas** | All signals combined + LLM investigation | Cumulative — **COVERED if other phases complete** |
| **Hazards — Do Not Read** | large files, skip dirs | 2E-3 (context hazards) — **COVERED** |
| **Extension Points** | LLM-generated from code reading | No scanner signal needed — **N/A** |
| **Change Playbooks** | LLM-generated from code reading | No scanner signal needed — **N/A** |
| **Reading Order** | import graph layers (topological) | 2C-2 — **COVERED** |
| **Environment Bootstrap** | env vars, config files, entry points | Gap 3 + Gap 6 — **COVERED after amendment** |

### Note on Data Contracts

The TS scanner already extracts `ts_interfaces`, `ts_type_aliases`, and `ts_enums` per file. However, the gap_features `extract_data_models()` function looks for Python-specific patterns (Pydantic BaseModel, dataclass, TypedDict). For TS, we need to:
1. Map TS interfaces with field definitions to the `data_models` format
2. Map TS type aliases (especially object types) similarly
3. Make `extract_data_models()` handle both Python and TS data

This is partially covered in Phase 2C-3 (investigation targets) which mentions "convert ts_interfaces/ts_type_aliases to data_models format". But the specific implementation needs to be explicit.

### Deep Crawl Plan Dependency Audit

The R14 crawl plan has 46 tasks. Here's what each priority tier needs from xray:

| Priority | Tasks | What xray provides | TS scanner status |
|----------|-------|--------------------|--------------------|
| P1: Request Traces | 5 | entry_points, call_graph, side_effects | Need 2B-4 + 2C-1 |
| P2: High-Uncertainty Modules | 2 | uncertainty scores from investigation_targets | Need 2C-3 |
| P3: Pillar Behavioral Summaries | 18 | architectural_pillars (hub modules) | Need 2A-1 fix |
| P4: Cross-Cutting Concerns | 10 | error handling, config, env vars, async patterns | Need 2B-1/2B-4 + Gap 3 + Gap 6 |
| P5: Conventions | 3 | coding conventions, test patterns | Need Gap 6 |
| P6: Gap Investigation | 3 | coupling anomalies, security concerns | Need 2A-3 + 2B-2 |
| P7: Change Impact | 5 | hub clusters, import graph | Need 2A-1 + 2C-2 |

**The critical missing signals for deep_crawl are:**
1. **Environment variables** (P4.9 directly queries env var detection) — **Gap 3**
2. **Linter/config rules** (P5.1 uses project config analysis) — **Gap 6**

Without these, the deep_crawl agent will still produce a document, but the Configuration Surface and Conventions sections will be based entirely on LLM code reading rather than guided by scanner signals. This makes them ~50% as good (the agent has to discover patterns from scratch instead of verifying pre-identified patterns).

---

## Part 3: Honest Uncertainties

Things where I don't know the right solution and we'll need to iterate:

### Uncertainty 1: Topological Layering Accuracy

The Python scanner uses import ratio + keyword matching to compute foundation/core/orchestration tiers. For projects like ccusage with flat structure (`apps/*/src/*.ts`), the keyword matching will miss most files (no "utils" or "config" in the paths). The ratio-based classification will work but may produce odd results:

- `logger.ts` (12 importers, 0 imports) → ratio = 12/1 = 12 → foundation. Correct.
- `data-loader.ts` (12 importers, 7 imports) → ratio = 12/8 = 1.5 → core. Correct.
- `commands/daily.ts` (0 importers, 11 imports) → ratio = 0/12 = 0 → orchestration. Correct.

Actually, the ratio approach may work better than I thought. But it won't work for projects with barrel files (index.ts re-exports) because those inflate the import count of the barrel rather than the actual source module.

**Plan:** Implement the ratio-based approach first, test against ccusage and another project, iterate if results are poor.

### Uncertainty 2: Call Graph Import Binding Tracking

The plan calls for building a symbol table from import declarations to resolve call sites. This handles the common case:

```typescript
import { createUser } from "./user-service"
createUser(input)  // Resolves to user-service.createUser
```

But these patterns will be missed:

- **Re-exports:** `export { createUser } from "./user-service"` — the binding exists in the barrel file, not the consumer
- **Dynamic access:** `const fn = getHandler("create"); fn(input)`
- **Method calls on instances:** `const svc = new UserService(); svc.createUser(input)` — need type info
- **Higher-order functions:** `items.map(processItem)` where `processItem` is imported
- **React JSX:** `<UserList users={data} />` where `UserList` is imported

**Honest estimate:** The binding table approach will capture ~60-70% of cross-module calls in typical TS codebases. The Python scanner captures ~85-90% because Python patterns are simpler. Getting to 80%+ without running `tsc` would require tracking `import * as` namespace calls and some higher-order function patterns, which adds ~100 lines of complexity.

**Plan:** Start with the basic binding table. Measure coverage against ccusage by comparing detected calls vs manual inspection of a few files. Add namespace import tracking in the same phase if time permits.

### Uncertainty 3: Logic Map Readability for TS

TS code has patterns that may produce noisy logic maps:

```typescript
// This produces a clean map
if (user.role === "admin") {
  grantAccess();
}

// This produces noise
const result = items
  ?.filter(x => x.active)
  ?.map(x => x.name)
  ?? [];
```

The optional chaining (`?.`) and nullish coalescing (`??`) create many implicit branches that may clutter the logic map. The Python scanner doesn't face this — Python's equivalent patterns are more verbose and explicit.

**Plan:** Implement the basic logic map (if/switch/for/while/try/return/throw), then evaluate readability. If optional chaining adds too much noise, filter it out or summarize it (`→ optional chain (3 hops)`). This is a tuning problem best solved by looking at real output.

### Uncertainty 4: How Well gap_features Works with TS Data

Many `gap_features.py` functions receive `results` and iterate over `results["structure"]["files"]`. The TS scanner populates this with absolute file paths as keys and `FileAnalysis` objects as values. The Python scanner uses relative paths. Several gap_features functions do path manipulation that may break:

- `detect_entry_points()` — already fixed in Phase 1
- `generate_prose()` — already fixed in Phase 1
- `extract_data_models()` — looks for Python-specific class patterns (Pydantic, dataclass)
- `get_environment_variables()` — calls `_extract_env_vars_from_file_ast()` which uses Python's `ast.parse()`
- `extract_state_mutations()` — uses Python's `ast.parse()`
- `extract_linter_rules()` — reads pyproject.toml (Python-specific)
- `find_agent_prompts()` — reads .md files (language-agnostic)
- `get_github_about()` — uses `gh api` (language-agnostic)

**The pattern:** Functions that use Python's `ast.parse()` will silently fail on TS files (they catch exceptions). Functions that read non-code files (markdown, JSON, git) work fine. Functions that iterate over scanner results work if the data shapes match.

**Plan:** For each gap_features function that uses `ast.parse()`, we have two options:
- **Option A:** Implement the equivalent detection in the TS scanner and emit the data in the JSON
- **Option B:** Rewrite the gap_features function to read from scanner output instead of re-parsing

Option A is better because it keeps the TS scanner self-contained. This is what the plan already does for most signals (silent failures, side effects, etc. are detected in the TS scanner, not by re-parsing in Python).

### Uncertainty 5: External Package Classification

The Python scanner classifies imports as "external" if they're not relative and not in the stdlib. For TS, the classification is:
- `node:fs`, `node:path` → Node.js builtins (should be treated like stdlib, not external)
- `@scope/package` → scoped package (external)
- `react`, `express` → unscoped package (external)

The current TS scanner's `getPackageName()` correctly extracts package names, but it includes `node:*` builtins in the external deps list. ccusage shows `node:buffer`, `node:fs`, `node:module`, etc. in the external deps.

**This is wrong.** Node builtins are not external dependencies in the same way npm packages are.

**Action:** Filter `node:*` prefixed imports from external deps (treat as builtins). ~5 lines. **Add to Phase 2A.**

---

## Part 4: Amended Phase Plan

### Additions to Phase 2A (Integration Fixes)

- **2A-6: Verify GitHub About works for TS projects** — Test with a project that has a GitHub remote. If not triggered, check gap_features gating. (~5 lines if needed)
- **2A-7: Filter Node.js builtins from external deps** — `node:fs`, `node:path`, etc. should not appear in external_deps list. (~5 lines in import-analysis.ts)

### Additions to Phase 2B (Behavioral Signals)

- **2B-6: Database query detection** — Detect SQL keywords (SELECT, INSERT, UPDATE, DELETE) in string literals and template literals. Skip ORM detection for now. (~40 lines in ast-analysis.ts)
- **2B-7: Environment variable detection** — Detect `process.env.KEY` and `process.env["KEY"]` patterns, extract key names and defaults from nullish coalescing. (~60 lines in ast-analysis.ts)
- **2B-8: Async violation detection** — Detect sync I/O APIs (`fs.readFileSync`, `execSync`) inside async functions. (~40 lines in ast-analysis.ts)
- **2B-9: Class field extraction** — Extract class property declarations and constructor `this.X = Y` assignments for richer class skeletons. (~40 lines in ast-analysis.ts)

### Amendments to Phase 2D

- **2D-4 expanded:** Also track `this.prop = value` mutations inside methods, not just module-level let/var.

### Additions to Phase 2E (Polish)

- **2E-6: TS config rule extraction** — Parse `tsconfig.json` strict flags. Report eslint/prettier config file presence. (~80 lines, new function in gap_features.py or a new TS scanner module)

### Updated Estimates

| Phase | Original Tasks | Added Tasks | New Total |
|-------|---------------|-------------|-----------|
| 2A | 5 | 2 | 7 |
| 2B | 5 | 4 | 9 |
| 2C | 3 | 0 | 3 |
| 2D | 4 (1 expanded) | 0 | 4 |
| 2E | 5 | 1 | 6 |
| **Total** | **22** | **7** | **29** |

### Updated Quality Trajectory

| After Phase | xray.md Quality | deep_crawl Readiness | What Changes |
|-------------|----------------|---------------------|--------------|
| 1 (current) | ~25% | ~15% | Skeleton, complexity, basic imports, type coverage |
| 2A | ~50% | ~40% | +Pillars, git, mermaid, skeletons, node builtins, github about |
| 2B | ~70% | ~60% | +Silent failures, security, deprecation, side effects, tests, env vars, SQL, async violations, class fields |
| 2C | ~80% | ~75% | +Call graph, topological layers, partial investigation targets, data model mapping |
| 2D | ~88% | ~82% | +Logic maps, git function churn, full investigation targets, state mutations |
| 2E | ~92% | ~88% | +CLI args, decorator display, config rules, re-exports, polish |

The remaining ~8-12% gap from Python parity comes from:
- Semantic tier (running `tsc` for full type resolution) — not planned
- Python-specific gap_features functions that use `ast.parse()` — would need TS rewrites
- Inherently harder TS patterns (call graph completeness, function churn in diffs)

---

## Part 5: What 90%+ Actually Means for deep_crawl

With all phases complete, a deep_crawl run on a TS project would produce a DEEP_ONBOARD.md with:

**Will be high quality (comparable to R14):**
- Critical Paths — entry points traced through call graph to side effects
- Module Behavioral Index — per-module summaries from signatures + side effects
- Change Impact Index — hub modules from import graph + git coupling
- Key Interfaces — class/function signatures with TS types
- Data Contracts — TS interfaces and type aliases as domain models
- Gotchas — from silent failures + security + async violations + LLM investigation
- Reading Order — from topological layers

**Will be medium quality (80% of R14):**
- Error Handling Strategy — we detect empty catch blocks and log-only handlers, but can't do the deep "exception taxonomy" analysis without re-parsing (the LLM agent fills this gap)
- Configuration Surface — env vars detected, tsconfig parsed, but JS-format configs not parsed
- Conventions — tsconfig strictness extracted, but eslint rules need JS config parsing

**Will be lower quality (60% of R14):**
- Shared State — module-level mutables and `this.X` mutations detected, but TS patterns like React state hooks (`useState`), Zustand stores, and Redux reducers are domain-specific and won't be caught by generic AST patterns. The LLM agent would need to identify these during investigation.
- Change Playbooks — quality depends on how well the LLM agent understands TS patterns. No scanner signal affects this directly, but better xray signals = better-guided investigation = better playbooks.

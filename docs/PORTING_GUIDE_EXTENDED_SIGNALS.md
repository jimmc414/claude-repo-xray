# Porting Guide: Extended Signals (Python → TypeScript)

> This document specifies everything added in the "extended signals" work so a TypeScript
> agent can build equivalent functionality without access to the Python conversation history.
> It covers both the deterministic scanner signals and the deep crawl pipeline extensions.

---

## Overview: What Was Added

Seven new scanner signals and their corresponding deep crawl consumption points:

| # | Signal | Scanner Module | JSON Key | Deep Crawl Sections Affected |
|---|--------|---------------|----------|------------------------------|
| 1 | Blast Radius | `lib/blast_analysis.py` (new) | `blast_radius` | Phase 1 (P7 seeding), Protocol E (step 0), S6 (Change Impact) |
| 2 | HTTP Route Detection | `lib/route_analysis.py` (new) | `routes` | Phase 1 (web_api auto-activate, P1 seeding), Protocol A (route context), S1 (API Index), S6 (playbook) |
| 3 | Import-Time Side Effects | `lib/investigation_targets.py` (extended) | `investigation_targets.import_time_side_effects` | Phase 1 (P4 task), Protocol B (step 2c), S2 (annotation), S5 (gotcha) |
| 4 | Resource Leaks | `lib/ast_analysis.py` (extended) | `resource_leaks` | Protocol B (step 3b), S4 (convention) |
| 5 | Unsafe Deserialization | `lib/ast_analysis.py` (extended) | `security_concerns[file][].category == "unsafe_deserialization"` | Phase 1 (P4 task), Protocol C (grep + investigation), S5 (gotcha) |
| 6 | Magic Methods | `lib/ast_analysis.py` (extended) | `structure[file].classes[].methods[].is_dunder` | Protocol B (step 2d), S3a (Key Interfaces), S5 (gotcha) |
| 7 | Decorator Details | `lib/ast_analysis.py` (extended) | `structure[file].{functions,classes}[].decorator_details[]` | Protocol B (step 3), Protocol D (step 1b), S4 (Config Surface) |

---

## Part 1: Deterministic Scanner Signals

### Signal 1: Blast Radius Analysis

**Purpose:** For every module in the codebase, compute how many other modules would be transitively affected if that module changed. Combines import edges AND call graph edges — strictly richer than import-only analysis.

**New file:** Equivalent of `lib/blast_analysis.py` (~220 lines)

**Algorithm:**

1. Build two reverse graphs from existing analysis results:
   - **Reverse import graph:** For each module M, collect every module that has M in its `imported_by` list. Source: `imports.graph[M].imported_by`.
   - **Reverse call graph:** For each module M, find modules that contain call sites to functions defined in M. Source: `calls.cross_module_calls` — for each qualified function name like `"utils.parse_config"`, extract the target module (`"utils"`), then find the caller modules from `call_sites[].file`.

2. For each module in the codebase, run **BFS** over the combined reverse graph:
   - Start from the target module, hop limit = 5
   - At each node, follow BOTH reverse-import edges and reverse-call edges
   - Track visited nodes with their hop distance
   - Remove the target itself from the result

3. Classify risk based on `affected_count`:
   ```
   ratio = affected_count / total_modules
   if ratio >= 0.5 OR affected_count >= 10: "critical"
   elif ratio >= 0.25 OR affected_count >= 5: "high"
   elif affected_count >= 2: "moderate"
   else: "isolated"
   ```

4. **Undertested dependents** (optional, requires git results): For each affected module, check if the pair (target, affected) appears in git coupling data. If a module depends on the target (via import/call graph) but has NEVER been co-modified in git history, flag it as `undertested_dependent`. This catches "structurally coupled but historically untested together" — a test gap signal.

**Input dependencies:**
- `import_results` from import analysis (specifically `imports.graph[module].imported_by`)
- `call_results` from call analysis (specifically `calls.cross_module_calls`)
- `git_results` (optional) for coupling data to compute undertested dependents

**Output schema:**
```json
{
  "blast_radius": {
    "files": [
      {
        "module": "config_loader",
        "affected_count": 12,
        "risk": "critical",
        "affected_modules": [
          {"module": "xray", "hops": 1},
          {"module": "markdown_formatter", "hops": 2}
        ],
        "max_hops": 3,
        "undertested_dependents": ["some_module", "other_module"]
      }
    ],
    "summary": {
      "critical_count": 2,
      "high_count": 4,
      "average_affected": 5.3
    }
  }
}
```

**Output limits:** Top 20 files by affected_count. Each file's `affected_modules` capped at 15 entries. `undertested_dependents` capped at 5.

**Pipeline integration:** Runs AFTER import analysis and call analysis (needs both). Runs AFTER git analysis if available (for undertested dependents). Conditional: only runs if `imports` result exists.

**Markdown output:** Section `## Blast Radius`. Table with columns: Module, Affected, Risk, Max Hops, Key Dependents. Only shows modules with risk >= "moderate". Cap at 15 rows. Summary line with critical/high counts.

---

### Signal 2: HTTP Route Detection

**Purpose:** Detect HTTP API endpoints by inspecting decorator patterns. Extracts method, path, handler, and per-handler side effects. Depends on Signal 7 (decorator details) being available.

**New file:** Equivalent of `lib/route_analysis.py` (~240 lines)

**Algorithm:**

1. Define known route decorator patterns:
   ```
   HTTP method decorators (the decorator name suffix maps to HTTP method):
     get → GET, post → POST, put → PUT, delete → DELETE,
     patch → PATCH, head → HEAD, options → OPTIONS
   
   Generic route decorators (method from kwargs):
     route → extract from kwargs["methods"]
     api_route → extract from kwargs["methods"]
   
   Django/DRF decorators:
     api_view → extract methods from positional args (list of strings)
   
   Known router/app object prefixes (the part before the dot):
     app, router, api, blueprint, bp, route, web, v1, v2, admin, auth
   ```

2. For each file in AST results, iterate all functions and class methods. For each function:
   - Check its `decorator_details` list (from Signal 7)
   - For each decorator, parse the `full_name` (dotted form, e.g., `"router.get"`)
   - Split into prefix + method_part: `"router"` + `"get"`
   - If prefix is in known router prefixes AND method_part is in known patterns → it's a route
   - Extract path from `args[0]` (first positional arg, should be a string)
   - For generic `@route()` / `@api_route()`, extract HTTP method from `kwargs["methods"]`
   - For DRF `@api_view(["GET", "POST"])`, extract methods from positional args

3. For each detected route, collect side effects within the handler's line range:
   - Filter `file_data.side_effects` to entries where `start_line <= se.line <= end_line`
   - Collect unique categories (db, api, file, subprocess, etc.)

4. Framework guessing heuristic from naming:
   - Contains "fastapi" or prefix is "router" → `"fastapi"`
   - Contains "flask" or prefix is "blueprint"/"bp" → `"flask"`
   - Contains "starlette" → `"starlette"`
   - Contains "aiohttp" → `"aiohttp"`
   - DRF patterns → `"django-rest-framework"`

**Input dependencies:**
- `ast_results` from AST analysis (specifically `files[path].functions[].decorator_details` and `files[path].classes[].methods[].decorator_details`)
- The `decorator_details` field must exist (Signal 7)

**Output schema:**
```json
{
  "routes": {
    "routes": [
      {
        "method": "GET",
        "path": "/users/{id}",
        "handler": "get_user",
        "file": "routes/users.py",
        "line": 42,
        "is_async": true,
        "framework_hint": "fastapi",
        "side_effects": ["db", "api"]
      }
    ],
    "summary": {
      "total_routes": 15,
      "by_method": {"GET": 8, "POST": 4, "DELETE": 3},
      "frameworks_detected": ["fastapi"]
    }
  }
}
```

**Output limits:** Routes sorted by (file, line). Cap at 20 in markdown output.

**Pipeline integration:** Runs AFTER AST analysis (needs decorator_details). Only included in output if routes are non-empty.

**Markdown output:** Section `## HTTP API Surface`. Table with columns: Method, Path, Handler, Side Effects. Frameworks line at bottom.

**TypeScript adaptation notes:** The decorator detection patterns are Python-specific (Flask, FastAPI, Django). For TypeScript, the equivalent would be Express/Koa/Fastify route patterns, NestJS decorators (`@Get`, `@Post`, `@Controller`), and Next.js file-based routing. The algorithm structure (inspect decorator/function metadata → extract method + path) is the same, but the pattern matching tables need to be language-specific.

---

### Signal 3: Import-Time Side Effects

**Purpose:** Find function calls at module scope (not inside any function or class) that produce side effects. These execute when the module is imported — action-at-a-distance behavior.

**Location:** Extended `lib/investigation_targets.py` — new function `compute_import_time_side_effects()`

**Algorithm:**

1. Define dangerous categories for import-time execution:
   ```
   {"db", "api", "file", "subprocess", "env", "deserialization"}
   ```

2. For each file in AST results:
   - Collect the line ranges of ALL functions and classes (start_line → end_line). These are "excluded scopes."
   - Iterate through `file_data.side_effects` (the existing side effect list)
   - For each side effect:
     - Skip if its `category` is not in the dangerous set
     - Check if its `line` falls inside any excluded scope range
     - If NOT inside any scope → it's a module-level (import-time) side effect
   - Record: `{file, line, call, category, risk: "Executes on import..."}`

3. Sort results by (file, line). Cap at 20 entries.

**Input dependencies:**
- `ast_results` (specifically `files[path].side_effects`, `files[path].functions[].start_line/end_line`, `files[path].classes[].start_line/end_line`)
- `call_results` (accepted but currently unused — reserved for future cross-reference)

**Output schema:**
```json
{
  "investigation_targets": {
    "import_time_side_effects": [
      {
        "file": "app/database.py",
        "line": 15,
        "call": "create_engine",
        "category": "db",
        "risk": "Executes on import — may cause action-at-a-distance"
      }
    ]
  }
}
```

**Pipeline integration:** Runs as part of the existing `compute_investigation_targets()` master function. No new pipeline stage — just an additional key in the investigation_targets output.

**Markdown output:** Appears in the `## Investigation Targets (for Deep Crawl)` section alongside existing targets.

**TypeScript adaptation notes:** The concept is identical — top-level statements in a module that perform I/O. In TypeScript/Node.js, this would be module-level calls outside of exported functions/classes (e.g., `const db = new DatabaseClient()` at file scope). The "excluded scope" detection is the same: find all function/class line ranges and flag side effects outside them.

---

### Signal 4: Resource Leaks

**Purpose:** Detect `open()` calls not wrapped in a context manager (`with` statement). Potential file handle leaks.

**Location:** Extended `lib/ast_analysis.py` — new function `_detect_resource_leaks()`

**Algorithm:**

1. **First pass:** Walk the entire AST and collect the `id()` of every `open()` call node that IS the context expression of a `With` or `AsyncWith` node. These are "safe" opens. Specifically: for each `With`/`AsyncWith` node, check each `item.context_expr` — if it's a `Call` to `open`, record its node identity.

2. **Second pass:** Walk the entire AST again. For every `Call` to `open()` (where `node.func` is a `Name` with `id == "open"`), check if its identity is in the safe set. If not, it's a leak.

3. Output: list of `{call: "open", line: N}` per file.

**Output schema:**
```json
{
  "resource_leaks": {
    "app/utils.py": [
      {"call": "open", "line": 42}
    ]
  }
}
```

Note: top-level dict keyed by filepath, each value is a list of leak objects.

**Pipeline integration:** Computed during the single-pass AST analysis of each file. Aggregated in `analyze_codebase()` as `results["resource_leaks"][filepath] = analysis.resource_leaks`.

**Markdown output:** Section `## Resource Leaks`. Bullet list: `- utils.py:42 — open()`. Cap at 15 entries.

**TypeScript adaptation notes:** The exact equivalent is less common in TypeScript/Node.js since file handles are typically managed differently (callbacks, streams, promises). The TS equivalent might detect: `fs.openSync()` without corresponding `fs.closeSync()`, or `fs.createReadStream()` / `fs.createWriteStream()` without `.destroy()` or `.close()` event handling. The pattern is "resource acquisition without explicit cleanup."

---

### Signal 5: Unsafe Deserialization

**Purpose:** Flag calls to deserialization functions that can execute arbitrary code if fed untrusted data.

**Location:** Extended `lib/ast_analysis.py` — added to existing `_detect_security_concern()` function.

**Detection patterns:**
```
pickle.loads, pickle.load, marshal.loads, marshal.load,
shelve.open, yaml.load, yaml.unsafe_load
```

Note: `yaml.safe_load` is NOT flagged. `cursor.execute()` etc. are NOT flagged (those are DB operations, not deserialization).

**Algorithm:** Inside the existing security concern detection function, after checking for `exec`/`eval`/`compile` builtins:
- Check if the call is an `ast.Attribute` node (dotted call like `pickle.loads`)
- Get the full dotted name via `_get_name()`
- If the full name matches any pattern in `UNSAFE_DESERIALIZATION_PATTERNS`, emit a concern with `category: "unsafe_deserialization"`

**Output schema:** Added to the existing `security_concerns` dict (keyed by filepath):
```json
{
  "security_concerns": {
    "app/serializer.py": [
      {"category": "unsafe_deserialization", "call": "pickle.loads", "line": 42},
      {"category": "code_execution", "call": "eval", "line": 15}
    ]
  }
}
```

**Pipeline integration:** Part of the existing single-pass AST walk. No new aggregation — just an additional entry type in the existing security_concerns output.

**Markdown output:** Appears in the existing `## Security Concerns` section alongside exec/eval/compile flags.

**TypeScript adaptation notes:** TypeScript doesn't have pickle/marshal. Equivalent unsafe deserialization patterns would be: `eval(JSON.parse(...))` (already covered by eval), `Function()` constructor, `vm.runInContext()`, `child_process.exec()` with user input, `require()` with dynamic paths. For YAML, `js-yaml`'s `yaml.load()` (without safe schema) is the equivalent of Python's `yaml.load()`.

---

### Signal 6: Magic Methods (is_dunder flag)

**Purpose:** Flag methods with dunder names (`__getattr__`, `__eq__`, `__call__`, etc.) so downstream consumers can identify classes with special behavior.

**Location:** Extended `lib/ast_analysis.py` — added field to `_extract_function_info()` return dict.

**Implementation:** Single line addition to the function info dict:
```python
"is_dunder": node.name.startswith("__") and node.name.endswith("__"),
```

**Output schema:** Boolean field on each method in class skeletons:
```json
{
  "structure": {
    "app/models.py": {
      "classes": [
        {
          "name": "User",
          "methods": [
            {"name": "__init__", "is_dunder": true, ...},
            {"name": "__eq__", "is_dunder": true, ...},
            {"name": "save", "is_dunder": false, ...}
          ]
        }
      ]
    }
  }
}
```

**Pipeline integration:** No new pipeline stage. Added to the per-method dict during existing AST extraction.

**Markdown output:** Section `## Magic Methods`. Lists classes that have dunder methods beyond `__init__`. Format: `- ClassName (file): __eq__, __hash__, __getattr__`. Cap at 10 classes, 8 dunders per class.

**TypeScript adaptation notes:** TypeScript doesn't have dunder methods. The equivalent concept is: well-known Symbol methods (`Symbol.iterator`, `Symbol.toPrimitive`, `Symbol.hasInstance`), `toString()` / `valueOf()` overrides, getter/setter properties (`get`/`set` keywords), and `Proxy` handler traps. The flag name might be `is_protocol_method` or `is_well_known_symbol` instead of `is_dunder`.

---

### Signal 7: Decorator Details

**Purpose:** Extract full positional and keyword arguments from every decorator, not just the name. Captures behavioral configuration embedded in decorators.

**Location:** Extended `lib/ast_analysis.py` — new function `_extract_decorator_detail()`, called for both functions and classes.

**Algorithm:**

1. For each decorator AST node, determine its form:
   - **Simple name** (`@staticmethod`): `full_name = dec.id`, no args
   - **Attribute** (`@app.route`): `full_name = _get_name(dec)` (dotted), no args
   - **Call** (`@retry(max_attempts=3)`): `full_name = _get_name(dec.func)`, then extract args

2. Extract positional args from `dec.args`:
   - Constants → their literal value
   - Names → the identifier string
   - Other complex expressions → `"..."`

3. Extract keyword args from `dec.keywords`:
   - `kw.arg` = key name, `kw.value` = value
   - Constants → literal value
   - Names/Attributes → identifier string
   - Other → `"..."`

**Output schema:** New `decorator_details` list alongside existing `decorators` list on both functions and classes:
```json
{
  "decorator_details": [
    {
      "name": "retry",
      "full_name": "backoff.retry",
      "args": [],
      "kwargs": {"max_attempts": 3, "backoff": "True"}
    },
    {
      "name": "get",
      "full_name": "router.get",
      "args": ["/users/{id}"],
      "kwargs": {"response_model": "User"}
    }
  ]
}
```

The existing `decorators` field (list of name strings) is preserved for backward compatibility.

**Pipeline integration:** Computed during the single-pass AST extraction for both `_extract_function_info()` and `_extract_class_info()`. No new pipeline stage.

**Markdown output:** No dedicated section. The decorator details are consumed by route_analysis (Signal 2) and are available in JSON for deep crawl agents.

**TypeScript adaptation notes:** TypeScript decorators have the same structure conceptually — `@Controller("/users")`, `@Get(":id")`, `@Injectable()`. The AST extraction is similar: parse the decorator expression, extract the call arguments. For non-decorator frameworks (Express, Koa), the equivalent data lives in function call arguments: `app.get("/path", handler)` — extract the route path from the first argument and the handler from the second.

---

## Part 2: Pipeline and Config Integration

### Config Changes (`configs/default_config.json`)

Added under `sections`:
```json
{
  "_comment_v33": "v3.3 codesight-inspired features",
  "blast_radius": true,
  "route_detection": true,
  "resource_leaks": true,
  "magic_methods": true
}
```

These are section toggles (not analysis toggles). They control whether the markdown formatter renders these sections. The analysis still runs; the data is still in JSON output regardless.

### CLI Flags

Added:
```
--no-blast-radius     Disable blast radius analysis
--no-route-detection  Disable HTTP route detection
```

These map to config section names via the flag→section mapping dict in the CLI parser.

### Gap Features Bridge (`xray.py:config_to_gap_features()`)

The gap features dict (which controls markdown section rendering) includes:
```python
"blast_radius": is_enabled("blast_radius"),
"route_detection": is_enabled("route_detection"),
"resource_leaks": is_enabled("resource_leaks"),
"magic_methods": is_enabled("magic_methods"),
```

### JSON Formatter

Added to the sections list that gets included when data exists:
```python
"blast_radius", "routes", "resource_leaks"
```

Decorator details and magic methods don't need explicit inclusion — they're nested inside `structure` which is always included.

### Pipeline Execution Order

The full pipeline is now 10 stages:

| Stage | Module | Depends On |
|-------|--------|------------|
| 1 | file_discovery | — |
| 2 | ast_analysis | 1 |
| 3 | import_analysis | 1 |
| 4 | call_analysis | 1, 2 |
| 5 | git_analysis | 1 |
| 6 | test_analysis | — |
| 7 | tech_debt_analysis | 1 |
| 8 | investigation_targets | 1-7 |
| 9 | **blast_analysis** | **3, 4** (optional: 5 for undertested) |
| 10 | **route_analysis** | **2** |

Stages 9 and 10 are independent of each other and could run in parallel.

Route analysis runs early (right after call_analysis, before git) because it only needs AST results.
Blast analysis runs late (after git) because it benefits from git coupling data for the undertested dependents feature.

Both are wrapped in try/except with graceful degradation — if they fail, the rest of the pipeline continues.

---

## Part 3: Deep Crawl Pipeline Extensions

All changes are to instruction/prompt files — no executable code. The TypeScript project should have equivalent instruction files.

### 3.1 Phase 1 (PLAN) Additions

**After reading investigation_targets, add these reads:**

1. Read `investigation_targets.import_time_side_effects`. If non-empty, add a P4 cross-cutting task: "Investigate import-time side effects — verify each flagged call, determine if intentional or accidental, document consequences."

2. Read `security_concerns` (dict keyed by filepath). Iterate all values. If any concern has `category == "unsafe_deserialization"`, add a P4 cross-cutting task: "Investigate unsafe deserialization — trace data source for each pickle.loads/yaml.load call."

3. If `routes.routes` exists and is non-empty, automatically activate the `web_api` domain facet (even if no other indicators matched). Seed P1 trace tasks from routes instead of generic entry points — group by handler file, select one representative per file (prefer routes with side_effects > 0), create task: "Trace {METHOD} {path} → {handler} (side effects: {list})".

4. Read `blast_radius.files` (filtered to risk "critical" or "high"). Use these to seed P7 change-impact tasks instead of hub_modules alone. Order by affected_count descending.

### 3.2 Protocol Extensions

**Protocol A (Request Trace) — add step 9:**
If the trace starts from an HTTP route: note method/path in trace header, look for middleware before the handler, note request parsing and response serialization, tag side effects with HTTP context.

**Protocol B (Module Deep Read) — add steps 2c, 2d, 3, 3b:**
- **2c:** Check `investigation_targets.import_time_side_effects` for this module. Investigate each flagged call: intentional? What if it fails at import? What modules import this one? Format: `"⚠ Import-time: {call} at line {N} — {consequence}"`
- **2d:** Check `structure.<filepath>.classes[].methods[]` for `is_dunder: true` methods beyond `__init__`. Document what each does, behavioral implications, consumer reliance.
- **3:** Note decorator arguments from `structure.<filepath>.functions[].decorator_details[]` — each has `name`, `args`, `kwargs`. Focus on retry (max_attempts, backoff), cache (TTL), auth (role), rate limit (limits).
- **3b:** Check `resource_leaks["<filepath>"]` for this module. Verify each: is there a close()? Is it in finally? Real leak or caller-managed? Confirmed leaks are [MEDIUM] gotchas.

**Protocol C (Cross-Cutting) — add grep pattern and investigation procedure:**
Add grep: `grep -rn "pickle\.loads\|pickle\.load\|yaml\.load\|marshal\.loads" --include="*.py"`
For each found: read full function, trace data parameter backward, classify source (user input = CRITICAL, external file = HIGH, internal = MEDIUM), check for safe alternatives.

**Protocol D (Convention Documentation) — add step 1b:**
When reading examples, note decorator PATTERNS including arguments. "All endpoints use @require_auth(role=...)" is a more useful convention than "@require_auth". The argument pattern is part of the convention.

**Protocol E (Change Impact) — add step 0 before existing step 1:**
Read `blast_radius.files` for this hub module. Note pre-computed affected_count, risk level, max_hops, undertested_dependents. This is the starting landscape — verify it, don't recompute it. If undertested_dependents is non-empty, flag as potential test gap.

### 3.3 Assembly Prompt Extensions

**S1 (Critical Paths):** If route trace findings exist, add `### API Endpoint Index` subsection at end of Critical Paths. Table: Method, Path, Handler, Side Effects, Auth.

**S2 (Module Behavioral Index):** For each module, check `investigation_targets.import_time_side_effects`. If present, prepend warning: `> ⚠ **Import-time side effect:** {call} at line {N} — executes on import. {consequence}.`

**S3a (Key Interfaces):** When documenting class interfaces, include magic methods that affect API behavior. Group by type: Attribute access (__getattr__ etc.), Container (__getitem__ etc.), Callable (__call__), Context (__enter__/__exit__), Comparison (__eq__/__hash__), Representation (__str__/__repr__). Only document behaviorally significant ones — skip __init__ and trivial __repr__.

**S4 (Conventions):** If resource leak deviations found, document as convention: "File I/O uses context managers — {N} deviations at {file:line list}." Also: decorator arguments containing configuration values are part of the Configuration Surface. Document retry config, cache TTLs, rate limits, auth requirements alongside env vars and config files.

**S5 (Gotchas):** Three new gotcha source rules:
- Import-time side effects → [HIGH] severity
- Unsafe deserialization → [CRITICAL] if user-controlled data, [HIGH] if external files, [MEDIUM] if internal
- Dangerous magic method combinations → __eq__ without __hash__ (unhashable), __getattr__ catching all (masks errors), __del__ with side effects (unpredictable timing), __bool__ non-obvious (conditional surprises)

**S6 (Change Impact Index):** For each hub module cluster, cross-reference with `blast_radius.files`. Add Blast Radius row to each hub module table: affected modules (count + risk), max propagation (hops), undertested list. If blast_radius shows critical risk but Protocol E didn't cover it, note as gap. Also: if HTTP route traces exist, include "Add New API Endpoint" playbook referencing an existing route's pattern.

### 3.4 Config File Changes

**`domain_profiles.json` — web_api facet:**
Add `xray_signals` to indicators:
```json
"indicators": {
  "frameworks": [...],
  "patterns": [...],
  "directories": [...],
  "xray_signals": ["routes.routes"]
}
```
This documents that the routes signal is an automatic activator for the web_api facet.

**`exemplar_templates.md` — Template 1 (Change Impact Index):**
Add `Blast Radius` column to the hub module table:
```
| Hub Module | Imported By | Blast Radius | High-Impact Functions | ...
| `{module}` | {N} modules | {affected_count} affected, {risk} risk, {max_hops} hops | ...
```
Add undertested-dependents exemplar.

**`DEEP_ONBOARD.md.template` — Document Map companion data line:**
Add to the "Also available in companion xray.md" paragraph: blast radius (transitive impact per module), HTTP route detection, resource leak flags, security concerns (unsafe deserialization).

---

## Part 4: Key JSON Path Reference

This is the critical section for deep crawl agents — every JSON path that SKILL.md references must exist in the scanner output.

| SKILL.md Reference | Actual JSON Path | Structure |
|-------------------|-----------------|-----------|
| `blast_radius.files` | `blast_radius.files` | List of {module, affected_count, risk, affected_modules, max_hops, undertested_dependents?} |
| `routes.routes` | `routes.routes` | List of {method, path, handler, file, line, is_async, framework_hint, side_effects?} |
| `investigation_targets.import_time_side_effects` | `investigation_targets.import_time_side_effects` | List of {file, line, call, category, risk} |
| `security_concerns` with `unsafe_deserialization` | `security_concerns[filepath][]` | Dict keyed by filepath → list of {category, call, line} |
| `resource_leaks` for a module | `resource_leaks[filepath]` | Dict keyed by filepath → list of {call, line} |
| `is_dunder` on methods | `structure[filepath].classes[].methods[].is_dunder` | Boolean field on each method |
| Decorator args/kwargs | `structure[filepath].functions[].decorator_details[].args/kwargs` | List of decorator objects with name, full_name, args[], kwargs{} |
| Decorator args on methods | `structure[filepath].classes[].methods[].decorator_details[].args/kwargs` | Same structure, on class methods |

---

## Part 5: What Does NOT Change

- No new ONBOARD sections. All signals integrate into existing deep crawl sections.
- No new investigation protocols (A-F are extended, not replaced).
- No new quality gates. Existing density floors are sufficient.
- No new validation questions.
- `quality_gates.json` unchanged.
- `compression_targets.json` unchanged.

---

## Part 6: TypeScript-Specific Adaptation Notes

### Language-Specific Pattern Tables

The Python scanner detects Python-specific patterns. The TypeScript port needs equivalent pattern tables:

| Python Pattern | TypeScript Equivalent |
|---------------|----------------------|
| `pickle.loads/load` | `eval()`, `Function()`, `vm.runInContext()`, dynamic `require()` |
| `yaml.load` (unsafe) | `js-yaml` `.load()` without safe schema |
| `marshal.loads` | N/A (no equivalent) |
| `open()` without `with` | `fs.openSync()` without `fs.closeSync()`, unclosed streams |
| `@app.get("/path")` | `app.get("/path", handler)` (Express), `@Get("/path")` (NestJS) |
| `__getattr__` / `__eq__` | `Proxy` handlers, `Symbol.iterator`, `valueOf()`, getter/setter |
| Module-level DB calls | Top-level `await` side effects, module-scope `new Client()` |

### AST Differences

Python uses the `ast` module. TypeScript should use the TypeScript Compiler API (`ts.createSourceFile`, `ts.forEachChild`) or a tool like `@typescript-eslint/parser`. The visitor pattern is the same — the node types differ.

### Framework Detection for Routes

| Framework | Pattern | How to Detect |
|-----------|---------|---------------|
| Express | `app.get("/path", handler)` | Call expression where callee is `app.get`/`router.get` etc. |
| Fastify | `fastify.get("/path", handler)` | Same pattern, different callee names |
| NestJS | `@Get("/path")`, `@Post("/path")` | Decorator on class method |
| Next.js | File-based routing | File path IS the route (detect `pages/` or `app/` directory) |
| Hono | `app.get("/path", handler)` | Same as Express pattern |
| tRPC | `router({ getUser: ... })` | Object literal in router call |

---

*Document generated from the Python implementation at commit 696d5f4.*

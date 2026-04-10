# Comparison: claude-repo-xray vs codesight

## Grades (Python-only: "How well does an AI get up to speed?")
- **claude-repo-xray: A** (42+ deterministic signals + deep crawl behavioral investigation)
- **codesight on Python: C+** (~6 shallow signals, Python is second-class)

---

## Part 1: Codesight Features xray Lacks (with AI value analysis)

### 1.1 Route Detection (FastAPI/Flask/Django)

**What codesight extracts:** HTTP method, path, URL params, handler file location, middleware chain. For Python, uses subprocess to spawn `ast` module — parses `@app.get("/users")`, `@router.post("/items")`, `@app.route("/api", methods=["POST"])`, Django `path()` calls.

**Specific AI value:** An AI reading route output knows:
- Every HTTP endpoint in the system (method + path + handler file)
- Which routes touch auth, DB, cache, payments (via auto-tagging)
- The API surface area without reading any source files
- Where to add a new endpoint (pattern matching existing routes)

**Why xray misses this:** `ast_analysis.py:_extract_decorator_name()` extracts decorator names but **discards all arguments**. `@app.get("/users")` becomes just `"get"`. The path `"/users"` is lost. xray already parses every decorator on every function — it just throws away the most valuable part for web apps.

**Layer 1 fix:** Extend `_extract_decorator_name()` to capture `(name, args, kwargs)` for `ast.Call` decorator nodes. Then add a `route_analysis.py` module that:
- Matches decorators against known framework patterns (FastAPI: `app.get/post/put/delete/patch`, Flask: `app.route/bp.route`, Django: detect `urlpatterns` with `path()`)
- Extracts HTTP method + URL path + URL params
- Associates route with handler function signature (already extracted)
- Auto-tags by scanning handler body for side effect categories (already detected)

**Deep crawl extension (Protocol A enhancement):** Currently Protocol A traces entry→side-effect but doesn't know HTTP semantics. With route data:
- Trace each route from HTTP entry → middleware → handler → service → side effect
- Document request/response schemas (Pydantic models used in route signatures)
- Map auth requirements per route (which routes require auth middleware)
- Identify unprotected routes (routes without auth decorator/dependency)
- Build API contract documentation with example payloads

**Evidence metrics for AI:** Route count, routes per module, auth coverage %, routes with DB side effects, routes without input validation, orphan routes (defined but unreachable).

---

### 1.2 Blast Radius Analysis

**What codesight extracts:** BFS through import graph showing: affected files (1-5 hops), affected routes, affected models, affected middleware. Configurable depth (default 3 hops). Multi-file support (combined blast for git diff).

**Specific AI value:** Before changing any file, the AI knows:
- How many files are transitively affected
- Which user-facing routes break
- Which DB models are touched
- Whether the change is isolated or system-wide
- Confidence level for making the change without extensive testing

**Why xray misses this:** xray has the import graph (`import_analysis.py`) AND the call graph (`call_analysis.py`) AND reverse lookups — all the data needed. It just doesn't expose a "change X, what breaks?" query.

**Layer 1 fix:** Add `blast_analysis.py`:
- BFS from target file through `imports.graph[module]["imported_by"]`
- At each hop, collect: functions called from this module (via `calls.reverse_lookup`), side effects in affected files, data models used
- Score blast radius: isolated (0-2 files), moderate (3-10), high (10+), critical (touches entry points)
- Output per-file: `{file, hop_distance, affected_functions, side_effects, risk_level}`

**Deep crawl extension (Protocol E enhancement):** Protocol E already does LLM-powered impact analysis for hub modules. With deterministic blast radius:
- Pre-compute blast radius for ALL modules, not just hubs
- Protocol E agents get blast radius as input context — focuses their investigation
- Add "blast radius verification" step: agent reads actual callers and confirms/refines the deterministic result
- Generate "safe change zones" — files where changes are provably isolated
- Cross-reference blast radius with git co-modification coupling: if blast radius says X affects Y but git says they never change together, flag potential undertesting

**Evidence metrics:** Blast radius per file (hop count), blast radius distribution (histogram), most dangerous files (highest blast), safest files (isolated), blast-to-test ratio (files in blast radius that lack tests).

---

### 1.3 Route Auto-Tagging

**What codesight extracts:** Scans handler file content for patterns and tags routes: auth (JWT, sessions, Clerk), db (Prisma, SQL), cache (Redis), queue (BullMQ), email (SendGrid), payment (Stripe), upload (multer), ai (OpenAI, Anthropic).

**Specific AI value:** The AI instantly knows the "flavor" of each endpoint without reading handlers. "This is a payment endpoint that touches the DB" vs "this is a read-only cache endpoint."

**Why xray can do this better:** xray already detects side effects per-function (DB, API, file, env, subprocess). It already knows which functions have security concerns. It already knows async vs sync. Combining existing signals per-route would produce richer tags than codesight's regex matching.

**Layer 1 fix:** If route detection is added (1.1), tag each route by:
- Side effect categories already detected in handler function
- Whether handler is async or sync
- Complexity score of handler
- Whether handler has error handling or silent failures
- Auth decorator presence

**Deep crawl extension:** Protocol A traces already follow routes to terminal side effects. With tagging:
- Validate tags against actual behavior (tag says "db" — does the trace confirm DB writes?)
- Detect tag mismatches (route tagged "read-only" but trace finds write side effects)
- Build API risk matrix: route × side-effect-type × auth-required × complexity

---

### 1.4 Middleware Detection & Classification

**What codesight extracts:** Classifies middleware by type: auth, rate-limit, CORS, validation, logging, error-handler, custom. 50+ regex patterns. File location + classification.

**Specific AI value:** The AI knows the request processing pipeline — what happens before and after handler execution. Critical for understanding auth flows, error handling, and request transformation.

**Why xray misses this:** xray doesn't have a concept of "middleware." For Python web apps, middleware manifests as: ASGI/WSGI middleware classes, FastAPI dependencies (`Depends()`), Flask `before_request`/`after_request` hooks, Django middleware classes.

**Layer 1 fix:** Detect middleware patterns in AST:
- Classes with `__call__` + request/response params (ASGI/WSGI middleware)
- Functions used in `Depends()` (FastAPI dependency injection)
- Functions decorated with `@app.before_request`, `@app.after_request` (Flask)
- Classes in Django `MIDDLEWARE` setting
- Classify by scanning function body for auth tokens, rate limit counters, CORS headers, validation calls

**Deep crawl extension:** Add to Protocol A traces:
- Document middleware execution order for each route
- Trace auth middleware: what it checks, what it injects into request context, what happens on failure
- Identify routes that bypass middleware (missing dependencies, excluded paths)
- Document middleware side effects (logging, metrics, header injection)

---

### 1.5 MCP Server Mode

**What codesight provides:** 8 specialized MCP tools (scan, summary, routes, schema, blast_radius, env, hot_files, refresh). Session caching — first call scans, subsequent calls return cached results.

**Specific AI value:** Instead of reading a static document, the AI can **query** the analysis interactively. "What's the blast radius if I change this file?" "Show me all auth routes." "What env vars are required?" This is fundamentally more useful during active coding sessions.

**Why xray should add this:** xray produces richer data than codesight — serving it via MCP would be strictly more valuable. The JSON formatter already produces structured output that maps directly to MCP tool responses.

**Layer 1 fix:** Add `mcp_server.py`:
- `xray_scan` — Full scan (cached)
- `xray_summary` — Compact overview (~500 tokens)
- `xray_skeleton` — Class/function signatures for a specific file
- `xray_blast_radius` — Impact analysis for a file (if 1.2 is implemented)
- `xray_routes` — Route list with filtering (if 1.1 is implemented)
- `xray_risk` — Git risk scores for files being modified
- `xray_complexity` — Complexity hotspots in a file or module
- `xray_side_effects` — Side effects in a file or call chain
- `xray_imports` — Import graph for a specific module

**Deep crawl extension:** MCP tools that query deep onboard data:
- `xray_trace` — Request trace for a specific entry point
- `xray_gotchas` — Gotchas relevant to files being modified
- `xray_playbook` — Change playbook for a specific modification type
- `xray_impact` — Change impact analysis for a specific hub module

---

### 1.6 Env Var Audit with Classification

**What codesight extracts:** All env var references, classified as required vs has-default. Source file tracking. Config file identification. Notable dependency filtering.

**Specific AI value:** The AI knows exactly what environment setup is needed before the code can run. Distinguishes "must set this or app crashes" from "optional, has sensible default."

**Why xray can do this better:** xray already extracts `os.environ.get()` and `os.getenv()` calls in side effect detection. It just doesn't classify them.

**Layer 1 fix:** Enhance env var extraction in `ast_analysis.py`:
- `os.environ["KEY"]` / `os.environ.get("KEY")` → required (no default)
- `os.environ.get("KEY", "default")` / `os.getenv("KEY", "default")` → has default
- Track which file and function uses each var
- Detect Pydantic `Settings` classes (common pattern: `class Settings(BaseSettings)`)
- Group by category: database, auth, API keys, feature flags, runtime config

**Deep crawl extension (Protocol C):** Cross-cutting investigation of config:
- Verify every required env var has documentation or `.env.example` entry
- Trace env var from read-site to usage — what behavior does it control?
- Identify env vars that are read but never used (dead config)
- Identify config that's hardcoded but should be an env var (magic strings)
- Document startup failure modes: which missing vars crash the app vs degrade gracefully

---

### 1.7 Watch Mode & Git Hooks

**What codesight provides:** `--watch` re-scans on file changes (500ms debounce). `--hook` installs git pre-commit hook to regenerate context on every commit.

**Specific AI value:** Context stays fresh without manual re-runs. The AI always works with current analysis.

**Layer 1 fix:** Add `--watch` flag using `watchdog`-style polling (stdlib only — use `os.stat` mtime checking on a timer). Add `--hook` to generate a `.git/hooks/pre-commit` script that runs xray.

**Deep crawl extension:** Not directly applicable — deep crawl is too expensive for watch mode. But could add incremental xray: only re-analyze files that changed since last run (compare mtimes against cached results).

---

## Part 2: Novel Signals BOTH Tools Miss (new capabilities)

These are signals neither tool extracts today that would be high-value for an AI working on a Python codebase. Each includes a Layer 1 (deterministic) implementation and Layer 2 (deep crawl) extension.

### 2.1 Resource Lifecycle Analysis

**What it is:** Track open/close, acquire/release, enter/exit patterns. Detect resource leaks.

**AI value:** The AI knows which functions acquire resources that must be released, which use context managers properly, and which leak. Critical for preventing resource exhaustion bugs.

**Layer 1 (AST):**
- Detect `open()` calls without `with` statement wrapping
- Detect classes implementing `__enter__`/`__exit__` (context managers)
- Detect `async with` patterns for async resource management
- Flag functions that call `open()`, `connect()`, `acquire()` without corresponding close/release
- Track `contextlib.contextmanager` decorated generators
- Output: `{function, resource_type, properly_managed: bool, line}`

**Deep crawl extension:**
- Protocol B: For each module, document resource lifecycle — what resources it acquires, how it releases them, what happens on exception
- Protocol C: Cross-cutting investigation of resource management patterns — is there a dominant strategy (context managers vs try/finally vs manual close)?
- Gotcha generation: Functions that leak resources under error paths

**Evidence metrics:** Resource leak count, context manager coverage %, functions with unmanaged resources.

---

### 2.2 Magic Method Inventory

**What it is:** Catalog all dunder methods that alter object behavior — `__getattr__`, `__call__`, `__missing__`, `__getitem__`, `__setattr__`, `__new__`, `__init_subclass__`.

**AI value:** Magic methods make code behave non-obviously. An AI that doesn't know `__getattr__` is defined will write code that calls non-existent attributes and be confused when it works. An AI that doesn't know `__call__` exists will miss that instances are callable.

**Layer 1 (AST):**
- Already extracting methods per class — just need to flag dunders and classify by behavior type:
  - Attribute access: `__getattr__`, `__getattribute__`, `__setattr__`, `__delattr__`
  - Container: `__getitem__`, `__setitem__`, `__contains__`, `__len__`, `__iter__`
  - Callable: `__call__`
  - Lifecycle: `__new__`, `__init_subclass__`, `__del__`
  - Context: `__enter__`, `__exit__`, `__aenter__`, `__aexit__`
  - Descriptor: `__get__`, `__set__`, `__delete__`
  - String: `__repr__`, `__str__`, `__format__`
- Output: Per-class magic method inventory with behavioral impact classification

**Deep crawl extension:**
- Protocol B: For modules with magic methods, document the actual behavior (what does `__getattr__` return? what does `__call__` do?)
- Gotcha generation: Classes where magic methods create non-obvious behavior (e.g., `__getattr__` that proxies to another object)
- Convention detection: Are magic methods used consistently or idiosyncratically?

---

### 2.3 Import-Time Side Effects

**What it is:** Detect code that executes at import time — module-level function calls, global variable assignments from function returns, class decorators that register instances.

**AI value:** Import-time side effects cause action-at-a-distance bugs. Importing a module might start a server, connect to a database, register handlers, or modify global state. The AI needs to know this before reorganizing imports.

**Layer 1 (AST):**
- Scan module-level statements for:
  - Function calls (not class/function definitions): `logging.getLogger()`, `app = Flask(__name__)`, `engine = create_engine()`
  - Variable assignments from function returns: `CONFIG = load_config()`
  - Decorator calls that register: `@app.route`, `@registry.register`
  - `if __name__ == "__main__"` guard detection (these are safe)
- Classify: benign (logging setup, type aliases), significant (DB connections, file opens, registrations), dangerous (network calls, subprocess, mutations)
- Output: `{module, line, statement, classification, guarded_by_main: bool}`

**Deep crawl extension:**
- Protocol C: Cross-cutting investigation — what happens when the test suite imports all modules? Are there import ordering dependencies?
- Gotcha generation: Modules where import order matters (module A must be imported before module B)
- Convention check: Is there a pattern for deferring side effects (lazy loading, dependency injection)?

---

### 2.4 Concurrency Primitive Inventory

**What it is:** Detect locks, semaphores, queues, thread pools, process pools, events, barriers — and track which code uses them.

**AI value:** Concurrency bugs are the hardest to diagnose. The AI needs to know where locks exist, what they protect, and where deadlock risks live.

**Layer 1 (AST):**
- Detect instantiation of: `threading.Lock()`, `threading.RLock()`, `asyncio.Lock()`, `asyncio.Semaphore()`, `queue.Queue()`, `ThreadPoolExecutor()`, `ProcessPoolExecutor()`, `multiprocessing.Pool()`, `asyncio.Event()`, `threading.Event()`
- Track which functions acquire/release each primitive
- Detect lock ordering (multiple locks acquired in a function — deadlock risk)
- Detect unguarded shared state (module-level mutable without lock)
- Output: `{primitive_type, variable_name, file, line, used_by: [functions], deadlock_risk: bool}`

**Deep crawl extension:**
- Protocol B: For modules with concurrency primitives, document what each lock protects and the acquisition order
- Protocol C: Cross-cutting investigation of thread safety patterns — is the codebase thread-safe? What's the dominant concurrency model (threading, asyncio, multiprocessing)?
- Gotcha: Functions that hold locks while calling external APIs (unbounded lock hold time)

---

### 2.5 Data Serialization Boundaries

**What it is:** Detect where data crosses serialization boundaries — JSON encode/decode, pickle, protobuf, msgpack, YAML, TOML parsing.

**AI value:** Serialization boundaries are where type information is lost, where schema mismatches cause runtime errors, and where security vulnerabilities (pickle, YAML load) live. The AI needs to know every place data is serialized/deserialized.

**Layer 1 (AST):**
- Detect calls to: `json.dumps/loads`, `pickle.dumps/loads`, `yaml.safe_load/load`, `toml.load`, `msgpack.pack/unpack`, `protobuf.SerializeToString/ParseFromString`, `pydantic.model_dump/model_validate`, `dataclasses.asdict`
- Track the data type being serialized (if type-annotated)
- Flag unsafe deserialization: `pickle.loads` (arbitrary code execution), `yaml.load` without `Loader=SafeLoader`
- Identify JSON schema drift risk: functions that serialize data in one module and deserialize in another
- Output: `{call, direction: serialize|deserialize, format, file, line, security_risk: bool}`

**Deep crawl extension:**
- Protocol A: Trace data serialization through request paths — where is the request body parsed? Where is the response serialized? What happens if the schema changes?
- Protocol C: Cross-cutting investigation — is there one serialization strategy or many? Are there custom encoders/decoders?
- Protocol E: Impact analysis — if a Pydantic model changes fields, which serialization sites break?
- Gotcha: Places where data is serialized in format A and deserialized assuming format B

---

### 2.6 Dependency Injection Pattern Detection

**What it is:** Detect how dependencies are wired — constructor injection, FastAPI `Depends()`, module-level singletons, factory functions, service locators.

**AI value:** The AI needs to know how to properly wire new code into the existing system. If the codebase uses DI, the AI should follow the same pattern. If it doesn't, the AI needs to know the actual wiring strategy.

**Layer 1 (AST):**
- Detect `Depends()` in FastAPI function signatures
- Detect `__init__` parameters that are service types (classes, not primitives)
- Detect factory functions (functions that return class instances)
- Detect service locator patterns (`container.get()`, `registry.resolve()`)
- Detect singleton patterns (`_instance = None`, `@lru_cache` on constructors)
- Classify codebase DI strategy: constructor injection, framework DI, singleton, manual wiring
- Output: `{pattern, file, line, dependencies: [types], classification}`

**Deep crawl extension:**
- Protocol D: Document the dominant DI convention with evidence counts
- Protocol F: Change playbooks should include "how to wire a new service" based on detected DI patterns
- Gotcha: Places where DI is bypassed (direct instantiation of services that should be injected)

---

### 2.7 Error Propagation Path Analysis

**What it is:** Trace how exceptions flow up the call stack. Which functions raise, which catch, which re-raise, which swallow.

**AI value:** The AI knows what happens when something fails at any point in the call chain. Does the error bubble up to the user? Is it logged and swallowed? Is it retried? Does it trigger a rollback?

**Layer 1 (AST):**
- For each function: what exceptions it raises (`raise X`), what it catches (`except X`), what it re-raises (`raise` in except block)
- Build exception flow graph: raiser → catcher chains
- Detect uncaught exceptions (raised but never caught in any caller)
- Detect catch-all handlers (`except Exception`, `except:`) — where the error flow stops
- Detect retry patterns (loops containing try/except with the same operation)
- xray already detects silent failures — this extends it with flow analysis
- Output: `{function, raises: [ExceptionType], catches: [ExceptionType], propagates: bool, uncaught_risk: bool}`

**Deep crawl extension:**
- Protocol A: Every trace should document the error path at each hop — not just the happy path
- Protocol C: Exception taxonomy — all custom exception classes, inheritance tree, where each is raised vs caught
- Gotcha: Functions where different exception types are caught with the same handler (losing error specificity)

---

### 2.8 State Machine Detection

**What it is:** Identify enum-based state machines, status fields with transition logic, workflow state patterns.

**AI value:** State machines are everywhere in business logic (order status, payment flow, user lifecycle). The AI needs to understand valid transitions to avoid putting entities in invalid states.

**Layer 1 (AST):**
- Detect `Enum` subclasses where values represent states (Status, State, Phase, Stage in name)
- Detect functions that compare against enum values and assign new values (transition functions)
- Detect string-based state machines (status fields compared with string literals)
- Build transition graph: `{state_A → state_B: [functions that perform transition]}`
- Output: state machine definitions with valid transitions and the functions that enforce them

**Deep crawl extension:**
- Protocol B: For modules containing state machines, document all valid transitions with business rules
- Gotcha: States that can't be reached (dead states), transitions that skip validation
- Change playbook: "Adding a new state" — which transition functions need updating

---

### 2.9 Monkey Patching & Dynamic Modification Detection

**What it is:** Detect `setattr()`, `type()` for dynamic class creation, `__class__` assignment, `sys.modules` manipulation, function replacement.

**AI value:** Dynamic modifications make code impossible to understand statically. The AI needs to know where the runtime behavior diverges from what the source code shows.

**Layer 1 (AST):**
- Detect `setattr(obj, name, value)` calls (especially on modules or classes)
- Detect `type(name, bases, dict)` for dynamic class creation
- Detect `sys.modules[name] = X` (module replacement)
- Detect `mock.patch` outside test files (production monkey patching)
- Detect `__class__` assignment
- Detect metaclasses (`class Meta(type)` or `metaclass=X`)
- Flag severity: test-only patching (safe) vs production patching (dangerous)
- Output: `{type, target, file, line, in_test: bool, severity}`

**Deep crawl extension:**
- Gotcha generation: Every production monkey patch is automatically a gotcha
- Protocol B: Document what each dynamic modification does and why it exists
- Convention check: Is monkey patching a pattern or an anomaly?

---

### 2.10 Feature Flag Detection

**What it is:** Detect how feature flags are checked and where — environment-based, config-file-based, or service-based (LaunchDarkly, Unleash).

**AI value:** Feature flags create hidden code paths. The AI needs to know which features are gated and which flags are stale (always on/off).

**Layer 1 (AST):**
- Detect patterns: `if settings.FEATURE_X`, `if os.getenv("ENABLE_X")`, `if feature_flags.is_enabled("X")`
- Detect flag checking functions (functions whose sole purpose is checking a flag)
- Track which code paths are gated by each flag
- Detect stale flags via git: flags that haven't changed in N months
- Output: `{flag_name, check_pattern, file, line, gated_code_lines, last_modified}`

**Deep crawl extension:**
- Protocol C: Cross-cutting investigation — how are feature flags managed? Is there a centralized system?
- Gotcha: Nested feature flags (flag A gates code that also checks flag B)
- Change playbook: "Removing a feature flag" — all files that reference it

---

## Part 3: Deep Crawl Extensions for ALL New Signals

The deep crawl pipeline is xray's moat. Every new Layer 1 signal becomes exponentially more valuable when the deep crawl investigates it. Here's how the pipeline extends:

### New Investigation Protocol: Protocol G — Data Flow Trace

Neither tool traces data flow. Protocol A traces call flow (function→function), but not data flow (what data enters, how it transforms, where it lands).

**Protocol G procedure:**
1. Start at an entry point (route handler, CLI command, event handler)
2. Identify input data (request body, CLI args, event payload)
3. At each hop, document: what fields are read, what transforms happen, what's written
4. Track type changes: JSON string → dict → Pydantic model → ORM object → DB row
5. Document validation points: where is input validated? What's rejected?
6. Document the serialization boundaries (2.5): where does data cross format boundaries?
7. Terminal: where does the data land? (DB, file, API response, message queue)

**Output format:**
```
UserInput(json) → validate(Pydantic) → transform(service) → persist(ORM) → DB
  [FACT] Request body parsed at api/routes.py:42
  [FACT] Validated by UserCreate model at models/user.py:15
  [FACT] Email normalized at services/user.py:28
  [FACT] Written to users table at repos/user.py:55
  [ABSENCE] No input sanitization for name field
```

### New Domain Profile: database_heavy

**Indicators:** SQLAlchemy, Django ORM, Tortoise, alembic, migrations/, models/
**Additional investigation:**
- Migration history and schema evolution patterns
- Query patterns (N+1 queries, raw SQL, ORM relationships)
- Transaction boundaries (where do transactions start/commit/rollback?)
- Connection pool configuration and lifecycle
- Database session management (per-request, per-function, global)

### New Domain Profile: message_driven

**Indicators:** celery, dramatiq, rq, pika, kafka-python, kombu
**Additional investigation:**
- Message schema contracts between producers and consumers
- Retry and dead letter queue handling
- Idempotency guarantees for message handlers
- Message ordering dependencies
- Worker concurrency model

### Enhanced Validation (Check 6 extension)

The adversarial simulation currently tests "add new primary_entity." Extend with:
- "Fix a bug in {highest-risk file}" — does the document tell you what to watch out for?
- "Add a new env var" — does the document tell you where to add it and what format?
- "Handle a new error type" — does the document tell you the error handling convention?
- "Add a new feature flag" — does the document tell you the flag checking pattern?

---

## Part 4: Priority-Ranked Implementation Plan

### Tier 1 — High value, builds on existing infrastructure

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 1 | **Blast radius analysis** | Small | Import graph exists. Add BFS. Biggest bang-for-buck. |
| 2 | **Route detection (FastAPI/Flask/Django)** | Medium | Decorator args need capture. Fills biggest gap vs codesight. |
| 3 | **Env var classification** | Small | Already extracting env vars. Just add default detection. |
| 4 | **Error propagation paths** | Medium | Silent failure detection exists. Extend to flow analysis. |
| 5 | **Resource lifecycle** | Small | Context manager detection is simple AST. High safety value. |

### Tier 2 — Medium value, moderate effort

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 6 | **Magic method inventory** | Small | Already extracting methods. Just flag dunders. |
| 7 | **Import-time side effects** | Small | Module-level AST scan. High gotcha value. |
| 8 | **Serialization boundaries** | Medium | Pattern matching on known APIs. Security value. |
| 9 | **DI pattern detection** | Medium | Multiple patterns to recognize. Convention value. |
| 10 | **Concurrency primitives** | Medium | Pattern matching + lock ordering analysis. |

### Tier 3 — High value, significant effort

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 11 | **MCP server mode** | Large | New runtime mode. Industry direction. |
| 12 | **State machine detection** | Medium | Enum + transition analysis. Domain-specific value. |
| 13 | **Data flow trace (Protocol G)** | Large | Deep crawl only. Novel capability. |
| 14 | **Middleware detection** | Medium | Framework-specific patterns. Web app value. |
| 15 | **Watch mode** | Medium | Polling + incremental analysis. DX value. |

### Tier 4 — Nice to have

| # | Feature | Effort | Why |
|---|---------|--------|-----|
| 16 | **Feature flag detection** | Small | Pattern matching. Niche value. |
| 17 | **Monkey patch detection** | Small | setattr/type detection. Safety value. |
| 18 | **Route auto-tagging** | Small | Builds on route detection + existing side effects. |
| 19 | **Token savings benchmarking** | Small | Measure xray output efficiency. Marketing value. |
| 20 | **New domain profiles** | Small | Config-only additions to deep crawl. |

---

## Part 5: Verdict

### For Python analysis, the gap is wide

**xray: A** — 42+ deterministic signals, deep crawl with 6 investigation protocols, evidence standards, quality gates, validated output. The deep crawl pipeline alone is a category-defining capability.

**codesight on Python: C+** — ~6 shallow signals (routes, SQLAlchemy models, relative imports, public functions, env vars, hot files). Python is a second-class citizen — no published benchmarks, import tracking misses absolute imports, blast radius is JS-only.

### What codesight does better (for Python)

Honestly, only **one thing**: route detection for FastAPI/Flask/Django. And even that is limited — no middleware awareness, no route-to-handler tracing, no auth analysis. xray should add this (it's the #2 priority above) but the gap is narrow.

### What xray does that has no equivalent

The deep crawl pipeline. Codesight has no behavioral analysis, no request traces, no change impact analysis, no change playbooks, no gotcha detection, no evidence standards, no quality gates, no validation. It maps structure. xray investigates behavior. That's the fundamental difference.

### The 10 novel signals (Part 2) would widen the gap further

Adding resource lifecycle, magic methods, import-time side effects, concurrency primitives, serialization boundaries, DI patterns, error propagation, state machines, monkey patching, and feature flags — each with deep crawl extensions — would make xray the most comprehensive Python codebase intelligence tool that exists. No competitor touches this depth.

### Bottom line

codesight is a good TypeScript/JavaScript tool that added Python support as an afterthought. xray is a purpose-built Python intelligence system with a unique LLM-powered deep investigation pipeline. For Python codebases, comparing them is like comparing a tourist map to a geological survey.



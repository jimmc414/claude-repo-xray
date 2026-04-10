# TypeScript Frontend Architecture Specification

Version 0.1 — 2026-04-04

---

## 1. Purpose and Scope

### What this covers

This document specifies the architecture for a **TypeScript/JavaScript static analysis frontend** that plugs into the existing repo-xray pipeline. The frontend is a standalone Node.js script that parses TS/JS source files using the TypeScript Compiler API, extracts structural signals, and emits a JSON results dict conforming to the shared output contract defined in Section 2.

The frontend handles files with extensions: `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.mjs`, `.cts`, `.cjs`.

### What this does NOT cover

- **Formatters**: `markdown_formatter.py` and `json_formatter.py` are language-agnostic consumers of the results dict. They are unchanged.
- **Config system**: `config_loader.py`, `configs/presets.json`, `configs/default_config.json` are reused as-is.
- **Git analysis**: `git_analysis.py` operates on file paths and git history, not language constructs. Reused as-is.
- **Deep crawl agents**: The agent layer reads `xray.json` output. It requires no changes as long as the output contract holds.
- **Orchestrator design**: How `xray.py` dispatches to the TS frontend is deferred.
- **Implementation details**: Exact code patterns, error handling minutiae, and testing strategy are separate documents.

### Inherited design constraints

From INTENT.md, the TS frontend inherits:

| Constraint | Implication for TS frontend |
|---|---|
| **Deterministic** | Same input files → same output JSON. No network calls, no randomness, no LLM inference. |
| **Fast** | Target: 500 files in ≤5 seconds (syntax-only tier). Semantic tier may be slower. |
| **Fault-tolerant per-file** | A parse error in one file must not crash the scan. Partial results with `parse_error` field. |
| **Minimal dependencies** | Single external dependency: the `typescript` npm package. No Babel, no ESLint, no bundler plugins. |
| **Read-only** | Observe and report. Never modify source files. |

### Why the TypeScript Compiler API

The deep research report (scored 23.3/25, highest of 8 language candidates) recommends the TypeScript Compiler API as the parser for both TypeScript and JavaScript. Key reasons:

1. **Unified TS/JS parsing** — One AST model handles `.ts`, `.tsx`, `.js`, `.jsx`, and JSDoc type annotations in JS files.
2. **Two-tier architecture** — `ts.createSourceFile()` for fast syntax-only; `ts.createProgram()` for full type resolution. Same API surface.
3. **Official, stable, widely used** — The compiler API is TypeScript itself, not a third-party wrapper.
4. **JSDoc type inference** — TypeScript can derive type information from JavaScript files with JSDoc annotations, providing partial type coverage for JS codebases.
5. **Error recovery** — The parser produces a partial AST even for files with syntax errors.

---

## 2. The Output Contract

This is the load-bearing section. Every downstream consumer — formatters, gap features, investigation targets, deep crawl agents — reads the results dict produced by `run_analysis()` (xray.py:291-477). The TS frontend must produce a dict with the **same shape**.

The schema below is extracted directly from the Python codebase. Types use TypeScript notation for clarity since this document targets TS implementors.

### 2.1 Top-Level Results Dict

```typescript
interface XRayResults {
  // Always present
  metadata: Metadata;
  summary: Summary;

  // Conditional on analysis options (present when enabled)
  structure?: Structure;
  complexity?: Complexity;
  types?: TypeCoverage;
  decorators?: DecoratorInventory;
  side_effects?: SideEffects;
  imports?: ImportAnalysis;
  calls?: CallAnalysis;
  git?: GitAnalysis;
  tests?: TestAnalysis;
  tech_debt?: TechDebt;

  // Always present when AST analysis runs (no config gate)
  security_concerns?: Record<string, SecurityConcern[]>;
  silent_failures?: Record<string, SilentFailure[]>;
  sql_strings?: Record<string, SqlString[]>;
  deprecation_markers?: DeprecationMarker[];
  async_patterns?: AsyncPatterns;

  // Supplementary (config-gated or derived)
  hotspots?: Hotspot[];
  author_expertise?: { note: string };
  commit_sizes?: CommitSize[];
  investigation_targets?: InvestigationTargets;

  // TS-specific extension (see Section 4)
  ts_specific?: TsSpecific;
}
```

### 2.2 Metadata

```typescript
interface Metadata {
  tool_version: string;           // e.g. "0.9.2"
  generated_at: string;           // ISO 8601, e.g. "2026-04-04T12:00:00Z"
  target_directory: string;       // Absolute path to scanned root
  preset: string | null;          // "minimal" | "standard" | "full" | null
  analysis_options: string[];     // ["skeleton", "complexity", "types", ...]
  file_count: number;
  // TS extension
  language?: "python" | "typescript";
  parser_tier?: "syntax" | "semantic";
  tsconfig_path?: string | null;
}
```

### 2.3 Summary

```typescript
interface Summary {
  total_files: number;
  total_lines: number;
  total_tokens: number;           // Estimated token count (original source)
  total_functions: number;
  total_classes: number;
  type_coverage: number;          // 0.0-100.0 percentage
  // Present when complexity analysis runs
  total_cc?: number;
  average_cc?: number;
  // TS extensions
  typed_functions?: number;       // Count of functions with explicit type annotations
}
```

### 2.4 Structure (skeleton)

Populated when `"skeleton"` is in analysis options.

```typescript
interface Structure {
  files: Record<string, FileAnalysis>;    // filepath → per-file analysis
  classes: ClassInfo[];                    // Aggregated across all files
  functions: FunctionInfo[];              // Aggregated across all files
}
```

#### 2.4.1 Per-File Analysis (`FileAnalysis.to_dict()`)

This is the per-file schema from `ast_analysis.py:134-170`. Every field must be present.

```typescript
interface FileAnalysis {
  filepath: string;
  line_count: number;
  classes: ClassInfo[];
  functions: FunctionInfo[];
  constants: ConstantInfo[];
  complexity: {
    total_cc: number;
    hotspots: Record<string, number>;    // function_name → CC score
  };
  type_coverage: {
    total_functions: number;
    typed_functions: number;
    coverage_percent: number;            // 0.0-100.0
  };
  decorators: Record<string, number>;    // decorator_name → count
  async_patterns: {
    async_functions: number;
    sync_functions: number;
    async_for_loops: number;
    async_context_managers: number;
  };
  side_effects: SideEffect[];
  security_concerns: SecurityConcern[];
  silent_failures: SilentFailure[];
  async_violations: AsyncViolation[];
  sql_strings: SqlString[];
  deprecation_markers: DeprecationMarker[];
  internal_calls: InternalCall[];
  tokens: {
    original: number;
    skeleton: number;
  };
  parse_error: string | null;
}
```

#### 2.4.2 ClassInfo

```typescript
interface ClassInfo {
  name: string;
  bases: string[];                       // Base class names
  methods: MethodInfo[];
  decorators: string[];
  line: number;
  docstring: string | null;
  file?: string;                         // Set during aggregation
}

interface MethodInfo {
  name: string;
  args: string[];                        // Parameter names (with type annotations if present)
  returns: string | null;                // Return type annotation
  decorators: string[];
  is_async: boolean;
  line: number;
  complexity: number;
}
```

#### 2.4.3 FunctionInfo

```typescript
interface FunctionInfo {
  name: string;
  args: string[];
  returns: string | null;
  decorators: string[];
  is_async: boolean;
  line: number;
  complexity: number;
  docstring: string | null;
  file?: string;                         // Set during aggregation
}
```

#### 2.4.4 ConstantInfo

```typescript
interface ConstantInfo {
  name: string;
  value: string | null;                  // String representation of value
  line: number;
}
```

### 2.5 Complexity

```typescript
interface Complexity {
  hotspots: Hotspot[];                   // Top 20 by CC
  average_cc: number;
  total_cc: number;
}

interface Hotspot {
  file: string;
  function: string;
  complexity: number;
}
```

### 2.6 Type Coverage

```typescript
interface TypeCoverage {
  coverage: number;                      // 0.0-100.0
  typed_functions: number;
  total_functions: number;
}
```

**TS-specific note**: In Python, type coverage measures functions with annotations (higher = better). In TypeScript, most code is typed by default. The useful inverse signal is **`any` density** — how many explicit or implicit `any` types exist. See Section 4 for the extension.

### 2.7 Decorators

```typescript
interface DecoratorInventory {
  inventory: Record<string, number>;     // decorator_name → count across codebase
}
```

**TS mapping**: TypeScript decorators (`@decorator`) map directly. The experimental decorator proposal and the TC39 Stage 3 decorators both produce AST nodes. Framework-specific function wrappers (e.g., `withAuth(handler)`) are NOT decorators for this purpose — they're call expressions.

### 2.8 Side Effects

```typescript
interface SideEffects {
  by_type: Record<string, SideEffectEntry[]>;
  by_file: Record<string, SideEffect[]>;
}

interface SideEffect {
  category: string;                      // "file_io", "network", "subprocess", "env_access", etc.
  call: string;                          // The call expression, e.g. "fs.readFileSync"
  line: number;
}

interface SideEffectEntry {
  file: string;
  call: string;
  line: number;
}
```

**TS side effect categories** (paralleling Python):

| Python pattern | TS/JS equivalent | Category |
|---|---|---|
| `open()`, `Path.write_text()` | `fs.readFile()`, `fs.writeFileSync()` | `file_io` |
| `requests.get()`, `urllib` | `fetch()`, `axios`, `http.request()` | `network` |
| `subprocess.run()` | `child_process.exec()`, `spawn()` | `subprocess` |
| `os.environ` | `process.env` | `env_access` |
| `print()` | `console.log()`, `console.error()` | `console_io` |
| `sqlite3.connect()` | DB client calls (`pg`, `mysql2`, `prisma`) | `database` |

### 2.9 Import Analysis

From `import_analysis.py:671-698`.

```typescript
interface ImportAnalysis {
  graph: Record<string, {
    imports: string[];                   // Modules this module imports
    imported_by: string[];               // Modules that import this module
  }>;
  layers: Record<string, string[]>;      // layer_name → module list
  aliases: Record<string, string>;       // alias → real module name
  alias_patterns: string[];
  orphans: string[];                     // Modules with no imports or importers
  circular: string[][];                  // Each entry is a cycle [A, B, ..., A]
  external_deps: string[];               // Sorted list of external package names
  distances: {
    max_depth: number;
    avg_depth: number;
    tightly_coupled: Array<{ modules: string[]; score: number }>;
    hub_modules: Array<{ module: string; connections: number }>;
  };
  summary: {
    total_modules: number;
    internal_edges: number;
    circular_count: number;
    orphan_count: number;
    external_deps_count: number;
  };
}
```

**TS import mapping**:

| Python | TS/JS |
|---|---|
| `import foo` | `import foo from "foo"` (ESM default) |
| `from foo import bar` | `import { bar } from "foo"` (ESM named) |
| `from foo import *` | `import * as foo from "foo"` (ESM namespace) |
| Relative: `from .sibling import x` | `import { x } from "./sibling"` |
| N/A | `const foo = require("foo")` (CommonJS) |
| N/A | `import("foo")` (dynamic import) |

The import analysis must handle both ESM (`import`/`export`) and CommonJS (`require()`/`module.exports`). Dynamic `import()` calls are recorded but treated as edges with lower confidence.

### 2.10 Call Analysis

From `call_analysis.py:422-437`.

```typescript
interface CallAnalysis {
  cross_module: Record<string, {
    call_count: number;
    call_sites: Array<{
      file: string;
      line: number;
      caller: string;
    }>;
  }>;
  reverse_lookup: Record<string, {
    caller_count: number;
    impact_rating: "high" | "medium" | "low";
    callers: Array<{ file: string; function: string }>;
  }>;
  most_called: Array<{ function: string; count: number }>;
  most_callers: Array<{ function: string; callers: number }>;
  isolated_functions: string[];
  high_impact: Array<{
    function: string;
    impact: "high";
    callers: number;
  }>;
  summary: {
    total_cross_module_calls: number;
    functions_with_cross_module_callers: number;
    high_impact_functions: number;
    isolated_functions: number;
  };
}
```

**TS-specific call graph limitations** (from deep research report):

Static call graphs for JavaScript/TypeScript are a known research problem. Syntax-only extraction delivers useful structural signals but cannot fully resolve:
- Callback-passing patterns (`array.map(fn)` — which `fn`?)
- Dynamic property access (`obj[key]()`)
- Event-driven dispatch (`emitter.on("event", handler)`)
- Higher-order component wrapping in React

The TS frontend should extract what is statically visible and document the confidence level. The semantic tier improves resolution for typed code but dynamic patterns remain a ceiling.

### 2.11 Git Analysis

Reused as-is from `git_analysis.py`. Included here for completeness of the contract.

```typescript
interface GitAnalysis {
  risk: Record<string, {
    score: number;
    factors: string[];
  }>;
  coupling: Array<{
    file_a: string;
    file_b: string;
    score: number;
    confidence: number;
    count: number;
  }>;
  freshness: Record<string, {
    last_modified: string;
    days_since: number;
    status: "fresh" | "recent" | "aging" | "stale";
  }>;
  function_churn: Record<string, number>;
  coupling_clusters: Array<{
    files: string[];
    cohesion: number;
  }>;
  velocity: {
    commits_per_week: number;
    active_files: number;
    trend: "accelerating" | "steady" | "decelerating";
  };
}
```

### 2.12 Test Analysis

```typescript
interface TestAnalysis {
  test_file_count: number;
  test_function_count: number;
  tested_modules: string[];
  untested_modules: string[];
  test_files: Array<{
    path: string;
    test_count: number;
  }>;
  fixtures?: string[];
  summary: {
    coverage_estimate: number;           // 0.0-100.0
  };
}
```

**TS test framework mapping**:

| Python | TS/JS |
|---|---|
| pytest (`test_*.py`, `def test_`) | Jest/Vitest (`*.test.ts`, `describe`/`it`/`test`) |
| unittest (`class TestX(unittest.TestCase)`) | Mocha (`describe`/`it`) |
| conftest.py fixtures | `beforeEach`/`afterEach`, test setup files |

Test file detection patterns for TS:
- `**/*.test.{ts,tsx,js,jsx}`
- `**/*.spec.{ts,tsx,js,jsx}`
- `**/__tests__/**/*.{ts,tsx,js,jsx}`
- `**/test/**/*.{ts,tsx,js,jsx}`

### 2.13 Tech Debt

```typescript
interface TechDebt {
  items: Array<{
    file: string;
    line: number;
    type: "TODO" | "FIXME" | "HACK" | "XXX" | "DEPRECATED";
    text: string;
  }>;
  deprecations: Array<{
    file: string;
    line: number;
    text: string;
  }>;
  summary: {
    total_count: number;
    by_type: Record<string, number>;
  };
}
```

Language-agnostic. Same regex patterns work for TS/JS comments (`//` and `/* */`).

### 2.14 Security Concerns

```typescript
// Keyed by filepath
type SecurityConcerns = Record<string, SecurityConcern[]>;

interface SecurityConcern {
  type: string;                          // "eval", "exec", "dynamic_import", etc.
  call: string;                          // The expression
  line: number;
  severity: "high" | "medium" | "low";
}
```

**TS security equivalents**:

| Python | TS/JS | Severity |
|---|---|---|
| `eval()` | `eval()` | high |
| `exec()` | `new Function()` | high |
| `compile()` | N/A | — |
| `os.system()` | `child_process.exec()` | high |
| `pickle.loads()` | `JSON.parse()` (benign), `deserialize()` | medium |
| `__import__()` | `import()` (dynamic) | medium |
| `subprocess.call(shell=True)` | `exec(cmd)` with string interpolation | high |
| N/A | `innerHTML` assignment | medium |
| N/A | `document.write()` | medium |
| N/A | `dangerouslySetInnerHTML` (React) | medium |

### 2.15 Silent Failures

```typescript
type SilentFailures = Record<string, SilentFailure[]>;

interface SilentFailure {
  type: string;                          // "empty_catch", "bare_catch", "pass_in_except"
  line: number;
  context: string;                       // Enclosing function/method
}
```

**TS mapping**:

| Python pattern | TS/JS equivalent |
|---|---|
| `except: pass` | `catch (e) {}` (empty catch block) |
| `except Exception:` (bare) | `catch {}` (catch without variable) |
| `except Exception as e: pass` | `catch (e) { /* intentionally empty */ }` |
| N/A | `.catch(() => {})` (swallowed promise rejection) |
| N/A | Missing `.catch()` on a promise chain |

### 2.16 Async Patterns

```typescript
interface AsyncPatterns {
  async_functions: number;
  sync_functions: number;
  async_for_loops: number;               // TS: `for await (const x of iter)`
  async_context_managers: number;         // TS: N/A directly; map to `using` (Stage 3)
  violations?: AsyncViolation[];
}

interface AsyncViolation {
  file: string;
  function: string;
  violation: string;                     // "blocking_call_in_async", "missing_await", etc.
  line: number;
}
```

**TS async-specific signals**:

| Signal | Detection |
|---|---|
| `async` functions | `ts.SyntaxKind.AsyncKeyword` modifier |
| `await` expressions | `ts.SyntaxKind.AwaitExpression` |
| `for await...of` | `ts.SyntaxKind.ForOfStatement` with `awaitModifier` |
| Missing `await` on async call | Syntax-only: heuristic. Semantic: check return type for `Promise`. |
| Blocking call in async | Pattern-match `fs.readFileSync` etc. inside `async` functions |
| Unhandled promise | Semantic tier: detect `Promise` return without `await`/`.then()` |

### 2.17 SQL Strings

```typescript
type SqlStrings = Record<string, SqlString[]>;

interface SqlString {
  line: number;
  sql: string;                           // The SQL string content
  context: string;                       // Enclosing function
  type: "query" | "template" | "tagged"; // How the SQL was expressed
}
```

TS detection targets:
- String literals containing SQL keywords (`SELECT`, `INSERT`, `CREATE TABLE`, etc.)
- Tagged template literals: `` sql`SELECT ...` ``
- ORM query builders passed raw SQL strings

### 2.18 Deprecation Markers

```typescript
interface DeprecationMarker {
  file: string;
  name: string;                          // Function/class/method name
  line: number;
  reason: string | null;
  source: "decorator" | "jsdoc" | "comment";
}
```

TS detection:
- `@deprecated` JSDoc tag
- `/** @deprecated reason */` comments
- Custom `@Deprecated()` decorators (if present)
- TypeScript's built-in `@deprecated` tag in JSDoc is recognized by the compiler

### 2.19 Investigation Targets

From `investigation_targets.py`. This is the key bridge to the deep crawl layer.

```typescript
interface InvestigationTargets {
  ambiguous_interfaces: Array<{
    function: string;
    class: string | null;
    file: string;
    line: number;
    reason: string;
    type_coverage: number;
    cc: number;
    cross_module_callers: number;
    ambiguity_score: number;
  }>;
  entry_to_side_effect_paths: Array<{
    entry_point: string;
    entry_type: string;
    reachable_side_effects: string[];
    estimated_hop_count: number;
    modules_traversed: number;
    granularity: string;
  }>;
  coupling_anomalies: Array<{
    files: string[];
    co_modification_score: number;
    has_import_relationship: boolean;
    reason: string;
  }>;
  convention_deviations: Array<{
    convention: string;
    conforming_count: number;
    violating: string[];
  }>;
  shared_mutable_state: Array<{
    variable: string;
    file: string;
    line: number;
    scope: string;
    mutated_by: string[];
    risk: string;
  }>;
  high_uncertainty_modules: Array<{
    module: string;
    reasons: string[];
    uncertainty_score: number;
    fan_in: number;
    type_coverage: number;
    max_cc: number;
  }>;
  domain_entities: Array<{
    name: string;
    type: string;
    file: string;
    line: number;
    fields?: string[];
    referenced_in?: string[];
  }>;
  summary: {
    ambiguous_interfaces: number;
    entry_paths: number;
    coupling_anomalies: number;
    convention_deviations: number;
    shared_mutable_state: number;
    high_uncertainty_modules: number;
    domain_entities: number;
  };
}
```

### 2.20 Formatter Contract Summary

The following table lists every top-level key read by each downstream consumer, confirming the contract boundary.

| Key | markdown_formatter | json_formatter | gap_features | investigation_targets |
|---|:---:|:---:|:---:|:---:|
| `metadata` | R | R | — | — |
| `summary` | R | R | R | — |
| `structure` | R | R | R | — |
| `structure.files` | — | — | R | R (via ast_results) |
| `complexity` | — | R | — | — |
| `hotspots` | R | R | R | — |
| `types` | — | R | — | — |
| `decorators` | R | R | — | — |
| `side_effects` | R | R | — | — |
| `imports` | R | R | R | R |
| `imports.graph` | — | — | R | R |
| `imports.circular` | — | R | — | — |
| `imports.external_deps` | — | — | R | — |
| `imports.layers` | — | — | R | — |
| `calls` | R | R | R | R |
| `calls.most_called` | — | — | R | — |
| `calls.high_impact` | — | R | — | — |
| `calls.cross_module` | — | — | — | R |
| `git` | R | R | R | R |
| `git.risk` | — | — | R | R |
| `git.coupling` | — | — | — | R |
| `tests` | R | R | R | — |
| `tests.tested_modules` | — | — | R | — |
| `tests.test_file_count` | — | — | R | — |
| `tech_debt` | R | R | — | — |
| `security_concerns` | R | R | — | — |
| `silent_failures` | R | R | — | — |
| `sql_strings` | R | R | — | — |
| `deprecation_markers` | R | R | — | — |
| `async_patterns` | R | — | — | — |
| `investigation_targets` | R | R | — | — |
| `author_expertise` | — | R | — | — |
| `commit_sizes` | — | R | — | — |
| `priority_files` | — | R | — | — |

R = reads this key.

---

## 3. Signal Mapping Table

This section maps every Python scanner signal to its TypeScript Compiler API equivalent. This is the Rosetta Stone for implementation.

### 3.1 Skeleton Extraction

| Python AST construct | TS equivalent | SyntaxKind / API | Notes |
|---|---|---|---|
| `ast.ClassDef` | Class declaration | `ClassDeclaration`, `ClassExpression` | Also handle `class X extends Y implements Z` |
| `ast.FunctionDef` | Function declaration | `FunctionDeclaration`, `FunctionExpression`, `ArrowFunction`, `MethodDeclaration` | Arrow functions are pervasive in TS |
| `ast.AsyncFunctionDef` | Async function | Check `AsyncKeyword` in modifiers | Same node types, different modifier |
| `ast.arguments` | Parameters | `Parameter` nodes from `parameters` property | Includes destructuring, rest, defaults |
| `ast.Return` + annotation | Return type | `type` property on function node, or `ReturnStatement` | Explicit annotation or inferred (semantic tier) |
| `ast.Assign` (module-level) | Const declaration | `VariableStatement` with `ConstKeyword` at module scope | `const X = ...` |
| `ast.Name` (bases) | Heritage clauses | `HeritageClause` with `ExtendsKeyword` or `ImplementsKeyword` | |
| Docstring (first `ast.Expr(ast.Constant(str))`) | JSDoc comment | `ts.getJSDocTags()` or leading comment trivia | TS compiler has first-class JSDoc support |
| `@decorator` | `@decorator` | `Decorator` nodes in `modifiers` / `decorators` array | TC39 Stage 3 decorators or `experimentalDecorators` |

### 3.2 Cyclomatic Complexity

Branching constructs that increment CC by 1:

| Python | TS/JS | SyntaxKind |
|---|---|---|
| `if` | `if` | `IfStatement` |
| `elif` | `else if` | Nested `IfStatement` in `elseStatement` |
| `for` | `for`, `for...of`, `for...in` | `ForStatement`, `ForOfStatement`, `ForInStatement` |
| `while` | `while` | `WhileStatement` |
| `except` (each) | `catch` | `CatchClause` |
| `and` | `&&` | `BinaryExpression` with `AmpersandAmpersandToken` |
| `or` | `\|\|` | `BinaryExpression` with `BarBarToken` |
| `x if cond else y` | `cond ? x : y` | `ConditionalExpression` |
| `case` (match statement) | `case` (switch) | `CaseClause` |
| N/A | `??` (nullish coalescing) | `BinaryExpression` with `QuestionQuestionToken` |
| N/A | `?.` (optional chaining) | `CallExpression` with `QuestionDotToken` — count or not is a design choice; recommend **not** counting to avoid noise |

### 3.3 Type Coverage

| Python signal | TS equivalent | Detection | Tier |
|---|---|---|---|
| Functions with param annotations | Functions with explicit param types | Check `type` property on `Parameter` nodes | Syntax |
| Functions with return annotations | Functions with explicit return types | Check `type` property on function node | Syntax |
| Coverage % (typed/total) | Coverage % (typed/total) | Same formula | Syntax |
| N/A | `any` count (explicit) | Count `AnyKeyword` type nodes | Syntax |
| N/A | `any` count (implicit) | Inferred `any` from missing types | Semantic |
| N/A | `as any` assertions | `AsExpression` with `AnyKeyword` | Syntax |
| N/A | `@ts-ignore` / `@ts-expect-error` | Comment scanning | Syntax |

### 3.4 Import / Dependency Graph

| Python | TS/JS | SyntaxKind | Notes |
|---|---|---|---|
| `import foo` | `import foo from "foo"` | `ImportDeclaration` with default import | |
| `from foo import bar` | `import { bar } from "foo"` | `ImportDeclaration` with named bindings | |
| `from foo import *` | `import * as foo from "foo"` | `ImportDeclaration` with namespace import | |
| N/A | `import type { T } from "foo"` | `ImportDeclaration` with `isTypeOnly` | Type-only imports (no runtime effect) |
| N/A | `require("foo")` | `CallExpression` with `Identifier("require")` | CommonJS |
| N/A | `import("foo")` | `CallExpression` with `ImportKeyword` | Dynamic import |
| N/A | `export { bar } from "foo"` | `ExportDeclaration` with `moduleSpecifier` | Re-exports |

**Module resolution for the import graph**: The syntax tier records raw specifiers as-is (`"./utils"`, `"react"`, `"@scope/pkg"`). The semantic tier can resolve specifiers to actual file paths using the TypeScript module resolution algorithm and tsconfig paths.

### 3.5 Cross-Module Call Graph

| Python | TS/JS | Detection | Difficulty |
|---|---|---|---|
| `module.function()` | `import { fn } from "./mod"; fn()` | Track import bindings → call expressions | Medium |
| `from mod import cls; cls.method()` | `import { Cls } from "./mod"; new Cls().method()` | Syntax: heuristic. Semantic: type-based. | Hard |
| N/A | `default export` calls | Track default import binding → call | Medium |
| N/A | `require("mod").fn()` | Match `require` call + property access | Medium |
| N/A | Callback passing | `fn(otherFn)` — static resolution loses the edge | Ceiling |
| N/A | Event emitter patterns | `emitter.on("x", handler)` → `emitter.emit("x")` | Ceiling |

### 3.6 Side Effects

| Python pattern | TS/JS pattern | Category |
|---|---|---|
| `open(f)`, `Path(f).read_text()` | `fs.readFile*`, `fs.writeFile*`, `fs.open` | `file_io` |
| `requests.*`, `urllib.*` | `fetch()`, `axios.*`, `http.request()`, `got.*` | `network` |
| `subprocess.*` | `child_process.*`, `execa()`, `spawn()` | `subprocess` |
| `os.environ` | `process.env.*` | `env_access` |
| `print()` | `console.*` | `console_io` |
| `sqlite3.*`, `psycopg2.*` | `pg.*`, `mysql2.*`, `prisma.*`, `knex.*`, `sequelize.*` | `database` |
| `os.remove()`, `shutil.*` | `fs.unlink()`, `fs.rm()`, `rimraf.*` | `file_io` |
| `sys.exit()` | `process.exit()` | `process` |

### 3.7 Security Concerns

| Python | TS/JS | Severity |
|---|---|---|
| `eval(expr)` | `eval(expr)` | high |
| `exec(code)` | `new Function(code)` | high |
| `compile(code, ...)` | N/A | — |
| `os.system(cmd)` | `exec(cmd)` from `child_process` | high |
| `subprocess.call(shell=True)` | Template string in `exec()` | high |
| `__import__(name)` | `import(expr)` (dynamic) | medium |
| `pickle.loads(data)` | `deserialize(data)`, `eval(JSON)` | medium |
| N/A | `innerHTML = expr` | medium |
| N/A | `document.write(expr)` | medium |
| N/A | `dangerouslySetInnerHTML` | medium |
| N/A | `RegExp(userInput)` | low |

### 3.8 Silent Failures

| Python | TS/JS |
|---|---|
| `except: pass` / `except Exception: pass` | `catch (e) {}` — empty catch body |
| `except Exception:` (bare, no variable) | `catch {}` — catch without binding |
| N/A | `.catch(() => {})` — swallowed promise rejection |
| N/A | `.catch(() => undefined)` — returns falsy from catch |
| N/A | Missing return in `.then()` chain (drops value) |

### 3.9 Async Patterns

| Python | TS/JS | Detection |
|---|---|---|
| `async def f()` | `async function f()` / `async () => {}` | `AsyncKeyword` modifier |
| `await expr` | `await expr` | `AwaitExpression` |
| `async for x in iter` | `for await (const x of iter)` | `ForOfStatement` with `awaitModifier` |
| `async with ctx` | `await using x = ...` (TC39 Stage 3) | `UsingKeyword` + `AwaitKeyword` |
| Blocking in async | `fs.readFileSync()` in `async` function | Pattern match sync APIs in async scope |
| N/A | `Promise.all()`, `Promise.race()` | Call expression detection |

### 3.10 Decorators / Annotations

| Python | TS/JS |
|---|---|
| `@app.route("/path")` | `@Get("/path")` (NestJS), route decorators |
| `@staticmethod` | `static` keyword (not a decorator) |
| `@property` | `get`/`set` accessors (not decorators) |
| `@dataclass` | No direct equivalent (see Section 4 data models) |
| `@pytest.fixture` | No equivalent (different test patterns) |
| `@deprecated` | `@Deprecated()` custom decorator, or JSDoc `@deprecated` |
| N/A | `@Injectable()` (NestJS/Angular DI) |
| N/A | `@Component()` (Angular) |
| N/A | `@Entity()` (TypeORM) |

### 3.11 Data Models

| Python | TS/JS |
|---|---|
| `@dataclass` | `interface`, `type` alias, class with typed fields |
| Pydantic `BaseModel` | Zod schema, io-ts, class-validator class |
| `TypedDict` | `interface` / `type` with object shape |
| `NamedTuple` | Tuple type with labels |
| `Enum` | `enum` (first-class in TS) |
| `attrs` class | Class with constructor parameter properties |

### 3.12 Entry Points

| Python | TS/JS |
|---|---|
| `if __name__ == "__main__"` | `package.json` `"main"` / `"bin"` fields |
| `@app.route()` (Flask/FastAPI) | Express route handlers, NestJS controllers |
| CLI `argparse` setup | Commander.js / yargs setup |
| `setup.py` / `pyproject.toml` `[scripts]` | `package.json` `"scripts"` and `"bin"` |
| N/A | `export default` in page files (Next.js) |
| N/A | `app.listen()` / `createServer()` |
| N/A | Lambda/serverless handler exports |
| N/A | React component exports (JSX files) |

### 3.13 Test Patterns

| Python | TS/JS |
|---|---|
| `def test_*` | `it()`, `test()` calls |
| `class Test*(unittest.TestCase)` | `describe()` blocks |
| `conftest.py` fixtures | `beforeEach`/`afterEach`/`beforeAll`/`afterAll` |
| `@pytest.mark.parametrize` | `it.each()` / `test.each()` (Jest) |
| `test_*.py` / `*_test.py` | `*.test.ts` / `*.spec.ts` / `__tests__/` |

### 3.14 Tech Debt Markers

Language-agnostic. Same patterns (`TODO`, `FIXME`, `HACK`, `XXX`, `DEPRECATED`) work in both `//` and `/* */` comments.

### 3.15 SQL String Detection

| Python | TS/JS |
|---|---|
| f-strings/strings with SQL keywords | Template literals with SQL keywords |
| N/A | Tagged templates: `` sql`SELECT ...` `` (common pattern) |
| N/A | Raw SQL in ORM calls: `prisma.$queryRaw`, `knex.raw()` |

### 3.16 Deprecation Markers

| Python | TS/JS |
|---|---|
| `@deprecated` decorator | `/** @deprecated reason */` JSDoc tag |
| `warnings.warn("deprecated")` | `console.warn("deprecated")` (heuristic) |
| N/A | `@Deprecated()` custom decorator |
| Comment-based (`# DEPRECATED`) | Comment-based (`// DEPRECATED`) — shared with tech debt |

### 3.17 Signal Feasibility Summary

From the deep research report's JS/TS feasibility matrix:

| Signal | Syntax-Only | With Semantic | Notes |
|---|---|---|---|
| Code skeletons | Excellent | Excellent | Arrow functions and exports require conventions |
| Cyclomatic complexity | Excellent | Excellent | All branches syntactic |
| Type annotation coverage | Partial | Good | JS lacks types; JSDoc helps |
| Import/dependency graph | Good | Excellent | CommonJS `require()` is syntactic but dynamic requires heuristic |
| Cross-module call graph | Partial | Good | Known-hard for JS; ceiling exists |
| Side effect detection | Good | Good | Pattern-match API names |
| Security concerns | Excellent | Excellent | `eval`, `Function`, dynamic patterns |
| Silent failures | Good | Good | Empty catch blocks syntactic |
| Async/concurrency | Excellent | Excellent | `async/await` and Promises are syntactic |
| Decorator inventory | Partial | Good | Decorators are proposal-dependent |
| Data model extraction | Partial | Good | Classes exist; many models are plain objects |
| Entry point detection | Good | Good | `package.json` + framework conventions |
| Git risk scores | Excellent | Excellent | Language-agnostic (reused) |
| Test coverage mapping | Good | Good | Jest/Vitest conventions |
| Tech debt markers | Excellent | Excellent | Language-agnostic (reused) |
| SQL string detection | Good | Good | Tagged templates identifiable |
| Deprecation markers | Partial | Partial | JSDoc `@deprecated` parseable |

---

## 4. TypeScript-Specific Signals

TypeScript has constructs with no Python equivalent. These must be captured without breaking the shared schema. Strategy: add fields to existing structures where natural, plus an optional `ts_specific` top-level key for constructs that don't map.

### 4.1 Interfaces and Type Aliases

```typescript
// These are core TS constructs with no Python equivalent.
// Map to: structure.files[path].ts_interfaces and structure.files[path].ts_type_aliases

interface TsInterfaceInfo {
  name: string;
  extends: string[];                     // Extended interfaces
  members: Array<{
    name: string;
    type: string;
    optional: boolean;
  }>;
  type_parameters: string[];             // Generic parameters
  line: number;
  exported: boolean;
}

interface TsTypeAliasInfo {
  name: string;
  type_kind: "object" | "union" | "intersection" | "mapped" | "conditional" | "primitive" | "other";
  type_parameters: string[];
  line: number;
  exported: boolean;
}
```

**Where in the schema**: Add to `FileAnalysis` as optional fields:
- `ts_interfaces?: TsInterfaceInfo[]`
- `ts_type_aliases?: TsTypeAliasInfo[]`

Interfaces also appear in the aggregated `Structure.classes` list with a marker `kind: "interface"` so that downstream consumers that iterate classes see them.

### 4.2 Enums

```typescript
interface TsEnumInfo {
  name: string;
  members: Array<{
    name: string;
    value: string | number | null;
  }>;
  is_const: boolean;                     // `const enum` (inlined at compile time)
  line: number;
  exported: boolean;
}
```

**Where in the schema**: Add to `FileAnalysis` as `ts_enums?: TsEnumInfo[]`. Also include in `Structure.classes` with `kind: "enum"` for aggregation.

### 4.3 Generics and Type Parameters

Type parameters are captured inline on classes, interfaces, functions, and type aliases via the `type_parameters` field (a `string[]` of parameter names).

No separate top-level key needed. The `FunctionInfo.args` array already includes type annotations in the string representation (e.g., `"items: T[]"`).

### 4.4 Union and Intersection Types

Not tracked individually. Their presence is captured:
- In type alias `type_kind` field
- In function parameter/return types as string representations
- In `ts_specific.any_density` when a union includes `any`

### 4.5 Declaration Files (.d.ts)

Declaration files define type shapes without implementation. They are:
- **Scanned** for interfaces, type aliases, enums, and exports
- **Excluded** from complexity, side effects, and security analysis (no runtime code)
- **Flagged** in `FileAnalysis` with `is_declaration: true`

### 4.6 JSX Components

JSX component definitions serve as structural entry points. Detected via:
- Functions/classes that return `JSX.Element` or `React.ReactElement` (semantic tier)
- Functions that contain JSX expressions (`JsxElement`, `JsxSelfClosingElement`) (syntax tier)
- Export position: default-exported components in files matching page/route patterns

Components appear in `FunctionInfo` / `ClassInfo` with an additional marker: `is_component: true`.

### 4.7 Module Augmentation and Declaration Merging

```typescript
// declare module "express" { ... }
// Extends third-party types
```

Captured in `ts_specific.module_augmentations` as an informational signal:
```typescript
interface ModuleAugmentation {
  target_module: string;                 // The module being augmented
  file: string;
  line: number;
  additions: string[];                   // Names of added declarations
}
```

### 4.8 The `ts_specific` Top-Level Key

```typescript
interface TsSpecific {
  // Type safety metrics
  any_density: {
    explicit_any: number;                // `x: any` declarations
    as_any_assertions: number;           // `x as any` expressions
    ts_ignore_count: number;             // @ts-ignore comments
    ts_expect_error_count: number;       // @ts-expect-error comments
  };
  // Module system
  module_system: "esm" | "commonjs" | "mixed";
  // Declaration files
  declaration_file_count: number;
  // Module augmentations
  module_augmentations: ModuleAugmentation[];
  // Namespace usage (legacy but still common)
  namespaces: Array<{
    name: string;
    file: string;
    line: number;
    exported: boolean;
  }>;
  // Project references (from tsconfig)
  project_references?: string[];
}
```

### 4.9 Schema Extension Strategy

**Principle**: The shared formatters and investigation targets read a fixed set of keys (Section 2.20). TS-specific data is added via:

1. **Optional fields on existing interfaces** — e.g., `ts_interfaces` on `FileAnalysis`, `is_component` on `FunctionInfo`. Downstream code that doesn't know about these fields ignores them (they use `.get()` with defaults).

2. **A single `ts_specific` top-level key** — for signals that don't map to any existing structure. The markdown formatter can render this section when present; the json formatter passes it through.

3. **Enriched string representations** — e.g., `args` entries like `"name: string"` instead of just `"name"`. Downstream code that displays args will show richer info automatically.

This strategy ensures zero changes to existing Python consumers for a TS scan to produce valid output. TS-specific rendering is additive.

---

## 5. Reuse Boundary Map

### 5.1 Reuse As-Is (no modifications)

| Module | Why it works unchanged |
|---|---|
| `git_analysis.py` | Operates on file paths and `git log` output. Language-agnostic. |
| `tech_debt_analysis.py` | Regex over comments. Works on any `//` or `/* */` comment syntax. |
| `formatters/markdown_formatter.py` | Reads the results dict via `.get()`. TS output conforms to the same dict shape. |
| `formatters/json_formatter.py` | Serializes the results dict. Extra keys pass through. |
| `configs/presets.json` | Analysis option names (`skeleton`, `complexity`, etc.) are reused. |
| `configs/default_config.json` | Section enable/disable config. TS sections use same names. |
| `lib/config_loader.py` | Loads config from `.xray.json`. Language-agnostic. |

### 5.2 Rewrite for TypeScript (new code, same output contract)

| Python module | TS equivalent | Notes |
|---|---|---|
| `ast_analysis.py` | `ast-analysis.ts` | Core rewrite. Uses `ts.createSourceFile()` / `ts.createProgram()` instead of Python `ast`. Must emit `FileAnalysis` dicts with identical shape. |
| `import_analysis.py` | `import-analysis.ts` | ESM + CommonJS import parsing. Graph structure and layer detection logic similar but import syntax differs completely. |
| `call_analysis.py` | `call-analysis.ts` | Cross-module call tracking. Must handle JS's more dynamic call patterns. Lower confidence ceiling than Python. |
| `test_analysis.py` | `test-analysis.ts` | Different test frameworks (Jest/Vitest/Mocha vs pytest). Different file naming conventions. Same output structure. |

### 5.3 Modify to Be Language-Aware (minimal changes to existing Python)

| Module | What changes | Scope |
|---|---|---|
| `file_discovery.py` | Add TS/JS extensions (`.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.mjs`, `.cts`, `.cjs`). Skip `node_modules/`, `dist/`, `.next/`, `build/` by default. | Small: add extensions to patterns, directories to ignore list. |
| `gap_features.py` | `detect_entry_points()`: add Express/Next.js/NestJS patterns. `extract_data_models()`: add interface/type alias/Zod schema detection. | Medium: new pattern branches in existing functions. |
| `investigation_targets.py` | Heuristics for ambiguity scoring, convention detection. TS conventions differ (naming, export patterns). | Small: parameterize language-specific heuristic thresholds. |

---

## 6. Deep Crawl Integration

### 6.1 Keys Deep Crawl Reads from xray.json

The deep crawl pipeline uses `xray.json` output to prioritize investigation. The specific keys consumed:

| Key | Deep crawl usage | TS parity requirement |
|---|---|---|
| `investigation_targets` | Primary roadmap — determines what the crawl agent reads first | Must be populated. All sub-keys used. |
| `investigation_targets.high_uncertainty_modules` | Highest-priority investigation targets | Same scoring logic; adjust thresholds for TS type coverage norms |
| `investigation_targets.ambiguous_interfaces` | Functions the crawl agent reads and documents | Same structure. TS may have fewer (types reduce ambiguity). |
| `investigation_targets.entry_to_side_effect_paths` | Trace paths the agent follows | Same structure. TS paths may traverse more modules (thinner files). |
| `investigation_targets.coupling_anomalies` | Co-modification patterns that lack import explanation | From git analysis — language-agnostic. |
| `investigation_targets.shared_mutable_state` | Global/module-level mutable state | Detect `let` at module scope, exported mutable objects. |
| `structure` | File list and per-file skeletons for navigation | Must be populated. |
| `imports` | Dependency graph for understanding module relationships | Must be populated. Circular deps are key signals. |
| `calls` | Call graph for tracing execution paths | Must be populated. Lower confidence than Python is acceptable. |
| `git` | Risk scores and coupling for prioritization | Language-agnostic. No TS-specific changes. |

### 6.2 Signal Quality Parity Assessment

| Signal | Python quality | TS quality (syntax) | TS quality (semantic) | Gap and mitigation |
|---|---|---|---|---|
| Type coverage | Direct (annotations present or not) | **Inverted**: TS is typed by default. Flag `any` density instead. | Excellent (inferred types visible) | Redefine "low type coverage" as "high `any` density" for TS. |
| Call graph | Good (Python naming conventions help) | Partial (dynamic patterns) | Good (type-guided resolution) | Accept lower precision. Document confidence per edge. |
| Entry points | Framework detection (Flask/FastAPI decorators) | Framework detection (Express/NestJS/Next.js patterns) | Same | Add TS framework heuristics. |
| Data models | `@dataclass`, Pydantic, TypedDict | Interfaces, type aliases, Zod schemas | Same + inferred shapes | Broader detection surface. |
| Side effects | API pattern matching | API pattern matching | Same + type-guided | Equivalent quality. |
| Security | `eval`/`exec`/`subprocess` | `eval`/`Function`/`innerHTML`/`exec` | Same | TS has additional DOM-specific concerns. |

### 6.3 TypeScript Domain Facets

The deep crawl pipeline uses domain facets to customize investigation protocols. TS-specific facets:

| Facet | Detection heuristic | Investigation emphasis |
|---|---|---|
| `react_app` | JSX files, `react` in dependencies, component exports | Component tree, state management, prop drilling, render paths |
| `next_app` | `next` in dependencies, `pages/` or `app/` directory, `next.config.*` | Route structure, SSR/SSG boundaries, API routes, middleware chain |
| `express_api` | `express` in dependencies, `app.get/post/put/delete` patterns | Route map, middleware stack, error handling chain |
| `nest_api` | `@nestjs/core` in dependencies, `@Controller`/`@Injectable` decorators | Module dependency graph, guard/interceptor chain, DI wiring |
| `cli_tool` | `commander`/`yargs`/`oclif` in dependencies, `bin` in package.json | Command tree, option parsing, output formatting |
| `electron_app` | `electron` in dependencies, main/renderer process split | IPC channels, process boundaries, native module usage |
| `serverless` | `serverless`/`aws-cdk`/`@aws-sdk` in dependencies, handler exports | Handler map, cold start risks, shared state between invocations |
| `monorepo` | `workspaces` in package.json, `lerna.json`, `pnpm-workspace.yaml` | Package boundaries, cross-package imports, shared types |

Domain facet detection reads `package.json` dependencies and directory structure — no AST required.

---

## 7. Two-Tier Architecture

### 7.1 Syntax-Only Tier

**API**: `ts.createSourceFile(fileName, sourceText, languageVersion)`

- Parses a single file in isolation
- No project context, no module resolution, no type checking
- Returns a full syntax tree with all declarations, expressions, and comments
- **Fast**: no disk I/O beyond reading the source file

**What it can extract** (all Section 3 signals rated "Excellent" or "Good" syntax-only):
- Complete skeleton (classes, functions, interfaces, enums, type aliases, constants)
- Cyclomatic complexity (all branch constructs are syntactic)
- Explicit type annotations (but not inferred types)
- Import statements (but not resolved file paths)
- Call expressions (but not cross-module resolution)
- Side effect patterns (API name matching)
- Security concerns (all pattern-based)
- Silent failures (empty catch blocks)
- Async patterns (async/await keywords)
- Decorators (syntactic nodes)
- JSDoc comments and tags
- Tech debt markers

**What it cannot extract**:
- Inferred types (e.g., `const x = 5` — is `number` or `5`?)
- Resolved import paths (`"./utils"` → which actual file?)
- Type-aware call graph edges
- Implicit `any` (requires type checker)
- Cross-project type resolution

### 7.2 Semantic Tier

**API**: `ts.createProgram(rootFiles, compilerOptions)` — or `ts.createWatchProgram()` for incremental analysis.

- Requires a `tsconfig.json` (or equivalent compiler options)
- Performs full module resolution and type checking
- Access to `TypeChecker` for querying inferred types, resolved symbols, call targets
- **Slower**: reads all project files, resolves all imports, performs type inference

**What the semantic tier adds**:
- Inferred types on all declarations
- Resolved import specifiers → actual file paths
- Type-guided call graph (know that `x.method()` calls `ClassY.method` through interface)
- Implicit `any` detection (the type checker knows when it fell back to `any`)
- Full cross-module reference resolution
- Generic type instantiation tracking

### 7.3 Tier Selection and Graceful Degradation

```
Has tsconfig.json?
  ├── Yes → Semantic tier (full analysis)
  │         Parse error in tsconfig? → Syntax-only with warning
  └── No  → Syntax-only tier
              Check for jsconfig.json? → Partial semantic (JS project)
```

| Scenario | Tier | Quality | Metadata |
|---|---|---|---|
| TS project with `tsconfig.json` | Semantic | ~85% of Python signal quality | `parser_tier: "semantic"` |
| TS project, broken `tsconfig.json` | Syntax-only | ~65% | `parser_tier: "syntax"`, warning in metadata |
| JS project with `jsconfig.json` | Partial semantic | ~70% | `parser_tier: "semantic"` |
| JS project, no config | Syntax-only | ~60% | `parser_tier: "syntax"` |
| Mixed TS/JS project | Semantic for TS, syntax for untyped JS | ~75% | `parser_tier: "semantic"` |
| Single file (no project context) | Syntax-only | ~65% | `parser_tier: "syntax"` |

**Degradation is always partial, never total.** A parse error in one file produces a `FileAnalysis` with `parse_error` set and whatever partial data was extractable. The scan continues to the next file.

### 7.4 Signal Quality by Tier

| Signal | Syntax-Only | Semantic | Delta |
|---|---|---|---|
| Skeleton | 100% | 100% | None |
| Complexity | 100% | 100% | None |
| Type coverage (explicit) | 100% | 100% | None |
| Type coverage (implicit `any`) | 0% | 100% | Semantic required |
| Import graph (edges) | 90% | 100% | Dynamic imports are ceiling |
| Import graph (resolved paths) | 0% | 100% | Semantic required |
| Cross-module calls | ~50% | ~80% | Dynamic dispatch is ceiling |
| Side effects | 95% | 98% | Semantic helps with aliased APIs |
| Security | 95% | 98% | Semantic helps with `eval` wrappers |
| Silent failures | 100% | 100% | None |
| Async patterns | 95% | 100% | Semantic catches missing `await` |
| Decorators | 100% | 100% | None |
| Data models | 70% | 90% | Semantic helps resolve base types |
| Entry points | 80% | 85% | Mostly framework heuristics |

---

## 8. Open Questions

These are decisions deferred from this specification. Each must be resolved before or during implementation.

### 8.1 Orchestrator Design

How does `xray.py` invoke the TS frontend?

**Options**:
1. **Subprocess**: `xray.py` calls `node xray-ts.js /path/to/project` and reads JSON from stdout. Cleanest separation. Requires Node.js on the system.
2. **Shared binary**: Bundle the TS scanner as a standalone executable via `pkg` or `esbuild` + `node` SEA. No Node.js requirement for the user.
3. **Language detection in xray.py**: `xray.py` detects file extensions, decides which scanner(s) to invoke, merges results.

**Leaning toward**: Option 3 with Option 1 as the invocation mechanism. `xray.py` remains the single entry point; it detects language, shells out to `xray-ts` for TS files, merges the results dicts, then formats.

### 8.2 Monorepo Handling

Many TS projects are monorepos with multiple `tsconfig.json` files and project references.

**Questions**:
- Does the scanner find and respect all `tsconfig.json` files in subdirectories?
- How do project references (`"references"` in tsconfig) affect module resolution?
- Do `packages/*/tsconfig.json` create separate `ts.createProgram()` calls?

**Likely approach**: Find all `tsconfig.json` files via glob, create one Program per tsconfig, deduplicate files that appear in multiple programs.

### 8.3 Mixed-Language Repos

A repo might contain both Python and TypeScript. The scanner needs to handle this.

**Questions**:
- Does `xray.py` run both scanners and merge results?
- How are files partitioned (by extension)?
- Do cross-language relationships get tracked (e.g., Python backend called by TS frontend via HTTP)?

**Likely approach**: Run both scanners independently. Merge at the results dict level (files from both scanners in `structure.files`). Cross-language edges are out of scope for the scanner — they're the agent's job.

### 8.4 Performance Targets

| Metric | Target | Notes |
|---|---|---|
| Syntax-only, 500 files | ≤5 seconds | Matches Python scanner target |
| Semantic, 500 files | ≤15 seconds | Type checking is inherently slower |
| Startup overhead (Node.js + TS compiler load) | ≤1 second | One-time cost per invocation |
| Memory | ≤512 MB for semantic, ≤256 MB for syntax | TS compiler is memory-hungry |

### 8.5 Bundling and Distribution

**Questions**:
- Is the TS scanner distributed as a separate npm package?
- Is it bundled into the repo-xray repository as a subdirectory?
- Does it require `npm install` by the user, or is the `typescript` dependency vendored?

**Likely approach**: Subdirectory (`ts-scanner/`) in the repo-xray repository. `package.json` with `typescript` as the single dependency. Users run `npm install` in that directory once. The orchestrator checks for `ts-scanner/node_modules/typescript` before attempting TS analysis.

### 8.6 JavaScript vs TypeScript Mode

The TS Compiler API handles both, but the signals differ:
- In a `.ts` file, type annotations are expected. Missing annotations are a signal.
- In a `.js` file, no annotations are expected. JSDoc annotations are a bonus.

**Question**: Should `any` density only count for TS files? Should type coverage be reported differently for JS-only projects?

**Likely approach**: Report both `type_coverage` (standard metric) and `ts_specific.any_density` (TS-specific). The markdown formatter can present the appropriate view based on the `module_system` and file extension distribution.

---

## Appendix A: Python Results Dict — Complete Key Reference

Extracted from `xray.py:run_analysis()` (lines 291-477). This is the authoritative list of every key the TS scanner must populate.

```
results
├── metadata
│   ├── tool_version: str
│   ├── generated_at: str (ISO 8601)
│   ├── target_directory: str
│   ├── preset: str | None
│   ├── analysis_options: list[str]
│   └── file_count: int
├── summary
│   ├── total_files: int
│   ├── total_lines: int
│   ├── total_tokens: int
│   ├── total_functions: int
│   ├── total_classes: int
│   └── type_coverage: float
├── structure                             (when "skeleton" enabled)
│   ├── files: dict[filepath → FileAnalysis]
│   ├── classes: list[ClassInfo]
│   └── functions: list[FunctionInfo]
├── complexity                            (when "complexity" enabled)
│   ├── hotspots: list[Hotspot]  (top 20)
│   ├── average_cc: float
│   └── total_cc: int
├── types                                 (when "types" enabled)
│   ├── coverage: float
│   ├── typed_functions: int
│   └── total_functions: int
├── decorators                            (when "decorators" enabled)
│   └── inventory: dict[name → count]
├── side_effects                          (when "side_effects" enabled)
│   ├── by_type: dict[category → list[{file, call, line}]]
│   └── by_file: dict[filepath → list[{category, call, line}]]
├── security_concerns: dict[filepath → list[{type, call, line, severity}]]
├── silent_failures: dict[filepath → list[{type, line, context}]]
├── sql_strings: dict[filepath → list[{line, sql, context, type}]]
├── deprecation_markers: list[{file, name, line, reason, source}]
├── async_patterns
│   ├── async_functions: int
│   ├── sync_functions: int
│   ├── async_for_loops: int
│   ├── async_context_managers: int
│   └── violations: list[{file, function, violation, line}]  (optional)
├── imports                               (when "imports" enabled)
│   ├── graph: dict[module → {imports, imported_by}]
│   ├── layers: dict[layer → list[module]]
│   ├── aliases: dict[alias → module]
│   ├── alias_patterns: list[str]
│   ├── orphans: list[str]
│   ├── circular: list[list[str]]
│   ├── external_deps: list[str]
│   ├── distances
│   │   ├── max_depth: int
│   │   ├── avg_depth: float
│   │   ├── tightly_coupled: list[{modules, score}]
│   │   └── hub_modules: list[{module, connections}]
│   └── summary
│       ├── total_modules: int
│       ├── internal_edges: int
│       ├── circular_count: int
│       ├── orphan_count: int
│       └── external_deps_count: int
├── calls                                 (when "calls" enabled)
│   ├── cross_module: dict[func → {call_count, call_sites}]
│   ├── reverse_lookup: dict[func → {caller_count, impact_rating, callers}]
│   ├── most_called: list[{function, count}]
│   ├── most_callers: list[{function, callers}]
│   ├── isolated_functions: list[str]
│   ├── high_impact: list[{function, impact, callers}]
│   └── summary
│       ├── total_cross_module_calls: int
│       ├── functions_with_cross_module_callers: int
│       ├── high_impact_functions: int
│       └── isolated_functions: int
├── git                                   (when "git" enabled)
│   ├── risk: dict[filepath → {score, factors}]
│   ├── coupling: list[{file_a, file_b, score, confidence, count}]
│   ├── freshness: dict[filepath → {last_modified, days_since, status}]
│   ├── function_churn: dict[func → churn_count]
│   ├── coupling_clusters: list[{files, cohesion}]
│   └── velocity: {commits_per_week, active_files, trend}
├── tests                                 (when "tests" enabled)
│   ├── test_file_count: int
│   ├── test_function_count: int
│   ├── tested_modules: list[str]
│   ├── untested_modules: list[str]
│   ├── test_files: list[{path, test_count}]
│   ├── fixtures: list[str]  (optional)
│   └── summary: {coverage_estimate: float}
├── tech_debt                             (when "tech_debt" enabled)
│   ├── items: list[{file, line, type, text}]
│   ├── deprecations: list[{file, line, text}]
│   └── summary: {total_count, by_type: dict[type → count]}
├── hotspots: list[{file, function, complexity}]
├── author_expertise: {note: str}
├── commit_sizes: list[CommitSize]
├── investigation_targets
│   ├── ambiguous_interfaces: list[...]
│   ├── entry_to_side_effect_paths: list[...]
│   ├── coupling_anomalies: list[...]
│   ├── convention_deviations: list[...]
│   ├── shared_mutable_state: list[...]
│   ├── high_uncertainty_modules: list[...]
│   ├── domain_entities: list[...]
│   └── summary: dict[target_type → count]
└── ts_specific                           (TS only, optional)
    ├── any_density: {explicit_any, as_any_assertions, ts_ignore_count, ts_expect_error_count}
    ├── module_system: "esm" | "commonjs" | "mixed"
    ├── declaration_file_count: int
    ├── module_augmentations: list[...]
    ├── namespaces: list[...]
    └── project_references: list[str]  (optional)
```

---

## Appendix B: TypeScript Compiler API Quick Reference

For Python developers familiar with `ast.parse()` and `ast.NodeVisitor`.

### B.1 Parsing (syntax-only)

```typescript
import * as ts from "typescript";

// Equivalent of: tree = ast.parse(source)
const sourceFile = ts.createSourceFile(
  "example.ts",                          // filename (for error messages)
  sourceText,                            // file contents as string
  ts.ScriptTarget.Latest,               // language version
  true,                                  // setParentNodes (needed for traversal)
  ts.ScriptKind.TSX                      // TS | TSX | JS | JSX
);
```

### B.2 Traversal (syntax-only)

```typescript
// Equivalent of: ast.NodeVisitor with visit_* methods
function visit(node: ts.Node): void {
  // Check node type (equivalent of isinstance(node, ast.FunctionDef))
  if (ts.isFunctionDeclaration(node)) {
    const name = node.name?.text;
    const params = node.parameters.map(p => p.name.getText());
    const returnType = node.type?.getText();
    const isAsync = node.modifiers?.some(
      m => m.kind === ts.SyntaxKind.AsyncKeyword
    );
    // ... extract data
  }

  // Recurse into children (equivalent of self.generic_visit(node))
  ts.forEachChild(node, visit);
}

visit(sourceFile);
```

### B.3 Key SyntaxKind Values

| Python AST node | TS SyntaxKind | TS type guard |
|---|---|---|
| `ast.FunctionDef` | `FunctionDeclaration` | `ts.isFunctionDeclaration(node)` |
| `ast.AsyncFunctionDef` | `FunctionDeclaration` + `AsyncKeyword` | Check `modifiers` |
| `ast.ClassDef` | `ClassDeclaration` | `ts.isClassDeclaration(node)` |
| `ast.Import` | `ImportDeclaration` | `ts.isImportDeclaration(node)` |
| `ast.Return` | `ReturnStatement` | `ts.isReturnStatement(node)` |
| `ast.If` | `IfStatement` | `ts.isIfStatement(node)` |
| `ast.For` | `ForStatement` / `ForOfStatement` / `ForInStatement` | `ts.isForStatement(node)` etc. |
| `ast.While` | `WhileStatement` | `ts.isWhileStatement(node)` |
| `ast.Try` | `TryStatement` | `ts.isTryStatement(node)` |
| `ast.ExceptHandler` | `CatchClause` | `ts.isCatchClause(node)` |
| `ast.Call` | `CallExpression` | `ts.isCallExpression(node)` |
| `ast.Attribute` | `PropertyAccessExpression` | `ts.isPropertyAccessExpression(node)` |
| `ast.Name` | `Identifier` | `ts.isIdentifier(node)` |
| `ast.Constant(str)` | `StringLiteral` | `ts.isStringLiteral(node)` |
| `ast.Assign` | `VariableStatement` / `ExpressionStatement` | `ts.isVariableStatement(node)` |
| N/A | `InterfaceDeclaration` | `ts.isInterfaceDeclaration(node)` |
| N/A | `TypeAliasDeclaration` | `ts.isTypeAliasDeclaration(node)` |
| N/A | `EnumDeclaration` | `ts.isEnumDeclaration(node)` |
| N/A | `ArrowFunction` | `ts.isArrowFunction(node)` |
| N/A | `JsxElement` / `JsxSelfClosingElement` | `ts.isJsxElement(node)` |

### B.4 Semantic Analysis (type checker)

```typescript
// Equivalent of: no direct Python stdlib equivalent
// (closest: mypy's type inference, but that's external)

// Create a program with full type checking
const program = ts.createProgram(
  ["src/index.ts"],                      // root files
  {                                      // compiler options (from tsconfig.json)
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.ESNext,
    strict: true,
  }
);

const checker = program.getTypeChecker();

// Get the resolved type of any expression
const type = checker.getTypeAtLocation(node);
const typeName = checker.typeToString(type);

// Resolve an import to its actual file
const symbol = checker.getSymbolAtLocation(importSpecifier);
const declarations = symbol?.getDeclarations();

// Check if a type is 'any'
const isAny = type.flags & ts.TypeFlags.Any;
```

### B.5 Error Recovery

```typescript
// The TS parser always produces a tree, even with errors.
// Errors are collected as diagnostics.
const diagnostics = ts.getPreEmitDiagnostics(program);

// For syntax-only parsing, check sourceFile.parseDiagnostics
// Each diagnostic has: file, start, length, messageText, category
// Category: ts.DiagnosticCategory.Error | Warning | Suggestion | Message

// A file with errors still has a full AST — just with some
// nodes marked as missing or containing error tokens.
// This is the TS equivalent of Python's ast.parse() raising
// SyntaxError, except TS recovers and continues.
```

---

## Decisions Made in This Document

| Decision | Rationale |
|---|---|
| TS scanner is a standalone Node.js script emitting the shared JSON schema | Clean separation. No Python↔Node FFI complexity. Formatters work unchanged. |
| TypeScript Compiler API is the parser (for both TS and JS) | Deep research scored it highest. Handles TS+JS+JSX. Official, stable. |
| Two-tier architecture (syntax-only + semantic) | Syntax tier is fast and zero-config. Semantic tier adds value when tsconfig exists. Graceful degradation. |
| Schema extension via optional fields + `ts_specific` key | Zero changes required to existing Python consumers. TS-specific rendering is additive. |
| `any` density as the TS-specific type safety metric | Type coverage is inverted in TS (most code is typed by default). `any` density is the actionable signal. |
| Single external dependency: `typescript` npm package | Matches INTENT.md's minimal-dependency constraint. No Babel, ESLint, or other tools. |

## Decisions Deferred

| Decision | Where it's resolved |
|---|---|
| Orchestrator design (subprocess vs binary vs detection) | Implementation spec |
| Exact code patterns and module structure | Implementation spec |
| Formatter modifications for TS-specific rendering | Formatter enhancement spec |
| Testing strategy and golden tests | Testing spec |
| Distribution and packaging | Distribution spec |
| Monorepo handling details | Implementation spec |
| Performance optimization techniques | Implementation spec |

# TypeScript Scanner: Detailed Design

Version 0.1 — 2026-04-04

**Prerequisite**: Read `docs/TS_FRONTEND_SPEC.md` first. This document resolves every decision that spec defers.

---

## 1. Orchestrator Design

*Resolves Spec Section 8.1 (Orchestrator Design), 8.3 (Mixed-Language Repos), 8.5 (Bundling).*

### 1.1 Decision: Subprocess with Language Detection in xray.py

`xray.py` remains the single entry point. It detects language, invokes the appropriate scanner(s), merges results, then formats.

```
User runs: python xray.py /path/to/project

xray.py:
  1. discover_files()          → {py_files, ts_files}
  2. if py_files:              → analyze via existing Python pipeline
  3. if ts_files:              → shell out to: node ts-scanner/dist/index.js <path> [options]
  4. merge results dicts       → unified XRayResults
  5. compute gap_features()    → language-aware detection
  6. compute investigation_targets() → combined signals
  7. format + output
```

### 1.2 Language Detection

Add to `file_discovery.py`:

```python
TS_EXTENSIONS = {'.ts', '.tsx', '.mts', '.cts'}
JS_EXTENSIONS = {'.js', '.jsx', '.mjs', '.cjs'}
FRONTEND_EXTENSIONS = TS_EXTENSIONS | JS_EXTENSIONS

def discover_ts_files(root_dir, ignore_dirs, ignore_exts, ignore_files):
    """Mirror of discover_python_files for TS/JS files."""
    # Same walk logic, but:
    #   - Match FRONTEND_EXTENSIONS instead of '.py'
    #   - Add to ignore_dirs: 'node_modules', 'dist', '.next', 'build', '.nuxt', 'coverage'
    #   - Skip declaration files (.d.ts) from structural analysis
    #     (scan them for interfaces/types only)
```

Detection logic in `xray.py`:

```python
py_files = discover_python_files(target, ...)
ts_files = discover_ts_files(target, ...)

language = "python"
if ts_files and not py_files:
    language = "typescript"
elif ts_files and py_files:
    language = "mixed"
```

### 1.3 TS Scanner Invocation Protocol

**CLI interface of the TS scanner:**

```
node ts-scanner/dist/index.js <target-dir> [options]

Options:
  --tier syntax|semantic    Parser tier (default: auto-detect from tsconfig presence)
  --verbose                 Progress to stderr
  --tsconfig <path>         Explicit tsconfig.json path
  --include <glob>          Additional file patterns to include
  --exclude <glob>          Additional patterns to exclude

Output:
  stdout: JSON conforming to XRayResults (Spec Section 2)
  stderr: Progress messages (when --verbose)
  exit 0: Success
  exit 1: Fatal error (stderr has message)
  exit 2: Partial success (some files failed, results are partial)
```

**Invocation from xray.py:**

```python
import subprocess, json

def invoke_ts_scanner(target, verbose=False, tsconfig=None):
    scanner_path = SCRIPT_DIR / "ts-scanner" / "dist" / "index.js"

    if not scanner_path.exists():
        if verbose:
            print("TS scanner not built. Run: cd ts-scanner && npm install && npm run build", file=sys.stderr)
        return None

    cmd = ["node", str(scanner_path), target]
    if verbose:
        cmd.append("--verbose")
    if tsconfig:
        cmd.extend(["--tsconfig", tsconfig])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        if verbose:
            print("Node.js not found. TS analysis skipped.", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        if verbose:
            print("TS scanner timed out after 120s.", file=sys.stderr)
        return None

    if proc.returncode not in (0, 2):
        if verbose:
            print(f"TS scanner failed: {proc.stderr}", file=sys.stderr)
        return None

    return json.loads(proc.stdout)
```

### 1.4 Result Merging

For mixed-language repos, results merge at the top level:

```python
def merge_results(py_results, ts_results):
    """Merge Python and TS analysis results into a single dict."""
    if not ts_results:
        return py_results
    if not py_results:
        return ts_results

    merged = copy.deepcopy(py_results)

    # Merge file-level data
    merged["structure"]["files"].update(ts_results.get("structure", {}).get("files", {}))
    merged["structure"]["classes"].extend(ts_results.get("structure", {}).get("classes", []))
    merged["structure"]["functions"].extend(ts_results.get("structure", {}).get("functions", []))

    # Merge per-file signal dicts
    for key in ("security_concerns", "silent_failures", "sql_strings"):
        merged.setdefault(key, {}).update(ts_results.get(key, {}))

    # Merge list signals
    for key in ("deprecation_markers", "hotspots"):
        merged.setdefault(key, []).extend(ts_results.get(key, []))

    # Merge import/call graphs
    if ts_results.get("imports"):
        py_graph = merged.get("imports", {}).get("graph", {})
        ts_graph = ts_results["imports"].get("graph", {})
        py_graph.update(ts_graph)
        # Recalculate summary stats

    # Aggregate summary
    for field in ("total_files", "total_lines", "total_tokens", "total_functions", "total_classes"):
        merged["summary"][field] += ts_results.get("summary", {}).get(field, 0)

    # Carry over ts_specific
    if ts_results.get("ts_specific"):
        merged["ts_specific"] = ts_results["ts_specific"]

    merged["metadata"]["language"] = "mixed"
    return merged
```

### 1.5 Prerequisite Check

On startup, `xray.py` checks:

1. `node --version` succeeds and returns v18+ (TypeScript 5.x requires Node 18+)
2. `ts-scanner/dist/index.js` exists (scanner is built)
3. `ts-scanner/node_modules/typescript` exists (dependency installed)

If any check fails and TS files are detected, print a warning to stderr and skip TS analysis. Never fail hard — a repo with both Python and TS files should still produce Python results.

---

## 2. Internal Module Structure

```
ts-scanner/
├── package.json                 Single dep: typescript
├── tsconfig.json                Compiler config for the scanner itself
├── src/
│   ├── index.ts                 Entry point: CLI parsing, orchestration, JSON output
│   ├── file-discovery.ts        Find TS/JS files, apply ignore patterns, detect tsconfig
│   ├── ast-analysis.ts          Multi-pass AST extraction (the core)
│   ├── import-analysis.ts       ESM + CJS import graph, layer detection, circular deps
│   ├── call-analysis.ts         Cross-module call sites, function registry
│   ├── test-analysis.ts         Jest/Vitest/Mocha detection, test file matching
│   ├── tech-debt-analysis.ts    TODO/FIXME scanning (regex over comments)
│   ├── gap-features.ts          Entry points, data models (TS patterns)
│   ├── investigation-targets.ts Combines all analyses into deep crawl signals
│   ├── types.ts                 Shared interfaces: FileAnalysis, ClassInfo, etc.
│   └── utils.ts                 Token counting, path helpers, timer
├── dist/                        Compiled output (gitignored except index.js)
└── test/
    ├── fixtures/                Synthetic TS projects for testing
    └── *.test.ts                Scanner tests (run with ts-node or vitest)
```

### 2.1 Module Responsibilities

| Module | Mirrors Python | Key difference |
|---|---|---|
| `index.ts` | `xray.py:run_analysis()` | Standalone CLI; outputs JSON to stdout |
| `file-discovery.ts` | `file_discovery.py` | Adds `node_modules`/`dist` exclusion, tsconfig detection |
| `ast-analysis.ts` | `ast_analysis.py` | Multi-pass instead of single `ast.walk()` |
| `import-analysis.ts` | `import_analysis.py` | Handles ESM + CJS + dynamic `import()` |
| `call-analysis.ts` | `call_analysis.py` | Same registry pattern; lower resolution ceiling |
| `test-analysis.ts` | `test_analysis.py` | Jest/Vitest/Mocha instead of pytest |
| `tech-debt-analysis.ts` | `tech_debt_analysis.py` | Nearly identical (regex over `//` and `/* */`) |
| `gap-features.ts` | `gap_features.py` (partial) | TS-specific entry points and data models only |
| `investigation-targets.ts` | `investigation_targets.py` | Same 7 sub-computations with TS heuristics |
| `types.ts` | `ast_analysis.py:FileAnalysis` | TypeScript interfaces matching Spec Section 2 |

### 2.2 What the Scanner Does NOT Include

The TS scanner does **not** replicate:
- `git_analysis.py` — language-agnostic, stays in Python
- `config_loader.py` — stays in Python, config passed via CLI flags
- `formatters/` — stays in Python, consumes the merged results dict
- `gap_features.py` functions that don't need AST (e.g., `compute_shared_mutable_state` in `investigation_targets.py` re-parses files, so its TS equivalent lives inside the TS scanner)

### 2.3 package.json

```json
{
  "name": "repo-xray-ts-scanner",
  "version": "0.1.0",
  "private": true,
  "main": "dist/index.js",
  "scripts": {
    "build": "tsc",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "typescript": "^5.5.0"
  },
  "devDependencies": {
    "vitest": "^2.0.0"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}
```

Single runtime dependency: `typescript`. `vitest` is dev-only.

---

## 3. Multi-Pass AST Architecture

*Resolves the fundamental difference between Python's `ast.walk()` and TS's `ts.forEachChild()`.*

### 3.1 Why Multiple Passes

Python's `ast.walk()` yields every node in an unordered flat iterator. A single loop accumulates all data because:
- No context needed (the module is flat — top-level functions and classes)
- No forward references (Python reads top-to-bottom in a single file)

TypeScript's `ts.forEachChild()` is recursive descent — you must walk the tree yourself. Additionally:
- Functions are often nested (arrow functions, callbacks, IIFEs)
- Classes can be expressions (`const Foo = class { ... }`)
- Exports wrap declarations (`export default function ...`)
- Call resolution needs a complete symbol table before matching

The scanner uses **2 passes for syntax tier**, **3 for semantic tier**.

### 3.2 Pass 1: Structure Collection

Walk all nodes top-down. Collect declarations and build the per-file symbol table.

**What it collects:**
- Function declarations, function expressions, arrow functions (→ `FunctionInfo`)
- Class declarations, class expressions (→ `ClassInfo` with methods, fields, heritage)
- Interface declarations (→ `TsInterfaceInfo`)
- Type alias declarations (→ `TsTypeAliasInfo`)
- Enum declarations (→ `TsEnumInfo`)
- Module-level `const`/`let`/`var` declarations (→ `ConstantInfo`)
- Import declarations (→ raw import list for `import-analysis.ts`)
- Export declarations (→ track what's exported)
- Decorator nodes on classes and methods
- JSDoc comments via `ts.getJSDocTags()`
- Cyclomatic complexity (count branch constructs per function body)
- Type annotations on parameters and return types
- `async` modifier presence

**Context management:**

```typescript
interface WalkContext {
  currentFunction: string | null;    // Qualified name of enclosing function
  currentClass: string | null;       // Name of enclosing class
  isAsync: boolean;                  // Whether current scope is async
  depth: number;                     // Nesting depth (for top-level detection)
  sourceFile: ts.SourceFile;         // For getText() calls
}

function walkPass1(node: ts.Node, ctx: WalkContext, result: FileAnalysis): void {
  if (ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node)) {
    const name = getFunctionName(node, ctx);
    const isAsync = hasModifier(node, ts.SyntaxKind.AsyncKeyword);
    // Extract params, return type, decorators, complexity
    // Register in result.functions (if top-level) or as method (if in class)
    // Recurse with updated context
    const childCtx = { ...ctx, currentFunction: name, isAsync };
    ts.forEachChild(node, child => walkPass1(child, childCtx, result));
    return; // Don't double-recurse
  }

  if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) {
    // Extract name, heritage clauses, decorators
    // Recurse with currentClass set
    const childCtx = { ...ctx, currentClass: getClassName(node) };
    ts.forEachChild(node, child => walkPass1(child, childCtx, result));
    return;
  }

  // ... interface, type alias, enum, variable declaration handlers

  ts.forEachChild(node, child => walkPass1(child, ctx, result));
}
```

**Symbol table output** (per file):

```typescript
interface SymbolTable {
  functions: Map<string, { line: number; isExported: boolean }>;
  classes: Map<string, { line: number; methods: string[]; isExported: boolean }>;
  interfaces: Map<string, { line: number; isExported: boolean }>;
  exports: Map<string, string>;  // exported name → local name
}
```

### 3.3 Pass 2: Relationship Detection

Walk the tree again. This time, use the symbol table from Pass 1 to identify:

**Call expressions:**
- Match `CallExpression` targets against the symbol table
- Track `identifier()` calls → check if identifier is in symbol table
- Track `obj.method()` calls → check if obj is an imported binding
- Record internal calls (callee is in the same file's symbol table)
- Record cross-module call candidates (callee is an imported name)

**Side effect detection:**
- Match call expression text against the TS side effect pattern table (Spec Section 3.6)
- Handle both qualified (`fs.readFileSync`) and unqualified (`readFileSync` imported directly) forms
- Use import bindings from Pass 1 to resolve unqualified names: if `readFileSync` was imported from `fs`, categorize as `file_io`

**Security concern detection:**
- `eval()` → high severity
- `new Function(...)` → high severity
- `child_process.exec()` / `execSync()` → high severity
- `innerHTML` assignment → medium severity (detect `PropertyAccessExpression` with name `innerHTML` on left side of `BinaryExpression`)
- `dangerouslySetInnerHTML` → medium severity
- `document.write()` → medium severity
- Dynamic `import()` with non-literal argument → medium severity

**Silent failure detection:**
- Empty `catch` blocks: `CatchClause` where `block.statements.length === 0`
- Catch without binding: `CatchClause` where `variableDeclaration` is undefined
- Swallowed promise rejections: `.catch(() => {})` — detect `CallExpression` where expression is `PropertyAccessExpression` with name `catch` and the callback argument has an empty body

**Async violation detection:**
- Inside async functions (tracked via context), flag calls to:
  - `fs.readFileSync`, `fs.writeFileSync`, `fs.mkdirSync`, etc. (pattern: `*Sync`)
  - `child_process.execSync`, `child_process.spawnSync`
  - `Array.prototype.forEach` with async callback (detect: `forEach` call where the argument is an `async` arrow function)

**SQL string detection:**
- String literals and template literals containing SQL keywords (`SELECT`, `INSERT`, `CREATE TABLE`, etc.)
- Tagged template literals where tag is `sql`, `Prisma.sql`, `knex.raw`, etc.
- Same regex approach as Python's `_detect_sql_strings()`

**Deprecation marker detection:**
- JSDoc `@deprecated` tags via `ts.getJSDocDeprecatedTag(node)`
- Custom `@Deprecated()` decorators
- Comment-based: same regex as tech debt (`// DEPRECATED`)

### 3.4 Pass 3: Semantic Enrichment (Semantic Tier Only)

Requires `ts.createProgram()` and `TypeChecker`.

**Type resolution:**
- For each function parameter without explicit annotation: query `checker.getTypeAtLocation(param)` to get the inferred type
- Detect implicit `any`: `checker.isTypeAssignableTo(type, anyType)` when no annotation exists
- Count `as any` assertions: already detected syntactically in Pass 2, but semantic tier confirms the cast target is `any`

**Import path resolution:**
- Use `ts.resolveModuleName(specifier, containingFile, compilerOptions, host)` to map every import specifier to its resolved file path
- This replaces the heuristic relative-path resolution of the syntax tier
- Produces an authoritative import graph with actual file paths as nodes

**Type-guided call graph refinement:**
- For method calls on typed variables (`x.method()`), use `checker.getTypeAtLocation(x)` to determine which class/interface `x` belongs to
- Match the method against the resolved class, not just by name heuristic
- This dramatically improves cross-module call accuracy for typed code

### 3.5 Pass Architecture Summary

| Pass | Tier | What it reads | What it produces | Dependencies |
|---|---|---|---|---|
| Pass 1 | Both | Raw AST nodes | Symbol table, `ClassInfo`, `FunctionInfo`, `InterfaceInfo`, constants, complexity, type annotations, decorators, JSDoc | None |
| Pass 2 | Both | AST nodes + Pass 1 symbol table + import bindings | Call graph, side effects, security concerns, silent failures, async violations, SQL strings, deprecation markers, internal calls | Pass 1 |
| Pass 3 | Semantic only | AST + TypeChecker | Inferred types, resolved imports, type-guided call edges, implicit `any` count | Pass 1, `ts.createProgram()` |

---

## 4. Import Resolution Strategy

*Resolves Spec Section 8.2 (Monorepo Handling), 8.6 (JS vs TS mode), and the import resolution gap identified in the honest assessment.*

### 4.1 Syntax Tier: Heuristic Resolution

Record raw specifiers from `ImportDeclaration` and `require()` calls. Classify each:

| Specifier shape | Classification | Example |
|---|---|---|
| Starts with `./` or `../` | `relative` | `"./utils"`, `"../lib/config"` |
| Bare name | `package` | `"react"`, `"express"` |
| Scoped package | `package` | `"@nestjs/core"`, `"@scope/pkg"` |
| Dynamic expression | `dynamic` | `import(variable)` |

**Relative import resolution (heuristic):**

```typescript
function resolveRelativeImport(specifier: string, fromFile: string, knownFiles: Set<string>): string | null {
  const dir = path.dirname(fromFile);
  const base = path.resolve(dir, specifier);

  // Try exact match, then with extensions, then /index
  const candidates = [
    base,
    base + '.ts', base + '.tsx', base + '.js', base + '.jsx',
    base + '/index.ts', base + '/index.tsx', base + '/index.js', base + '/index.jsx',
  ];

  for (const candidate of candidates) {
    if (knownFiles.has(candidate)) return candidate;
  }
  return null; // Unresolved — record as-is
}
```

This is approximate but sufficient for building an import graph with known internal modules. Unresolved specifiers are recorded in `external_deps`.

**Graph construction mirrors `import_analysis.py:build_import_graph()`:**
- Nodes are file paths (not module names — TS has no Python-style `module.submodule` convention)
- Edges are import relationships
- Circular detection: same BFS approach as Python
- Layer classification: adapted keyword heuristics (see Section 4.3)

### 4.2 Semantic Tier: Authoritative Resolution

Use the TypeScript module resolution algorithm:

```typescript
const host = ts.createCompilerHost(compilerOptions);

for (const [specifier, fromFile] of allImports) {
  const resolved = ts.resolveModuleName(specifier, fromFile, compilerOptions, host);
  if (resolved.resolvedModule) {
    const targetPath = resolved.resolvedModule.resolvedFileName;
    // Add edge: fromFile → targetPath
  }
}
```

This handles all complexity automatically:
- `tsconfig.json` `paths` and `baseUrl` aliases
- `package.json` `exports` field
- `node_modules` resolution with scoped packages
- Project references (`references` in tsconfig)
- Conditional imports (e.g., `import`/`require` conditions)

### 4.3 Layer Detection

Adapt Python's keyword-based layer classification. TS projects use directory-based organization more than Python:

```typescript
const LAYER_RULES: Array<{ layer: string; patterns: RegExp[] }> = [
  { layer: "api",          patterns: [/\/api\//, /\/routes\//, /\/controllers\//, /\/handlers\//] },
  { layer: "services",     patterns: [/\/services\//, /\/usecases\//] },
  { layer: "models",       patterns: [/\/models\//, /\/entities\//, /\/schemas\//] },
  { layer: "middleware",    patterns: [/\/middleware\//, /\/guards\//, /\/interceptors\//] },
  { layer: "utils",        patterns: [/\/utils\//, /\/helpers\//, /\/lib\//, /\/common\//] },
  { layer: "types",        patterns: [/\/types\//, /\/interfaces\//, /\/dtos\//] },
  { layer: "config",       patterns: [/\/config\//, /\/constants\//] },
  { layer: "tests",        patterns: [/\/test\//, /\/__tests__\//, /\.test\./, /\.spec\./] },
  { layer: "components",   patterns: [/\/components\//, /\/views\//, /\/pages\//] },
  { layer: "store",        patterns: [/\/store\//, /\/state\//, /\/reducers\//, /\/slices\//] },
];

// Also detect framework-specific layers:
// NestJS: modules/, providers/, pipes/, filters/
// Next.js: app/, pages/, api/ (route handlers)
// Express: router files with app.get/post patterns
```

### 4.4 Monorepo Handling

*Resolves Spec Section 8.2.*

**Detection:** Look for `workspaces` in root `package.json`, or `lerna.json`, or `pnpm-workspace.yaml`.

**Strategy:** Find all `tsconfig.json` files. For the semantic tier, create one `ts.createProgram()` per tsconfig. For the syntax tier, scan all TS/JS files regardless of tsconfig boundaries.

**Deduplication:** A file referenced by multiple tsconfigs is analyzed once (first encounter wins). Cross-package imports are captured in the import graph as edges between packages.

**Scope limitation:** The scanner targets a single root directory. Monorepo-wide analysis runs once from the monorepo root. Package-level analysis runs from a package directory. The scanner does not "discover upward" to find the monorepo root.

---

## 5. Analysis Module Dependency Graph

*Makes explicit what the spec leaves implicit.*

```
file-discovery
      │
      ▼
ast-analysis (Pass 1 + Pass 2, or +Pass 3 for semantic)
      │
      ├──────────────────────────────────┐
      ▼                                  ▼
import-analysis                    call-analysis
(needs: file list,                 (needs: ast-analysis symbol tables,
 raw imports from Pass 1)           import bindings from Pass 1)
      │                                  │
      ▼                                  ▼
      └──────────────┬───────────────────┘
                     ▼
              gap-features
              (needs: structure + imports + calls)
                     │
                     ▼
           investigation-targets
           (needs: everything above)
```

### 5.1 Data Flow Between Modules

| Edge | Data passed | Required keys | Failure mode |
|---|---|---|---|
| file-discovery → ast-analysis | `string[]` (file paths) | — | Empty array → empty results |
| ast-analysis → import-analysis | Per-file import statements (collected during Pass 1) | `imports` array per file | Missing → graph has no edges |
| ast-analysis → call-analysis | Symbol tables from Pass 1 | `functions`, `classes` maps per file | Missing → no call resolution |
| ast-analysis → gap-features | Full `FileAnalysis` per file | `structure.files` | Missing → no entry points or data models |
| import-analysis → investigation-targets | `graph`, `distances`, `hub_modules` | `imports.graph` | Missing → no coupling anomalies |
| call-analysis → investigation-targets | `cross_module`, `reverse_lookup` | `calls.cross_module` | Missing → no ambiguous interface scoring |
| gap-features → investigation-targets | `entry_points`, `data_models` | Lists from gap detection | Missing → no entry-to-side-effect paths, no domain entities |

### 5.2 Execution Order

```typescript
// index.ts orchestration (mirrors xray.py:run_analysis)

const files = discoverFiles(targetDir, options);
const astResults = analyzeAST(files, tier, tsconfigPath);

// These two are independent of each other — could parallelize
const importResults = analyzeImports(files, astResults.rawImports, targetDir, tier, tsconfigPath);
const callResults = analyzeCalls(files, astResults.symbolTables, targetDir);

// Depends on structure + imports + calls
const gapResults = computeGapFeatures(astResults, importResults, callResults, targetDir);

// Depends on everything
const investigationTargets = computeInvestigationTargets(
  astResults, importResults, callResults, gapResults, targetDir
);

// tech-debt and test-analysis are independent — can run in parallel with anything
const techDebtResults = analyzeTechDebt(files);
const testResults = analyzeTests(targetDir);
```

### 5.3 Error Isolation

Each module catches errors per-file and continues, matching the Python pattern. A failure in `call-analysis` does not prevent `import-analysis` from completing. The orchestrator wraps each module call in try/catch and includes partial results.

```typescript
function safeRun<T>(name: string, fn: () => T, fallback: T, verbose: boolean): T {
  try {
    return fn();
  } catch (e) {
    if (verbose) process.stderr.write(`  ${name} failed: ${e}\n`);
    return fallback;
  }
}
```

---

## 6. TS-Specific Detection Patterns

*Concrete rules for every signal where Python and TS diverge.*

### 6.1 Data Models

The spec's `extract_data_models()` equivalent must detect TS data structures that serve the same role as Python's `@dataclass`, Pydantic `BaseModel`, and `TypedDict`.

| Pattern | Detection | `model_type` value |
|---|---|---|
| `interface` with >2 members | `ts.isInterfaceDeclaration(node)` + count `members` | `"interface"` |
| `type` alias with object shape | `ts.isTypeAliasDeclaration(node)` where `type` is `TypeLiteral` | `"type_alias"` |
| Class with `@Entity()` / `@Column()` (TypeORM) | Decorator detection on class | `"typeorm_entity"` |
| `z.object({...})` calls (Zod) | `CallExpression` where callee matches `z.object` or `zod.object` | `"zod_schema"` |
| Class with `@IsString()` / `@IsNumber()` (class-validator) | Decorator detection on class properties | `"class_validator"` |
| `Prisma` model references | Import from `@prisma/client` + type usage | `"prisma_model"` |
| `enum` declarations | `ts.isEnumDeclaration(node)` | `"enum"` |
| Class with typed fields and constructor | Class where constructor has parameter properties (`public name: string`) | `"class_model"` |

**Domain classification** mirrors the Python approach — derive from file path:

```typescript
function classifyDomain(filePath: string, name: string): string {
  const pathLower = filePath.toLowerCase();
  const nameLower = name.toLowerCase();

  if (/\/api\/|\/routes\/|\/controllers\//.test(pathLower)) return "API";
  if (/\/models\/|\/entities\/|\/schemas\//.test(pathLower)) return "Models";
  if (nameLower.includes("config") || nameLower.includes("settings")) return "Config";
  if (nameLower.includes("request") || nameLower.includes("response")) return "API";
  if (/\/store\/|\/state\/|\/slices\//.test(pathLower)) return "State";

  // Fallback: parent directory name
  const parts = filePath.split(/[/\\]/);
  return parts.length >= 2 ? capitalize(parts[parts.length - 2]) : "Other";
}
```

### 6.2 Entry Points

The spec's `detect_entry_points()` equivalent for TS:

| Pattern | Detection | `entry_type` |
|---|---|---|
| `package.json` `"main"` field | Read `package.json`, resolve path | `"package_main"` |
| `package.json` `"bin"` field | Read `package.json`, resolve path(s) | `"cli_binary"` |
| `app.listen()` / `server.listen()` | Call expression pattern match | `"server"` |
| `http.createServer()` / `https.createServer()` | Call expression pattern match | `"server"` |
| `export default` in `pages/` or `app/` directory (Next.js) | Export + path heuristic | `"next_page"` |
| `export const handler` / `export async function handler` (Lambda) | Exported function named `handler` in root-level files | `"lambda_handler"` |
| NestJS `@Controller()` decorated classes | Decorator detection | `"nest_controller"` |
| Express/Fastify route handlers (`app.get`, `router.post`, etc.) | Call expression pattern | `"route_handler"` |
| Files matching `**/index.{ts,js}` at package root | Path heuristic | `"package_index"` |
| `commander`/`yargs` setup | Import detection + `.parse()` call | `"cli_entry"` |

### 6.3 CLI Arguments Extraction

Replaces Python's argparse/Click/Typer extraction:

| Framework | Detection | Extraction |
|---|---|---|
| `commander` | Import from `commander` + `.option()` / `.argument()` chains | Parse option strings from first argument |
| `yargs` | Import from `yargs` + `.option()` / `.positional()` calls | Extract from option config objects |
| `oclif` | Class extending `Command` with `static flags` | Read static `flags` property |
| `meow` | Import from `meow` + config object | Parse `flags` from config argument |
| NestJS CLI | Custom patterns — detect `@Option()` decorators | Read decorator metadata |

### 6.4 Side Effects Pattern Table

Full pattern table for the TS scanner:

```typescript
const SIDE_EFFECT_PATTERNS: Record<string, string[]> = {
  file_io: [
    "fs.readFile", "fs.writeFile", "fs.readFileSync", "fs.writeFileSync",
    "fs.appendFile", "fs.unlink", "fs.mkdir", "fs.rmdir", "fs.rm",
    "fs.rename", "fs.copyFile", "fs.open", "fs.createReadStream",
    "fs.createWriteStream", "fsPromises.",
    "readFile", "writeFile",  // When imported directly from 'fs'
  ],
  network: [
    "fetch(", "axios.", "http.request", "https.request",
    "http.get", "https.get", "got.", "ky.", "superagent.",
    "XMLHttpRequest", "WebSocket(",
  ],
  database: [
    "prisma.", "knex.", "sequelize.", "typeorm.",
    "mongoose.", "pg.", "mysql.", "redis.",
    ".query(", ".execute(", ".findOne(", ".findMany(",
    ".create(", ".update(", ".delete(", ".save(",
  ],
  subprocess: [
    "child_process.", "exec(", "execSync(", "spawn(",
    "spawnSync(", "fork(", "execFile(",
    "execa(", "execa.", // Popular third-party
  ],
  env_access: [
    "process.env",
  ],
  console_io: [
    "console.log", "console.error", "console.warn",
    "console.info", "console.debug", "console.trace",
  ],
  process: [
    "process.exit", "process.kill", "process.abort",
  ],
  dom: [
    "document.write", "document.createElement",
    ".innerHTML", ".outerHTML",
    "window.location", "window.open",
    "localStorage.", "sessionStorage.",
  ],
};
```

**Unqualified import resolution:** If a file imports `{ readFileSync } from "fs"`, then a bare `readFileSync()` call should be classified as `file_io`. Pass 2 uses the import bindings from Pass 1 to match unqualified calls to their module.

### 6.5 Async Violations

| Violation | Detection |
|---|---|
| Sync API in async function | Any `*Sync` function call (`readFileSync`, `execSync`, etc.) inside a function with `AsyncKeyword` modifier |
| `.forEach` with async callback | `.forEach(CallExpression)` where the callback has `AsyncKeyword` — `await` has no effect inside `forEach` |
| Missing `await` on async call | **Semantic tier only**: call returns `Promise<T>` but result is not `await`ed and not assigned or returned |
| Unhandled promise | `.then()` chain without `.catch()` at the end — heuristic, limited confidence |

### 6.6 Framework Detection

Detect frameworks from `package.json` `dependencies` + `devDependencies`:

```typescript
interface FrameworkSignal {
  name: string;
  packages: string[];          // Any of these in deps triggers detection
  codePatterns?: RegExp[];     // Additional code-level confirmation
}

const FRAMEWORK_SIGNALS: FrameworkSignal[] = [
  { name: "react",    packages: ["react", "react-dom"] },
  { name: "next",     packages: ["next"] },
  { name: "express",  packages: ["express"], codePatterns: [/app\.(get|post|put|delete|use)\(/] },
  { name: "nestjs",   packages: ["@nestjs/core"] },
  { name: "fastify",  packages: ["fastify"] },
  { name: "angular",  packages: ["@angular/core"] },
  { name: "vue",      packages: ["vue"] },
  { name: "nuxt",     packages: ["nuxt", "nuxt3"] },
  { name: "electron", packages: ["electron"] },
  { name: "jest",     packages: ["jest", "@jest/core"] },
  { name: "vitest",   packages: ["vitest"] },
  { name: "mocha",    packages: ["mocha"] },
];
```

Framework signals are included in `ts_specific` output and used by gap-features for entry point detection.

---

## 7. Pipeline Adaptation Scope

*Acknowledges what the spec overclaims about language-agnosticism. Every change needed outside the TS scanner.*

### 7.1 Changes to Existing Python Code

| File | Change | Size | Details |
|---|---|---|---|
| `xray.py` | Language detection, TS scanner invocation, result merging | Medium | New `invoke_ts_scanner()`, `merge_results()` functions. Modify `run_analysis()` to check for TS files. Add `--language` flag to force Python/TS/auto. |
| `lib/file_discovery.py` | Add `discover_ts_files()` function | Small | New function mirroring `discover_python_files()` with TS extensions and `node_modules`/`dist` in ignore list. |
| `lib/gap_features.py` | Language-conditional data model and entry point detection | Medium | `extract_data_models()`: add branch for TS results (interfaces, type aliases, Zod schemas). `detect_entry_points()`: add branch for package.json/Express/NestJS patterns. `extract_cli_args()`: add Commander/Yargs extraction. These can dispatch to TS scanner output if available, or fall back to the Python-native detection. |
| `lib/investigation_targets.py` | Parameterize heuristic thresholds | Small | `GENERIC_FUNCTION_NAMES`: already mostly language-agnostic. Add TS-common names (`render`, `useEffect`, `middleware`). `GENERIC_MODULE_NAMES`: add TS-common (`index`, `types`, `constants`, `hooks`). `compute_convention_deviations()`: add TS convention checks (export patterns, naming). |
| `formatters/markdown_formatter.py` | Conditional code block language, TS-aware headers | Small | Replace hardcoded `` ```python `` with `` ```{language} `` based on `metadata.language`. Replace `| Python files |` with `| Files |`. Add `ts_specific` section rendering when present. |
| `formatters/json_formatter.py` | No changes needed | None | Already passes through all keys. |

### 7.2 Changes to Deep Crawl Pipeline

| Component | Change | Size | Details |
|---|---|---|---|
| `SKILL.md` | TS file patterns, framework names, test conventions | Medium | Replace `--include="*.py"` with `--include="*.ts" --include="*.tsx"` (or detect from xray metadata). Add TS framework investigation protocols. Update test discovery patterns. |
| `domain_profiles.json` | Add TS domain facets | Medium | Add `react_app`, `next_app`, `express_api`, `nest_api`, `cli_tool`, `electron_app`, `serverless`, `monorepo` facets (as specified in Spec Section 6.3). |
| `quality_gates.json` | No changes needed | None | Gates are defined in terms of counts, not language. |
| `generic_names.json` | Add TS-common names | Small | Add `render`, `use*`, `middleware`, `handler`, `controller`, `component`. |

### 7.3 Changes to Agent Definitions

| Agent | Change | Details |
|---|---|---|
| `repo_xray` | Remove `python xray.py` hardcoding | Reference the scanner generically or detect language. |
| `deep_crawl` | TS-aware investigation protocols | Protocol B (Module Deep Read): adapt for TS module conventions. Protocol C (Cross-Cutting Concern): adapt grep patterns for TS. |
| `repo_retrospective` | No changes needed | Validates documents against code — language-agnostic. |

---

## 8. Testing & Validation Strategy

### 8.1 Golden Test Corpus

A synthetic TS project in `ts-scanner/test/fixtures/golden/` covering every signal:

```
golden/
├── package.json                     Framework detection, entry points
├── tsconfig.json                    Semantic tier testing
├── src/
│   ├── index.ts                     Entry point, exports
│   ├── server.ts                    Express app.listen(), route handlers
│   ├── models/
│   │   ├── user.interface.ts        Interface data model
│   │   ├── user.schema.ts           Zod schema data model
│   │   └── config.ts                Enum, const declarations
│   ├── services/
│   │   ├── user.service.ts          Cross-module calls, side effects (DB)
│   │   └── auth.service.ts          Security concerns, async patterns
│   ├── utils/
│   │   ├── logger.ts                Side effects (console), exports
│   │   └── helpers.ts               Generic-named functions (ambiguity targets)
│   ├── middleware/
│   │   └── error-handler.ts         Silent failures (empty catch), error patterns
│   ├── legacy/
│   │   ├── old-module.ts            Deprecation markers, tech debt comments
│   │   └── require-style.ts         CommonJS require() patterns
│   ├── async-example.ts             Async violations, Promise patterns
│   ├── sql-queries.ts               SQL string detection, tagged templates
│   └── shared-state.ts              Module-level let, mutable exports
├── test/
│   ├── user.service.test.ts         Jest test patterns
│   └── auth.service.spec.ts         Spec-style test patterns
└── types/
    └── global.d.ts                  Declaration file (scanned for types only)
```

**Workflow:** Run the scanner on this corpus, snapshot the JSON output. On every code change, compare against the snapshot. Differences must be intentional.

### 8.2 Contract Validation

A JSON Schema derived from Spec Section 2 interfaces. Every scanner output is validated against it:

```typescript
// test/contract.test.ts
import { validateOutput } from "./schema-validator";

test("golden corpus output matches contract", () => {
  const output = runScanner("test/fixtures/golden");
  const errors = validateOutput(output);
  expect(errors).toEqual([]);
});
```

The schema enforces:
- All required keys present (`metadata`, `summary`)
- Correct types for every field
- `FileAnalysis` objects have all required sub-keys
- No unknown keys at the top level (catches typos)

### 8.3 Signal Parity Tests

For each of the 17 signal categories, a minimal TS file that triggers that signal:

| Signal | Test file | Expected output |
|---|---|---|
| 1. Skeleton | `class Foo { bar(): string }` | `classes[0].name === "Foo"`, method `bar` with return type `string` |
| 2. Complexity | `function f(x) { if(x) { for(...) { switch... } } }` | `complexity > 1` |
| 3. Type coverage | Functions with/without annotations | Correct `typed_functions` / `total_functions` ratio |
| 4. Import graph | Files importing each other | Correct `imports.graph` edges |
| 5. Cross-module calls | Function in A, called in B | Entry in `calls.cross_module` |
| 6. Side effects | `fs.writeFileSync()` call | Entry in `side_effects` with category `file_io` |
| 7. Security | `eval(userInput)` | Entry in `security_concerns` with severity `high` |
| 8. Silent failures | `catch (e) {}` | Entry in `silent_failures` |
| 9. Async patterns | `async function f() { await ... }` | `async_functions === 1` |
| 10. Async violations | `readFileSync` inside `async` | Entry in `async_violations` |
| 11. Decorators | `@Injectable() class Foo {}` | Entry in `decorators.inventory` |
| 12. Data models | `interface User { name: string }` | Entry in `ts_interfaces` |
| 13. Entry points | `app.listen(3000)` | Entry in gap-features entry points |
| 14. Test patterns | `describe("...", () => { it("...", ...) })` | Correct `test_function_count` |
| 15. Tech debt | `// TODO: fix this` | Entry in `tech_debt.items` |
| 16. SQL strings | `` sql`SELECT * FROM users` `` | Entry in `sql_strings` |
| 17. Deprecation | `/** @deprecated Use newFn instead */` | Entry in `deprecation_markers` |

### 8.4 Degradation Tests

Verify graceful handling of edge cases:

| Scenario | Input | Expected behavior |
|---|---|---|
| Syntax error | File with invalid TS | `parse_error` set, partial data extracted, scan continues |
| Missing tsconfig | Project without tsconfig.json | Falls back to syntax tier, metadata notes `parser_tier: "syntax"` |
| Broken tsconfig | Invalid JSON in tsconfig.json | Falls back to syntax tier with warning |
| CommonJS modules | Files using `require()` / `module.exports` | Import graph includes CJS edges, no crash |
| `.js` files without types | Plain JavaScript with no annotations | `type_coverage: 0`, no `any_density` inflation |
| Empty file | `// nothing here` | Valid `FileAnalysis` with zero counts |
| Huge file | 10K+ line file | Completes without OOM, within time budget |
| Mixed TS/JS | Project with both `.ts` and `.js` files | Both file types in `structure.files` |
| `.d.ts` files | Type declaration files | Scanned for types/interfaces, excluded from complexity/side-effects |
| Dynamic imports | `const mod = await import("./mod")` | Recorded as import edge with lower confidence |
| Barrel files | `export * from "./a"; export * from "./b"` | Re-exports tracked in import graph |

### 8.5 Performance Benchmarks

Generate synthetic projects at scale:

```typescript
function generateProject(fileCount: number): string {
  // Create fileCount .ts files with realistic structure:
  // - 30% contain classes (2-5 methods each)
  // - 50% contain functions (3-8 per file)
  // - 20% contain only types/interfaces
  // - Random cross-file imports (avg 3 per file)
  // Returns temp directory path
}
```

| Metric | 100 files | 500 files | 1000 files | Budget |
|---|---|---|---|---|
| Syntax tier time | — | — | — | ≤5s for 500 |
| Semantic tier time | — | — | — | ≤15s for 500 |
| Peak memory | — | — | — | ≤256MB syntax, ≤512MB semantic |

Run benchmarks in CI. Alert on >20% regression.

---

## 9. Build & Distribution

### 9.1 Repository Layout

The scanner lives as a subdirectory in the repo-xray repository:

```
claude-repo-xray/
├── xray.py
├── lib/
├── formatters/
├── configs/
├── ts-scanner/           ← New subdirectory
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   ├── dist/             ← Compiled JS (gitignored except as release artifact)
│   └── test/
├── docs/
└── ...
```

### 9.2 Build Process

```bash
cd ts-scanner
npm install              # Install typescript (+ vitest for dev)
npm run build            # tsc compiles src/ → dist/
```

The built `dist/index.js` is the entry point that `xray.py` invokes. The `dist/` directory is gitignored in development but included in releases.

### 9.3 User Installation Flow

For users who want TS analysis:

```bash
# One-time setup
cd ts-scanner && npm install && npm run build && cd ..

# Then use normally — xray.py auto-detects TS files
python xray.py /path/to/ts-project
```

For users who only analyze Python: no setup needed. `xray.py` silently skips TS analysis when the scanner isn't built.

### 9.4 CI Integration

```yaml
# GitHub Actions snippet
- name: Build TS scanner
  run: cd ts-scanner && npm ci && npm run build

- name: Run TS scanner tests
  run: cd ts-scanner && npm test

- name: Run integration tests
  run: python -m pytest tests/ -x -q  # Includes tests that invoke TS scanner
```

---

## Appendix A: Deferred Decisions from TS_FRONTEND_SPEC.md — Resolution Status

Every open question from Spec Section 8, resolved or explicitly re-deferred:

| Spec section | Question | Resolution in this document |
|---|---|---|
| 8.1 Orchestrator Design | How does xray.py invoke the TS frontend? | **Section 1**: Subprocess. xray.py detects language, shells out to `node ts-scanner/dist/index.js`, reads JSON from stdout, merges results. |
| 8.2 Monorepo Handling | How to handle multiple tsconfig.json files? | **Section 4.4**: Find all tsconfigs, one `ts.createProgram()` per config (semantic tier), deduplicate files. |
| 8.3 Mixed-Language Repos | How to merge Python + TS results? | **Section 1.4**: Run both scanners independently, merge at the results dict level. Cross-language edges are out of scope for the scanner. |
| 8.4 Performance Targets | Concrete numbers? | **Section 8.5**: ≤5s syntax / ≤15s semantic for 500 files. ≤256MB / ≤512MB memory. |
| 8.5 Bundling and Distribution | npm package, subdirectory, or vendored? | **Section 9**: Subdirectory `ts-scanner/` in the repo. `package.json` with `typescript` as single dep. Users run `npm install` once. |
| 8.6 JS vs TS Mode | Should `any` density differ for JS-only? | **Section 6, inherited from spec**: Report both `type_coverage` (standard) and `ts_specific.any_density` (TS-specific). `any_density` counts only for TS files. JS files report type coverage as 0% without penalty. |

## Appendix B: Spec Section 5.1 Corrections

The spec claims several components are "Reuse as-is." Investigation shows this is overly optimistic. Corrected assessment:

| Spec claim | Actual status | Details |
|---|---|---|
| `markdown_formatter.py` — reuse as-is | **Requires small changes** | Hardcodes `` ```python `` code blocks and `\| Python files \|` headers. Needs language-conditional formatting. (Section 7.1) |
| `json_formatter.py` — reuse as-is | **Correct** | Serializes the dict. Extra keys pass through. |
| `gap_features.py` — implied reuse | **Requires medium changes** | `extract_data_models()` hardcodes Pydantic/dataclass/TypedDict. `detect_entry_points()` hardcodes Python filenames. `extract_cli_args()` knows only argparse/Click/Typer. All need TS branches. (Section 7.1) |
| `investigation_targets.py` — implied reuse | **Requires small changes** | Heuristic thresholds are Python-biased. `compute_convention_deviations()` checks `__init__` patterns. Needs TS convention equivalents. `compute_shared_mutable_state()` re-parses Python files — TS equivalent must live in the TS scanner. (Section 7.1) |
| Deep crawl agents — "requires no changes" | **Requires medium changes** | SKILL.md has hardcoded `--include="*.py"`, Python framework names, `test_*.py` patterns, Protocol B/C grep commands. (Section 7.2) |
| Config system — reuse as-is | **Correct** | `config_loader.py` and config files are language-agnostic. |
| Git analysis — reuse as-is | **Correct** | Operates on file paths and `git log`. Language-agnostic. |
| `tech_debt_analysis.py` — reuse as-is | **Mostly correct** | Regex patterns work on `//` and `/* */` comments. Minor: should also handle JSDoc `/** @deprecated */` but that's already covered by the TS scanner's deprecation detection. |

## Appendix C: What Comes After This Document

1. **TS Scanner implementation** — Build `ts-scanner/` following this design. Start with `ast-analysis.ts` (the core), then `import-analysis.ts`, then remaining modules. Target: syntax tier first, semantic tier second.

2. **Pipeline adaptation** — Modify `xray.py`, `file_discovery.py`, `gap_features.py`, `investigation_targets.py`, `markdown_formatter.py` per Section 7.1.

3. **Deep crawl adaptation** — Update `SKILL.md`, `domain_profiles.json`, agent definitions per Section 7.2-7.3.

4. **Integration testing** — Run the full pipeline (xray.py → TS scanner → formatters → deep crawl) on a real-world open-source TS project (e.g., Express, NestJS starter, Next.js template).

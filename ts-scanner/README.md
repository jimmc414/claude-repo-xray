# repo-xray TypeScript Scanner

Static analysis frontend for TypeScript and JavaScript codebases. Produces the same `XRayResults` JSON schema as the Python scanner, so all downstream tooling (formatters, gap features, investigation targets, deep crawl) works identically for both languages.

## Setup

```bash
npm install
npm run build
```

Requires Node.js >= 18.0.0. The only runtime dependency is the TypeScript compiler API.

## Usage

The scanner is invoked by `xray.py` automatically when it detects a TypeScript project. You don't normally run it directly.

```bash
# Normal usage (via xray.py — auto-detects language)
python xray.py /path/to/ts-project

# Direct invocation (for debugging)
node dist/index.js /path/to/ts-project [--verbose]
```

Output is JSON to stdout, progress to stderr.

## What It Extracts

### Structural Signals

| Signal | Module | Description |
|--------|--------|-------------|
| File structure | `file-discovery.ts` | File list with ignore patterns, declaration file detection |
| Function skeletons | `ast-analysis.ts` | Name, args, return type, decorators, async, complexity, docstrings |
| Class skeletons | `ast-analysis.ts` | Name, bases, methods, properties, decorator details |
| Type coverage | `ast-analysis.ts` | Typed vs untyped functions, coverage percentage |
| Decorator inventory | `ast-analysis.ts` | Decorator names and usage counts across codebase |
| Complexity hotspots | `ast-analysis.ts` | Cyclomatic complexity per function, top-20 ranked |

### Dependency Signals

| Signal | Module | Description |
|--------|--------|-------------|
| Import graph | `import-analysis.ts` | Module dependencies, layers, circular deps, import distance |
| Barrel file detection | `import-analysis.ts` | Re-export-only index files with source tracking |
| Call graph | `call-analysis.ts` | Cross-module call sites, reverse lookup, fan-in/fan-out |
| Blast radius | `blast-analysis.ts` | Per-module change impact via import + call graph |

### Behavioral Signals

| Signal | Module | Description |
|--------|--------|-------------|
| Side effects | `detectors.ts` | File I/O, network, database, process, crypto, console |
| Security concerns | `detectors.ts` | eval, dynamic require, shell exec, hardcoded secrets |
| Silent failures | `detectors.ts` | Empty catch blocks, catch-and-ignore patterns |
| SQL strings | `detectors.ts` | Raw SQL in string literals and template expressions |
| Deprecation markers | `detectors.ts` | `@deprecated` JSDoc and decorator patterns |
| Async patterns | `ast-analysis.ts` | Async/sync function ratio, async violations |
| Resource leaks | `detectors.ts` | Unclosed streams, handles, connections |
| Environment variables | `detectors.ts` | `process.env.*` access with defaults and fallback types |
| Import-time effects | `import-time-effects.ts` | Top-level side effects that run at import time |

### Framework-Aware Signals

| Signal | Module | Description |
|--------|--------|-------------|
| HTTP routes | `route-analysis.ts` | Express/Fastify/Koa/Hono call-based, NestJS decorator-based, Next.js App Router and SvelteKit file-path convention |
| CLI frameworks | `cli-analysis.ts` | Commander, yargs, oclif, meow, caporal, clipanion, gluegun |
| Config rules | `config-analysis.ts` | tsconfig, ESLint, and Prettier configuration extraction |
| Logic maps | `logic-maps.ts` | Control flow maps for complex hotspot functions |
| Test detection | `test-analysis.ts` | Test files, framework detection, coverage patterns |

### TS-Specific Signals

| Signal | Module | Description |
|--------|--------|-------------|
| Any density | `ast-analysis.ts` | `explicit any`, `as any` assertions, `@ts-ignore`, `@ts-expect-error` counts |
| Module system | `ast-analysis.ts` | ESM vs CommonJS vs mixed |
| Declaration files | `file-discovery.ts` | `.d.ts` file count |
| Module augmentations | `ast-analysis.ts` | `declare module` extensions |
| Namespaces | `ast-analysis.ts` | TypeScript namespace declarations |

### Git Signals

| Signal | Module | Description |
|--------|--------|-------------|
| Risk scores | `git-analysis.ts` | Per-file risk from churn, hotfixes, author count |
| Co-modification coupling | `git-analysis.ts` | Files that change together |
| Coupling clusters | `git-analysis.ts` | Groups of highly co-modified files |
| Freshness | `git-analysis.ts` | Active, aging, stale, dormant classification |
| Function churn | `git-analysis.ts` | Per-function commit history and risk |
| Velocity | `git-analysis.ts` | Monthly commit trends per file |

### Derived Signals

| Signal | Module | Description |
|--------|--------|-------------|
| Investigation targets | `investigation-targets.ts` | Priority files combining complexity, coupling, churn |
| Tech debt markers | `tech-debt.ts` | TODO, FIXME, HACK, XXX with context |

## Architecture

```
src/
├── index.ts                 Entry point, orchestration, aggregation
├── types.ts                 XRayResults contract interfaces (683 lines)
├── file-discovery.ts        Find TS/JS files, apply ignore patterns
├── ast-analysis.ts          Single-pass AST: skeletons, complexity, types (932 lines)
├── detectors.ts             Behavioral signal detectors (490 lines)
├── import-analysis.ts       Dependency graph, layers, circular deps, barrels (713 lines)
├── call-analysis.ts         Cross-module call sites, fan-in
├── route-analysis.ts        HTTP route detection (call, decorator, file-path)
├── cli-analysis.ts          CLI framework detection
├── config-analysis.ts       tsconfig/ESLint/Prettier extraction
├── logic-maps.ts            Control flow maps for complex functions
├── blast-analysis.ts        Change impact via import + call graph
├── git-analysis.ts          Risk, coupling, freshness from git log (495 lines)
├── investigation-targets.ts Priority file ranking
├── import-time-effects.ts   Top-level side effect detection
├── tech-debt.ts             TODO/FIXME marker scanning
├── test-analysis.ts         Test file detection
└── utils.ts                 Shared helpers
```

20 modules, ~6,000 lines of TypeScript.

## Pipeline

```
file-discovery → ast-analysis → import-analysis → call-analysis → test-analysis
                                                                 → route-analysis
                                                                 → blast-analysis
                                                                 → import-time-effects
                                                                 → git-analysis
                                                                 → tech-debt
                                                 → aggregation   → logic-maps
                                                                 → config-analysis
                                                                 → cli-analysis
                                                                 → investigation-targets
                                                                 → ts_specific aggregation
                                                                 → resource_leaks aggregation
```

Each file is parsed once by `ast-analysis.ts` using `ts.createSourceFile`. The resulting `FileAnalysis` records are passed to all downstream modules. No file is read twice.

## Route Detection

Three detection strategies, applied per file:

1. **Call-based** — Express/Fastify/Koa/Hono: `app.get("/path", handler)`
2. **Decorator-based** — NestJS: `@Get("/path")` on `@Controller` class methods
3. **File-path convention** — Next.js App Router (`app/**/route.ts`) and SvelteKit (`routes/**/+server.ts`)

File-path convention detection:
- Extracts URL path from file system path
- Strips route groups: `(auth)`, `(chat)` segments removed
- Preserves dynamic segments: `[id]`, `[...slug]`
- Finds exported HTTP methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`
- Handles monorepos: matches `app/` as a path segment (not `apps/`)

## Tests

```bash
npm test              # Run all unit tests (vitest)
npm run test:watch    # Watch mode
```

8 test files, ~120 tests. Test fixtures in `test/fixtures/minimal/`.

| Test File | Covers |
|-----------|--------|
| `ast-analysis.test.ts` | Function/class extraction, complexity, decorators, TS-specific |
| `import-analysis.test.ts` | Import graph, circular deps, barrel files, layers |
| `call-analysis.test.ts` | Cross-module calls, fan-in, reverse lookup |
| `behavioral.test.ts` | Side effects, security, silent failures, SQL, deprecation |
| `cli-analysis.test.ts` | All 7 CLI frameworks |
| `config-analysis.test.ts` | tsconfig, ESLint, Prettier extraction |
| `logic-maps.test.ts` | Control flow map generation |
| `integration.test.ts` | Full scanner end-to-end on fixture project |

## Relationship to xray.py

`xray.py` detects the project language via `detect_language()`. For TypeScript projects:

1. Invokes `node ts-scanner/dist/index.js <target>` via subprocess
2. Parses the JSON output
3. Augments with language-agnostic git analysis (`_augment_with_git()`)
4. Computes entry points and data models via `gap_features.py`
5. Recomputes investigation targets with combined signals
6. Passes to formatters (markdown + JSON)

The TS scanner is a standalone npm project — it does not import from or depend on the Python codebase. Communication is JSON over subprocess stdout.

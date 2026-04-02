# Multi-Language Analysis Research: Extending repo-xray Beyond Python

## Executive Summary

repo-xray currently analyzes Python codebases using Python's `ast` module — a zero-dependency, deterministic, single-pass approach that extracts 37+ signals from syntax, import graphs, git history, and code patterns. This document evaluates how to replicate that approach for TypeScript, Rust, Go, C#, and COBOL.

**The central finding:** The quality of multi-language analysis hinges entirely on the static analysis foundation available for each language. Python's `ast` module provides a rare sweet spot — built into the language runtime, zero setup, full syntax tree access. No other language has an exact equivalent, but some come remarkably close (Go), while others require significant tradeoffs (COBOL).

**Recommendation summary:**

| Language | Best Tool | Dependency Model | Semantic Depth | Effort |
|----------|-----------|-----------------|----------------|--------|
| Go | `go/ast` + `go/types` (stdlib) | Zero-dep binary | Highest | Low |
| TypeScript | TypeScript Compiler API | Single npm pkg (`typescript`) | High | Medium |
| Rust | `syn` crate + `cargo metadata` | Compiled binary | Medium | Medium |
| C# | Roslyn (`Microsoft.CodeAnalysis`) | NuGet package | High | Medium-High |
| COBOL | Custom regex/pattern parser | Zero-dep | Low-Medium | High |

---

## What We Need to Replicate

Before evaluating tools, we must define exactly what signals repo-xray extracts and which are language-universal vs Python-specific.

### Core Signals (Language-Universal)

These signals exist in every language and form the backbone of the scanner output:

| Signal | Source Module | What It Produces |
|--------|-------------|-----------------|
| **Code skeleton** | `ast_analysis.py` | Function/method/class signatures with parameters and return types |
| **Complexity metrics** | `ast_analysis.py` | Cyclomatic complexity per function, hotspot identification |
| **Type annotation coverage** | `ast_analysis.py` | Percentage of functions with type hints |
| **Import/dependency graph** | `import_analysis.py` | Module dependency edges, layers, circular deps, orphans |
| **Cross-module call graph** | `call_analysis.py` | Who calls what across files, fan-in/fan-out, reverse lookup |
| **Side effect detection** | `ast_analysis.py` | I/O, network, DB, subprocess calls flagged by pattern matching |
| **Decorator/attribute inventory** | `ast_analysis.py` | Framework markers (`@app.route`, `#[derive]`, `[HttpGet]`) |
| **Async pattern detection** | `ast_analysis.py` | Async functions, await usage, concurrency patterns |
| **Git risk scores** | `git_analysis.py` | Churn rate, recency, co-modification coupling |
| **Test coverage mapping** | `test_analysis.py` | Which modules have tests, test patterns |
| **Tech debt markers** | `tech_debt_analysis.py` | TODO/FIXME/HACK comments |
| **Data model extraction** | `gap_features.py` | Pydantic, dataclass, TypedDict → struct/interface equivalents |
| **Entry point detection** | `gap_features.py` | Main functions, CLI handlers, HTTP routes |
| **Logic maps** | `gap_features.py` | Control flow visualization for complex functions |
| **Hazard detection** | `gap_features.py` | Large files, high complexity, low test coverage warnings |

### Language-Specific Signals to Add

Each target language has unique constructs that matter for AI orientation:

| Language | Unique Signals |
|----------|---------------|
| **TypeScript** | Interface vs type alias, union/intersection types, generic constraints, JSX components, module augmentation, declaration merging |
| **Rust** | Ownership/borrowing patterns, `unsafe` blocks, trait implementations, lifetime annotations, macro invocations, derive attributes, error handling patterns (`Result`/`Option`) |
| **Go** | Goroutine spawns, channel usage patterns, interface satisfaction, defer/panic/recover, embedded structs, build tags |
| **C#** | Nullable reference types, LINQ patterns, attribute-driven frameworks (ASP.NET, EF), partial classes, source generators, async state machines |
| **COBOL** | Division structure, level-number hierarchies (01-49, 66, 77, 88), COPY/copybook dependencies, PERFORM call graphs, EXEC SQL/CICS blocks, file I/O declarations |

---

## Design Principles for Multi-Language Support

From INTENT.md, the scanner must be:

1. **Deterministic** — Same input, same output. No LLM calls, no network requests during analysis.
2. **Fast** — 5 seconds on a 500-file codebase. Analysis speed matters because the scanner runs frequently.
3. **Zero/minimal dependencies** — The Python scanner uses only stdlib. Each language scanner should minimize external requirements.
4. **Fault-tolerant** — A single unparseable file must never crash the scan. Partial results are better than no results.
5. **Syntax-first, semantics-optional** — The Python scanner works from AST alone (no type checker, no runtime). Semantic enhancement (type resolution, call graph precision) should be an optional tier, not a requirement.

### Architecture Options

**Option A: One scanner per language (recommended)**
Each language gets its own scanner binary/script written in a language with good tooling for that target. A Go binary analyzes Go code. A Node.js script analyzes TypeScript. A Rust binary analyzes Rust. A C# tool analyzes C#.

*Pros:* Best tooling access, idiomatic analysis, can leverage each language's native AST libraries.
*Cons:* Multiple codebases to maintain, different installation requirements per language.

**Option B: Polyglot scanner using tree-sitter**
A single Python tool (extending xray.py) uses tree-sitter grammars for all languages. Tree-sitter has Python bindings and grammars for every target language.

*Pros:* Single codebase, uniform API, shared infrastructure (git analysis, formatters, config).
*Cons:* Syntax-only analysis (no type resolution for any language), tree-sitter Python bindings are an external dependency (violates zero-dep principle), CST is lower-level than language-native ASTs.

**Option C: Hybrid — shared core + language-specific frontends**
The output format, git analysis, formatters, and config system are shared. Each language has a frontend that produces a standardized intermediate representation (JSON) that feeds into shared formatters.

*Pros:* Reuses the most complex part (formatting/output), allows best-in-class parsing per language.
*Cons:* Must define and maintain a cross-language IR schema.

**Recommendation: Option C (Hybrid).** The git analysis, markdown formatter, JSON formatter, config system, and output pipeline are language-agnostic today. The language-specific part is the AST analysis pipeline (`ast_analysis.py`, `import_analysis.py`, `call_analysis.py`). Each language frontend produces the same JSON structure these modules output, and the rest of the pipeline works unchanged.

---

## Language-by-Language Analysis

---

### 1. Go — The Best Case

**Go is the most favorable language for this approach.** It has first-class AST tooling in its standard library, compiles to a zero-dependency static binary, and its type system is simple enough that static analysis captures nearly everything.

#### Tool Options

| Tool | Type | Semantic Depth | Dependencies | Speed |
|------|------|---------------|--------------|-------|
| `go/ast` + `go/parser` (stdlib) | Syntax AST | Syntax only | Zero | Fast |
| `go/types` (stdlib) | Type checker | Full type resolution | Needs Go toolchain | Moderate |
| `golang.org/x/tools/go/packages` | Package loader | Full (wraps go/types) | Needs Go toolchain | Moderate |
| `golang.org/x/tools/go/callgraph` (VTA) | Call graph | Resolved dispatch | Needs whole program | Slow |
| `golang.org/x/tools/go/ssa` | SSA IR | Data flow | Needs whole program | Slow |
| `tree-sitter-go` | CST parser | Syntax only | C library | Fast |

#### Recommended Approach: `go/ast` + `go/parser` (primary), `go/types` (optional enhancement)

**Why `go/ast` is the direct equivalent of Python's `ast` module:**
- It is part of Go's standard library — `import "go/ast"` with zero external dependencies
- It produces a strongly-typed AST with dedicated node types (`*ast.FuncDecl`, `*ast.GenDecl`, `*ast.TypeSpec`, etc.)
- It includes a built-in walker (`ast.Walk`, `ast.Inspect`) analogous to Python's `ast.NodeVisitor`
- It parses comments and associates them with nodes (unlike many parsers)
- Each file is parsed independently in milliseconds

**What `go/ast` alone provides (syntax-only tier):**

| xray Signal | Go Extraction Method | Quality |
|-------------|---------------------|---------|
| Code skeleton | `*ast.FuncDecl` for functions, `*ast.TypeSpec` for structs/interfaces | Excellent — signatures include parameter names and syntactic types |
| Complexity | Count `*ast.IfStmt`, `*ast.CaseClause`, `*ast.ForStmt`, `*ast.RangeStmt`, `*ast.CommClause` | Excellent |
| Type annotations | Go is statically typed — every parameter has an explicit type in the AST | 100% coverage by definition |
| Import graph | `*ast.ImportSpec` gives import paths directly | Excellent — Go imports are explicit file paths |
| Call sites | `*ast.CallExpr` with function name extraction | Good — unresolved through interfaces |
| Side effects | Pattern-match on known I/O package calls (`os.`, `net/http.`, `database/sql.`) | Good |
| Async/concurrency | `*ast.GoStmt` (goroutines), `*ast.SendStmt`/`*ast.UnaryExpr` with `<-` (channels), `*ast.SelectStmt` | Excellent — all goroutine/channel usage is syntactically visible |
| Decorator equivalents | N/A — Go has no decorators. Struct tags (`json:"name"`) are extractable from `*ast.Field.Tag` | Different but useful |
| Data models | `*ast.StructType` with fields, tags, embedded types | Excellent |
| Entry points | `func main()` in `package main`, `func init()`, HTTP handler signatures | Excellent |

**What `go/types` adds (semantic tier, requires Go toolchain on target):**

- Resolved types for every expression (turns `x` into `*http.Request`)
- Interface satisfaction (knows that `MyHandler` implements `http.Handler`)
- Cross-package reference resolution (follows imports to definitions)
- Method set computation (all methods on a type, including promoted methods from embedded structs)
- Constant evaluation

**What `golang.org/x/tools/go/callgraph/vta` adds (deep tier, expensive):**

- Precise call graph through interfaces (resolves dynamic dispatch)
- Dead code detection (unreachable functions)
- Full fan-in/fan-out with resolved targets

#### Why Go is Easiest

1. **No macros, no code generation, no metaprogramming.** What you see in the source is what runs. Unlike Rust (macros), TypeScript (decorators + build transforms), or C# (source generators), Go's static analysis sees everything.
2. **Explicit types everywhere.** No type inference to resolve (except `:=` short variable declarations, which `go/types` handles). The syntax tree contains complete type information.
3. **Simple module system.** Import paths map directly to directories. No complex module resolution rules like Node.js or Rust.
4. **Single binary deployment.** The analyzer compiles to a static binary with zero runtime dependencies. Users don't need Go installed to run the syntax-only tier.
5. **No inheritance.** Go's composition model (embedding + interfaces) is simpler to analyze statically than deep inheritance hierarchies.

#### Deployment

```
# Build the analyzer
go build -o xray-go ./cmd/xray-go

# Run it (no Go installation needed on target for syntax-only)
./xray-go /path/to/go/project

# Enhanced mode (needs Go toolchain for type resolution)
./xray-go --semantic /path/to/go/project
```

Output: same JSON schema as Python xray → feeds into shared markdown/JSON formatters.

#### Effort Estimate

A Go scanner matching Python xray's signal coverage could be built with approximately:
- `ast_analysis.go`: ~800 lines (skeleton + complexity + side effects + concurrency patterns)
- `import_analysis.go`: ~400 lines (import graph from AST, layer classification)
- `call_analysis.go`: ~300 lines (syntactic call extraction, cross-file matching)
- Shared utilities: ~200 lines
- Total: **~1,700 lines of Go**, zero external dependencies

---

### 2. TypeScript — The Pragmatic Choice

TypeScript analysis has a clear winner: the TypeScript Compiler API. It provides both syntax-only parsing (fast, zero-project-setup) and full semantic analysis (type resolution, cross-module references) through a single dependency.

#### Tool Options

| Tool | Type Resolution | Speed (parse) | Dependencies | AST Quality |
|------|----------------|---------------|--------------|-------------|
| **TypeScript Compiler API** | Full | Moderate | `typescript` npm pkg only | Native, complete |
| ts-morph | Full (wraps TS) | Same as TS API | 3 npm packages | Convenience wrapper |
| @typescript-eslint/parser | Full (via TS) | Same as TS API | 4+ npm packages | ESTree (lossy conversion) |
| SWC | None | Very fast (Rust-based) | Native binary | Custom format |
| Babel parser | None | Fast | Pure JS, light | Babel AST |
| tree-sitter-typescript | None | Fast | C library | CST (verbose) |
| OXC | None | Very fast (Rust-based) | WASM/native | ESTree |

**The clear dividing line:** Only the TypeScript Compiler API (and wrappers around it) provides type resolution. Every other option is syntax-only. Since type resolution is what makes the analysis valuable (resolving imports, following inheritance, building accurate call graphs), the Compiler API is the only serious contender.

#### Recommended Approach: TypeScript Compiler API directly

**Two operating modes:**

1. **`ts.createSourceFile()` — syntax-only, fast, zero project setup**
   - Parses a single file into an AST (~1ms per file)
   - No `tsconfig.json` needed
   - Extracts: function/class/interface declarations, type annotations as written, import statements, decorator syntax, complexity metrics, JSX components

2. **`ts.createProgram()` — full semantic analysis, needs project context**
   - Loads via `tsconfig.json`, builds the type checker
   - 5-30 seconds for a large project (same cost as `tsc --noEmit`)
   - Adds: resolved types, cross-module references, class hierarchy traversal, interface implementation checking, overload resolution, generic instantiation

**What each mode provides:**

| xray Signal | Syntax-only (`createSourceFile`) | Semantic (`createProgram`) |
|-------------|----------------------------------|---------------------------|
| Code skeleton | Declarations with parameter names and written types | + resolved types, inferred return types |
| Complexity | Branch counting (`if`, `switch`, `for`, ternary, `&&`/`||`) | Same |
| Type coverage | Presence of `: Type` annotations | + inferred types for unannotated code |
| Import graph | `import` statements with paths | + resolved module targets |
| Call graph | `CallExpression` nodes with syntactic names | + resolved function targets through interfaces/types |
| Side effects | Pattern matching on `fetch()`, `fs.`, `console.`, DOM mutations | + type-based detection (knows if arg is `WritableStream`) |
| Decorators | `@decorator` syntax nodes | + resolved decorator functions |
| Async patterns | `async`/`await` keywords | + Promise type resolution |
| Data models | `interface`, `type`, `class` declarations | + resolved generic parameters, extended types |
| Entry points | `export default`, named exports, Express/Next.js route patterns | + type-based framework detection |
| JSX components | `<Component>` elements | + prop type resolution |

**Why not ts-morph?** ts-morph wraps the Compiler API with convenience methods (`.getClasses()`, `.getFunctions()`). This is nice for quick scripts but adds a dependency and abstraction layer. For a tool that needs deep, controlled access to the compiler (our use case), you end up calling through to `.compilerNode` frequently anyway. Start with the raw API.

**Why not SWC/Babel/tree-sitter?** These are all syntax-only parsers. They're faster but lack type resolution. The speed advantage is irrelevant — the type checker dominates analysis time anyway, and even syntax-only analysis of a 5,000-file project takes under 5 seconds with the TS Compiler API.

#### The `typescript` Package as Sole Dependency

The `typescript` npm package is the equivalent of Python's `ast` module — it is the language's own tooling. Key facts:
- Pure JavaScript, no native modules, no build step required
- ~45MB installed, zero transitive dependencies
- The analyzer can be a plain `.js` file: `const ts = require("typescript")`
- Runs anywhere Node.js runs (Node 14+)
- Extremely stable — Microsoft ships new releases quarterly, core APIs haven't broken in years

**Minimal setup:**
```
mkdir xray-ts && cd xray-ts
npm init -y && npm install typescript
# Write analyze.js (plain JS, no transpilation needed)
node analyze.js /path/to/ts/project
```

#### Key Gotchas

1. **No built-in visitor pattern.** You write recursive `ts.forEachChild(node, visitor)`. Manageable but less ergonomic than Python's `ast.NodeVisitor`.
2. **The AST is a concrete syntax tree.** Every token (parentheses, semicolons, commas) is a node. More verbose to walk but nothing is lost.
3. **Compiler API is technically "internal."** Microsoft doesn't version it as stable API, but in practice the core surface (`createProgram`, `TypeChecker`, `Node` types) has been stable for years. The ecosystem depends on it.
4. **Memory-heavy for semantic analysis.** Large monorepos can use 1-4 GB for the type checker. Syntax-only mode is lightweight.
5. **Project references and monorepos** add complexity. A monorepo with 50 `tsconfig.json` files requires loading multiple programs or using the project references API.

#### Deployment

```
# Option 1: Ship as Node.js script
node xray-ts.js /path/to/project

# Option 2: Bundle with pkg/nexe for single binary
npx pkg xray-ts.js --target node18-linux-x64

# Option 3: Use Deno for single-file execution
deno run --allow-read xray-ts.ts /path/to/project
```

#### Effort Estimate

- `ast_analysis.ts`: ~1,000 lines (skeleton + complexity + side effects + JSX + decorators)
- `import_analysis.ts`: ~500 lines (import graph, module resolution)
- `call_analysis.ts`: ~400 lines (call expression extraction, cross-file matching)
- `type_analysis.ts`: ~300 lines (type coverage, interface/type alias extraction)
- Total: **~2,200 lines of TypeScript/JavaScript**, single npm dependency

---

### 3. Rust — The Macro Problem

Rust is the trickiest modern language for static analysis. The language itself is richly typed and statically analyzable in theory, but Rust's pervasive macro system means a pure syntax parser sees a meaningfully incomplete picture. The gap between syntax-only and semantic analysis is wider in Rust than in any other language on this list.

#### Tool Options

| Tool | Type Resolution | Macro Expansion | Dependencies | API Stability |
|------|----------------|-----------------|--------------|---------------|
| **`syn`** (crate) | None | None | Pure Rust, compiles to binary | Excellent (v2) |
| **`ra_ap_syntax`** (rust-analyzer syntax) | None | None | Pure Rust | Unstable (weekly releases) |
| **`ra_ap_hir`** (rust-analyzer semantic) | Full | Yes | Heavy dep tree + Rust toolchain | Unstable |
| `rustc` internals (`rustc_private`) | Full + borrow checker | Yes | Nightly Rust only | None (changes weekly) |
| `tree-sitter-rust` | None | None | C library | Good |
| `cargo metadata` (subcommand) | N/A | N/A | Needs `cargo` | Stable JSON format |

#### The Macro Problem — Quantified

This is the key issue. Rust macros generate code that is invisible to any syntax-only parser:

- **Derive macros** (`#[derive(Debug, Clone, Serialize)]`): Generate `impl` blocks. In a typical web service using `serde`, `clap`, `sqlx`, `axum` — derive macros generate 20-40% of the effective code.
- **Attribute macros** (`#[tokio::main]`, `#[test]`, `#[async_trait]`): Transform function signatures and bodies.
- **Declarative macros** (`macro_rules!`): `vec![]`, `println!()`, custom DSLs. The invocation is visible but the expansion is not.
- **Function-like proc macros** (`sqlx::query!("SELECT ...")`, `html! { <div>...</div> }`): Generate entire expression trees.

**Is this a dealbreaker?** No, for the same reason Python's `ast` module works despite metaclasses and decorators generating code at runtime. The scanner extracts *the code humans wrote and read*, which is what an AI assistant needs for orientation. Knowing `#[derive(Serialize)]` is on a struct is more useful for navigation than seeing the generated `impl Serialize` block.

#### Recommended Approach: `syn` crate (primary), `cargo metadata` (complement)

**Why `syn`:**
- The dominant Rust parsing crate — the foundation of the entire proc-macro ecosystem
- Maintained by David Tolnay (one of the most prolific Rust contributors)
- Strongly-typed AST: `ItemFn`, `ItemStruct`, `ItemEnum`, `ItemTrait`, `ImplBlock` — each with typed fields
- Pure Rust, compiles to a static binary with zero runtime requirements
- Stable API (v2 was a careful rewrite)
- Parses any valid Rust syntax including all macro invocations (as opaque token streams)

**Why not `ra_ap_hir` (rust-analyzer)?**
- Full semantic analysis (type resolution, macro expansion, trait resolution, cross-module references)
- BUT: API changes weekly, massive dependency tree, requires Rust toolchain + compiled project for proc-macro expansion
- Setup is ~500+ lines of boilerplate just to create an `AnalysisHost`
- Right choice for a dedicated Rust IDE tool, wrong choice for a lightweight scanner

**Why not `rustc_private`?**
- Everything the compiler knows (types, lifetimes, borrow checker, MIR)
- BUT: nightly-only forever (explicit policy), API breaks weekly, requires full compilation of target project
- Only viable if you're building something that ships with the Rust toolchain (like Clippy)

**What `syn` provides:**

| xray Signal | Extraction Method | Quality |
|-------------|------------------|---------|
| Code skeleton | `ItemFn` (signatures), `ItemStruct`/`ItemEnum` (type defs), `ItemTrait` (interfaces), `ImplBlock` (implementations) | Excellent — full signatures with generics, lifetimes, where clauses |
| Complexity | Count `If`, `Match` arms, `While`, `Loop`, `For`, `?` operator | Good |
| Type annotations | Rust is statically typed — all params and return types in the AST | 100% (explicit types only; `impl Trait` returns stay opaque) |
| Import graph | `UseTree` items give `use` paths; `mod` declarations give module structure | Good — need to implement module resolution (file path conventions) |
| Call graph | `ExprCall` and `ExprMethodCall` with syntactic names | Medium — cannot resolve trait method dispatch |
| Side effects | Pattern match on `std::fs::`, `std::net::`, `tokio::`, `reqwest::` calls | Good |
| Unsafe detection | `unsafe` blocks, `unsafe fn`, `unsafe impl`, `unsafe trait` | Excellent — all syntactically visible |
| Attribute inventory | `#[derive(...)]`, `#[cfg(...)]`, `#[test]`, custom attributes | Excellent |
| Async patterns | `async fn`, `.await` expressions | Excellent |
| Error handling | `Result<T, E>` return types, `?` operator usage, `.unwrap()` calls | Good |
| Data models | `struct` (named, tuple, unit), `enum` with variants | Excellent |
| Lifetime annotations | Lifetime parameters on functions and types | Excellent |

**What `cargo metadata` adds (requires `cargo` on target):**
- Complete dependency graph with versions, features, and sources
- Workspace structure
- Target information (lib, bin, test, example, bench)
- Feature flag configurations
- Stable JSON output format — trivial to parse from any language

**Module resolution (must implement manually):**
`syn` parses individual files. To build a cross-file picture, you must follow `mod` declarations:
- `mod foo;` → look for `foo.rs` or `foo/mod.rs` (Rust 2015) or `foo.rs` with `foo/` subdirectory (Rust 2018+)
- This is ~100 lines of path-walking logic
- `use crate::foo::Bar` → resolve against the module tree you built

#### Key Honest Assessment

Rust syntax-only analysis gives you roughly **70-80% of the useful signals** compared to Python's AST analysis. The 20-30% gap comes from:
- Macro-generated code being invisible (~15% of the gap)
- Trait method dispatch being unresolvable without type info (~10%)
- Generic type instantiation being opaque (~5%)

For an AI coding assistant's orientation needs, this is acceptable. The scanner tells you the structure, the agent layer reads the actual code.

#### Deployment

```
# Build the analyzer (produces a static binary)
cargo build --release
# Binary at target/release/xray-rust (~2-5 MB stripped)

# Run it (no Rust installation needed on target)
./xray-rust /path/to/rust/project
```

#### Effort Estimate

- `ast_analysis.rs`: ~1,200 lines (skeleton + complexity + unsafe + async + attributes + error patterns)
- `module_resolver.rs`: ~200 lines (follow `mod` declarations to build file tree)
- `import_analysis.rs`: ~400 lines (use tree parsing, dependency graph)
- `call_analysis.rs`: ~350 lines (call expression extraction, cross-file name matching)
- `cargo_metadata.rs`: ~150 lines (invoke `cargo metadata`, parse JSON)
- Total: **~2,300 lines of Rust**, `syn` as sole code dependency + `cargo metadata` subprocess

---

### 4. C# — The Roslyn Advantage

C# has Roslyn — the official open-source compiler platform from Microsoft. Roslyn is the most powerful static analysis platform of any language on this list. The challenge is that extracting its full power requires project context that may not always be available.

#### Tool Options

| Tool | Semantic Depth | Dependencies | Needs Project File? | Deployment |
|------|---------------|--------------|--------------------|----|
| **Roslyn SyntaxTree** | Syntax only | `Microsoft.CodeAnalysis.CSharp` NuGet | No | Self-contained .NET binary |
| **Roslyn SemanticModel** | Full type resolution | Same + MSBuild/NuGet | Yes (for full fidelity) | Needs .NET SDK on target |
| Roslyn ad-hoc compilation | Partial (BCL types only) | Same | No | Self-contained .NET binary |
| tree-sitter-c-sharp | Syntax only | C library | No | Small binary |
| Mono.Cecil | IL-level (compiled assemblies) | NuGet | Needs `dotnet build` first | .NET binary |
| NDepend | Everything | Commercial license | Yes | Windows-centric |

#### Recommended Approach: Roslyn syntax-only (primary), ad-hoc compilation (enhancement), MSBuild workspace (optional full fidelity)

**Three-tier architecture:**

**Tier 1 — Syntax-only (`CSharpSyntaxTree.ParseText()`):**
- Parses any `.cs` file as a standalone string — no project file needed
- Zero setup, fast (milliseconds per file), fault-tolerant (Roslyn's parser is error-recovering)
- This is the equivalent of Python's `ast.parse()` — works on any source text

**Tier 2 — Ad-hoc compilation with BCL references:**
- Create a `CSharpCompilation` from all parsed syntax trees + the .NET runtime assemblies
- Resolves standard library types (`string`, `int`, `Task`, `List<T>`, LINQ, etc.)
- NuGet types appear as `ErrorType` — accepted, not crashed on
- Gets you partial type resolution, basic inheritance chains within the codebase

**Tier 3 — MSBuild workspace (if .NET SDK is available):**
- `MSBuildWorkspace.Create().OpenProjectAsync("Foo.csproj")`
- Full type resolution including NuGet packages
- Requires `dotnet restore` to have been run
- 10-30 seconds for a large solution

**Signal extraction by tier:**

| xray Signal | Tier 1 (Syntax) | Tier 2 (Ad-hoc) | Tier 3 (MSBuild) |
|-------------|----------------|-----------------|------------------|
| Code skeleton | Full declarations with written types | + resolved `var` types | + NuGet types resolved |
| Complexity | Branch counting | Same | Same |
| Type annotations | As written (including `var` = unknown) | `var` resolved for BCL types | All types resolved |
| Import graph | `using` directives | Same | + actual symbol usage |
| Call graph | Syntactic method names (ambiguous) | Partially resolved | Fully resolved |
| Side effects | Pattern matching on I/O call names | + type-based detection | + full `IDisposable` tracking |
| Attributes | `[AttributeName]` as text | + resolved attribute types | Same |
| Async patterns | `async`/`await` keywords | + Task type resolution | Same |
| Nullable analysis | `?` annotation syntax | Partial flow analysis | Full flow analysis |
| Data models | Class/record/struct declarations | + inheritance within codebase | + EF entity relationships |
| Entry points | `static void Main`, `[ApiController]`, `Program.cs` top-level | Same | + full ASP.NET routing |
| LINQ patterns | Query syntax and method syntax | Same | + resolved extension methods |
| Partial classes | Each fragment separately | Merged within source files | Fully merged including generated |

#### The Source Generator Problem

Modern C# makes heavy use of source generators — compile-time code generation that produces `.cs` files:
- `System.Text.Json` generates serialization code
- `Microsoft.Extensions.Logging` generates logging methods
- ASP.NET generates endpoint routing
- gRPC generates client/server stubs
- Regex source generator produces optimized matchers

**Impact:** A syntax-only scan of a modern ASP.NET app may miss 10-30% of the type surface. For a console app or class library, the gap is 0-5%.

**Mitigation:** Tier 3 (MSBuild workspace) runs source generators automatically. For Tiers 1-2, flag `partial class` declarations as potentially incomplete and note which source generator attributes are present (e.g., `[GeneratedRegex]`, `[JsonSerializable]`).

#### Additional C#-specific signals worth extracting:

- **Nullable reference type annotations** (`string?` vs `string`, `#nullable enable`)
- **Record types** (C# 9+) — immutable data models with value equality
- **Primary constructors** (C# 12) — constructor parameters on the type declaration
- **Pattern matching** (`is`, `switch` expressions with patterns) — affects complexity metrics
- **Extension methods** — invisible at call sites in syntax-only mode (look like instance methods)
- **`IDisposable` / `using` patterns** — resource management signals
- **Dependency injection registration** (in `Startup.cs` / `Program.cs`) — wiring map

#### Deployment

```bash
# Build self-contained single-file binary
dotnet publish -r linux-x64 --self-contained -p:PublishSingleFile=true -o ./out

# Run (no .NET runtime needed on target for syntax-only)
./out/xray-csharp /path/to/csharp/project

# Full fidelity mode (needs .NET SDK for MSBuild)
./out/xray-csharp --full /path/to/csharp/project
```

Binary size: ~30-50 MB self-contained (syntax-only), ~100-150 MB (with MSBuild support).

#### Effort Estimate

- `SyntaxAnalyzer.cs`: ~1,000 lines (skeleton + complexity + attributes + async + nullable + patterns)
- `ImportAnalyzer.cs`: ~400 lines (using directives, namespace structure, .csproj parsing)
- `CallAnalyzer.cs`: ~400 lines (invocation extraction, cross-file matching)
- `SemanticEnhancer.cs`: ~500 lines (ad-hoc compilation setup, type resolution)
- Total: **~2,300 lines of C#**, `Microsoft.CodeAnalysis.CSharp` as primary dependency

---

### 5. COBOL — The Hard Case

COBOL is a genuinely different beast. The difficulty isn't the language itself (it's syntactically verbose but structurally simple) — it's the ecosystem: dialect fragmentation, preprocessor complexity, and environmental coupling to mainframe subsystems (JCL, DB2, CICS, IMS).

That said, for structural extraction, COBOL is more tractable than most people assume. Its rigidity and verbosity actually make pattern-based parsing viable.

#### Tool Options

| Tool | Parse Quality | Dependencies | COPY Resolution | Dialect Coverage |
|------|--------------|--------------|-----------------|-----------------|
| **Custom regex/pattern parser** | 85-90% | Zero | Manual (if copybooks available) | Configurable |
| **ANTLR COBOL 85 grammar** | 90-95% | ANTLR runtime | Java preprocessor available | COBOL 85 + some IBM |
| **tree-sitter-cobol** | 85-90% | C library | No | COBOL 85 core |
| **GnuCOBOL preprocessor** (`cobc -E`) | N/A (preprocessor only) | GnuCOBOL installation | Yes (primary value) | COBOL 85 + IBM/MF extensions |
| Eclipse Che4z COBOL LSP | 95%+ | Java + LSP | Yes (incl. mainframe) | IBM Enterprise COBOL |
| Micro Focus Enterprise Analyzer | 99% | Commercial license | Yes | All major dialects |

#### Why Regex/Pattern Parsing is Viable for COBOL

Unlike modern languages where metaprogramming, closures, and complex expressions make regex parsing hopeless, COBOL has properties that make line-by-line extraction practical:

- **Fixed-format structure:** Columns 1-6 are sequence numbers, column 7 is an indicator (`*` = comment, `-` = continuation), columns 8-72 are code. This is a machine-readable format by design.
- **Explicit division headers:** `IDENTIFICATION DIVISION.`, `ENVIRONMENT DIVISION.`, `DATA DIVISION.`, `PROCEDURE DIVISION.` are unambiguous markers.
- **Rigid data declarations:** Level numbers (01-49, 66, 77, 88) with PIC clauses follow strict patterns: `01 CUSTOMER-RECORD.` then `05 CUST-NAME PIC X(30).`
- **Simple control flow keywords:** `PERFORM`, `CALL`, `GO TO`, `IF`/`EVALUATE` — all keyword-initiated, period-terminated.
- **No expressions with operator precedence** (mostly). `COMPUTE` has arithmetic but structural analysis doesn't need to parse it.

#### Recommended Approach: Custom regex parser (primary), GnuCOBOL preprocessing (optional enhancement)

**Phase 1 — Column handler and preprocessor:**
```
1. Detect format (fixed vs free) from >>SOURCE FORMAT directive or heuristics
2. Strip columns 1-6 (sequence numbers) and 73-80 (identification area)
3. Check column 7: '*' or '/' = comment, '-' = continuation, 'D' = debug
4. Join continuation lines
5. Normalize to single logical lines
```

**Phase 2 — Division splitting and per-division extraction:**

| COBOL Division | Extractable Signals | Regex Reliability |
|---------------|--------------------|--------------------|
| **IDENTIFICATION** | Program name, author, date | 95%+ |
| **ENVIRONMENT** | SELECT/ASSIGN (file → physical name), SPECIAL-NAMES | 95%+ |
| **DATA** | Level hierarchies, PIC clauses, USAGE, REDEFINES, OCCURS, 88-level conditions, FD/SD entries, WORKING-STORAGE vs LINKAGE vs LOCAL-STORAGE | 90%+ |
| **PROCEDURE** | Paragraph/section names, PERFORM targets, CALL targets, GO TO targets, EXEC SQL/CICS blocks, IF/EVALUATE nesting | 85-90% |

**What the regex approach handles well:**

| xray Signal Equivalent | COBOL Extraction | Reliability |
|----------------------|-----------------|-------------|
| Code skeleton | Paragraph/section names, CALL interface (LINKAGE SECTION) | 90%+ |
| Complexity | Count IF/EVALUATE/PERFORM UNTIL nesting depth | 85% |
| Data models | Level-number hierarchies with PIC clauses = complete data layout | 90%+ |
| Import graph | COPY statement dependencies (copybook names) | 95%+ |
| Call graph | PERFORM paragraph targets + CALL program targets | 85-90% |
| File I/O | SELECT/ASSIGN + FD entries = complete file map | 95%+ |
| Side effects | EXEC SQL (DB), EXEC CICS (transaction), CALL (external), file I/O verbs (READ/WRITE/REWRITE/DELETE) | 90%+ |
| Entry points | PROCEDURE DIVISION header, ENTRY statements | 95%+ |
| External dependencies | EXEC SQL tables/views, CALL program names | 85% |
| Condition names | 88-level items (business rule flags) | 95%+ |

**What the regex approach struggles with:**

- **Inline PERFORM blocks** — `PERFORM ... END-PERFORM` requires scope tracking beyond simple regex
- **Nested IF/EVALUATE** — Counting nesting depth requires a simple state machine
- **COPY REPLACING** with complex patterns — Textual substitution logic
- **PERFORM THRU** — Control flow depends on paragraph ordering in source, not just the target name
- **Reference modification** — `FIELD(start:length)` inside expressions
- **Continuation of string literals** across lines

**GnuCOBOL enhancement (Tier 2):**
If GnuCOBOL is installed, `cobc -E program.cbl` produces copybook-expanded source. This solves the hardest problem (COPY resolution) and gives the regex parser cleaner input. Detection: check if `cobc` is on PATH.

#### COBOL-Specific Signals Worth Extracting

These are unique to COBOL and critical for AI orientation in mainframe codebases:

1. **Data hierarchy as a tree.** COBOL's level numbers (01→05→10→15) define a hierarchical data structure analogous to nested structs. This IS the data model — there are no classes.

2. **88-level condition names.** These are named boolean conditions on data items: `88 IS-ACTIVE VALUE 'A'.` They encode business rules directly in the data division.

3. **COPY dependency graph.** Copybooks are shared data structures. Mapping which programs use which copybooks reveals shared data contracts.

4. **PERFORM call graph.** COBOL programs are structured as paragraphs that PERFORM each other. The paragraph call graph IS the control flow — there are no function calls in the modern sense.

5. **EXEC block inventory.** `EXEC SQL`, `EXEC CICS`, `EXEC DLI` blocks reveal what external subsystems the program interacts with. This is the equivalent of import analysis for mainframe dependencies.

6. **File section mapping.** `SELECT file-name ASSIGN TO dd-name` + `FD file-name` defines the program's I/O interface. The `dd-name` connects to JCL, which connects to physical datasets.

7. **WORKING-STORAGE vs LINKAGE.** WORKING-STORAGE is private state; LINKAGE SECTION is the program's public API (parameters received via CALL). This distinction is the closest COBOL has to public/private visibility.

#### Honest Difficulty Assessment

| Aspect | Difficulty | Notes |
|--------|-----------|-------|
| Parsing standard COBOL | Moderate | Verbose but regular syntax |
| Column handling (fixed format) | Easy | 50 lines of code |
| Continuation lines | Easy-Medium | Known algorithm |
| COPY resolution | Medium-Hard | Need copybook paths, REPLACING logic |
| Data division extraction | Easy-Medium | Level numbers are mechanical |
| PERFORM call graph | Medium | Must handle THRU and inline PERFORM |
| EXEC block extraction | Easy | Delimited by EXEC...END-EXEC |
| Dialect differences | Hard | IBM vs Micro Focus vs GnuCOBOL extensions |
| Full complexity metrics | Medium | Requires scope tracking for nesting |
| Overall effort | **Medium-High** | Higher than any modern language due to format handling |

#### Deployment

Since the zero-dep approach is a custom parser, this could be:
- A Python module (extending xray.py directly — COBOL has no Python AST module, but the regex approach is pure Python)
- A standalone script in any language
- Part of the hybrid architecture, producing the same JSON output schema

#### Effort Estimate

- `cobol_parser.py`: ~600 lines (column handling, continuation joining, division splitting)
- `cobol_data_analysis.py`: ~500 lines (level hierarchies, PIC parsing, 88-levels, REDEFINES)
- `cobol_procedure_analysis.py`: ~500 lines (paragraph extraction, PERFORM graph, CALL targets)
- `cobol_environment_analysis.py`: ~200 lines (SELECT/ASSIGN, EXEC blocks, file descriptions)
- Total: **~1,800 lines of Python**, zero external dependencies

---

## Cross-Cutting Concerns

### The Shared Output Schema

All language frontends should produce the same JSON intermediate format that feeds into the existing markdown/JSON formatters. The schema maps naturally:

```json
{
  "files": {
    "path/to/file.ext": {
      "line_count": 250,
      "language": "go",
      "structures": [
        {
          "kind": "function|method|class|struct|interface|trait|enum|paragraph",
          "name": "ProcessOrder",
          "signature": "func ProcessOrder(ctx context.Context, order *Order) error",
          "visibility": "public",
          "line": 42,
          "complexity": 8,
          "is_async": false,
          "decorators_or_attributes": ["#[test]", "[HttpGet]"],
          "side_effects": ["db", "file"],
          "parameters": [...],
          "return_type": "error"
        }
      ],
      "imports": ["fmt", "net/http", "internal/models"],
      "data_models": [...],
      "constants": [...]
    }
  },
  "dependency_graph": { "edges": [...], "layers": [...], "circular": [...] },
  "call_graph": { "edges": [...], "fan_in": {...}, "fan_out": {...} },
  "entry_points": [...],
  "concurrency_patterns": { "goroutines": [...], "channels": [...], "async_functions": [...] }
}
```

This schema is language-agnostic but extensible. Language-specific fields (e.g., `unsafe_blocks` for Rust, `level_hierarchy` for COBOL) live under a `language_specific` key that formatters can optionally render.

### The tree-sitter Fallback Strategy

For languages where building a dedicated scanner isn't justified (low demand or niche languages), tree-sitter provides a "good enough" universal fallback:

- tree-sitter has grammars for 100+ languages
- Python bindings exist (`pip install tree-sitter`)
- Syntax-only but consistent API across languages
- Error-tolerant (produces partial trees for broken files)

This could be a `--language auto` mode that uses tree-sitter for any language without a dedicated frontend. Quality: ~60-70% of the signals, but better than nothing.

### Git Analysis is Already Language-Agnostic

The existing `git_analysis.py` module (risk scores, co-modification coupling, freshness, author expertise) works on file paths and git history — it doesn't parse code. This module works unchanged for any language.

### Test Detection Needs Language-Specific Patterns

| Language | Test File Patterns | Test Function Patterns |
|----------|-------------------|----------------------|
| Python | `test_*.py`, `*_test.py` | `def test_*`, `class Test*` |
| Go | `*_test.go` | `func Test*(t *testing.T)`, `func Benchmark*` |
| TypeScript | `*.test.ts`, `*.spec.ts`, `__tests__/` | `describe()`, `it()`, `test()` |
| Rust | `#[cfg(test)] mod tests`, `tests/` dir | `#[test] fn test_*` |
| C# | `*.Tests.csproj`, `*Tests.cs` | `[Test]`, `[Fact]`, `[Theory]`, `[TestMethod]` |
| COBOL | No standard convention | N/A (tested via JCL job streams) |

---

## Implementation Roadmap

### Phase 1: Go Scanner (Highest ROI, Lowest Risk)
- **Why first:** Best stdlib tooling, simplest type system, zero-dep binary, growing demand
- **Scope:** Full signal parity with Python scanner using `go/ast`
- **Timeline driver:** ~1,700 lines of Go
- **Deliverable:** `xray-go` binary that produces JSON feeding into existing formatters

### Phase 2: TypeScript Scanner (Largest User Base)
- **Why second:** Biggest user base (TypeScript/JavaScript are the most common languages in many orgs), single well-understood dependency (`typescript` npm package)
- **Scope:** Syntax-only tier + optional semantic tier via `ts.createProgram()`
- **Timeline driver:** ~2,200 lines of JS/TS
- **Deliverable:** `xray-ts` Node.js tool or bundled binary

### Phase 3: Rust Scanner (Growing Demand)
- **Why third:** Growing systems-programming adoption, `syn` is a strong foundation, macro opacity is manageable
- **Scope:** Syntax extraction via `syn` + `cargo metadata` for dependency graphs
- **Timeline driver:** ~2,300 lines of Rust
- **Deliverable:** `xray-rust` static binary

### Phase 4: C# Scanner (Enterprise Demand)
- **Why fourth:** Large enterprise user base, Roslyn is powerful but deployment is heavier
- **Scope:** Three-tier approach (syntax → ad-hoc compilation → MSBuild)
- **Timeline driver:** ~2,300 lines of C#
- **Deliverable:** `xray-csharp` self-contained .NET binary

### Phase 5: COBOL Scanner (Niche but Unique Value)
- **Why last:** Smallest user base, but AI-assisted COBOL comprehension has outsized value (millions of lines of underdocumented mainframe code). This is where repo-xray could be genuinely transformative — no other tool does this.
- **Scope:** Regex/pattern parser in Python, optional GnuCOBOL enhancement
- **Timeline driver:** ~1,800 lines of Python
- **Deliverable:** `xray-cobol` Python script or module integrated into existing `xray.py`

### Cross-Phase Work
- Define and stabilize the cross-language JSON output schema (before Phase 1)
- Refactor markdown formatter to accept language-agnostic JSON (during Phase 1)
- Add `--language` flag to the main `xray.py` entry point that dispatches to the appropriate scanner (Phase 2+)
- tree-sitter fallback mode for unsupported languages (Phase 3+)

---

## Comparative Summary

### Static Analysis Quality by Language

How much of the code's "truth" can a syntax-only scanner capture?

| Language | Syntax-Only Coverage | Why |
|----------|---------------------|-----|
| **Go** | ~90% | No macros, explicit types everywhere, simple module system |
| **Python** | ~85% | Dynamic typing means types are often unknown; decorators/metaclasses generate code |
| **TypeScript** | ~75% | `type` inference means many types are invisible; decorators and build transforms |
| **C#** | ~70% | `var` inference, source generators, partial classes, extension methods |
| **Rust** | ~70% | Macro-generated code invisible, trait dispatch unresolvable, generics opaque |
| **COBOL** | ~85% | What you see is what you get — no metaprogramming, but COPY inclusion is a gap |

### Dependency Weight

| Language | Scanner Written In | External Dependencies | Runtime Requirement |
|----------|-------------------|----------------------|-------------------|
| Go | Go | None (stdlib only) | None (static binary) |
| TypeScript | JavaScript | `typescript` (npm) | Node.js |
| Rust | Rust | `syn` (crate) | None (static binary) |
| C# | C# | `Microsoft.CodeAnalysis` (NuGet) | None (self-contained publish) or .NET runtime |
| COBOL | Python | None | Python 3.8+ |
| Python (current) | Python | None (stdlib only) | Python 3.8+ |

### The Honest Take

**Go is the slam dunk.** Best tooling, simplest language, zero dependencies, highest analysis quality. Build this first.

**TypeScript is the highest impact.** Largest potential user base, well-understood tooling, single dependency. Build this second.

**Rust is doable but imperfect.** The macro gap is real but manageable. The `syn` crate is excellent. Worth building for the growing Rust ecosystem.

**C# is powerful but heavy.** Roslyn gives you everything if you can accept the .NET dependency. The three-tier approach makes it practical. Enterprise demand justifies the effort.

**COBOL is the sleeper.** Tiny user base but massive untapped value. Millions of lines of critical mainframe code with no modern tooling for AI-assisted comprehension. A COBOL scanner, even at 85% accuracy, would be genuinely novel and valuable. The regex approach is unsexy but practical — and it's how most real-world COBOL analysis tools started.

**The tree-sitter universal fallback** handles everything else (Java, Ruby, PHP, Swift, Kotlin...) at 60-70% quality. Not great, not terrible, better than nothing. Good enough for the long tail of languages.

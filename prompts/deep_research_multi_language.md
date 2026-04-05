# Deep Research Prompt: Multi-Language Scanner Feasibility Analysis

## Objective

Produce a comprehensive feasibility and usefulness analysis for extending repo-xray's deterministic AST-based scanning model to 8 specific languages: **AcuCobol, JavaScript, SQL, Java, C++, C, Swift, and Kotlin**. The output should be structured to directly expand the existing research document at `MULTI_LANGUAGE_RESEARCH.md`.

## Background Context

repo-xray is a Python codebase analyzer that extracts 42+ structural signals from AST, import graph, git history, and code patterns in a single deterministic pass. It runs in 5 seconds on 500 files with zero external dependencies (Python 3.8+ stdlib only). The scanner output feeds an optional LLM-powered deep investigation layer that produces comprehensive AI onboarding documents.

### What the scanner extracts (the signal set to replicate per language)

1. **Code skeletons** — function/class/method signatures with parameter names and types
2. **Cyclomatic complexity** — per-function branch counting (if/for/while/switch/catch/boolean ops)
3. **Type annotation coverage** — percentage of functions with explicit type information
4. **Import/dependency graph** — module dependency edges, circular deps, orphans, hub modules, layer classification
5. **Cross-module call graph** — who calls what across files, fan-in/fan-out, reverse lookup, impact ratings
6. **Side effect detection** — DB, API, file I/O, subprocess, environment mutations flagged by pattern matching
7. **Security concerns** — exec/eval/compile equivalents (code injection vectors)
8. **Silent failures** — empty catch blocks, catch-and-swallow patterns
9. **Async/concurrency patterns** — async functions, blocking-in-async violations, concurrency primitives
10. **Decorator/annotation inventory** — framework markers (@Route, @Injectable, @Test, etc.)
11. **Data model extraction** — structs, classes, interfaces, enums with field information
12. **Entry point detection** — main functions, CLI handlers, HTTP routes, event handlers
13. **Git risk scores** — churn, co-modification coupling, freshness, author entropy (language-agnostic, already implemented)
14. **Test coverage mapping** — which modules have tests, test patterns
15. **Tech debt markers** — TODO/FIXME/HACK comments (language-agnostic, already implemented)
16. **SQL string detection** — raw query patterns in string literals
17. **Deprecation markers** — deprecated annotations, comments, compiler warnings

### Design constraints that MUST be preserved

- **Deterministic** — same input, same output, every time. No LLM calls during scanning.
- **Fast** — target 5 seconds for 500 files. If a language's tooling makes this impossible, document why and what the realistic floor is.
- **Minimal dependencies** — ideally zero external deps (like Python's stdlib `ast` module). If impossible, document the minimum viable dependency and its size/stability.
- **Fault-tolerant** — one unparseable file must never crash the scan. Partial results always.
- **Syntax-first, semantics-optional** — the Python scanner works from AST alone with no type checker. Semantic analysis (type resolution, call graph precision) should be an optional enhancement tier, not required.

### Architecture already decided

The existing research recommends **Option C: Hybrid** — shared core (git analysis, formatters, config system, output pipeline) with language-specific frontends that produce a standardized JSON intermediate representation. Each language frontend only needs to produce the same JSON structure that Python's `ast_analysis.py`, `import_analysis.py`, and `call_analysis.py` output. The shared backend handles everything else.

### What's already been researched

The existing document covers Go, TypeScript, Rust, C#, and COBOL. For each, it identifies the best parsing tool, dependency model, signal extraction capabilities, key gotchas, deployment model, and effort estimate. **Do not repeat this work.** The 8 languages below are either not covered at all or need distinct treatment from what's there.

---

## Research Deliverables Per Language

For each of the 8 target languages, produce the following sections in this exact structure:

### {Language} — {One-line verdict: "Best Case" / "Feasible with Tradeoffs" / "Challenging but Possible" / "Questionable ROI"}

#### 1. Market Relevance and AI Assistant Value

- **Who uses this language today?** — Industry sectors, company types, codebase sizes, developer population.
- **What does a typical codebase look like?** — Average file count, project structure, build system, package manager.
- **Why would an AI assistant need a scanner for this language?** — What's the cold start problem like? How large are typical codebases? What's the cost of an AI misunderstanding the architecture?
- **Is there competitive tooling already?** — Do existing tools (IDE plugins, linters, SonarQube, etc.) already solve the orientation problem? If so, what gap does repo-xray fill?

#### 2. Parsing Tool Landscape

Produce a comparison table:

| Tool | Type Resolution | Speed | Dependencies | API Stability | Actively Maintained? |
|------|----------------|-------|--------------|---------------|---------------------|
| ... | ... | ... | ... | ... | ... |

For each tool, evaluate:
- Can it parse a single file without project context? (critical for the zero-setup tier)
- Does it handle syntax errors gracefully or crash?
- What's the minimum runtime requirement? (e.g., needs JDK? needs Node? standalone binary?)
- Is the AST well-documented with typed node types, or is it an opaque tree?
- How stable is the API across versions?

**Recommend one tool** with explicit reasoning.

#### 3. Signal Extraction Feasibility Matrix

For ALL 17 signals listed above, rate extraction feasibility:

| Signal | Syntax-Only | With Type Resolution | Language-Specific Notes |
|--------|-------------|---------------------|----------------------|
| Code skeletons | ... | ... | ... |
| Cyclomatic complexity | ... | ... | ... |
| (all 17) | ... | ... | ... |

Use ratings: **Excellent** (direct AST node), **Good** (pattern matching), **Partial** (significant gaps), **Not Applicable** (language doesn't have this concept), **Requires Semantic** (impossible without type checker).

#### 4. Language-Specific Signals to Add

What unique constructs does this language have that matter for AI orientation but don't exist in Python? For each:
- What is it?
- Why does an AI need to know about it?
- How would you detect it (AST node type or pattern)?

#### 5. Key Gotchas and Honest Limitations

- What percentage of useful signals does syntax-only analysis capture vs full semantic analysis?
- What code patterns will the scanner completely miss? (e.g., macros, reflection, code generation, dynamic dispatch)
- What false positive/negative patterns should we expect?
- Are there language idioms that make static analysis particularly hard or easy?

#### 6. Deployment Model

- How would the scanner be distributed? (standalone binary? requires runtime? npm package?)
- What does the user need installed to run it?
- Can it be packaged as a single file/binary with no installation?

#### 7. Effort Estimate

- Estimated lines of code for the language frontend
- Number and size of external dependencies
- Development time estimate (assuming familiarity with the language)
- Maintenance burden (how often do parsing tools break across language versions?)

#### 8. Recommendation

- **Build it?** Yes / Yes with caveats / Not yet / No
- **Priority relative to the other 7 languages in this research**
- **What would change the recommendation?** (e.g., "if tree-sitter adds type resolution", "if the user base requests it")

---

## Language-Specific Research Notes

### AcuCobol

This is the highest-risk, highest-specificity language on the list. Research should cover:
- **Which AcuCobol dialect specifically?** — ACUCOBOL-GT (Micro Focus/Rocket), vs standard COBOL-85, vs COBOL 2002+. What are the syntactic differences that affect parsing?
- **What does an AcuCobol codebase look like?** — Fixed-format vs free-format source, copybook structure, DIVISION/SECTION/PARAGRAPH hierarchy, level numbers (01-49, 66, 77, 88), PERFORM graph.
- **Existing COBOL parsing tools** — GnuCOBOL's parser, Micro Focus tools, open-source COBOL grammars (tree-sitter-cobol, ANTLR grammars), IBM's Z Open Editor. What actually works on AcuCobol dialect?
- **The EXEC block problem** — AcuCobol may embed EXEC SQL, EXEC CICS, or EXEC DL/I blocks. These are separate languages within COBOL source. How do existing parsers handle them?
- **Copybook resolution** — COPY statements are COBOL's #include. They're critical for understanding data structures (FD/01-level hierarchies). Can the scanner resolve them? What happens if copybook paths are environment-dependent?
- **The existing MULTI_LANGUAGE_RESEARCH.md has a section on COBOL** — focus on what's specific to AcuCobol that differs from the general COBOL analysis there.

### JavaScript (distinct from TypeScript)

The existing research covers TypeScript via the TS Compiler API. JavaScript needs separate analysis because:
- **Many JavaScript codebases don't use TypeScript at all** — no tsconfig.json, no type annotations, pure .js/.mjs/.cjs files.
- **What parser works best for plain JS?** — Acorn, Babel parser, espree (ESLint's parser), esprima, tree-sitter-javascript, V8 parser (via Node). Which handles JSX, ES modules, CommonJS, and modern syntax (optional chaining, nullish coalescing, top-level await)?
- **The type information gap** — JavaScript has zero type annotations (unless JSDoc). How much can be inferred from usage patterns? Is JSDoc parsing worth supporting?
- **CommonJS vs ES modules** — `require()` vs `import`. How does this affect dependency graph construction? Can both be detected from syntax?
- **Dynamic dispatch is the norm** — JavaScript is fundamentally dynamic. `obj[method]()`, prototype chains, `apply`/`call`/`bind`. What's the realistic ceiling for static call graph construction?
- **Framework detection** — Express, Next.js, React, Vue, Angular, Nest.js. Each has different entry point patterns, routing conventions, and component structures. How much framework-specific detection is needed?

### SQL

SQL is fundamentally different from the other languages — it's declarative, not procedural. Research should address:
- **What does "scanning a SQL codebase" mean?** — Is it a directory of `.sql` migration files? Stored procedures in a database? Embedded SQL in application code? A dbt project? All of the above?
- **What signals are meaningful?** — Table/view/function definitions, dependency graph (view→table, procedure→table), complexity (nested subqueries, CTE depth), join patterns, index usage hints, migration ordering.
- **Which SQL dialects matter?** — PostgreSQL, MySQL, SQL Server (T-SQL), Oracle (PL/SQL), SQLite. How different are their grammars? Can one parser handle all?
- **Parsing tools** — sqlparse (Python, already stdlib-compatible!), pg_query (libpg_query bindings), ANTLR SQL grammars, sqlfluff, tree-sitter-sql. Which handles the widest dialect range?
- **The stored procedure problem** — PL/pgSQL, T-SQL, PL/SQL are procedural languages that contain SQL. They have variables, control flow, cursors, exception handling. Are these analyzable like regular code?
- **dbt and migration frameworks** — dbt models are SQL with Jinja templating. Alembic/Flyway/Liquibase migrations have ordering dependencies. Should the scanner understand these tools specifically?
- **Cross-language integration** — SQL is almost always embedded in or called from another language. Should the SQL scanner operate standalone or as an enhancement to the Python/Java/etc. scanner?

### Java

- **The JDK's own tools** — `javac` with annotation processing, the Compiler Tree API (com.sun.source.tree), JavaParser (open source), Eclipse JDT, ANTLR Java grammar. Which provides the best AST access with minimal dependencies?
- **Build system complexity** — Maven, Gradle, Ant. How do you resolve dependencies and classpaths without running a full build?
- **Annotations are everything** — Spring, Jakarta EE, JPA, Lombok. Annotations drive code generation and framework behavior. How much can syntax-only analysis capture vs needing annotation processor output?
- **Reflection and dynamic proxies** — Java frameworks (Spring, Hibernate) use reflection extensively. What's invisible to static analysis?
- **Module system** — Java 9+ module system (module-info.java) vs classpath. Does this help or complicate the scanner?
- **Enterprise codebases** — Java projects can be enormous (10K+ files, deep package hierarchies). Performance at scale matters.

### C++

- **The preprocessor problem** — `#include`, `#define`, `#ifdef` transform source before parsing. Does the scanner need to run the preprocessor? What happens if it doesn't?
- **Template metaprogramming** — C++ templates are Turing-complete. Template instantiation is invisible to syntax-only analysis. How much signal is lost?
- **Parsing tools** — Clang's libclang/libtooling (the gold standard), tree-sitter-cpp, ANTLR C++ grammar (known to be incomplete), cppast. What's the minimum viable parser?
- **Header files** — `.h`/`.hpp` files define the public interface but may contain implementation (inline functions, templates). Should they be scanned as separate entities or merged with their `.cpp` files?
- **Build system integration** — CMake, Make, Bazel, MSBuild. `compile_commands.json` is the standard way to tell tools about compiler flags. Is this required?
- **Multiple standards** — C++11, C++14, C++17, C++20, C++23. Each adds syntax (lambdas, concepts, modules, coroutines). Can one parser handle all?

### C

- **Simpler than C++ but still has the preprocessor** — `#include` chains can pull in thousands of lines. `#define` macros can redefine syntax.
- **How is C different from C++ for scanner purposes?** — No classes, no templates, no namespaces, no exceptions. Simpler to parse but the preprocessor is equally problematic.
- **What does a C codebase look like for AI orientation?** — Header-based API, function pointer tables, global state, manual memory management patterns. What signals matter most?
- **Parsing tools** — libclang (same as C++), pycparser (Python, pure parser!), tree-sitter-c, sparse (Linux kernel's checker). Is pycparser sufficient for a zero-dep Python extension?
- **Embedded/systems context** — C is dominant in embedded systems, kernels, firmware. These codebases have unique patterns (register manipulation, interrupt handlers, hardware abstraction layers). Should the scanner detect these?

### Swift

- **Apple ecosystem lock-in** — Swift codebases are almost exclusively iOS/macOS. Is the user base large enough to justify investment?
- **SwiftSyntax** — Apple's official Swift parser library (used by swift-format, swift-lint). Written in Swift, ships with the Swift toolchain. Is this the obvious choice?
- **Protocol-oriented programming** — Swift emphasizes protocols (interfaces) over inheritance. How does this affect call graph construction and architectural analysis?
- **Xcode project structure** — `.xcodeproj`/`.xcworkspace`, Swift Package Manager, CocoaPods, Carthage. How do you resolve dependencies without Xcode?
- **SwiftUI vs UIKit** — Two fundamentally different UI paradigms coexist. Can the scanner distinguish between them? Does it matter for orientation?
- **Concurrency** — Swift's structured concurrency (async/await, actors, task groups) is relatively new. How does it compare to Python's asyncio for analysis purposes?

### Kotlin

- **Dual ecosystem** — Kotlin runs on JVM (Android, server-side) and Kotlin/Native and Kotlin/JS. Which targets matter?
- **KAPT and KSP** — Kotlin's annotation processing tools generate code. Same problem as Java annotations but with Kotlin-specific patterns.
- **Kotlin compiler plugins** — The Kotlin compiler has a plugin API. Can it be used for analysis? Is it stable?
- **Parsing tools** — Kotlin compiler's PSI (Program Structure Interface), tree-sitter-kotlin, ANTLR Kotlin grammar, kotlinx.ast. Which provides the best standalone AST access?
- **Coroutines** — Kotlin's coroutines are suspension-based. `suspend fun`, `launch`, `async`, `Flow`. How does this compare to Python's async for analysis?
- **Android-specific patterns** — Activities, Fragments, ViewModels, Compose. These are the architectural primitives for Android apps. Should the scanner detect them?
- **Interop with Java** — Kotlin compiles to JVM bytecode and interops seamlessly with Java. Should the Kotlin scanner also analyze Java files in the same project?

---

## Cross-Language Analysis

After the per-language sections, produce:

### Priority Ranking

Rank all 8 languages by: `(market_demand × feasibility × signal_quality) / effort`. Show the formula inputs and final ranking.

### Shared Infrastructure Opportunities

What can be shared across all language frontends?
- Which signals are truly language-agnostic? (git analysis, tech debt markers, file discovery)
- What's the minimal JSON intermediate representation schema?
- Can tree-sitter serve as a universal fallback for languages without better tooling?

### The "80% Scanner" Concept

For each language, estimate what percentage of Python xray's signal quality is achievable with:
- Syntax-only analysis (no type checker, no project context)
- Syntax + project metadata (package.json, Cargo.toml, pom.xml, etc.)
- Full semantic analysis (type checker, resolved dependencies)

### Implementation Roadmap

Suggest a phased rollout order with rationale. Which languages first? What's the MVP for each?

---

## Output Format

Structure the response as a markdown document that can be directly appended to or merged with the existing `MULTI_LANGUAGE_RESEARCH.md`. Use the same heading hierarchy (##, ###, ####), same table formatting, and same assessment style (honest about limitations, quantified where possible, with specific tool names and version numbers).

Total expected length: 8,000-12,000 words.

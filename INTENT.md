# INTENT

## Why This Exists

AI coding assistants are powerful but context-limited. A codebase might span 2 million tokens. A context window holds 200K. The assistant cannot read everything, yet must understand the architecture to work effectively.

This creates a bootstrapping problem: the assistant needs to understand the architecture to know what to read, but needs to read to understand the architecture.

repo-xray exists to break that loop. It gives the AI a map before it starts exploring.

## The Problem We're Solving

When a fresh AI agent is dropped into an unfamiliar codebase, it does one of two things: it reads files at random and wastes context on implementation details, or it reads nothing and guesses. Both lead to confident, plausible, wrong suggestions.

The cost of this isn't the bad suggestion itself — it's the compounding effect. A wrong mental model early in a session infects every subsequent decision. An agent that misidentifies the architectural style will write code that technically works but fights the existing design. An agent that doesn't know about a shared cache will introduce a subtle concurrency bug. An agent that doesn't know which files are generated will waste half its context reading code no human wrote.

We are solving the cold start problem: getting an AI from "I know nothing" to "I know where to look and what to be careful about" in the fewest tokens possible.

## What Success Looks Like

A fresh Claude instance reads our output and can immediately:

- Navigate to the right file for any given task without trial and error
- Avoid the files that would waste its context
- Understand why the code is structured the way it is, not just how
- Make changes that are consistent with the existing design
- Anticipate what might break before it breaks

The measure isn't "how much does the AI know" — it's "how many files does the AI need to open before it's confident enough to act safely." Every file-read we eliminate through better onboarding is context freed up for actual work.

## What This Is NOT

This is not a documentation generator. We don't produce docs for humans to read. The output is optimized for machine consumption — dense, structured, actionable.

This is not a linter, a code quality tool, or a refactoring assistant. We don't judge the code. We describe it accurately so that something else can make good decisions about it.

This is not a replacement for reading code. It's a guide for reading code *efficiently*. The AI will still need to open files. We just make sure it opens the right ones first.

## The Two-Layer Design

The project has two distinct layers with deliberately different properties:

**Layer 1: The Scanner (xray.py)**

Deterministic. Fast. Zero dependencies. Zero API calls. Produces the same output every time for the same input. Runs in 5 seconds on a 500-file codebase. This is the map.

We chose determinism over intelligence here on purpose. The scanner runs frequently — on every commit in CI, before every analysis session, as a quick check. It cannot be flaky, slow, or expensive. It sacrifices depth for reliability.

The scanner extracts 49+ signals from the AST, import graph, git history, and code patterns. It doesn't interpret these signals — it just surfaces them. Interpretation is the agent's job.

**Layer 2: The Agents (deep_crawl, repo_xray)**

LLM-powered. Expensive. Non-deterministic. Uses the scanner's output as a map to guide intelligent investigation. Reads actual code, verifies signals, discovers things the scanner can't see (behavioral semantics, implicit assumptions, counterintuitive gotchas).

This layer exists because a map is not understanding. The scanner can tell you that a function has cyclomatic complexity 25 and is called from 8 modules. It cannot tell you whether that complexity is essential business logic or accidental tech debt. It cannot tell you that the function silently swallows timeout errors. It cannot tell you that changing it will break an undocumented integration. Only reading the code can tell you that.

The deep_crawl agent is designed to spend unlimited tokens during generation to produce a comprehensive, maximally useful onboarding document. The economics work because the document is read by many future sessions — the generation cost is amortized. We deliberately removed the token budget constraint from generation because optimizing for cheap generation at the expense of output quality is a false economy when the output will be read hundreds of times.

## Design Decisions That Were Hard

**Why AST-only and not runtime analysis for the scanner.**
We considered adding pytest tracing, coverage integration, and runtime type capture. Each would produce more accurate data. We rejected them because they add dependencies, require a working test suite, take minutes instead of seconds, and produce non-deterministic output. The scanner's value is that it works on any codebase with zero setup (Python) or minimal setup (TypeScript — requires Node.js). Requiring a passing test suite would cut our addressable use cases in half. Runtime analysis belongs in the agent layer, not the scanner.

**Why the onboarding document is for AI, not humans.**
Early versions tried to serve both audiences. The result was a document that was too verbose for AI (wasting context tokens on prose that helps humans but not machines) and too structured for humans (tables and compact notation that machines parse easily but humans find cold). We chose the AI audience because that's where the leverage is — a human can read code directly, but an AI's ability to work effectively is bottlenecked by what fits in context. Optimizing for the constrained consumer matters more.

**Why investigation targets in the scanner output.**
The scanner was originally pure observation — here are the signals, do what you want with them. We added investigation targets (ambiguous interfaces, coupling anomalies, high-uncertainty modules) because without them, the crawl agent wastes significant time deciding what to investigate. The scanner can cheaply compute "this function is probably confusing" from name genericity and type coverage. Surfacing that as a prioritized list makes the expensive crawl agent 2-3x more efficient. It's still deterministic — just a more opinionated view of the same data.

**Why the onboarding document is delivered via CLAUDE.md, not read on demand.**
An agent that has to know to look for the onboarding document will sometimes not look for it. An agent that receives it automatically in system context always has it. The 10-20K token cost of auto-loading is less than the cost of a single session where the agent works without orientation. Prompt caching reduces the ongoing cost to near zero after the first session.

## Scope Boundaries

**We analyze Python and TypeScript/JavaScript.** The Python scanner uses Python's `ast` module; the TypeScript scanner uses the TypeScript compiler API (`ts.createSourceFile`). Each is a self-contained implementation — they share no code, only the output JSON schema (`XRayResults`). `xray.py` detects the project language and delegates to the appropriate scanner, then runs language-agnostic git analysis and investigation target computation on top. The agent layer, formatters, and onboarding document format are fully language-agnostic — a future scanner for Rust or Go would plug into the same pipeline by producing the same JSON shape.

**We don't modify code.** We observe, analyze, and document. We never suggest refactoring, never auto-fix, never change a file. Our output is read-only intelligence for something else to act on.

**We don't replace human judgment about intent.** The scanner can extract what the code does. The crawl agent can infer behavioral patterns. Neither can know *why* the code was written this way. That context — business constraints, historical decisions, future plans — must come from humans. This is why INTENT.md exists as a human-written document alongside our machine-generated ones.

## The Tradeoffs We Accept

**Compression loses information.** A 2M-token codebase compressed to 15K tokens loses 99.25% of its content. We accept this because the alternative — no compression — means the AI can't see any of it. The goal is not completeness. It's maximum useful information per token.

**Unrestricted mode validates the compression tradeoff.** The deep crawl pipeline can run without token budget ceilings to measure how much useful content exists before compression. This is essential for calibrating budget targets: you can't know the right ceiling without first seeing the unrestricted output. Unrestricted mode removes all `target_tokens` and `max_tokens` constraints, all per-section budget comments in templates, and the Phase 4 trim step — replacing "compress to budget" with "include everything that's not redundant with information derivable from file names and signatures." The investigation protocols, evidence standards, validation pipeline, and quality checks remain identical. The only variable is output size.

**Deterministic extraction misses semantic meaning.** The scanner doesn't know that `process()` orchestrates the entire order lifecycle. It just knows it has CC=25 and 8 callers. We accept this because semantic understanding requires LLM inference, which belongs in the agent layer, not the scanner.

**The onboarding document can go stale.** Code changes but the document stays the same until someone runs a refresh. We accept this because a slightly stale onboarding document is better than no onboarding document. The refresh mechanism and git hash tracking mitigate the risk.

**Agent-generated analysis is non-deterministic.** Two crawl runs on the same codebase will produce different documents. We accept this because the value comes from the investigation and synthesis, not from reproducibility. The scanner provides the reproducible foundation; the agent provides the intelligence.

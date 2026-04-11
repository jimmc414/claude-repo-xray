# Adversarial Review: X-Ray + Deep Crawl Pipeline Output Quality

**Target codebase:** Kosmos — 802 files, ~2.5M tokens, autonomous AI scientist
**Evaluation lens:** What does an AI agent need to fix bugs, add features, and refactor?
**Artifacts reviewed:** xray.md (1,668 lines), R14 DEEP_ONBOARD (57,727 words), Current DEEP_ONBOARD (61,189 words)
**Date:** 2026-04-10

---

## Part 1: The X-Ray Scan

### What Works

The xray.md output has genuine value in three areas:

**Architectural pillars table** — identifying that `logging.py` has 140 importers and `config.py` has risk 0.96 directly prevents breaking changes. An agent about to edit config.py sees "danger" before touching it.

**Hidden coupling analysis** — co-change data (`config.py` ↔ `anthropic.py`: 5 co-changes, no import relationship) captures coupling that static analysis misses. This is information an agent literally cannot derive from grep.

**Circular dependency detection** — the two cycles (`llm.py` ↔ `anthropic.py`, `world_model` ↔ `artifacts`) are critical for any refactoring task. Worth the tokens.

### What's Low-Value or Useless

**Data Models section (204 lines): ~85% noise.** Claims "192 Pydantic/dataclass models found" but shows ~20 arbitrary examples. An agent needing a specific model would grep `class.*BaseModel` in 0.2 seconds. The 20 examples provide no grouping, no relationships, no context for why these 20 were selected. Dead weight.

**Import layer tables (62 lines): ~90% noise.** Lists every module's import count. An agent asking "who imports logging?" runs grep faster than scanning a table. Only the top 5-10 by criticality matter; the remaining 84 modules are padding.

**Decorator usage tallies (11 lines): ~95% noise.** Knowing there are "509 @patch decorators" is trivia. What matters is whether @patch is over-mocking — the count tells you nothing actionable.

**Entry points table (65 lines): ~80% noise.** Redundant with `grep -r "^def main():" kosmos/`. Lists main() functions in files an agent would find by convention.

**Class skeletons (258 lines): misleading.** Shows ResearchDirectorAgent has 50+ methods but with signatures truncated to `def _research_plan_context(...)`. No arguments, no return types, no docstrings. Then "... and 44 more methods." The skeleton is incomplete enough to be dangerous — agent thinks it has the interface but is missing 88% of it.

### What's Critically Missing

**No behavioral context at any level.** Xray tells you `get_client()` exists in `llm.py`. It does not tell you:
- It uses double-checked locking with `threading.Lock`
- The first call has initialization latency
- It returns different clients based on provider config
- The circular import with `anthropic.py` exists because of lazy initialization

An agent reading xray.md sees a skeleton. An agent modifying `get_client()` needs the behavioral facts above. The skeleton saves zero file reads for any non-trivial task.

**No error recovery patterns.** `research_director.py` has `MAX_CONSECUTIVE_ERRORS = 3` and `ERROR_BACKOFF_SECONDS = [2, 4, 8]` — critical constants for any agent working with the research loop. Xray doesn't extract them. The silent failures section lists broad `except:` patterns but not recovery strategies.

**No state lifecycle.** Config, world model, cache, database engine — all are singletons with initialization order dependencies. Xray lists them as "module-level mutables" but doesn't explain: if you reset config, what breaks? What initializes first? What depends on what? An agent adding a new singleton needs this; xray provides none of it.

**No data flow across boundaries.** Xray shows imports and call sites but not data movement. How does a research question flow from CLI → ResearchDirectorAgent → HypothesisGenerator → database? Where is it validated? Where is it serialized? Where do assumptions break if the type changes? This is the #1 information need for feature work, and xray provides zero coverage.

**No provider abstraction documentation.** An agent adding OpenRouter support needs: the provider interface (base.py), required methods, async requirements, config wiring, type signatures. Xray identifies `providers.base` as critical (124 affected modules) but provides none of the interface details. The agent must read 3-4 source files to reverse-engineer what xray could have extracted from AST alone.

### Failure Scenarios Where Xray Actively Misleads

**Scenario: "Fix the circular dependency between llm.py and anthropic.py."** Xray says "circular dependency exists" — 3 words. Agent must still read both files completely to understand *why* it exists, *what specific imports* create it, and *whether* it can be broken without restructuring initialization. The xray entry creates a false sense that the problem is understood when only the symptom is documented.

**Scenario: "Add a new LLM provider."** Xray shows the provider directory exists and `base.py` is important. But without the interface contract (required methods, async patterns, config registration), an agent attempting this from xray alone would produce code that compiles but doesn't integrate. The skeleton view for base.py truncates the exact methods the agent needs.

**Scenario: "Optimize World Model queries."** Xray lists `Neo4jWorldModel` as a class with 13+ methods. No query patterns, no performance characteristics, no schema information. Agent has zero insight into what's slow or why.

### Xray Verdict

**40% useful, 60% padding.** The genuinely valuable content (pillars, hotspots, coupling, circular deps) occupies ~300 lines. The remaining 1,368 lines are information an agent could derive faster from grep/LSP, or information so incomplete it requires reading source anyway. The core problem: xray documents *structure* but agents need *behavior* to act.

---

## Part 2: The Deep Crawl

### R14 vs Current — Where Quality Decreased

#### Gotcha Severity Calibration (R14: 4.8 → Current: 4.5)

R14 reserved CRITICAL for genuinely active production problems: dead message routing, unwired safety checks. It had 2 CRITICAL gotchas out of 91 total (2.2%).

The current version's severity labels are misaligned with actual impact. An audit of sampled HIGH gotchas reveals 5 that should be CRITICAL:

| Gotcha | Current Label | Should Be | Why |
|--------|--------------|-----------|-----|
| Unrestricted `exec()` fallback | HIGH | CRITICAL | Arbitrary code execution without sandbox |
| Silent sandbox downgrade (Docker unavail) | HIGH | CRITICAL | Security degrades without caller knowledge |
| SafetyGuardrails NOT wired into executor | HIGH | CRITICAL | Safety mechanism is dead code |
| `config.openai` can be None at access | HIGH | CRITICAL | Production crash on attribute access |
| Cypher injection via f-strings | HIGH | CRITICAL | Database injection possible |

The document conflates "rare" with "low severity." A sandbox bypass is CRITICAL even if triggered once per year. R14 understood this distinction; the current version lost it.

Meanwhile, the subsystem clustering regressed from 17 clusters (R14) to 7 clusters (current). Agent System gotchas get 20 entries and ~1,200 words; Database gotchas get 6 entries and ~400 words. This 6x depth disparity across clusters suggests different investigation agents had different coverage targets and never calibrated to a common depth.

#### Data Contracts Depth (R14: 4.0 → Current: 3.8)

R14 traced the Hypothesis→Experiment→Result pipeline with field-level specificity, including which fields are present in each representation and where `to_dict()` vs `model_dump()` diverge.

The current version lists 40+ models in tables (~770 words per model) but at summary level. Test: "Can an agent implement a new Hypothesis consumer from this alone?" No. The current version identifies three different serialization strategies (ExperimentResult.to_dict uses compat layer, Hypothesis.to_dict is manual, ExperimentProtocol.to_dict is 100-line manual) — but does not explain *when to use which*. No decision tree. No field list. No validation rules. Agent must read `hypothesis.py` anyway.

The regression mechanism: broader coverage traded for shallower depth. 40+ models at summary level is less useful than 5 models at field level. An agent implementing a consumer needs one model's complete schema, not forty models' names.

#### Gaps Honesty (R14: 4.0 → Current: 3.5)

R14 had 5 gap categories with quantified scope: "440 async functions may have more subtle boundary issues." That number (440) tells the agent how much unknown territory exists.

Current version has 5 gaps, all vague:
- "The 440 async functions may have more subtle boundary issues not yet catalogued" — same R14 phrasing, copy-pasted
- "kosmos-reference/ subprojects were scanned but not deeply investigated" — no count of what's missing
- "Docker/deployment was not investigated" — no impact estimate
- "Alembic migrations were noted but not traced" — no consequence stated

Missing gaps not mentioned at all: test coverage gaps, production-readiness assessment, observability gaps, security audit status. The document has 61,189 words but only ~120 words on what it doesn't know.

#### [FACT] Tag Precision (R14: ~90% precise → Current: ~47% precise)

This is the most damaging regression. Sampling 15 [FACT] tags from the current document:

- **7/15 (47%) are precise** — cite file:line, verifiable (e.g., `[FACT] (kosmos/agents/base.py:113-153)`)
- **4/15 (27%) are vague but checkable** — cite a module or pattern without line numbers
- **4/15 (27%) are phantom references** — cite crawl artifacts like `(shared_state.md)`, `(database_storage.md)`, `(initialization.md)` that do not exist in the repository

The current version doubled [FACT] count (777 → 1,587) but halved average precision. Approximately 200+ facts reference phantom crawl-output files (`shared_state.md`, `database_storage.md`, `initialization.md`, `providers_base.md`) that appear ~100 times throughout the document. An agent following these citations finds nothing. R14's lower count but higher precision was more useful — every citation led somewhere.

### Multi-Agent Assembly Artifacts

The current document was assembled by 7 independent sub-agents. The seams are visible:

**Terminology inconsistency.** "Research director" vs "ResearchDirectorAgent" vs "the orchestrator" — three names for the same entity, switching unpredictably across sections. "Experiment cache" vs "experiment_cache.py" vs "ExperimentCache" — no consistent casing.

**Repeated information across sections.** BaseAgent's lifecycle appears in: Critical Path 0 (line ~85), Module Index (line ~2124), Change Impact (line ~2415), Key Interfaces (line ~2470), and Gotchas (lines ~4036-4065). Five sections, slightly different wording each time. ~1,000 tokens of duplication that a single-author document would consolidate.

**Contradictory claims about SafetyGuardrails.** Critical Paths says CodeValidator.validate() is called (safety is on). Domain Glossary says SafetyGuardrails is "not currently wired" (safety is off). A gotcha says the bypass was "explicitly removed" (safety is on again). Three sections, three different answers. The actual answer (CodeValidator is called but SafetyGuardrails.emergency_stop is not) requires reading all three and synthesizing — exactly the work the document should have done.

**Tonal shifts.** Critical Paths reads like a machine trace (precise, terse). Configuration Surface reads like a textbook (expository, advisory). Gotchas read like a code review (conversational, opinionated). No unified voice.

**Inconsistent coverage depth.** Agent System gotchas: 20 entries, ~1,200 words. Database gotchas: 6 entries, ~400 words. Caching gotchas: 6 entries, ~300 words. The coverage is 4x deeper for agents than for databases, but there's no reason to believe agents have 4x more gotchas. Different investigation agents simply had different thoroughness levels.

### Wasted Tokens in Both Versions

**Cross-reference annotations (~1,200 tokens wasted).** `(see Module Index: cli_main.py)` appears ~200 times. In a static Markdown document loaded into context, an agent doesn't "follow cross-refs" — it uses grep or reads linearly. These parentheticals add noise to every trace hop.

**Phantom document references (~600 tokens wasted).** `(shared_state.md)`, `(database_storage.md)`, `(initialization.md)`, `(providers_base.md)` are crawl-process artifacts, not repository files. They appear ~100 times and lead nowhere.

**Restated programming facts (~500 tokens wasted).** "PaperMetadata is a dataclass, not Pydantic. This means no automatic validation, no JSON schema generation..." — 85 words explaining what `@dataclass` means. An AI agent already knows this.

**Singleton pattern explanations (~400 tokens wasted).** "if _config is None or reload: _config = KosmosConfig()" followed by 6 sentences explaining lazy initialization. Universal Python pattern. The initialization *ordering dependencies* are valuable; the pattern explanation is noise.

**Meta-metrics about the document itself (~300 tokens wasted).** "Investigation tasks: 46/46 complete, Coverage scope: 20 modules deep-read..." An agent using the document for onboarding does not care how many investigation tasks produced it.

**Decorative dividers (~400 tokens wasted).** 43 lines containing only `---` or section breaks with no content.

### The Actionability Problem (Both Versions)

The fundamental limitation shared by R14 and the current version: **both are awareness documents, not action documents.** They tell agents what exists and what's dangerous, but not how to modify safely.

Test: read the Module Behavioral Index for `alerts.py`. It describes 7 gotchas, notes "no test coverage," documents what breaks if you change it. Now: actually fix the alert ID collision bug. The document tells you the *symptom* (same-name alerts within one second share an ID) and the *location* (alerts.py:12). It does not tell you:
- What the ID generation function looks like
- Whether a dedup check already exists elsewhere
- What the downstream consumers of alert IDs assume
- Whether existing tests would catch a regression

The agent must still open alerts.py. The document saved one file read (identifying alerts.py as the target) but didn't save the actual investigation.

Change playbooks are the exception — they're genuinely actionable with step-by-step file:line targets. But both versions have only 2 playbooks covering "add new X" scenarios. The more common agent task — "modify existing behavior" — has zero playbook coverage.

---

## Part 3: How They Work Together (And Where They Don't)

### The Intended Division of Labor

Xray provides structural facts (imports, complexity, risk scores, class skeletons). DEEP_ONBOARD provides behavioral facts (what code does, what's dangerous, how to navigate). Together, an agent gets both the skeleton and the flesh.

### Where the Division Works

**Risk triage.** Xray's `config.py: risk 0.96, churn 27` flags the file. DEEP_ONBOARD's module entry explains *why* it's risky (lazy init ordering, provider registration race). The combination gives both the signal and the context. Neither alone is sufficient.

**Entry point identification + tracing.** Xray lists `main()` in `cli.py` as an entry point with CC:67. DEEP_ONBOARD traces the full call chain from `main()` → `ResearchDirectorAgent.execute()` → database persistence. Xray says "start here," DEEP_ONBOARD says "this is the path."

**Coupling analysis.** Xray identifies co-change pairs (`config.py` ↔ `anthropic.py`). DEEP_ONBOARD's hidden coupling section explains *why* they co-change (provider config field additions require factory updates). Structural fact + behavioral explanation.

### Where the Division Breaks Down

**Overlapping noise.** Both documents list the same 802 files, the same import counts, the same entry points. The xray import layer table is duplicated wholesale in DEEP_ONBOARD's module index. An agent loading both gets the same information twice at ~3,000 tokens of redundancy.

**Gap between structural and behavioral.** Xray identifies 192 data models. DEEP_ONBOARD documents ~20 behaviorally. The remaining 172 models exist in a documentation void — structurally listed but behaviorally unknown. An agent encountering one of the undocumented 172 must fall back to reading source with no guidance.

**Neither documents the provider interface.** Xray shows `providers.base` as a pillar (124 importers). DEEP_ONBOARD describes provider behavioral quirks. But neither documents the actual provider *interface contract* — the methods, signatures, and async requirements that a new provider must implement. This is arguably the most common extension task for Kosmos, and the combined documents don't support it without source reading.

**Neither documents database schema.** Xray mentions `get_session()` and `get_hypothesis()` as API surface. DEEP_ONBOARD discusses SQLAlchemy patterns and Alembic migrations at summary level. Neither provides the actual schema (tables, columns, constraints, relationships). An agent fixing a query or adding a model field has zero schema information from either document.

**Neither documents async concurrency model.** Xray says "440 async functions, 1 blocking violation." DEEP_ONBOARD says "both asyncio.Lock AND threading.RLock used." Neither explains: what's the executor strategy? How many concurrent agents can run? What happens if two agents write to the same world model entity simultaneously? The concurrency model is undocumented in both.

### The Referral Problem

DEEP_ONBOARD frequently says `(see companion xray.md for full import graphs)`. But when an agent follows this referral, xray's import tables are bulk data — they don't answer the specific question the agent had. Example: DEEP_ONBOARD says config.py affects 54 importers (see xray). Xray lists all 54 as a flat table with import counts. The agent needed to know *which of the 54 would break if field X is renamed*. Neither document answers this.

The referral pattern creates an illusion of coverage: "the information exists in the other document." In practice, the information exists in neither — xray has structural data the agent can't act on, and DEEP_ONBOARD has behavioral data that's too summary-level.

### Composite Gaps — What Neither Document Provides

| Need | Xray | DEEP_ONBOARD | Agent Must |
|------|------|-------------|-----------|
| "What methods must a new Provider implement?" | Lists base.py as pillar | Describes provider quirks | Read base.py |
| "What's the DB schema for Hypothesis?" | Lists domain_entities | Describes serialization gotchas | Read models/*.py |
| "What happens if Neo4j is down?" | Nothing | "Methods return silently" (1 sentence) | Read world_model.py |
| "What test fixtures exist?" | Lists 207 test files | "Testing conventions are surface-level" (gap) | Read conftest.py |
| "How does async work here?" | "440 async functions" | "Both lock types used" | Read research_director.py |
| "What's the cost per research cycle?" | Nothing | Nothing | Run it and measure |
| "What's safe to delete?" | Dead code list (structural) | Nothing | Cross-reference both |

The gap pattern: xray provides *what exists* (structural), DEEP_ONBOARD provides *what's dangerous* (behavioral), but **neither provides *what to do*** (procedural). The only procedural content is the 2 change playbooks covering 2 scenarios out of dozens an agent would face.

### What an Agent Actually Needs But Gets From Neither

1. **Interface contracts for extension points** — not just "base.py is important" but "implement these 4 methods with these signatures"
2. **Decision trees for common tasks** — "if you're adding a field to Hypothesis, update these 5 files in this order because X depends on Y"
3. **Safe deletion guide** — which code is actually dead vs dormant-but-triggered-by-config
4. **Runtime behavior under failure** — what happens when the LLM returns garbage, when Neo4j is down, when the experiment times out
5. **Test gap map** — not "207 test files" or "testing is thin" but "these 15 public methods in hub modules have zero test coverage"

---

## Part 4: Summary of Regressions (R14 → Current)

| Dimension | Direction | Evidence |
|-----------|-----------|----------|
| Gotcha severity calibration | **Worse** | 5 genuinely CRITICAL issues mislabeled HIGH; subsystem cluster depth varies 6x |
| [FACT] tag precision | **Worse** | ~47% precise vs R14's ~90%; ~200 phantom document references |
| Data contract depth | **Worse** | 40+ models at summary level vs R14's fewer models at field level |
| Gaps honesty | **Worse** | Vague, unquantified, missing entire categories (test coverage, security) |
| Narrative coherence | **Worse** | Visible 7-agent stitching: terminology shifts, repeated info, contradictions |
| Token efficiency | **Worse** | +20% word count, -30% actionable depth per token |
| Trace breadth | **Better** | 9 traces vs 5 — every major entry point covered |
| Convention documentation | **Better** | 38 directives with N/M counts vs ~20 unstructured |
| [ABSENCE] coverage | **Better** | 92 vs 4 — knowing what doesn't exist prevents wasted searches |
| Change impact actionability | **Better** | Safe/dangerous classifications per cluster |

### Net Assessment

The current version optimized for *volume* (more traces, more facts, more conventions) at the cost of *precision* (lower citation quality, shallower depth per item, worse calibration). An agent using R14 had fewer answers but could trust each one. An agent using the current version has more answers but must verify more of them.

### The Core Problem

Xray documents **structure**. DEEP_ONBOARD documents **awareness**. Neither documents **procedure**. The missing third layer — how to safely modify this codebase for common tasks — is where agents spend the most time and get the least help.

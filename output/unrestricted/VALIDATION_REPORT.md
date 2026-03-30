# Deep Crawl Validation Report: Kosmos

## 5a. Standard Questions Test

| # | Question | Answer from DEEP_ONBOARD.md | Status |
|---|----------|----------------------------|--------|
| Q1 | PURPOSE: What does this codebase do? | "Autonomous AI scientist that runs research cycles: generate hypotheses, design experiments, execute code in sandboxed Docker containers, analyze results, and refine hypotheses until convergence." | YES |
| Q2 | ENTRY: Where does a request enter? | "CLI entry point: `kosmos run`. Path 1 traces cli_entrypoint -> main() -> run_research() -> ResearchDirectorAgent" | YES |
| Q3 | FLOW: Critical path from input to output? | Path 1 shows full chain from CLI to state machine loop with DB commits and convergence check | YES |
| Q4 | HAZARDS: What files to never read? | Hazards table lists 7 patterns totaling 100K+ tokens to avoid | YES |
| Q5 | ERRORS: What happens on main operation failure? | Error Handling Strategy section: catch-warn-continue for infra, retry [2,4,8]s then halt after 3 for LLM, MAX_ACTIONS=50 loop prevention | YES |
| Q6 | EXTERNAL: What external systems? | Identity + Config Surface: Anthropic/OpenAI APIs, Neo4j, SQLite/PostgreSQL, ChromaDB, Redis (optional), Docker | YES |
| Q7 | STATE: Shared state that could cause bugs? | Shared State table: 8 singletons documented with risk descriptions; world model not thread-safe called out | YES |
| Q8 | TESTING: Testing conventions? | Conventions #5: pytest marks, conftest.py reset fixtures, 207 test files, ~3721 functions | YES |
| Q9 | GOTCHAS: Top 3 counterintuitive things? | 10 gotchas documented; top 3: LLMResponse not str, two orchestration systems, flat config requirement | YES |
| Q10 | EXTENSION: Where to start adding new entity? | Extension Points table: 6 tasks with Start/Touch/WatchOut | YES |

**Score: 10/10 questions answerable**

## 5b. Spot-Check Verification

| # | Claim | File:Line | Verified |
|---|-------|-----------|----------|
| 1 | get_client() at line 613 of llm.py is thread-safe with _client_lock | core/llm.py:613, :610 (_client_lock = Lock) | PASS |
| 2 | MAX_CONSECUTIVE_ERRORS = 3 | research_director.py:45 | PASS |
| 3 | ERROR_BACKOFF_SECONDS = [2, 4, 8] | research_director.py:46 | PASS |
| 4 | MAX_ACTIONS_PER_ITERATION = 50 | research_director.py:50 | PASS |
| 5 | World model factory says NOT thread-safe | world_model/factory.py:37 | PASS |
| 6 | reset_database() drops all tables | db/__init__.py:191-201 | PASS |
| 7 | LLMResponse has strip/lower/etc delegations | core/providers/base.py:107-154 | PASS |
| 8 | CLI flattens config at run.py:148-170 | commands/run.py:148-170 | PASS |
| 9 | config.py singleton at line 1137 | config.py:1137 (_config: Optional[KosmosConfig]) | PASS |
| 10 | BaseAgent sync wrappers use asyncio.run | agents/base.py:324-326 | PASS |

**Score: 10/10 claims verified**

## 5c. Redundancy Check

Reviewed each section for "would grep find this in 30 seconds":
- Identity: NOT grepable (synthesized from multiple sources)
- Critical Paths: NOT grepable (multi-file trace)
- Module Index: NOT grepable (behavioral descriptions)
- Key Interfaces: PARTIALLY grepable but saves opening 6 files
- Error Handling: NOT grepable (cross-module synthesis)
- Shared State: PARTIALLY grepable but saves opening 8 files
- Config Surface: PARTIALLY grepable but organized and annotated
- Conventions: NOT grepable (pattern synthesis with counts)
- Gotchas: NOT grepable (non-obvious behaviors requiring multi-file understanding)
- Extension Points: NOT grepable (requires architectural understanding)

**No sections removed — all provide value beyond grep.**

## 5d. Adversarial Simulation

**Task:** "Add a new LLM provider (e.g., Google Gemini) that supports generate() and generate_async()"

### 5-Step Plan (from DEEP_ONBOARD.md only):

1. Create `kosmos/core/providers/gemini.py` subclassing `LLMProvider` from `core/providers/base.py`. Implement `generate()`, `generate_async()`, `generate_with_messages()`, `generate_structured()`, `get_model_info()`. Return `LLMResponse` objects (not str).

2. Add `GeminiConfig(BaseSettings)` to `config.py` following the pattern of `OpenAIConfig` (lines 91-140). Add `gemini: Optional[GeminiConfig]` to `KosmosConfig`.

3. Register the provider in `core/providers/factory.py` by adding a "gemini" branch to `get_provider_from_config()`.

4. Add `GEMINI_API_KEY` and `GEMINI_MODEL` to the env var documentation and `.env.example`.

5. Update `commands/run.py` flat_config (lines 148-170) if any new config fields need to be passed to agents.

### Verification against actual codebase:
- Step 1: CORRECT — LLMProvider ABC at providers/base.py defines the exact interface
- Step 2: CORRECT — OpenAIConfig at config.py:91 is the right pattern to follow
- Step 3: CORRECT — factory.py dispatches on config.llm_provider string
- Step 4: CORRECT — needed for env-based config loading
- Step 5: CORRECT — gotcha about flat config is real and documented

**Score: PASS (5/5 steps correct)**

## 5e. Caching Structure Verification

Document section ordering:
1. Identity (stable)
2. Critical Paths (stable)
3. Module Behavioral Index (stable)
4. Key Interfaces (stable)
5. Error Handling Strategy (stable)
6. Shared State (stable)
7. Configuration Surface (moderately stable)
8. Conventions (stable)
9. Gotchas (volatile — changes with code)
10. Hazards (volatile — file sizes change)
11. Extension Points (moderately volatile)
12. Reading Order (stable)
13. Gaps (volatile)

**Stable sections come first. Structure is correct for prompt caching.**

## Summary

| Metric | Score |
|--------|-------|
| Questions answerable | 10/10 |
| Claims verified | 10/10 |
| Adversarial test | PASS (5/5) |
| Redundancy | 0 sections cut |
| Cache structure | Correct |

**Overall: PASS**

# Deep Crawl Plan: Kosmos

> Domain: Agent-based Scientific Research Platform (hybrid: CLI + workflow orchestration + agent system)
> Codebase: 802 analyzed Python files (~1520 total), ~2.5M tokens
> X-Ray scan: 2026-03-29T04:49:55
> Plan generated: 2026-03-29
> Git commit: current HEAD

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | 5 | 5 |
| 2 | 8 | 8 |
| 3 | 7 | 7 |
| 4 | 6 | 6 |
| 5 | 4 | 4 |
| 6 | 3 | 3 |

### Priority 1: Request Traces (5 tasks)
- [x] T1.1: CLI `kosmos run` → ResearchDirectorAgent → full research cycle
- [x] T1.2: ResearchWorkflow.run() → research cycle (alternative entry)
- [x] T1.3: Code execution path: code_generator → sandbox → Docker exec → result
- [x] T1.4: Hypothesis generation: HypothesisGeneratorAgent → LLM → novelty → DB
- [x] T1.5: LLM provider chain: core/llm.py → factory → anthropic/openai → response

### Priority 2: High-Uncertainty Module Deep Reads (8 tasks)
- [x] T2.1: agents/base.py — BaseAgent class
- [x] T2.2: config.py — Hierarchical Pydantic configuration
- [x] T2.3: execution/executor.py — Code execution engine
- [x] T2.4: execution/sandbox.py — Docker sandbox
- [x] T2.5: safety/code_validator.py — Code safety validation
- [x] T2.6: core/providers/anthropic.py — Anthropic provider
- [x] T2.7: knowledge/graph.py — Neo4j knowledge graph
- [x] T2.8: knowledge/vector_db.py — ChromaDB vector store

### Priority 3: Pillar Behavioral Summaries (7 tasks)
- [x] T3.1-T3.7: All pillar summaries complete

### Priority 4: Cross-Cutting Concerns (6 tasks)
- [x] T4.1: Error handling strategy
- [x] T4.2: Configuration surface
- [x] T4.3: LLM provider abstraction
- [x] T4.4: Code execution security model
- [x] T4.5: Shared mutable state verification
- [x] T4.6: Database and persistence strategy

### Priority 5: Conventions and Patterns (4 tasks)
- [x] T5.1-T5.4: All conventions documented

### Priority 6: Gap Investigation (3 tasks)
- [x] T6.1-T6.3: All gaps investigated

Last checkpoint: all tasks complete

# Deep Crawl Plan: Kosmos

**Domain:** Autonomous AI Scientist / Multi-Domain Scientific Research Platform
**Detected Architecture:** Agent-based orchestration with workflow state machine, multi-provider LLM integration, knowledge graph persistence
**Files:** 802 Python files, ~284K lines, ~2.4M tokens

## Priority 1 (Critical Path)

### P1-T1: Protocol A - Research Loop Trace
Entry: `kosmos run "question"` -> cli/commands/run.py:run_research() -> ResearchDirectorAgent.execute()
Trace through: workflow state machine (INIT -> HYPOTHESES -> EXPERIMENTS -> EXECUTING -> ANALYZING -> REFINING -> CONVERGED)
Side effects: DB writes, LLM API calls, file I/O (results), knowledge graph mutations

### P1-T2: Protocol B - ResearchDirectorAgent Deep Read
File: kosmos/agents/research_director.py (30K tokens, ~1500 lines)
Why: Master orchestrator, highest fan-in among agents, coordinates all sub-agents

### P1-T3: Protocol B - config.py Deep Read
File: kosmos/config.py (risk: 0.96, churn: 27, hotfixes: 18)
Why: Highest risk hotspot, all components depend on KosmosConfig singleton

### P1-T4: Protocol B - core/llm.py Deep Read
File: kosmos/core/llm.py (risk: 0.70)
Why: Multi-provider LLM abstraction, ClaudeClient backward compat, get_client() singleton

### P1-T5: Protocol C - Error Handling Strategy
Pattern: try/except per-operation with continue, error recovery with exponential backoff
Search: error recovery patterns across agents, executor, LLM clients

## Priority 2 (Structural Understanding)

### P2-T1: Protocol B - core/workflow.py
File: kosmos/core/workflow.py
Why: State machine definition (WorkflowState enum, ResearchPlan model)

### P2-T2: Protocol B - execution/executor.py
File: kosmos/execution/executor.py
Why: Sandboxed code execution, restricted builtins, module allowlisting

### P2-T3: Protocol B - agents/base.py
File: kosmos/agents/base.py
Why: BaseAgent ABC, async message passing, agent lifecycle

### P2-T4: Protocol B - core/convergence.py
File: kosmos/core/convergence.py
Why: Stopping criteria detection, novelty decline detection

### P2-T5: Protocol C - Singleton Pattern
Pattern: get_config(), get_client(), get_world_model(), _engine/_SessionLocal
Search: module-level globals with lazy init + lock

## Priority 3 (Domain & Integration)

### P3-T1: Protocol B - knowledge/graph.py
File: kosmos/knowledge/graph.py
Why: Neo4j integration, auto-start Docker container

### P3-T2: Protocol B - db/models.py + db/operations.py
Why: SQLAlchemy ORM schema, CRUD operations, eager loading

### P3-T3: Protocol B - core/providers/base.py + factory.py
Why: LLMProvider ABC, provider registry, LLMResponse string compatibility

### P3-T4: Protocol C - Async Architecture
Pattern: async/await with asyncio.Lock, sync wrappers, threading.RLock fallback
Search: async patterns across ResearchDirector, EventBus, base agent

### P3-T5: Protocol D - Config via Environment
Convention: All config from env vars via pydantic-settings, alias mapping

## Priority 4 (Safety & Conventions)

### P4-T1: Protocol B - safety/code_validator.py
Why: Code safety checks, ethical guidelines, risk assessment

### P4-T2: Protocol B - execution/sandbox.py
Why: Docker-based isolated execution, resource limits

### P4-T3: Protocol D - Agent Implementation Pattern
Convention: Inherit BaseAgent, implement execute(), use get_client() for LLM

### P4-T4: Protocol D - Model Definitions
Convention: Pydantic models in models/, SQLAlchemy in db/models.py, dataclasses for API types

### P4-T5: Protocol C - Logging Convention
Pattern: kosmos/core/logging.py JSON formatter, contextvars for correlation ID

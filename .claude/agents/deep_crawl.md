---
name: deep_crawl
description: Sequential fallback for deep codebase investigation. For orchestrated parallel execution with sub-agents, use /deep-crawl full instead.
tools: Read, Grep, Glob, Bash
model: opus
skills: deep-crawl
---

# Deep Crawl Agent (Sequential Mode)

You are running as a sub-agent without Agent tool access. The deep-crawl
skill instructions are preloaded in your context — follow them for all phases.

## Phase 2 Override

Execute the crawl plan **sequentially** using the Investigation Protocols
from the skill directly. Do not attempt to spawn sub-agents.

For each task in CRAWL_PLAN.md, in priority order:
1. Select the appropriate protocol (A for traces, B for modules, C for
   cross-cutting, D for conventions)
2. Execute the protocol directly — read the code, write findings to disk
3. Write findings to the appropriate `.deep_crawl/findings/{type}/` directory
4. After every 5 tasks, update CRAWL_PLAN.md with `[x]` marks

When all tasks are complete, verify the stopping criteria and coverage checks
from the skill instructions, then continue to Phase 3.

## All Other Phases

Phases 0, 1, 3, 4, 5, 6 — execute identically to the skill instructions.

## Notice

Log at the start of Phase 2:
"Running in sequential mode via @deep_crawl. For parallel investigation
with sub-agents, use /deep-crawl full instead."

# Archived: Legacy Two-Phase Design

These files represent the original two-phase agent/skill architecture that has been superseded by the unified `repo_xray` agent.

## Why Archived

The original design separated analysis into two phases:

1. **Phase 1 (repo_architect + repo-xray)**: Structural analysis → WARM_START.md
2. **Phase 2 (repo_investigator + repo-investigator)**: Behavioral analysis → HOT_START.md

After refactoring the underlying tool (`xray.py`) to extract all signals in a single pass, this separation became unnecessary:

- The tool now extracts structural AND behavioral signals together
- Presets control output depth (not separate phases)
- A single agent with modes provides the same functionality more simply

## New Design

The unified design uses:

- **One agent**: `repo_xray` (`.claude/agents/repo_xray.md`)
- **One skill**: `repo-xray` (`.claude/skills/repo-xray/`)
- **Modes instead of phases**: survey, analyze, query, focus, refresh

## Contents

```
archived/
├── agents/
│   ├── repo_architect.md      # Phase 1 agent (structural)
│   └── repo_investigator.md   # Phase 2 agent (behavioral)
└── skills/
    └── repo-investigator/     # Phase 2 skill
        ├── SKILL.md
        ├── scripts/
        │   ├── complexity.py
        │   ├── smart_read.py
        │   ├── verify.py
        │   └── generate_hot_start.py
        └── templates/
            └── HOT_START.md.template
```

## Reference Value

These files are preserved for:

1. Understanding the evolution of the design
2. Reference implementations of specific techniques
3. Potential reuse of scripts if needed

The `smart_read.py` concept (surgical reading of complex methods) is now integrated into the agent's investigation workflow rather than being a separate script.

## Do Not Use

These archived agents and skills should not be invoked. Use the current:

```
@repo_xray analyze    # Full analysis
@repo_xray survey     # Quick reconnaissance
@repo_xray query      # Targeted questions
@repo_xray focus      # Subsystem deep-dive
```

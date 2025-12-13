# Resume Prompt: Comprehensive Data Source Audit

## Context

repo-xray is a two-pass analysis system for Python codebases:
- **Pass 1 (WARM_START.md)**: Structural analysis via repo-xray skill
- **Pass 2 (HOT_START.md)**: Behavioral analysis via repo-investigator skill

Current claim: "18 signals from 14 metadata sources"

## Project Goal

Comprehensive audit to:
1. Enumerate all 14 data sources and verify the claim
2. Identify if additional data can be extracted beyond the 18 signals
3. Verify each section of WARM_START.md and HOT_START.md for accuracy/completeness
4. Generate debug output as reference examples

## First Task: Generate Debug Examples

```bash
# Generate WARM_START.md with debug output for Kosmos
python .claude/skills/repo-xray/scripts/generate_warm_start.py /mnt/c/python/kosmos --debug -v -o WARM_START.md

# Generate HOT_START.md with debug output for Kosmos
python .claude/skills/repo-investigator/scripts/generate_hot_start.py /mnt/c/python/kosmos --debug -v --detail 4 -o HOT_START.md

# Save debug directories as examples
cp -r WARM_START_debug/ examples/
cp -r HOT_START_debug/ examples/
```

## Data Sources to Audit

### Pass 1 Sources (repo-xray)

| # | Source | Tool | Signals Extracted |
|---|--------|------|-------------------|
| 1 | Directory tree | mapper.py | File count, token estimates, large files |
| 2 | Python AST (classes) | skeleton.py | Class definitions, methods, fields |
| 3 | Python AST (imports) | dependency_graph.py | Import relationships, layers |
| 4 | Git log (commits) | git_analysis.py | Churn, hotfixes, authors |
| 5 | Git log (co-changes) | git_analysis.py | Coupling pairs |
| 6 | Git log (dates) | git_analysis.py | Freshness categories |
| 7 | Test directories | generate_warm_start.py | Test coverage metadata |
| 8 | __main__ blocks | generate_warm_start.py | Entry points |
| 9 | pyproject.toml/setup.py | configure.py | Project structure |

### Pass 2 Sources (repo-investigator)

| # | Source | Tool | Signals Extracted |
|---|--------|------|-------------------|
| 10 | Python AST (control flow) | complexity.py | Cyclomatic complexity |
| 11 | Python AST (function bodies) | generate_hot_start.py | Logic maps |
| 12 | Python AST (calls) | generate_hot_start.py | Side effects |
| 13 | Python AST (assignments) | generate_hot_start.py | State mutations |
| 14 | Source code patterns | generate_hot_start.py | Hidden deps (env vars, services) |

## Audit Checklist

### For Each Data Source:
- [ ] Verify source is actually being used
- [ ] Document what data is extracted
- [ ] Identify what data is available but NOT extracted
- [ ] Assess value of omitted data

### For Each WARM_START.md Section:
1. System Context (Mermaid diagram)
2. Architecture Overview
3. Critical Classes
4. Data Flow
5. Entry Points
6. Context Hazards
7. Quick Verification
8. X-Ray Commands
9. Architecture Layers
10. Risk Assessment
11. Hidden Coupling
12. Potential Dead Code
13. Test Coverage

### For Each HOT_START.md Section:
1. System Dynamics (Priority table + Mermaid)
2. Logic Maps
3. Dependency Verification
4. Hidden Dependencies
5. Module Dependencies
5.5 Git Analysis
6. Logic Map Legend
7. Developer Activity (placeholder)
8. Reference

## Key Files

| File | Purpose |
|------|---------|
| `.claude/skills/repo-xray/scripts/generate_warm_start.py` | Pass 1 generator |
| `.claude/skills/repo-investigator/scripts/generate_hot_start.py` | Pass 2 generator |
| `.claude/skills/repo-xray/scripts/mapper.py` | Directory/token mapping |
| `.claude/skills/repo-xray/scripts/skeleton.py` | AST class extraction |
| `.claude/skills/repo-xray/scripts/dependency_graph.py` | Import analysis |
| `.claude/skills/repo-xray/scripts/git_analysis.py` | Git history analysis |
| `.claude/skills/repo-investigator/scripts/complexity.py` | CC calculation |

## Questions to Answer

1. Are there exactly 14 data sources? More? Fewer?
2. Are there exactly 18 signals? What are they specifically?
3. What additional signals could be extracted from existing sources?
4. Are any sections producing inaccurate or incomplete data?
5. What data is being discarded that might be valuable?

## Output Deliverables

1. `DATA_SOURCES_AUDIT.md` - Complete enumeration of sources and signals
2. Updated debug examples in `examples/` directory
3. List of potential enhancements with effort estimates
4. Corrected signal/source counts for README if needed

## Start Command

```
Resume the comprehensive data source audit for repo-xray.

Read resume_prompt.md for full context, then:
1. First generate debug output for Kosmos (WARM_START and HOT_START with --debug)
2. Save debug directories to examples/
3. Begin systematic audit of each data source
4. Document findings in DATA_SOURCES_AUDIT.md
```

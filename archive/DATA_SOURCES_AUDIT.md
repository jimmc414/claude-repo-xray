# Data Sources Audit

**Audit Date**: 2025-12-13
**Target Repository**: Kosmos (`/mnt/c/python/kosmos`)
**Tool Version**: repo-xray + repo-investigator (Two-Pass Analysis)

---

## Executive Summary

### Claim Verification: "18 signals from 14 metadata sources"

| Aspect | Claimed | Verified | Status |
|--------|---------|----------|--------|
| **Sources** | 14 | 14 | ✅ Accurate |
| **Signals** | 18 | 30+ (depends on granularity) | ⚠️ Undercounted |

**Finding**: The "18 signals" claim is conservative. At fine granularity, we extract 30+ distinct signals. At coarse granularity (grouping related signals), we extract ~18.

### Signal Counting Methodology

**Coarse (grouped by function)**: ~18 signals
- This is what the README claims

**Fine (individual data points)**: 30+ signals
- Each signal may have sub-signals (e.g., "risk" has churn, hotfixes, authors)
- Each category may have multiple items (e.g., "hidden_deps" has env_vars, services, configs)

---

## Source-by-Source Analysis

### Pass 1 Sources (repo-xray → WARM_START.md)

#### Source 1: Directory Tree
| Attribute | Value |
|-----------|-------|
| **Tool** | `mapper.py` |
| **Raw Data** | File system traversal via `os.walk()` |
| **Signals Extracted** | |
| token_budget | Sum of file sizes ÷ 4 (Kosmos: 159,935,098 tokens) |
| file_count | Count of non-ignored files (Kosmos: 2,627 files) |
| directory_tree | Hierarchical visualization with indentation |
| large_files | Files >10K tokens with paths and token counts (Kosmos: 178 files) |
| **Data Available but NOT Extracted** | |
| file_modification_times | `os.stat().st_mtime` available |
| file_permissions | `os.stat().st_mode` available |
| extension_distribution | Could count files by extension |
| directory_depth | Could calculate max nesting depth |
| symlink_detection | Could identify symbolic links |
| **Value of Omitted** | Low - not useful for cold start understanding |
| **Effort to Add** | ~15 lines each |

#### Source 2: Python AST (Classes)
| Attribute | Value |
|-----------|-------|
| **Tool** | `skeleton.py` |
| **Raw Data** | Python AST via `ast.parse()` |
| **Signals Extracted** | |
| skeleton_code | Class signatures, method signatures, decorators, fields |
| original_tokens | Token count of full file |
| skeleton_tokens | Token count of interface only |
| reduction_percentage | (1 - skeleton/original) × 100 |
| line_numbers | For navigation (optional) |
| **Data Available but NOT Extracted** | |
| complete_docstrings | Only first line extracted |
| exception_types | `ast.Raise` nodes available |
| method_bodies | Full implementation available |
| comments | Could extract via tokenize module |
| type_annotation_coverage | Percentage of typed functions |
| **Value of Omitted** | Medium - docstrings valuable, method bodies too verbose |
| **Effort to Add** | ~20 lines for docstrings, ~10 lines for type coverage |

#### Source 3: Python AST (Imports)
| Attribute | Value |
|-----------|-------|
| **Tool** | `dependency_graph.py` |
| **Raw Data** | `ast.Import` and `ast.ImportFrom` nodes |
| **Signals Extracted** | |
| modules_list | All discovered Python modules (Kosmos: 793 modules) |
| import_edges | Internal module-to-module dependencies (Kosmos: 1,106 edges) |
| external_dependencies | Third-party packages used |
| circular_dependencies | Modules with mutual imports (Kosmos: 2 circulars) |
| architectural_layers | Foundation/Core/Orchestration/Leaf classification |
| orphan_modules | Not imported by anything (Kosmos: 130 orphans) |
| impact_analysis | Transitive dependents/blast radius |
| **Data Available but NOT Extracted** | |
| import_counts_per_module | How many imports in each file |
| relative_vs_absolute | Pattern analysis of import style |
| stability_index | Based on afferent/efferent coupling |
| api_surface | Exports via `__all__` |
| **Value of Omitted** | Medium - stability metrics useful for architecture |
| **Effort to Add** | ~25 lines for stability, ~10 lines for counts |

#### Source 4: Git Log (Commits)
| Attribute | Value |
|-----------|-------|
| **Tool** | `git_analysis.py` |
| **Raw Data** | `git log --name-only --pretty=format` |
| **Signals Extracted** | |
| risk_score | Composite: 40% churn + 40% hotfixes + 20% author_entropy |
| churn | Number of commits in period (Kosmos: up to 23 for config.py) |
| hotfixes | Commits with fix/bug/urgent/revert keywords (Kosmos: up to 14) |
| author_entropy | Unique authors / total commits (Kosmos: up to 4 authors) |
| **Data Available but NOT Extracted** | |
| commit_size_loc | Lines added/removed per commit |
| blame_authorship | Line-by-line ownership |
| velocity_trends | Commits over time windows |
| commit_messages | Beyond keyword matching |
| breaking_changes | Pattern detection in messages |
| **Value of Omitted** | High - blame data very useful for ownership |
| **Effort to Add** | ~30 lines for blame, ~20 lines for LOC |

#### Source 5: Git Log (Co-changes)
| Attribute | Value |
|-----------|-------|
| **Tool** | `git_analysis.py` |
| **Raw Data** | Files modified in same commits |
| **Signals Extracted** | |
| coupling_pairs | Files that change together (Kosmos: 9 pairs) |
| co_occurrence_count | How many times pair appears together (up to 5) |
| **Data Available but NOT Extracted** | |
| pr_review_metrics | Approval time, reviewer count |
| regression_patterns | Which files cause bugs when changed |
| branch_merge_patterns | Feature branch vs hotfix patterns |
| **Value of Omitted** | High - regression patterns extremely valuable |
| **Effort to Add** | ~50 lines for PR metrics (requires GitHub API) |

#### Source 6: Git Log (Dates)
| Attribute | Value |
|-----------|-------|
| **Tool** | `git_analysis.py` |
| **Raw Data** | Commit timestamps |
| **Signals Extracted** | |
| freshness_categories | Active (<30d) / Aging (30-90d) / Stale (90-180d) / Dormant (>180d) |
| days_since_modification | Exact days from last commit |
| **Kosmos Results** | Active: 674, Aging: 130, Stale: 0, Dormant: 0 |
| **Data Available but NOT Extracted** | |
| release_proximity | Days since last tag/release |
| burst_patterns | Periods of high activity |
| **Value of Omitted** | Low - current signals sufficient |
| **Effort to Add** | ~15 lines for release proximity |

#### Source 7: Test Directories
| Attribute | Value |
|-----------|-------|
| **Tool** | `generate_warm_start.py` |
| **Raw Data** | Directory structure + file patterns |
| **Signals Extracted** | |
| test_file_count | Python files in test directories |
| test_function_count | Count of "def test_" patterns |
| coverage_by_type | Breakdown by unit/integration/e2e |
| tested_directories | Source dirs with corresponding test dirs |
| untested_directories | Source dirs without tests |
| fixtures | @pytest.fixture decorated functions |
| **Data Available but NOT Extracted** | |
| actual_coverage_percent | Requires .coverage file or pytest-cov |
| test_execution_times | Requires pytest timing data |
| fixture_dependencies | Which tests use which fixtures |
| parameterized_variations | @pytest.mark.parametrize counts |
| **Value of Omitted** | Medium - actual coverage % would be valuable |
| **Effort to Add** | ~30 lines for coverage file parsing |

#### Source 8: __main__ Blocks
| Attribute | Value |
|-----------|-------|
| **Tool** | `generate_warm_start.py` |
| **Raw Data** | File patterns + AST analysis |
| **Signals Extracted** | |
| entry_points | Files matching patterns + if __name__ == "__main__" blocks |
| entry_type | main / cli / app / async (Kosmos: 10 entry points) |
| entry_description | Human-readable description |
| **Data Available but NOT Extracted** | |
| argument_parsing | argparse/click/typer structure |
| cli_command_tree | Subcommand hierarchy |
| required_vs_optional_args | Argument metadata |
| **Value of Omitted** | Low - current detection sufficient |
| **Effort to Add** | ~40 lines for argparse analysis |

#### Source 9: pyproject.toml / setup.py
| Attribute | Value |
|-----------|-------|
| **Tool** | `configure.py` |
| **Raw Data** | TOML/Python file parsing |
| **Signals Extracted** | |
| project_root | Via .git, pyproject.toml, setup.py, or __init__.py density |
| root_package_name | Most common internal import |
| ignore_directories | Merged from defaults + .gitignore + heuristics |
| ignore_extensions | Same merge pattern |
| ignore_files | Same merge pattern |
| priority_modules_critical/high/medium/low | Via folder/file name matching |
| entry_point_hints | Keywords for finding main workflow classes |
| architecture_keywords | Class/method patterns indicating importance |
| **Data Available but NOT Extracted** | |
| dependency_versions | Package versions from pyproject.toml |
| python_version_requirement | `requires-python` field |
| package_metadata | Author, license, description |
| console_scripts | Entry points defined in pyproject.toml |
| optional_dependencies | Extra features groups |
| **Value of Omitted** | Medium - dependency versions useful for compatibility |
| **Effort to Add** | ~25 lines for version parsing |

---

### Pass 2 Sources (repo-investigator → HOT_START.md)

#### Source 10: Python AST (Control Flow)
| Attribute | Value |
|-----------|-------|
| **Tool** | `complexity.py` |
| **Raw Data** | `ast.If`, `ast.While`, `ast.For`, `ast.Try`, `ast.BoolOp` |
| **Signals Extracted** | |
| cyclomatic_complexity | Base=1 + decision points (Kosmos: up to 235 for research_director.py) |
| method_hotspots | Per-method CC values |
| **Unified Priority Score Formula** | |
| 5-signal | CC(30%) + Import(20%) + Risk(20%) + Freshness(15%) + Untested(15%) |
| 4-signal | CC(35%) + Import(25%) + Risk(25%) + Freshness(15%) |
| **Data Available but NOT Extracted** | |
| async_vs_sync | FunctionDef vs AsyncFunctionDef distinction |
| decorator_analysis | Which decorators are applied |
| dead_code_paths | Unreachable code detection |
| recursion_detection | Self-calling functions |
| **Value of Omitted** | Medium - async distinction useful for understanding concurrency |
| **Effort to Add** | ~15 lines for async, ~25 lines for dead code |

#### Source 11: Python AST (Function Bodies)
| Attribute | Value |
|-----------|-------|
| **Tool** | `generate_hot_start.py` (LogicMapGenerator) |
| **Raw Data** | Full function AST nodes |
| **Signals Extracted** | |
| method_signature | Function name, parameters, return type annotation |
| docstring | Method documentation (truncated at detail level <4) |
| control_flow | Arrow notation diagram of conditions/loops |
| return_patterns | What values are returned |
| exceptions_caught | Try/except block types |
| **Logic Map Example** | |
```
-> action == NextAction.GENERATE_HYPOTHESIS?
  -> action == NextAction.DESIGN_EXPERIMENT?
    -> untested?
      -> self.enable_concurrent?
        try:
          -> evaluations?
        ! except Exception
```
| **Data Available but NOT Extracted** | |
| recursion_depth | Max call nesting |
| call_graph | Function-to-function call relationships |
| variable_scoping | Local/global/nonlocal analysis |
| closure_detection | Functions capturing outer scope |
| **Value of Omitted** | High - call graph very useful for understanding flow |
| **Effort to Add** | ~50 lines for call graph, ~20 lines for recursion |

#### Source 12: Python AST (Calls)
| Attribute | Value |
|-----------|-------|
| **Tool** | `generate_hot_start.py` |
| **Raw Data** | `ast.Call` nodes |
| **Signals Extracted** | |
| side_effects_db | db.*, insert, update, delete, query, session.commit |
| side_effects_api | requests.*, httpx.*, post, put, patch, fetch, api.send |
| side_effects_file | file.write, json.dump, pickle.dump, export |
| side_effects_email | send_email, send_mail, notify, smtp.send |
| side_effects_cache | cache.set, redis.set, cache.invalidate, cache.clear |
| **Data Available but NOT Extracted** | |
| call_chain_depth | How deeply nested are call chains |
| method_chaining | obj.method1().method2().method3() patterns |
| callback_patterns | Functions passed as arguments |
| **Value of Omitted** | Low - side effect detection covers main use case |
| **Effort to Add** | ~20 lines for call chain depth |

#### Source 13: Python AST (Assignments)
| Attribute | Value |
|-----------|-------|
| **Tool** | `generate_hot_start.py` |
| **Raw Data** | `ast.Assign` nodes |
| **Signals Extracted** | |
| state_mutations | self.x = ... assignments (Kosmos: detected in logic maps) |
| external_inputs | request.*, input(), args.*, params.*, payload.*, body.* |
| **Data Available but NOT Extracted** | |
| variable_naming_patterns | snake_case vs camelCase violations |
| unused_variables | Assigned but never read |
| shadowed_variables | Outer scope name reuse |
| type_mismatches | Runtime type violations (requires static analysis) |
| **Value of Omitted** | Low - naming patterns not critical for cold start |
| **Effort to Add** | ~25 lines for unused detection |

#### Source 14: Source Code Patterns
| Attribute | Value |
|-----------|-------|
| **Tool** | `generate_hot_start.py` |
| **Raw Data** | Regex on source code |
| **Signals Extracted** | |
| env_vars | os.environ.get(), os.environ[], os.getenv() (Kosmos: 54 vars) |
| external_services | Import-based: database, cache, queue, storage, api (Kosmos: 3 categories) |
| config_files | .json, .yaml, .yml, .toml, .ini, .cfg, .env patterns (Kosmos: 1 file) |
| conditions | If/else condition text (preserved in logic maps) |
| **Data Available but NOT Extracted** | |
| todo_fixme_comments | TODO, FIXME, HACK, XXX markers |
| code_duplication | Similar code blocks across files |
| design_patterns | Factory, Singleton, Observer detection |
| magic_numbers | Hardcoded constants without names |
| **Value of Omitted** | Medium - TODO/FIXME very useful for tech debt |
| **Effort to Add** | ~10 lines for TODO detection, ~100+ lines for duplication |

---

## Signal Count Reconciliation

### Detailed Signal Enumeration

#### Pass 1 Signals (WARM_START.md)

| # | Signal | Sub-signals | Source |
|---|--------|-------------|--------|
| 1 | Token budget | 1 | Directory tree |
| 2 | File count | 1 | Directory tree |
| 3 | Directory tree | 1 | Directory tree |
| 4 | Large files | 1 | Directory tree |
| 5 | Skeleton code | 1 | AST (classes) |
| 6 | Token reduction | 3 (original, skeleton, %) | AST (classes) |
| 7 | Module list | 1 | AST (imports) |
| 8 | Import edges | 1 | AST (imports) |
| 9 | External deps | 1 | AST (imports) |
| 10 | Circular deps | 1 | AST (imports) |
| 11 | Layers | 4 (foundation, core, orch, leaf) | AST (imports) |
| 12 | Orphans | 1 | AST (imports) |
| 13 | Risk score | 4 (score, churn, hotfixes, authors) | Git (commits) |
| 14 | Coupling pairs | 2 (pair, count) | Git (co-changes) |
| 15 | Freshness | 5 (4 categories + days) | Git (dates) |
| 16 | Test coverage | 6 (files, functions, types, tested, untested, fixtures) | Test dirs |
| 17 | Entry points | 3 (module, type, description) | __main__ blocks |
| 18 | Project config | 8 (root, package, ignores, priorities, keywords) | pyproject/setup |

**Pass 1 Total**: 18 grouped signals, 44 sub-signals

#### Pass 2 Signals (HOT_START.md)

| # | Signal | Sub-signals | Source |
|---|--------|-------------|--------|
| 19 | Cyclomatic complexity | 2 (file CC, method hotspots) | AST (control flow) |
| 20 | Priority score | 5 (CC, import, risk, freshness, untested) | Unified scoring |
| 21 | Logic maps | 8 (signature, docstring, flow, returns, exceptions, side effects, inputs, mutations) | AST (function bodies) |
| 22 | Side effects | 5 (DB, API, file, email, cache) | AST (calls) |
| 23 | State mutations | 1 | AST (assignments) |
| 24 | External inputs | 1 | AST (assignments) |
| 25 | Hidden deps - env vars | 1 | Source patterns |
| 26 | Hidden deps - services | 1 | Source patterns |
| 27 | Hidden deps - configs | 1 | Source patterns |
| 28 | Verification | 3 (status, warnings, external deps) | Import check |

**Pass 2 Total**: 10 grouped signals, 28 sub-signals

### Grand Total

| Counting Method | Count |
|-----------------|-------|
| **Grouped signals** | 28 |
| **Sub-signals** | 72 |
| **Unique data points** | 50+ |

### Recommended README Wording

**Current**: "18 signals from 14 metadata sources"

**Proposed (more accurate)**:
```
Analyzes 14 metadata sources to extract 28+ signals across 6 dimensions:
- Structure (4): tokens, files, interfaces, dependencies
- Architecture (4): layers, orphans, circulars, impact
- History (3): risk, coupling, freshness
- Complexity (3): cyclomatic, hotspots, priority score
- Behavior (8): side effects (5 types), inputs, mutations, logic maps
- Coverage (6): test files, functions, types, tested/untested dirs, fixtures
```

---

## Section Accuracy Verification

### WARM_START.md Sections

| Section | Debug File | Accuracy | Notes |
|---------|------------|----------|-------|
| 1. System Context (Mermaid) | section_01_context.json | ✅ | Diagram generated from deps data |
| 2. Architecture Overview | section_02_overview.json | ✅ | Layer counts accurate |
| 3. Critical Classes | section_03_classes.json | ✅ | 7 classes extracted, truncated to 3 displayed |
| 4. Data Flow | N/A | ⚠️ | Not implemented |
| 5. Entry Points | raw_data.json | ✅ | 10 entry points detected |
| 6. Context Hazards | section_06_hazards.json | ✅ | 178 large files identified |
| 7. Quick Verification | N/A | N/A | Static content |
| 8. X-Ray Commands | N/A | N/A | Static content |
| 9. Architecture Layers | section_09_layers.json | ✅ | 4 layers with correct module counts |
| 10. Risk Assessment | section_10_risk.json | ✅ | 147 files with risk scores |
| 11. Hidden Coupling | section_11_coupling.json | ✅ | 9 coupling pairs |
| 12. Potential Dead Code | section_12_deadcode.json | ✅ | 130 orphan modules |
| 13. Test Coverage | section_13_test_coverage.json | ✅ | Metadata accurate |

### HOT_START.md Sections

| Section | Debug File | Accuracy | Notes |
|---------|------------|----------|-------|
| 1. System Dynamics | priorities.json | ✅ | 10 priority files with 5-signal scoring |
| 2. Logic Maps | logic_maps.json | ✅ | 10 methods analyzed with full detail |
| 3. Dependency Verification | verification.json | ✅ | 20 files verified |
| 4. Hidden Dependencies | analysis_data.json | ✅ | 54 env vars, 3 services, 1 config |
| 5. Module Dependencies | analysis_data.json | ✅ | From Phase 1 data |
| 5.5 Git Analysis | analysis_data.json | ✅ | Risk, coupling, freshness from Phase 1 |
| 6. Logic Map Legend | N/A | N/A | Static content |
| 7. Developer Activity | N/A | N/A | Placeholder (not implemented) |
| 8. Reference | N/A | N/A | Static content |

---

## Untapped Data: Quick Wins

| Addition | Source | Lines | Value | Priority |
|----------|--------|-------|-------|----------|
| TODO/FIXME counts | Regex | ~10 | High - tech debt visibility | P1 |
| Type annotation coverage % | AST | ~20 | High - code maturity | P1 |
| Author expertise per file | Git blame | ~30 | High - ownership clarity | P1 |
| Async/await distinction | AST | ~15 | Medium - concurrency understanding | P2 |
| Decorator inventory | AST | ~15 | Medium - patterns | P2 |
| Commit size (LOC added/removed) | Git log | ~20 | Medium - change magnitude | P2 |
| Method count per file | AST | ~5 | Low - size metric | P3 |
| Call graph | AST | ~50 | High - flow understanding | P2 |

---

## Appendix: Debug Output Reference

### Directory Structure
```
examples/kosmos/
├── WARM_START_debug/
│   ├── raw_data.json           # 468KB - All extracted data
│   ├── section_01_context.json # Mermaid diagram data
│   ├── section_02_overview.json # Architecture overview
│   ├── section_03_classes.json  # Critical classes
│   ├── section_06_hazards.json  # Large files
│   ├── section_09_layers.json   # Layer classification
│   ├── section_10_risk.json     # Risk scores
│   ├── section_11_coupling.json # Coupling pairs
│   ├── section_12_deadcode.json # Orphan modules
│   └── section_13_test_coverage.json
│
└── HOT_START_debug/
    ├── analysis_data.json    # 672KB - All analysis data
    ├── logic_maps.json       # 21KB - Flow diagrams
    ├── priorities.json       # 7KB - Priority files with metrics
    └── verification.json     # 4KB - Import verification results
```

### Sample Data Structures

**Priority File Entry** (priorities.json):
```json
{
  "path": "kosmos/agents/research_director.py",
  "score": 0.667,
  "metrics": {
    "cc": 235,
    "imp_score": 0.15,
    "risk": 0.82,
    "freshness": 0.5,
    "untested": null
  },
  "hotspots": {
    "_do_execute_action": 31,
    "decide_next_action": 23,
    "__init__": 11
  }
}
```

**Logic Map Entry** (logic_maps.json):
```json
{
  "method": "_do_execute_action",
  "line": 1788,
  "complexity": 31,
  "flow": ["-> action == NextAction.GENERATE_HYPOTHESIS?", "  -> ..."],
  "side_effects": [],
  "inputs": [],
  "state_mutations": ["self._actions_this_iteration"],
  "conditions": ["action == NextAction.GENERATE_HYPOTHESIS", "..."],
  "signature": "async def _do_execute_action(self, action: NextAction)",
  "docstring": "Internal async method to execute action."
}
```

**Risk Score Entry** (raw_data.json):
```json
{
  "file": "kosmos/config.py",
  "risk_score": 0.96,
  "churn": 23,
  "hotfixes": 14,
  "authors": 4
}
```

---

## Conclusion

The repo-xray two-pass analysis system extracts **comprehensive metadata** from Python codebases. The claim of "18 signals from 14 metadata sources" is:

- **Accurate for sources**: 14 distinct metadata sources confirmed
- **Conservative for signals**: 28+ grouped signals, 72+ sub-signals extracted

The system provides excellent coverage for cold start understanding, with the highest-value untapped opportunities being:
1. TODO/FIXME detection (tech debt)
2. Type annotation coverage (code maturity)
3. Author expertise via git blame (ownership)
4. Call graph analysis (flow understanding)

These additions would require approximately 100-150 lines of code total and would enhance the cold start context significantly.

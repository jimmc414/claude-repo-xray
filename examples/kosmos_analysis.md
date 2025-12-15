# Codebase Analysis: kosmos

Generated: 2025-12-14T07:59:44.606387Z | Preset: full | Files: 793

## Summary

| Metric | Value |
|--------|-------|
| Python files | 793 |
| Total lines | 278,390 |
| Functions | 2147 |
| Classes | 1542 |
| Type coverage | 36.1% |
| Est. tokens | 2,394,233 |

## Complexity Hotspots

*Functions with highest cyclomatic complexity:*

| CC | Function | File |
|----|----------|------|
| 67 | `main` | cli.py |
| 36 | `load_from_github` | skill_loader.py |
| 34 | `create_compression_callback` | event_compression.py |
| 29 | `handle_read_skill_document` | mcp_handlers.py |
| 28 | `recalc` | recalc.py |
| 28 | `recalc` | recalc.py |
| 28 | `recalc` | recalc.py |
| 27 | `test_anthropic_specific_skills` | test_integration.py |
| 26 | `validate_csv` | prepare_batch_csv.py |
| 25 | `main` | main.py |

## Import Analysis

### Architectural Layers

**FOUNDATION** (92 modules)

- `kosmos.core.logging`
- `kosmos.config`
- `kosmos.models.hypothesis`
- `kosmos.literature.base_client`
- `kosmos.models.experiment`
- *...and 87 more*

**CORE** (298 modules)

- `kosmos.agents.research_director`
- `kosmos.knowledge.vector_db`
- `kosmos.execution.executor`
- `kosmos.knowledge.graph`
- `kosmos.safety.code_validator`
- *...and 293 more*

**ORCHESTRATION** (146 modules)

- `kosmos.core.workflow`
- `kosmos.workflow.research_loop`
- `kosmos.world_model.factory`
- `kosmos.agents.literature_analyzer`
- `kosmos.core.cache_manager`
- *...and 141 more*

**LEAF** (257 modules)

- `kosmos.alembic.versions.2ec489a3eb6b_initial_schema`
- `kosmos.alembic.versions.dc24ead48293_add_profiling_tables`
- `kosmos.alembic.versions.fb9e61f33cbf_add_performance_indexes`
- `kosmos.docs.conf`
- `kosmos.examples.02_biology_gene_expression`
- *...and 252 more*

### Circular Dependencies

- `kosmos.world_model` <-> `kosmos.world_model.artifacts`
- `kosmos.core.llm` <-> `kosmos.core.providers.anthropic`

### Orphan Candidates

*Files with no importers (may be entry points or dead code):*

- `/mnt/c/python/kosmos/examples/03_placeholder.py`
- `/mnt/c/python/kosmos/examples/04_placeholder.py`
- `/mnt/c/python/kosmos/examples/05_placeholder.py`
- `/mnt/c/python/kosmos/examples/06_placeholder.py`
- `/mnt/c/python/kosmos/examples/07_placeholder.py`

## Cross-Module Calls

*Most called functions across modules:*

| Function | Call Sites | Modules |
|----------|------------|---------|
| `fda_query.FDACache.set` | 267 | 76 |
| `main` | 203 | 132 |
| `get_config` | 85 | 39 |
| `reset_config` | 82 | 7 |
| `get_world_model` | 58 | 13 |
| `reset_world_model` | 41 | 9 |
| `get_icon` | 36 | 10 |
| `model_to_dict` | 33 | 15 |
| `print_error` | 32 | 9 |
| `get_bounding_box_messages` | 30 | 1 |

## Git History Analysis

### High-Risk Files

*Files with high churn, hotfixes, or author entropy:*

| Risk | File | Factors |
|------|------|---------|
| 0.96 | `config.py` | churn:23 hotfix:14 authors:4 |
| 0.82 | `research_director.py` | churn:17 hotfix:13 authors:3 |
| 0.71 | `llm.py` | churn:11 hotfix:5 authors:3 |
| 0.68 | `executor.py` | churn:9 hotfix:5 authors:3 |
| 0.67 | `run.py` | churn:11 hotfix:9 authors:2 |

### Freshness

- **Active** (< 30 days): 672 files
- **Aging** (30-90 days): 132 files
- **Stale** (90-180 days): 0 files
- **Dormant** (> 180 days): 0 files

## Side Effects

*Functions with external I/O operations:*

### ENV
- `os.environ.get` in config_manager.py:73
- `os.environ.get` in config_manager.py:74
- `os.environ.get` in config_manager.py:72
- `os.environ.get` in config_manager.py:122
- `os.environ.get` in config_manager.py:255

### SUBPROCESS
- `subprocess.run` in provider_detector.py:46
- `subprocess.run` in provider_detector.py:59
- `subprocess.run` in test_runner.py:120
- `subprocess.run` in test_runner.py:186
- `subprocess.run` in setup_environment.py:47

### FILE
- `json.dumps` in report_generator.py:105
- `json.dumps` in biorxiv_search.py:432
- `json.dumps` in query_clinicaltrials.py:215
- `json.dump` in query_clinpgx.py:106
- `xml_file.write_bytes` in unpack.py:24

### DB
- `cursor.execute` in smoke-test.py:138
- `session.commit` in experiment_designer.py:783
- `session.commit` in hypothesis_generator.py:469
- `cursor.execute` in experiment_cache.py:247
- `cursor.execute` in experiment_cache.py:264

### API
- `requests.Session` in biorxiv_search.py:40
- `requests.get` in query_clinicaltrials.py:87
- `requests.get` in query_clinicaltrials.py:110
- `requests.get` in query_clinpgx.py:36
- `requests.get` in query_clinpgx.py:55

## Test Coverage

**205** test files, **~3693** test functions

| Type | Files |
|------|-------|
| `unit/` | 98 |
| `requirements/` | 58 |
| `integration/` | 32 |
| `e2e/` | 12 |
| `manual/` | 3 |

**Tested:** `agents`, `analysis`, `biology`, `cli`, `compression`, `core`, `data_analysis`, `db`

## Technical Debt

**22** markers found:

- **TODO**: 14
- **BUG**: 5
- **OPTIMIZE**: 3

## Decorator Usage

- `@patch`: 506
- `@fixture`: 386
- `@requirement`: 335
- `@priority`: 330
- `@asyncio`: 202
- `@unit`: 155
- `@dataclass`: 111
- `@staticmethod`: 94
- `@integration`: 42
- `@property`: 40

## Async Patterns

- Async functions: 423
- Sync functions: 8821
- Async for loops: 22
- Async context managers: 21

---

*Generated by Repo X-Ray v2.0.0*
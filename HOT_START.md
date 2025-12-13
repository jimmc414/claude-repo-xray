# skills: Semantic Hot Start (Pass 2: Behavioral Analysis)

> Semantic analysis companion to WARM_START.md
> Generated: 2025-12-13T12:47:41.148697
> Priority files analyzed: 10
> Detail level: 4 (full)
>
> **Pass 2** extracts behavioral metadata: control flow, logic maps, method signatures, and module relationships.
> See **WARM_START.md** for Pass 1 (structural analysis).

---

## 1. System Dynamics

High-density logic maps of the system's critical paths.

### Targeting Summary

| Rank | File | Priority Score | Factors |
|------|------|----------------|---------|
| 1 | `repo-xray/scripts/dependency_graph.py` | 0.673 | CC:190 Imp:1.0 Risk:0 |
| 2 | `repo-investigator/scripts/generate_hot_start.py` | 0.425 | CC:191 Imp:0 Risk:0 |
| 3 | `repo-xray/lib/ast_utils.py` | 0.405 | CC:89 Imp:0.67 Risk:0 |
| 4 | `repo-xray/scripts/generate_warm_start.py` | 0.403 | CC:179 Imp:0 Risk:0 |
| 5 | `repo-investigator/scripts/verify.py` | 0.32 | CC:88 Imp:0.33 Risk:0 |
| 6 | `repo-investigator/scripts/smart_read.py` | 0.307 | CC:81 Imp:0.33 Risk:0 |
| 7 | `repo-xray/scripts/git_analysis.py` | 0.305 | CC:80 Imp:0.33 Risk:0 |
| 8 | `repo-investigator/scripts/complexity.py` | 0.301 | CC:78 Imp:0.33 Risk:0 |
| 9 | `repo-xray/scripts/mapper.py` | 0.224 | CC:36 Imp:0.33 Risk:0 |
| 10 | `repo-xray/scripts/configure.py` | 0.211 | CC:74 Imp:0 Risk:0 |

**Factor Legend**: CC=Cyclomatic Complexity, Imp=Import Weight (how many modules depend on this), Risk=Git churn risk score, Untested=No test coverage detected

---

## 2. Logic Maps

### build_dependency_graph

```python
def build_dependency_graph(directory: str, root_package: Optional[str]=None, auto_detect: bool=True, source_dir: Optional[str]=None) -> Dict
```

> Build a dependency graph for all Python files.

**Entry Point**: `repo-xray/scripts/dependency_graph.py:build_dependency_graph` (L279)
**Complexity**: CC=47
**Priority Score**: 0.673

#### Data Flow
```
build_dependency_graph():
  -> root_package is None and auto_detect?
    -> root_package?
  -> source_dir is None and root_package is None?
    -> source_dir and source_dir != directory?
  * for (root, dirs, files) in os.walk(directory):
    * for filename in files:
      -> not filename.endswith('.py')?
      -> source_dir and filepath.startswith(source_dir)?
      * while module_name.startswith('.'):
      -> root_package and not module_name.startswith(root_package)?
  * for mod_name in modules:
  * for (module_name, info) in modules.items(...):
    * for imp in abs_imports:
      -> imp in modules?
      -> not target?
        * for known_module in modules:
          -> known_module.startswith(...)?
      -> not target?
        * for known_module in modules:
          -> imp.startswith(...)?
      -> not target and base in leaf_to_modules?
        -> len(candidates) == 1?
          -> candidates?
            * for cand in candidates:
              -> os.path.dirname(cand_file) == module_dir?
            -> not target?
      -> target and target != module_name?
        -> target not in info['imports']?
        -> not target and base not in EXTERNAL_PACKAGES?
    * for rel_imp in rel_imports:
      * while target and target not in modules:
      -> target and target != module_name?
        -> target not in info['imports']?
  * for (a, b) in internal_edges:
    -> (b, a) in seen_pairs?
  -> Return({...})
```

---

### detect_source_root

```python
def detect_source_root(directory: str) -> Optional[str]
```

> Detect the logical source root for Python files.

**Entry Point**: `repo-xray/scripts/dependency_graph.py:detect_source_root` (L206)
**Complexity**: CC=20
**Priority Score**: 0.673

#### Data Flow
```
detect_source_root():
  * for (root, dirs, files) in os.walk(directory):
    -> py_files?
  -> not py_dirs?
    -> Return(None)
  -> len(py_dirs) == 1?
    -> Return(py_dirs[0][0])
  -> rel_path != '.' and len(...) >= 2?
    * for (py_dir, _) in py_dirs:
      * for py_file in Path(py_dir).glob('*.py'):
        try:
          -> 'sys.path.insert' in content or 'sys.path.append' in content?
            -> Return(str(py_dir))
        ! except Exception
  -> len(py_dirs) > 1?
    * for p in paths[...]:
      * for (i, (a, b)) in enumerate(...):
        -> a == b?
    -> common_parts?
      -> common_path != directory?
        -> Return(common_path)
  -> Return(None)
```

---

### collect_analysis_data

```python
def collect_analysis_data(directory: str, deps_path: str, git_path: str, warm_start_debug: Optional[str], top_n: int=10, verbose: bool=False, detail_level: int=2) -> Dict[str, Any]
```

> Collect all analysis data for HOT_START generation.

**Entry Point**: `repo-investigator/scripts/generate_hot_start.py:collect_analysis_data` (L483)
**Complexity**: CC=41
**Priority Score**: 0.425

#### Data Flow
```
collect_analysis_data():
  -> PHASE1_AVAILABLE?
    -> verbose?
    try:
      * for (mod_name, info) in modules.items(...):
        * for imp in info.get('imports', ...):
      * for (mod_name, info) in modules.items(...):
        -> filepath?
          -> short_name not in mod_to_file?
      -> import_weights?
        * for (mod_name, weight) in import_weights.items(...):
          -> mod_name in mod_to_file?
          -> short_name in mod_to_file?
      -> verbose?
      -> verbose?
    ! except Exception
  -> not imports and deps_path and os.path.exists(deps_path) and git_path and os.path.exists(git_path)?
    -> verbose?
  -> verbose?
  -> not files?
    -> verbose?
    -> Return(data)
  -> verbose?
  * for filepath in files:
    -> cc > 0?
  * for (filepath, cc_val) in raw_cc.items(...):
    -> use_5_signal?
      -> imports or risks?
  -> verbose?
  * for priority in data['priorities'][...]:
    -> not hotspots?
    -> not generator.parse(...)?
    * for (method_name, cc) in top_methods:
      -> logic_map?
  -> verbose?
  * for filepath in files[...]:
  -> verbose?
  -> Return(data)
```

---

### generate_hot_start_md

```python
def generate_hot_start_md(data: Dict, detail_level: int=2) -> str
```

> Generate HOT_START.md content from collected data.

**Entry Point**: `repo-investigator/scripts/generate_hot_start.py:generate_hot_start_md` (L758)
**Complexity**: CC=40
**Priority Score**: 0.425

#### Data Flow
```
generate_hot_start_md():
  * for (i, p) in enumerate(..., ...):
    -> m.get('untested') is not None?
  -> detail_level == 1?
    -> Return('\n'.join(lines))
  -> data['logic_maps']?
    * for lm in data['logic_maps']:
      -> detail_level >= 4?
        -> lm.get('signature')?
        -> lm.get('docstring')?
      -> lm['side_effects']?
        * for se in lm['side_effects']:
      -> lm['state_mutations']?
        * for sm in lm['state_mutations']:
  -> verified?
    * for v in verified[...]:
  -> broken?
    * for v in broken:
  -> warnings?
    * for v in warnings[...]:
      * for w in v['warnings']:
  -> data['hidden_deps']['env_vars']?
    * for var in data['hidden_deps']['env_vars']:
  -> data['hidden_deps']['external_services']?
    * for svc in data['hidden_deps']['external_services']:
  -> data['hidden_deps']['config_files']?
    * for cfg in data['hidden_deps']['config_files']:
  -> edges or import_weights?
    -> import_weights?
      * for (mod, count) in sorted_weights[...]:
        -> count > 0?
    -> edges?
      * for (a, b) in edges:
        -> a not in edge_by_source?
      * for source in sorted(...):
  -> Return('\n'.join(lines))
```

---

### _process_class

```python
def _process_class(node: ast.ClassDef, lines: List[str], indent: int, include_private: bool, include_line_numbers: bool)
```

> Process a class definition with fields and decorators.

**Entry Point**: `repo-xray/lib/ast_utils.py:_process_class` (L113)
**Complexity**: CC=16
**Priority Score**: 0.405

#### Data Flow
```
_process_class():
  -> ...?
  * for child in node.body:
    -> isinstance(child, ...) and isinstance(..., ...)?
      -> child.value?
      -> isinstance(child, ...)?
        * for target in child.targets:
          -> isinstance(target, ...)?
        -> isinstance(child, ...)?
          -> include_private or not child.name.startswith('_') or child.name.startswith('__') and child.name.endswith('__')?
          -> isinstance(child, ...)?
  -> not has_content?
```

---

### get_skeleton

```python
def get_skeleton(filepath: str, include_private: bool=False, include_line_numbers: bool=True) -> Tuple[str, int, int]
```

> Extract the skeleton (interface) of a Python file using AST.

**Entry Point**: `repo-xray/lib/ast_utils.py:get_skeleton` (L16)
**Complexity**: CC=13
**Priority Score**: 0.405

#### Data Flow
```
get_skeleton():
  try:
    -> Return((..., 0, 0))
    -> Return((..., 0, 0))
  ! except SyntaxError
  ! except Exception
  -> ...?
  * for node in tree.body:
    -> isinstance(node, ...)?
      * for target in node.targets:
        -> isinstance(target, ...) and target.id.isupper(...)?
      -> isinstance(node, ...)?
        -> isinstance(node, ...)?
          -> include_private or not node.name.startswith('_')?
  -> Return((skeleton, original_tokens, skeleton_tokens))
```

---

### detect_entry_points

```python
def detect_entry_points(directory: str, graph: Dict, layers: Dict, root_package: str='') -> List[Dict]
```

> Find CLI and API entry points.

**Entry Point**: `repo-xray/scripts/generate_warm_start.py:detect_entry_points` (L203)
**Complexity**: CC=20
**Priority Score**: 0.403

#### Data Flow
```
detect_entry_points():
  -> Return(any(...))
  * for (module_name, info) in modules.items(...):
    -> should_skip_file(filepath)?
    -> filename in entry_patterns?
      -> filename in existing_filenames?
    -> filepath and os.path.exists(filepath)?
      -> not is_relevant?
      try:
        -> 'if __name__ ==' in content or 'if __name__==' in content?
          -> module_name not in ...?
      ! except Exception
  * for module_name in layers.get('orchestration', ...):
    -> any(...)?
      -> module_name not in ...?
  * for ep in entry_points:
  -> Return(entry_points[...])
```

---

### analyze_test_coverage

```python
def analyze_test_coverage(directory: str, source_modules: Dict) -> Dict
```

> Analyze test coverage metadata without reading test content.

**Entry Point**: `repo-xray/scripts/generate_warm_start.py:analyze_test_coverage` (L381)
**Complexity**: CC=18
**Priority Score**: 0.403

#### Data Flow
```
analyze_test_coverage():
  * for test_dir in test_dirs:
    -> test_path.exists(...)?
      * for py_file in test_path.rglob('*.py'):
        -> py_file.name == 'conftest.py'?
          try:
          ! except Exception
  * for test_file in test_files:
    try:
    ! except Exception
  * for test_file in test_files:
    -> len(parts) >= 2?
      -> test_type.endswith('.py')?
      -> test_type not in coverage_by_type?
      * for part in parts[...]:
        -> not part.startswith('test_') and not part.startswith('__') and not part.endswith('.py')?
  * for module_name in source_modules.keys(...):
    -> len(parts) >= 2?
  -> Return({...})
```

---

### main

```python
def main()
```

**Entry Point**: `repo-investigator/scripts/verify.py:main` (L335)
**Complexity**: CC=24
**Priority Score**: 0.32

#### Data Flow
```
main():
  -> is_directory?
    -> args.debug?
    -> args.json?
      * for r in results:
        -> r['warnings']?
          * for w in r['warnings']:
        -> r['status'] == 'FAIL'?
    -> fail_count > 0?
    -> Return
  -> is_file and not os.path.exists(path)?
    -> os.path.exists(...)?
  -> args.mode == 'safe' or is_file?
    -> not is_file?
    -> warnings?
    -> args.json?
      -> not ok?
  -> args.mode == 'strict'?
    -> args.json?
      -> not ok?
```

---

### check_safe

```python
def check_safe(filepath: str, verbose: bool=False) -> Tuple[bool, str, List[str]]
```

> AST-based verification (no execution).

**Entry Point**: `repo-investigator/scripts/verify.py:check_safe` (L55)
**Complexity**: CC=19
**Priority Score**: 0.32

#### Data Flow
```
check_safe():
  -> verbose?
  -> not os.path.exists(filepath)?
    -> Return((False, 'File not found', warnings))
  try:
    -> Return((False, ..., warnings))
    -> Return((False, ..., warnings))
  ! except SyntaxError
  ! except Exception
  * for node in ast.walk(tree):
    -> isinstance(node, ...)?
      * for alias in node.names:
        -> mod in STDLIB_MODULES?
        -> not _module_exists_locally(mod, cwd)?
          -> _is_likely_external(mod)?
      -> isinstance(node, ...)?
        -> node.level > 0?
        -> node.module?
          -> mod in STDLIB_MODULES?
          -> not _module_exists_locally(mod, cwd)?
            -> _is_likely_external(mod)?
  -> missing?
  -> external?
  -> Return((True, 'AST Valid', warnings))
```

---

## 3. Dependency Verification

**Summary**: 15 passed, 0 failed

### Verified Modules
- `repo-investigator/scripts/complexity.py`
- `repo-investigator/scripts/generate_hot_start.py`
- `repo-investigator/scripts/smart_read.py`
- `repo-investigator/scripts/verify.py`
- `repo-xray/lib/ast_utils.py`
- `repo-xray/lib/token_estimator.py`
- `repo-xray/lib/__init__.py`
- `repo-xray/scripts/configure.py`
- `repo-xray/scripts/dependency_graph.py`
- `repo-xray/scripts/generate_warm_start.py`

### Broken Paths
*None detected*

### Warnings
- `repo-investigator/scripts/generate_hot_start.py`: Potential missing imports: complexity, smart_read, verify, dependency_graph
- `repo-xray/scripts/generate_warm_start.py`: Potential missing imports: dependency_graph, git_analysis, mapper, lib.ast_utils
- `repo-xray/scripts/skeleton.py`: Potential missing imports: lib.ast_utils
- `repo-xray/tests/test_generate_warm_start.py`: Potential missing imports: dependency_graph
- `repo-xray/tests/test_generate_warm_start.py`: External dependencies: pytest

---

## 4. Hidden Dependencies

### Environment Variables
*None detected*

### External Services
*None detected*

### Configuration Files
*None detected*

---

## 5. Module Dependencies

### Foundation Modules

Modules imported by multiple other modules (high import weight):

| Module | Imported By |
|--------|-------------|
| `dependency_graph` | 3 modules |
| `lib.ast_utils` | 2 modules |
| `repo-investigator.scripts.complexity` | 1 modules |
| `repo-investigator.scripts.smart_read` | 1 modules |
| `repo-investigator.scripts.verify` | 1 modules |
| `git_analysis` | 1 modules |
| `mapper` | 1 modules |

### Internal Dependencies

How modules connect (A imports B):

```
generate_warm_start -> dependency_graph, git_analysis, mapper, ast_utils
generate_hot_start -> complexity, smart_read, verify, dependency_graph
skeleton -> ast_utils
test_generate_warm_start -> dependency_graph
```

---

## 6. Logic Map Legend

```
->    : Control flow
[X]   : Side effect (DB write, API call, file I/O)
<X>   : External input (user input, API response)
{X}   : State mutation (object modification)
?     : Conditional branch
*     : Loop iteration
!     : Exception/error path
```

---

## 7. Reference

This document complements:
- WARM_START.md (structural architecture)
- Phase 1 tools (repo-xray)

To refresh: `python generate_hot_start.py . -v`

---

*Generated by repo-investigator*
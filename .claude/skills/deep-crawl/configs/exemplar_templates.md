# Structural Exemplar Templates

Structural skeletons showing what elements each section type should contain. Use `{placeholder}` markers where codebase-specific identifiers go. For quality reference from the current repo, see `/tmp/deep_crawl/findings/calibration/cal_{type}.md` (generated during Phase 1b).

---

## Template 1: Change Impact Index

Target: hub module table + hidden coupling bullets + blast radius ranking + safe/dangerous lists.

```markdown
### {Cluster Name}

| Hub Module | Imported By | Blast Radius | High-Impact Functions | Signature Change Breaks | Behavior Change Breaks |
|------------|-------------|-------------|----------------------|------------------------|----------------------|
| `{module_path}` | {N} production modules + {M} {pattern} importers | {affected_count} affected, {risk} risk, {max_hops} hops | `{function}()` ({call_count} call sites, {impact_level}), `{constant}` ({importer_count} importers, {impact_level}) | {Describe what breaks on rename/signature change} [FACT] ({file}:{line}). {Describe downstream model impacts} [FACT] — {explain silent consequence}. | `{function}()` {describe hidden side effect} [FACT] ({file}:{line}) — {explain why callers don't expect this}. |

**Hidden coupling discovered:**
- `{entity}` ({visibility hint} = "{actual visibility}") is imported by {N} external modules [FACT] ({file}:{line}) — de facto public API. {Describe breaking change consequence}.
- `{class}.{method}` resolves {resource} against `{path_expression}` [FACT] ({file}:{line}) — {describe what moving/renaming silently changes}.

**Blast radius ranking:**
1. `{Entity}` class — {N} importers + {M} manual mapping sites + {K} representations (highest risk)
2. `{Entity}` dataclass — {N} importers across {layer_a} + {layer_b} layers

**Test coverage gaps (from blast radius):**
- `{module_a}` depends on `{hub}` (2 hops) but has never been co-modified — 0 historical co-changes. [ABSENCE]

**Safe changes:** {List changes that won't break callers}. {List changes isolated to low-impact modules}.
**Dangerous changes:** {Rename/move that breaks N importers}. {Return type change affecting N callers}. {File move that breaks path resolution}.
```

---

## Template 2: Change Playbook

Target: ordered steps with file:line targets + [FACT] density + common mistakes format.

```markdown
### {Scenario Title}

#### 1. {First step description}
{Action with specific guidance}. Every existing {entity_type} has a dedicated {artifact} [FACT] (`{example_path_1}`, `{example_path_2}`, `{example_path_3}`). Follow the {convention_name} convention: {describe convention} [PATTERN: {N}/{M} {entities}]. Use `{specific_api}` for {reason} [FACT] ({file}:{line}).

#### 2. {Second step description}
Create `{target_path}`. {Base class or interface} [FACT] ({file}:{line}) with this {pattern_name} pattern:
    {code_snippet_showing_expected_structure}
This {pattern} is used by all {entity_type} [PATTERN: {N}/{M} {entities} — {file_a}:{line}, {file_b}:{line}].

#### 3. {Third step description}
{Describe wiring/integration step with specific targets}.
1. {Sub-step with lazy-init pattern} [FACT] ({file}:{line})
2. {Sub-step with call convention} [FACT] ({file}:{line})
3. {Sub-step with tracking/metrics} [FACT] ({file}:{line})
4. {Sub-step with state transition} [FACT] ({file}:{line})
5. {Sub-step with error handling} [FACT] ({file}:{line})

**Common Mistakes:**
1. {Mistake description} — {why it's wrong and what happens} [FACT] ({file}:{line})
2. {Mistake description} — {behavioral consequence of omission}
3. {Mistake description} — {describe state corruption or race condition}
4. {Mistake description} — {describe silent data loss or degradation}
5. {Mistake description} — {describe incorrect error propagation}
6. {Mistake description} — {describe test isolation failure}
7. {Mistake description} — {describe configuration ordering issue}
8. {Mistake description} — {describe deployment/runtime surprise}
```

---

## Template 3: Data Contract

Target: table rows with cross-boundary flow + non-trivial gotchas.

```markdown
| Model | File | Type | Key Fields | Serialization | Cross-Boundary Flow | Gotcha |
|-------|------|------|------------|---------------|---------------------|--------|
| `{ModelName}` | `{file}:{line}` | {Pydantic/dataclass/TypedDict/NamedTuple} | {field_1}, {field_2}, {field_3}, {field_4} | {Custom method name or stdlib mechanism} | Created by {ProducerComponent} -> consumed by {N}+ modules | **{Gotcha title}**: {Describe representation mismatch, missing fields, or silent conversion issue}. {Detail which representations coexist}. {Explain manual update requirement}. [FACT: {file_a}:{line} vs {file_b}:{line}] |
| `{ModelName}` | `{file}:{line}` | {type} | {fields} | `{serialization_method}` ({mechanism}) | Created by {producer} -> consumed by {consumers} via `{interface}()` | **{Gotcha title}**: {Describe dual-type contract or interface mismatch}. {N}+ {workaround_type} bridge the gap, but `{check_expression}` breaks. [FACT: {file}:{line}] |
```

---

## Template 4: Critical Path Trace

Target: hop chain with branching and error paths, [FACT] at every hop.

```markdown
### Path {N}: {Entry Description} to {Terminal Effect}

`{entry_function}()` ({file}:{line})
  [FACT] {Function type/decorator}. Accepts {params}. ({file}:{line})

  Branching at entry:
  - If {condition_a} -> calls `{branch_a_function}()` ({file}:{line})
  - If {condition_b} -> {early_exit_behavior} ({file}:{line})

  Data transformation: {Describe parameter reshaping/mapping} ({file}:{line}). [FACT]

  -> `{NextClass}.{method}()` ({file}:{line})
    Sub-hops during {method}:
    -> `{dependency_call}()` ({file}:{line}) -- {Behavioral note}. [FACT] ({file}:{line})
    -> `{side_effect_call}()` ({file}:{line}) -- [SIDE EFFECT: {effect_type}]
    -> `{external_call}()` ({file}:{line}) -- [SIDE EFFECT: {effect_type}]

  -> `{async_or_sync_bridge}({...})` ({file}:{line})
    Phase A: `await {phase_a_call}({...})`
    Phase B: while {loop_condition}...
      -> `{iteration_call}()` ({file}:{line})
      -> {describe state mutation per iteration}

  Error path:
  - If {failure_condition}: {describe error handling} [FACT] ({file}:{line})
  - {Describe retry/fallback behavior if present}
```

---

## Template 5: Gotcha Entry

Target: domain-cluster headers (derived from investigation subsystems) + severity tags per entry + specific file:line evidence.

```markdown
### {Domain Cluster A} Gotchas

1. [CRITICAL] **{Gotcha title}** -- {Describe the dangerous behavior in one sentence}. If {condition}, this {consequence}. [FACT] (`{file_a}:{line}`, `{file_b}:{line}`)

2. [HIGH] **{Gotcha title}** -- {Describe silent degradation mechanism}. [FACT] (`{file_a}:{line}`, `{file_b}:{line}`)

3. [MEDIUM] **{Gotcha title}** -- {Describe confusing behavior}. [FACT] (`{file}:{line}`)

### {Domain Cluster B} Gotchas

4. [CRITICAL] **{Gotcha title}** -- {Describe data loss risk}. [FACT] (`{file_a}:{line}` vs `{file_b}:{line}`)

5. [HIGH] **{Gotcha title}** -- {Describe condition where valid input produces wrong output}. [FACT] ({file}:{line})

### {Domain Cluster C} Gotchas

6. [MEDIUM] **{Gotcha title}** -- {Describe why the code structure misleads developers}. [FACT] ({file}:{line})
```

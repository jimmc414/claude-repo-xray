# Phase Kickoff Prompts

Read PLAN_TS_SCANNER_PHASES.md for specs and PLAN_TS_SCANNER_GAP_AUDIT.md for the full gap analysis.

Copy-paste each prompt below to kick off the next phase. Each prompt is self-contained — it reads the plan, implements the tasks, runs verification, and marks the phase complete.

---

## Phase 2A Kickoff

```
Read PLAN_TS_SCANNER_PHASES.md and PLAN_TS_SCANNER_GAP_AUDIT.md, then implement Phase 2A (Integration Fixes + Git Analysis). This phase fixes bugs where existing TS scanner data isn't rendering because the Python formatter/gap_features assume Python-style data shapes.

The 7 tasks:
- 2A-1: Fix pillar dedup in gap_features.py:203 — split(".") collapses all .ts files to same key. For path-style keys (containing "/"), use Path(mod_name).stem instead.
- 2A-2: Fix mermaid safe IDs (slashes in paths produce invalid mermaid node IDs) and layer name mapping (TS uses "api"/"services"/etc, mermaid expects "orchestration"/"core"/"foundation"). Add _safe_mermaid_id() helper and _normalize_layers() that maps TS directory names to tiers.
- 2A-3: Make git_analysis.py language-aware — 6 filter points hardcode .py (lines 68, 106, 168, 218, 270, 519), plus function churn regex (line 364) only matches Python def/class. Add extensions parameter to all functions. xray.py _augment_with_git() and run_analysis() must pass the right extensions based on detected language.
- 2A-4: Fix class skeleton syntax in markdown_formatter.py — TS classes should use {} braces, // comments, and bare method names instead of Python "def" / ":" / "#" style. Also fix method signatures section.
- 2A-5: Fix orphan deduplication — same filename from different dirs appears multiple times in the orphan list. Deduplicate display names.
- 2A-6: Verify GitHub About works for TS projects — test if gap_features.get_github_about() triggers for TS scanner results. If gated behind Python-specific checks, remove the gate.
- 2A-7: Filter Node.js builtins from external deps — imports like "node:fs", "node:path", "node:process" should NOT appear in the external_deps list. They're builtins, not third-party packages. Fix in ts-scanner/src/import-analysis.ts getPackageName() or the external dep collection.

After implementation, run verification:
1. python xray.py /tmp/ccusage 2>/dev/null | grep -A 12 "Architectural Pillars" (should show ~10 rows)
2. python xray.py /tmp/ccusage 2>/dev/null | grep -c "subgraph" (should be >= 2)
3. python xray.py /tmp/ccusage 2>/dev/null | grep -A 5 "High-Risk\|Freshness" (should show populated git data)
4. python xray.py /tmp/ccusage 2>/dev/null | grep "def constructor" (should find NO matches)
5. python xray.py /tmp/ccusage 2>/dev/null | grep "node:fs" (should find NO matches in external deps)
6. python -m pytest tests/ -x -q (all pass)
7. cd ts-scanner && npm test (all pass)

When all verification passes, mark Phase 2A as complete in PLAN_TS_SCANNER_PHASES.md with status and date.
```

---

## Phase 2B Kickoff

```
Read PLAN_TS_SCANNER_PHASES.md and PLAN_TS_SCANNER_GAP_AUDIT.md (Part 1, Gaps 1-7), then implement Phase 2B (Behavioral Signals). Phase 2A is complete. This phase adds 9 new signals to the TS scanner — all are pattern-matching on known API calls or syntax patterns during the AST walk.

The 9 tasks:
- 2B-1: Silent failure detection — detect catch clauses with empty blocks or trivial console.log-only handlers. Add to walkPass1() in ast-analysis.ts. Populate the existing silent_failures array in FileAnalysis.
- 2B-2: Security concern detection — detect eval(), new Function(), innerHTML assignment, dangerouslySetInnerHTML, child_process.exec, document.write. Populate security_concerns array.
- 2B-3: Deprecation marker detection — detect @deprecated JSDoc tags (extend existing getJSDocSummary infrastructure) and @Deprecated() decorators. Populate deprecation_markers array.
- 2B-4: Side effect detection — detect fs.*, fetch(), http.request, process.exit, child_process.*, console.*, database patterns (prisma, .query, mongoose, knex). Record category, call text, line. Populate side_effects array AND aggregate into the top-level side_effects.by_type/by_file structure in index.ts.
- 2B-5: Test file detection — new file ts-scanner/src/test-analysis.ts. Classify files by naming convention (*.test.ts, *.spec.ts, __tests__/). Count describe/it/test calls. Detect framework from imports. Wire into index.ts output.
- 2B-6: Database query detection (Gap Audit Gap 2) — detect SQL keywords (SELECT, INSERT, UPDATE, DELETE, CREATE, DROP) in string literals and template literals. Also detect tagged template SQL (sql`...`). Populate sql_strings array.
- 2B-7: Environment variable detection (Gap Audit Gap 3) — detect process.env.KEY and process.env["KEY"] patterns. Extract key names and defaults from nullish coalescing (??) or logical OR (||). Emit as a new env_vars field on FileAnalysis, and aggregate to top-level. This is critical for deep_crawl's Configuration Surface section.
- 2B-8: Async violation detection (Gap Audit Gap 4) — when inside an async function (tracked via WalkContext.isAsync), detect calls to synchronous APIs: fs.readFileSync, fs.writeFileSync, child_process.execSync, etc. Populate async_violations array.
- 2B-9: Class field extraction (Gap Audit Gap 7) — extract class property declarations (including type, visibility modifier, and initializer) and constructor this.X = Y assignments. Add as instance_vars to ClassInfo so class skeletons include "# Instance variables:" like the Python output does.

For all signals, the types already exist in ts-scanner/src/types.ts (SilentFailure, SecurityConcern, etc.) — they were defined as stubs in Phase 0. For env_vars, you'll need to add a new interface. Populate them now.

Add tests for each new signal. Build with npm run build and verify:
1. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '[.structure.files[] | .silent_failures | length] | add'
2. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.side_effects.by_type | keys'
3. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.deprecation_markers | length'
4. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '[.structure.files[] | .env_vars // [] | length] | add' (should find process.env usage)
5. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '[.structure.files[] | .sql_strings | length] | add'
6. python xray.py /tmp/ccusage 2>/dev/null | grep -c "Side Effect\|Security\|Silent\|Environment"
7. cd ts-scanner && npm test (all pass)
8. python -m pytest tests/ -x -q (all pass)

When all verification passes, mark Phase 2B as complete in PLAN_TS_SCANNER_PHASES.md with status and date.
```

---

## Phase 2C Kickoff

```
Read PLAN_TS_SCANNER_PHASES.md and implement Phase 2C (Call Graph + Topological Layering). Phases 2A and 2B are complete. This phase adds cross-module call analysis, computes architecture tiers from import graph structure, and enables partial investigation targets.

The 3 tasks:

- 2C-1: Cross-module call analysis — new file ts-scanner/src/call-analysis.ts (~350 lines). Build an import binding table mapping local names to source modules during import parsing. During the AST walk, when a CallExpression's callee is an Identifier, look it up in the binding table. For namespace imports (import * as mod), handle mod.func() calls. Output must match the CallAnalysis interface in types.ts. Wire into index.ts.

- 2C-2: Topological layer computation — add to ts-scanner/src/import-analysis.ts (~80 lines). For each module compute ratio = imported_by_count / (imports_count + 1). Classify: ORCHESTRATION_KEYWORDS match → orchestration, FOUNDATION_KEYWORDS match → foundation, ratio > 2 → foundation, ratio < 0.5 and imports > 2 → orchestration, else → core, no edges → leaf. Emit as imports.tiers alongside existing imports.layers. Update the Python formatter/gap_features to read tiers when available (this improves the mermaid diagram from Phase 2A).

- 2C-3: Partial investigation targets — modify xray.py to call compute_investigation_targets() for TS projects by reshaping the TS scanner output into the ast_results format investigation_targets.py expects. Build gap_results with TS entry points and data models (convert ts_interfaces/ts_type_aliases to data_models format). Add "constructor" alongside "__init__" in convention_deviations. Add TS builtins (Promise, Record, Partial, etc.) to _BUILTIN_TYPES in compute_domain_entities.

Verification:
1. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.calls.summary'
2. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.imports.tiers | to_entries[] | "\(.key): \(.value | length)"'
3. python xray.py /tmp/ccusage 2>/dev/null | grep -A 15 "Investigation Targets"
4. python xray.py /tmp/ccusage 2>/dev/null | grep -c "subgraph" (should be >= 2, improved tiers)
5. cd ts-scanner && npm test (all pass)
6. python -m pytest tests/ -x -q (all pass)

When all verification passes, mark Phase 2C as complete in PLAN_TS_SCANNER_PHASES.md with status and date.
```

---

## Phase 2D Kickoff

```
Read PLAN_TS_SCANNER_PHASES.md and implement Phase 2D (Logic Maps + Advanced Git + Full Investigation Targets). Phases 2A-2C are complete. This phase adds the most complex remaining signals.

The 4 tasks:

- 2D-1: Logic maps — new file ts-scanner/src/logic-maps.ts (~400 lines). For the top N complex functions, walk the function body depth-first and generate a textual control-flow representation. IfStatement → "→ <condition>?", SwitchStatement → "→ switch(<expr>)", For/While → "→ for/while:", TryStatement/CatchClause, ReturnStatement → "→ Return(...)", ThrowStatement → "→ Throw(...)". Note TS-specific patterns: optional chaining (?.) as hidden branches, nullish coalescing (??), exhaustive switch on union types. Output: function name, file, line, complexity, summary string, and the map text. Wire into index.ts and the markdown formatter's Logic Maps section.

- 2D-2: Git function churn for TypeScript — in lib/git_analysis.py, the hunk regex at line ~364 only matches Python def/class. Add a TS-aware regex that matches: function declarations, async function, class, const/let/var assignments (for arrow functions), with optional export prefix. Select regex based on the extensions parameter added in Phase 2A. Handle multiple capture groups (function name position varies by construct).

- 2D-3: Full investigation targets — with call graph (2C-1), side effects (2B-4), and git (2A-3) all working, the remaining investigation_targets sub-functions should now produce output. Verify compute_entry_side_effect_paths works (needs entry_points + side_effects + call graph). Verify compute_domain_entities works with TS data models.

- 2D-4: Shared mutable state detection (expanded per Gap Audit Gap 5) — add to ts-scanner/src/ast-analysis.ts. Detect: (a) module-level let/var declarations (not const) at depth 0, (b) class static mutable fields, AND (c) this.prop = value mutations inside methods (Gap 5 — instance state mutations). Emit module-level state as shared_mutable_state. Emit instance mutations as state_mutations on ClassInfo. This replaces compute_shared_mutable_state() in investigation_targets.py which uses Python ast.parse() and silently fails on TS files.

Verification:
1. python xray.py /tmp/ccusage 2>/dev/null | grep -A 5 "Logic Map\|Summary:"
2. python xray.py /tmp/ccusage 2>/dev/null | grep -A 10 "Function-Level"
3. python xray.py /tmp/ccusage 2>/dev/null | grep -A 20 "Investigation Targets"
4. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '[.structure.files[] | .shared_mutable_state // [] | length] | add'
5. cd ts-scanner && npm test (all pass)
6. python -m pytest tests/ -x -q (all pass)

When all verification passes, mark Phase 2D as complete in PLAN_TS_SCANNER_PHASES.md with status and date.
```

---

## Phase 2E Kickoff

```
Read PLAN_TS_SCANNER_PHASES.md and implement Phase 2E (Polish + Edge Cases). Phases 2A-2D are complete. This is the final phase — handle remaining gaps and improve output quality.

The 5 tasks:

- 2E-1: CLI argument extraction (best-effort) — new file ts-scanner/src/cli-analysis.ts (~150 lines). Detect CLI framework from imports (commander, yargs, meow, cac, gunshi, clipanion). For commander and yargs (the two most common), extract arguments by pattern-matching .option() and .command() calls. For others, just report the framework name. Don't try to be exhaustive — 70% coverage is the target.

- 2E-2: Decorator aggregation in markdown — the TS scanner emits decorators.inventory with counts. Verify the markdown formatter's decorator section triggers for TS data. Fix any gate check that prevents it from rendering.

- 2E-3: Context hazards improvements — when language is typescript/mixed, add TS-standard skip directories to the context hazards section: node_modules/, dist/, build/, .next/, .nuxt/, coverage/. Currently only .git/ is shown.

- 2E-4: Re-export resolution in import graph — in ts-scanner/src/import-analysis.ts, after building the initial graph, detect barrel files (files where >80% of content is re-exports). Optionally add transitive edges so hub detection counts the actual source modules rather than the barrel. This is a nice-to-have that improves accuracy by ~2-3%.

- 2E-5: Persona map for TS projects — verify that the persona map detection in gap_features.py runs regardless of language. It reads .md files, not code, so it should be language-agnostic. If gated behind Python-specific checks, remove the gate.
- 2E-6: TS config rule extraction (Gap Audit Gap 6) — parse tsconfig.json strict flags (strict, noImplicitAny, strictNullChecks, noUnusedLocals, etc.) and report them as project conventions. Also detect presence of eslint config (eslint.config.js, .eslintrc*) and prettier config (.prettierrc*) and report which tools are configured, even if we don't parse the JS config contents. This feeds the Conventions section of DEEP_ONBOARD. ~80 lines, either in gap_features.py (reading JSON config files is language-agnostic) or as a new TS scanner module.

Verification:
1. node ts-scanner/dist/index.js /tmp/ccusage 2>/dev/null | jq '.cli'
2. python xray.py /tmp/ccusage 2>/dev/null | grep -A 5 "Decorator"
3. python xray.py /tmp/ccusage 2>/dev/null | grep "node_modules\|dist/"
4. python xray.py /tmp/ccusage 2>/dev/null | grep -A 5 "tsconfig\|strict\|eslint\|prettier" (config rules detected)
5. python xray.py /tmp/ccusage 2>/dev/null | wc -l (should be significantly more than 331 lines from Phase 1)
6. cd ts-scanner && npm test (all pass)
7. python -m pytest tests/ -x -q (all pass)

When all verification passes, mark Phase 2E as complete in PLAN_TS_SCANNER_PHASES.md with status and date.

Then run a final quality comparison: save the full output with `python xray.py /tmp/ccusage 2>/dev/null > /tmp/ccusage_final_2e.md` and count sections, lines, and populated tables vs the Phase 1 baseline of 331 lines and ~25% quality. Report the final quality estimate.
```

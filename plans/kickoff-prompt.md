You are implementing the Deep Crawl addon for repo-xray. Before doing anything, read these files in this order:

1. `INTENT.md` — understand why this project exists and the design constraints
2. `CLAUDE.md` — understand the codebase architecture, conventions, and rules
3. `plans/deep-crawl-spec-v2.md` — the primary specification
   `plans/deep-crawl-spec-v1.md` — referenced by v2 for domain_profiles.json and investigation_targets.py implementation skeleton
4. `docs/TECHNICAL_METRICS.md` — reference for existing analysis signals

The spec has two parts. Part 1 (Sections 1-14 + Appendices) is the design. Part 2 (Sections 15-23) contains implementable artifacts including agent definitions, skill files, templates, configs, and the implementation skeleton for `investigation_targets.py`.

## Implementation Order

Follow the spec's implementation plan (Section 13) exactly:

### Phase 1: xray Modifications

1. **First**, run the data structure verification script from Section 4.2 against this project's own codebase. Run `python xray.py . --output json --out /tmp/xray_self_test` and then inspect the JSON to determine the actual key names used in ast_results, call_results, git_results, and import_results. The implementation skeleton in the spec uses assumed key names that must be verified. Document which keys are correct and which need adjustment.

2. Create `lib/investigation_targets.py` using the skeleton from spec Section 20, adjusted for the verified key names. The module must produce non-empty results for each of its 7 sub-sections when run against this project's own codebase.

3. Integrate into `xray.py` per spec Section 21 — add the import and call after existing analyses complete, add results to the output dict.

4. Update `formatters/markdown_formatter.py` — add the compact investigation targets section described in Section 4 (Markdown Output).

5. Update `formatters/json_formatter.py` — include investigation_targets in JSON output.

6. **Verify**: Run `python xray.py . --output both --out /tmp/xray_verify` and confirm the investigation_targets section appears in both outputs with non-empty data.

### Phase 2: Agent and Skill Creation

Create all files from spec Part 2:

1. `.claude/agents/deep_crawl.md` — the deep crawl agent (Section 15). Build the complete agent body from the six-phase workflow in Section 5.2, evidence standards in Section 5.3, and edge case handling. This is an Opus agent.

2. `.claude/agents/deep_onboard_validator.md` — the validation agent (Section 16). Include the 7-check protocol from Section 12.2 and the adversarial simulation protocol from Appendix D. This is a Sonnet agent.

3. `.claude/skills/deep-crawl/SKILL.md` — from Section 17.1
4. `.claude/skills/deep-crawl/COMMANDS.md` — from Section 17.2
5. `.claude/skills/deep-crawl/configs/generic_names.json` — from Appendix A
6. `.claude/skills/deep-crawl/configs/domain_profiles.json` — from Section 18.2 (full profiles are in v1 spec Section 16.2 which is referenced)
7. `.claude/skills/deep-crawl/configs/compression_targets.json` — from Section 18.3
8. `.claude/skills/deep-crawl/templates/DEEP_ONBOARD.md.template` — from Section 7.1
9. `.claude/skills/deep-crawl/templates/CRAWL_PLAN.md.template` — from Section 19.2
10. `.claude/skills/deep-crawl/templates/VALIDATION_REPORT.md.template` — from Section 19.3

### Phase 3: Verification

1. Run `python xray.py . --output both --out /tmp/xray_final` and verify all investigation_targets sub-sections are populated.
2. Run `python -m pytest tests/ -x -q` and confirm nothing is broken.
3. Verify the agent and skill files are well-formed and internally consistent.

## Critical Rules

- Do not add external dependencies. This project is stdlib-only.
- Do not parse files more than once. If you need new AST data, extend the existing visitor in ast_analysis.py or create a new module that takes combined results as input.
- Do not put analysis logic in formatters. Formatters only format.
- The scanner must remain deterministic. No LLM calls, no network requests during analysis (except the existing GitHub metadata fetch).
- Follow existing patterns in lib/ modules: functions take file lists or result dicts, return dicts, catch exceptions per-file.
- New combined-result analyses get their own module (like investigation_targets.py), not added to gap_features.py.

## What Success Looks Like

After implementation, running `python xray.py . --output both --out /tmp/xray` on any Python codebase produces JSON and markdown that include an `investigation_targets` section with 7 populated sub-sections: ambiguous_interfaces, entry_to_side_effect_paths, coupling_anomalies, convention_deviations, shared_mutable_state, high_uncertainty_modules, and domain_entities.

The `.claude/agents/` and `.claude/skills/deep-crawl/` directories contain complete, internally consistent agent definitions, skill files, configs, and templates that a Claude Code user can invoke with `@deep_crawl full`.

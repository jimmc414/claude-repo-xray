/**
 * Investigation targets: combined-signal analysis for the TS scanner.
 *
 * Computes high-value investigation sub-targets by combining signals
 * from AST analysis, call graph, imports, git, and side effects.
 */

import * as path from "path";
import type {
  FileAnalysis, CallAnalysis, ImportAnalysis, GitAnalysis, ImportTimeSideEffect,
  UncertaintyModule, AmbiguousInterface, EntryToSideEffectPath,
  SharedMutableStateTarget, DomainEntity, CouplingAnomaly, InvestigationTargets,
} from "./types.js";

const GENERIC_NAMES = new Set([
  "process", "handle", "run", "get", "set", "do", "execute", "perform",
  "init", "setup", "configure", "prepare", "cleanup",
  "main", "start", "stop", "reset", "refresh", "sync",
  "update", "create", "delete", "make", "generate", "build",
  "fetch", "load", "save", "send", "parse", "format",
  "transform", "convert", "resolve", "manage",
  "validate", "check", "verify", "compute", "calculate", "evaluate",
  "apply", "dispatch", "emit", "notify", "trigger",
  "call", "invoke", "wrap", "decorate", "inject", "register", "connect",
  "pull", "push", "merge", "split",
  "filter", "map", "reduce", "aggregate", "collect",
  "render", "display", "show", "output", "log",
]);

// =============================================================================
// High Uncertainty Modules
// =============================================================================

function computeHighUncertaintyModules(
  fileResults: Record<string, FileAnalysis>,
  calls: CallAnalysis | undefined,
  targetDir: string,
): UncertaintyModule[] {
  const results: UncertaintyModule[] = [];

  // Build fan-in per file from call analysis
  const fileFanIn = new Map<string, number>();
  if (calls) {
    for (const [, info] of Object.entries(calls.reverse_lookup)) {
      for (const caller of info.callers) {
        fileFanIn.set(caller.file, (fileFanIn.get(caller.file) ?? 0) + 1);
      }
    }
  }

  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");
    const reasons: string[] = [];
    let score = 0;

    // Low type coverage
    const tc = fa.type_coverage;
    if (tc.total_functions > 0) {
      const coverage = tc.coverage_percent;
      if (coverage < 30) {
        score += 0.3;
        reasons.push(`low type coverage (${coverage}%)`);
      } else if (coverage < 60) {
        score += 0.15;
        reasons.push(`moderate type coverage (${coverage}%)`);
      }
    }

    // High complexity
    const avgCC = fa.type_coverage.total_functions > 0
      ? fa.complexity.total_cc / fa.type_coverage.total_functions
      : 0;
    if (avgCC > 8) {
      score += 0.25;
      reasons.push(`high avg complexity (${avgCC.toFixed(1)})`);
    } else if (avgCC > 5) {
      score += 0.1;
      reasons.push(`moderate avg complexity (${avgCC.toFixed(1)})`);
    }

    // High fan-in
    const fanIn = fileFanIn.get(rel) ?? 0;
    if (fanIn >= 5) {
      score += 0.2;
      reasons.push(`high fan-in (${fanIn} callers)`);
    }

    // No docstrings
    const totalFuncs = fa.functions.length + fa.classes.reduce((s, c) => s + c.methods.length, 0);
    const documented = fa.functions.filter(f => f.docstring).length +
      fa.classes.reduce((s, c) => s + c.methods.filter(m => "docstring" in m).length, 0);
    if (totalFuncs > 2 && documented === 0) {
      score += 0.15;
      reasons.push("no docstrings");
    }

    // Silent failures
    if (fa.silent_failures.length > 0) {
      score += 0.1;
      reasons.push(`${fa.silent_failures.length} silent failures`);
    }

    if (score >= 0.3 && reasons.length > 0) {
      results.push({ file: rel, score: Math.round(score * 100) / 100, reasons });
    }
  }

  results.sort((a, b) => b.score - a.score);
  return results.slice(0, 20);
}

// =============================================================================
// Ambiguous Interfaces
// =============================================================================

function computeAmbiguousInterfaces(
  fileResults: Record<string, FileAnalysis>,
  calls: CallAnalysis | undefined,
  targetDir: string,
): AmbiguousInterface[] {
  const results: AmbiguousInterface[] = [];

  // Build caller count per function from call analysis
  const callerCounts = new Map<string, number>();
  if (calls) {
    for (const [funcName, info] of Object.entries(calls.reverse_lookup)) {
      callerCounts.set(funcName, info.caller_count);
    }
  }

  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");

    for (const fn of fa.functions) {
      const reasons: string[] = [];
      let score = 0;

      // Generic name
      if (GENERIC_NAMES.has(fn.name.toLowerCase())) {
        score += 2;
        reasons.push("generic name");
      }

      // Low type coverage
      const hasTypes = fn.returns !== null || fn.args.some(a => !!a.type);
      if (!hasTypes && fn.args.length > 0) {
        score += 1.5;
        reasons.push("no type annotations");
      }

      // High callers
      const callers = callerCounts.get(fn.name) ?? 0;
      if (callers >= 3) {
        score += callers * 0.5;
        reasons.push(`${callers} cross-module callers`);
      }

      // High complexity
      if (fn.complexity > 5) {
        score += fn.complexity * 0.2;
        reasons.push(`complexity ${fn.complexity}`);
      }

      // Gate: generic name OR (no type annotations AND cross-module callers)
      // Matches Python's _assess_function_ambiguity logic
      const isGeneric = GENERIC_NAMES.has(fn.name.toLowerCase());
      if (!isGeneric && (hasTypes || callers < 2)) {
        continue;
      }
      if (score > 0) {
        results.push({
          file: rel,
          function: fn.name,
          score: Math.round(score * 100) / 100,
          reasons,
        });
      }
    }
  }

  results.sort((a, b) => b.score - a.score);
  return results.slice(0, 20);
}

// =============================================================================
// Entry-to-Side-Effect Paths
// =============================================================================

function computeEntryToSideEffectPaths(
  fileResults: Record<string, FileAnalysis>,
  calls: CallAnalysis | undefined,
  targetDir: string,
): EntryToSideEffectPath[] {
  if (!calls) return [];

  const results: EntryToSideEffectPath[] = [];

  // Build side-effect set: which functions contain side effects
  const funcSideEffects = new Map<string, Array<{ call: string; file: string }>>();
  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");
    for (const se of fa.side_effects) {
      // Find which function this side effect is in
      for (const fn of fa.functions) {
        if (fn.end_line != null && se.line >= fn.line && se.line <= fn.end_line) {
          const key = fn.name;
          if (!funcSideEffects.has(key)) funcSideEffects.set(key, []);
          funcSideEffects.get(key)!.push({ call: se.call, file: rel });
          break;
        }
      }
    }
  }

  // Identify entry points: exported functions with no callers or in main/index files
  const entryPoints: Array<{ name: string; file: string }> = [];
  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");
    const isEntry = rel.includes("index.") || rel.includes("main.") ||
      rel.includes("app.") || rel.includes("server.");

    for (const fn of fa.functions) {
      const callerCount = calls.reverse_lookup[fn.name]?.caller_count ?? 0;
      if (isEntry || callerCount === 0) {
        entryPoints.push({ name: fn.name, file: rel });
      }
    }
  }

  // BFS from each entry point through call graph
  for (const entry of entryPoints.slice(0, 10)) {
    const visited = new Set<string>();
    const queue: Array<{ name: string; hops: number }> = [{ name: entry.name, hops: 0 }];
    const reachableSE: Array<{ call: string; file: string; hops: number }> = [];

    while (queue.length > 0) {
      const { name, hops } = queue.shift()!;
      if (visited.has(name) || hops > 5) continue;
      visited.add(name);

      // Check if this function has side effects
      const ses = funcSideEffects.get(name);
      if (ses) {
        for (const se of ses) {
          reachableSE.push({ ...se, hops });
        }
      }

      // Follow call graph: look up functions that this function calls (callees)
      // cross_module is keyed by callee → call_sites, so we need the reverse:
      // find entries where this function appears as a caller
      for (const [callee, info] of Object.entries(calls.cross_module)) {
        if (info.call_sites.some(site => site.caller === name)) {
          queue.push({ name: callee, hops: hops + 1 });
        }
      }
    }

    if (reachableSE.length > 0) {
      results.push({
        entry_point: entry.name,
        entry_file: entry.file,
        side_effects: reachableSE.slice(0, 10),
      });
    }
  }

  results.sort((a, b) => b.side_effects.length - a.side_effects.length);
  return results.slice(0, 15);
}

// =============================================================================
// Shared Mutable State
// =============================================================================

function computeSharedMutableState(
  fileResults: Record<string, FileAnalysis>,
  targetDir: string,
): SharedMutableStateTarget[] {
  const results: SharedMutableStateTarget[] = [];

  for (const [filePath, fa] of Object.entries(fileResults)) {
    if (!fa.shared_mutable_state) continue;
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");

    for (const sms of fa.shared_mutable_state) {
      results.push({
        name: sms.name,
        file: rel,
        line: sms.line,
        kind: sms.kind,
        mutated_by: sms.mutated_by,
      });
    }
  }

  return results;
}

// =============================================================================
// Domain Entities
// =============================================================================

function computeDomainEntities(
  fileResults: Record<string, FileAnalysis>,
  targetDir: string,
): DomainEntity[] {
  // Collect classes and interfaces, track which files reference them in type annotations
  const entityFiles = new Map<string, { kind: DomainEntity["kind"]; file: string; usedIn: Set<string> }>();

  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");

    // Register classes
    for (const cls of fa.classes) {
      if (!entityFiles.has(cls.name)) {
        entityFiles.set(cls.name, { kind: "class", file: rel, usedIn: new Set() });
      }
    }

    // Register interfaces
    if (fa.ts_interfaces) {
      for (const iface of fa.ts_interfaces) {
        if (!entityFiles.has(iface.name)) {
          entityFiles.set(iface.name, { kind: "interface", file: rel, usedIn: new Set() });
        }
      }
    }

    // Register type aliases
    if (fa.ts_type_aliases) {
      for (const ta of fa.ts_type_aliases) {
        if (!entityFiles.has(ta.name)) {
          entityFiles.set(ta.name, { kind: "type_alias", file: rel, usedIn: new Set() });
        }
      }
    }
  }

  // Track usage: scan function/method arg types and return types for entity names
  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");

    const checkType = (typeStr: string | null | undefined) => {
      if (!typeStr) return;
      for (const name of entityFiles.keys()) {
        if (typeStr.includes(name)) {
          const ent = entityFiles.get(name)!;
          if (ent.file !== rel) {
            ent.usedIn.add(rel);
          }
        }
      }
    };

    for (const fn of fa.functions) {
      checkType(fn.returns);
      for (const arg of fn.args) checkType(arg.type);
    }
    for (const cls of fa.classes) {
      for (const method of cls.methods) {
        checkType(method.returns);
        for (const arg of method.args) checkType(arg.type);
      }
    }
  }

  const results: DomainEntity[] = [];
  for (const [name, info] of entityFiles) {
    if (info.usedIn.size >= 3) {
      results.push({
        name,
        kind: info.kind,
        file: info.file,
        used_in_files: Array.from(info.usedIn).sort(),
      });
    }
  }

  results.sort((a, b) => b.used_in_files.length - a.used_in_files.length);
  return results.slice(0, 20);
}

// =============================================================================
// Coupling Anomalies
// =============================================================================

function computeCouplingAnomalies(
  git: GitAnalysis | null,
  imports: ImportAnalysis | undefined,
): CouplingAnomaly[] {
  if (!git || !imports) return [];

  const results: CouplingAnomaly[] = [];

  // Build import relationship set
  const importPairs = new Set<string>();
  for (const [file, info] of Object.entries(imports.graph)) {
    for (const imp of info.imports) {
      const pair = [file, imp].sort().join("\0");
      importPairs.add(pair);
    }
  }

  // Check git coupling pairs against import graph
  for (const cp of git.coupling) {
    const pair = [cp.file_a, cp.file_b].sort().join("\0");
    const hasImport = importPairs.has(pair);

    if (!hasImport && cp.count >= 3) {
      results.push({
        file_a: cp.file_a,
        file_b: cp.file_b,
        git_cochanges: cp.count,
        has_import_relationship: false,
      });
    }
  }

  results.sort((a, b) => b.git_cochanges - a.git_cochanges);
  return results.slice(0, 15);
}

// =============================================================================
// Orchestrator
// =============================================================================

export function computeInvestigationTargets(
  fileResults: Record<string, FileAnalysis>,
  calls: CallAnalysis | undefined,
  imports: ImportAnalysis | undefined,
  git: GitAnalysis | null,
  importTimeSideEffects: ImportTimeSideEffect[],
  targetDir: string,
): InvestigationTargets {
  const targets: InvestigationTargets = {
    import_time_side_effects: importTimeSideEffects,
  };

  const uncertainty = computeHighUncertaintyModules(fileResults, calls, targetDir);
  if (uncertainty.length > 0) targets.high_uncertainty_modules = uncertainty;

  const ambiguous = computeAmbiguousInterfaces(fileResults, calls, targetDir);
  if (ambiguous.length > 0) targets.ambiguous_interfaces = ambiguous;

  const paths = computeEntryToSideEffectPaths(fileResults, calls, targetDir);
  if (paths.length > 0) targets.entry_to_side_effect_paths = paths;

  const mutableState = computeSharedMutableState(fileResults, targetDir);
  if (mutableState.length > 0) targets.shared_mutable_state = mutableState;

  const domainEntities = computeDomainEntities(fileResults, targetDir);
  if (domainEntities.length > 0) targets.domain_entities = domainEntities;

  const anomalies = computeCouplingAnomalies(git, imports);
  if (anomalies.length > 0) targets.coupling_anomalies = anomalies;

  return targets;
}

/**
 * Blast Radius Analysis for TypeScript/JavaScript projects.
 *
 * Computes transitive impact of changing any module by BFS through
 * the combined reverse import + call graphs. Answers: "If I change
 * this file, what else might break?"
 */

import * as path from "path";
import type { ImportAnalysis, CallAnalysis, BlastRadius, BlastRadiusEntry } from "./types.js";

const MAX_HOPS = 5;

/**
 * Build reverse import graph: module → set of modules that import it.
 */
function buildReverseImportGraph(imports: ImportAnalysis): Map<string, Set<string>> {
  const reverse = new Map<string, Set<string>>();
  for (const [mod, info] of Object.entries(imports.graph)) {
    if (!reverse.has(mod)) reverse.set(mod, new Set());
    for (const dep of info.imported_by) {
      if (!reverse.has(mod)) reverse.set(mod, new Set());
      reverse.get(mod)!.add(dep);
    }
  }
  return reverse;
}

/**
 * Build reverse call graph: module → set of modules that call into it.
 */
function buildReverseCallGraph(calls: CallAnalysis): Map<string, Set<string>> {
  const reverse = new Map<string, Set<string>>();

  for (const [funcName, data] of Object.entries(calls.cross_module)) {
    // Extract target module from qualified function name
    const targetModule = funcName.includes(".") ? funcName.split(".")[0] : "";
    if (!targetModule) continue;

    for (const site of data.call_sites) {
      const callerFile = site.file;
      // Extract module stem from file path
      const callerModule = path.basename(callerFile).replace(/\.[^.]+$/, "");
      if (callerModule && callerModule !== targetModule) {
        if (!reverse.has(targetModule)) reverse.set(targetModule, new Set());
        reverse.get(targetModule)!.add(callerModule);
      }
    }
  }

  return reverse;
}

/**
 * BFS from a target module through combined reverse graphs.
 */
function computeModuleBlast(
  target: string,
  reverseImports: Map<string, Set<string>>,
  reverseCalls: Map<string, Set<string>>,
): Map<string, number> {
  const visited = new Map<string, number>(); // module → hop distance
  const queue: Array<[string, number]> = [[target, 0]];

  while (queue.length > 0) {
    const [mod, hops] = queue.shift()!;
    if (visited.has(mod) || hops > MAX_HOPS) continue;
    visited.set(mod, hops);

    // Expand via import edges
    const importDeps = reverseImports.get(mod);
    if (importDeps) {
      for (const dep of importDeps) {
        if (!visited.has(dep)) queue.push([dep, hops + 1]);
      }
    }

    // Expand via call edges
    const callDeps = reverseCalls.get(mod);
    if (callDeps) {
      for (const dep of callDeps) {
        if (!visited.has(dep)) queue.push([dep, hops + 1]);
      }
    }
  }

  // Remove self
  visited.delete(target);
  return visited;
}

/**
 * Classify risk based on affected count and total module count.
 */
function classifyRisk(
  affectedCount: number,
  totalModules: number,
): BlastRadiusEntry["risk"] {
  const ratio = totalModules > 0 ? affectedCount / totalModules : 0;
  if (affectedCount >= 10 || ratio >= 0.5) return "critical";
  if (affectedCount >= 5 || ratio >= 0.25) return "high";
  if (affectedCount >= 2) return "moderate";
  return "isolated";
}

/**
 * Analyze blast radius for all modules.
 */
export function analyzeBlastRadius(
  imports: ImportAnalysis,
  calls: CallAnalysis,
): BlastRadius {
  const reverseImports = buildReverseImportGraph(imports);
  const reverseCalls = buildReverseCallGraph(calls);

  // Get all known modules
  const allModules = new Set<string>();
  for (const mod of Object.keys(imports.graph)) allModules.add(mod);
  for (const mod of reverseImports.keys()) allModules.add(mod);
  for (const mod of reverseCalls.keys()) allModules.add(mod);

  const totalModules = allModules.size;
  const entries: BlastRadiusEntry[] = [];

  for (const mod of allModules) {
    const blast = computeModuleBlast(mod, reverseImports, reverseCalls);
    if (blast.size === 0) continue;

    const affectedModules = [...blast.entries()]
      .sort((a, b) => a[1] - b[1])
      .map(([m, h]) => ({ module: m, hops: h }));

    entries.push({
      module: mod,
      affected_count: blast.size,
      risk: classifyRisk(blast.size, totalModules),
      affected_modules: affectedModules,
      max_hops: Math.max(...blast.values()),
    });
  }

  // Sort by affected_count descending, take top 20
  entries.sort((a, b) => b.affected_count - a.affected_count);
  const top = entries.slice(0, 20);

  const criticalCount = top.filter(e => e.risk === "critical").length;
  const highCount = top.filter(e => e.risk === "high").length;
  const avgAffected = top.length > 0
    ? Math.round((top.reduce((s, e) => s + e.affected_count, 0) / top.length) * 10) / 10
    : 0;

  return {
    files: top,
    summary: {
      critical_count: criticalCount,
      high_count: highCount,
      average_affected: avgAffected,
    },
  };
}

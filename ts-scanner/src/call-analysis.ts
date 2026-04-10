/**
 * Cross-module call graph analysis for TS/JS codebases.
 *
 * Mirrors lib/call_analysis.py: builds a function registry from
 * file analysis results, resolves call expressions against the
 * import binding table, and computes impact ratings.
 */

import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";
import type { CallAnalysis, FileAnalysis } from "./types.js";
import { buildBindingTable, type BindingEntry } from "./import-analysis.js";
import { getScriptKind, relativePath } from "./utils.js";

// =============================================================================
// Public API
// =============================================================================

export function analyzeCallGraph(
  fileResults: Record<string, FileAnalysis>,
  files: string[],
  rootDir: string,
): CallAnalysis {
  const absRoot = path.resolve(rootDir);
  const fileSet = new Set(files);

  // Step 1: Build function registry — maps qualified names to source location
  const registry = new Map<string, { file: string; line: number }>();
  for (const [filePath, fa] of Object.entries(fileResults)) {
    const stem = path.basename(filePath).replace(/\.[^.]+$/, "");
    for (const fn of fa.functions) {
      registry.set(`${stem}.${fn.name}`, { file: filePath, line: fn.line });
    }
    for (const cls of fa.classes) {
      for (const method of cls.methods) {
        registry.set(`${stem}.${cls.name}.${method.name}`, { file: filePath, line: method.line });
      }
    }
  }

  // Step 2: For each file, resolve calls against the binding table
  interface RawCallSite {
    callee: string;       // qualified name
    callerFile: string;
    callerFunction: string;
    line: number;
  }

  const allCallSites: RawCallSite[] = [];

  for (const filePath of files) {
    const bindingTable = buildBindingTable(filePath, fileSet);
    if (bindingTable.size === 0) continue;

    let source: string;
    try {
      source = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }

    const scriptKind = getScriptKind(filePath);
    let sourceFile: ts.SourceFile;
    try {
      sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, scriptKind);
    } catch {
      continue;
    }

    const currentFunction = { name: "(module)" };

    function visit(node: ts.Node): void {
      if (!node) return;
      // Track function context
      if (ts.isFunctionDeclaration(node) && node.name) {
        const prev = currentFunction.name;
        currentFunction.name = node.name.text;
        ts.forEachChild(node, visit);
        currentFunction.name = prev;
        return;
      }
      if (ts.isMethodDeclaration(node) && node.name) {
        const prev = currentFunction.name;
        currentFunction.name = node.name.getText(sourceFile);
        ts.forEachChild(node, visit);
        currentFunction.name = prev;
        return;
      }
      if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) &&
          node.initializer && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
        const prev = currentFunction.name;
        currentFunction.name = node.name.text;
        ts.forEachChild(node.initializer, visit);
        currentFunction.name = prev;
        return;
      }

      // Resolve call expressions
      if (ts.isCallExpression(node)) {
        const resolved = resolveCallExpression(node, bindingTable, sourceFile, absRoot);
        if (resolved) {
          const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
          allCallSites.push({
            callee: resolved,
            callerFile: filePath,
            callerFunction: currentFunction.name,
            line,
          });
        }
      }

      ts.forEachChild(node, visit);
    }

    ts.forEachChild(sourceFile, visit);
  }

  // Step 3: Aggregate into cross_module
  const crossModule: CallAnalysis["cross_module"] = {};
  for (const site of allCallSites) {
    if (!crossModule[site.callee]) {
      crossModule[site.callee] = { call_count: 0, call_sites: [] };
    }
    crossModule[site.callee].call_count++;
    crossModule[site.callee].call_sites.push({
      file: relativePath(site.callerFile, absRoot),
      line: site.line,
      caller: site.callerFunction,
    });
  }

  // Step 4: Build reverse lookup
  const reverseLookup: CallAnalysis["reverse_lookup"] = {};
  for (const [callee, data] of Object.entries(crossModule)) {
    const callerModules = new Set(data.call_sites.map(s => s.file));
    const callerCount = data.call_count;
    const moduleCount = callerModules.size;

    let impactRating: "high" | "medium" | "low";
    if (moduleCount >= 5 || callerCount >= 10) {
      impactRating = "high";
    } else if (moduleCount >= 2 || callerCount >= 5) {
      impactRating = "medium";
    } else {
      impactRating = "low";
    }

    const callers: Array<{ file: string; function: string }> = [];
    const seen = new Set<string>();
    for (const site of data.call_sites) {
      const key = `${site.file}:${site.caller}`;
      if (!seen.has(key)) {
        seen.add(key);
        callers.push({ file: site.file, function: site.caller });
      }
    }

    reverseLookup[callee] = {
      caller_count: callerCount,
      impact_rating: impactRating,
      callers,
    };
  }

  // Step 5: Most called (top 15)
  const mostCalled = Object.entries(crossModule)
    .map(([fn, data]) => ({
      function: fn,
      call_sites: data.call_count,
      modules: new Set(data.call_sites.map(s => s.file)).size,
    }))
    .sort((a, b) => b.call_sites - a.call_sites)
    .slice(0, 15);

  // Step 6: Most callers — top 15 by outgoing calls
  const outgoingCounts = new Map<string, number>();
  for (const site of allCallSites) {
    const callerKey = `${path.basename(site.callerFile).replace(/\.[^.]+$/, "")}.${site.callerFunction}`;
    outgoingCounts.set(callerKey, (outgoingCounts.get(callerKey) || 0) + 1);
  }
  const mostCallers = [...outgoingCounts.entries()]
    .map(([fn, count]) => ({ function: fn, calls_made: count }))
    .sort((a, b) => b.calls_made - a.calls_made)
    .slice(0, 15);

  // Step 7: Isolated functions — in registry but never a callee
  const calledFunctions = new Set(Object.keys(crossModule));
  const isolatedFunctions = [...registry.keys()].filter(qn => !calledFunctions.has(qn));

  // Step 8: High impact
  const highImpact = Object.entries(reverseLookup)
    .filter(([_, data]) => data.impact_rating === "high")
    .map(([fn, data]) => ({
      function: fn,
      impact: "high" as const,
      callers: data.caller_count,
    }));

  // Summary
  const summary = {
    total_cross_module_calls: allCallSites.length,
    functions_with_cross_module_callers: Object.keys(crossModule).length,
    high_impact_functions: highImpact.length,
    isolated_functions: isolatedFunctions.length,
  };

  return {
    cross_module: crossModule,
    reverse_lookup: reverseLookup,
    most_called: mostCalled,
    most_callers: mostCallers,
    isolated_functions: isolatedFunctions,
    high_impact: highImpact,
    summary,
  };
}

// =============================================================================
// Call expression resolution
// =============================================================================

function resolveCallExpression(
  node: ts.CallExpression,
  bindingTable: Map<string, BindingEntry>,
  sourceFile: ts.SourceFile,
  absRoot: string,
): string | null {
  const expr = node.expression;

  // Direct call: identifier(...)
  // e.g., createUser() where createUser was imported
  if (ts.isIdentifier(expr)) {
    const binding = bindingTable.get(expr.text);
    if (binding && binding.kind === "named") {
      const moduleStem = path.basename(binding.resolvedModule).replace(/\.[^.]+$/, "");
      return `${moduleStem}.${binding.exportedName}`;
    }
    if (binding && binding.kind === "default") {
      const moduleStem = path.basename(binding.resolvedModule).replace(/\.[^.]+$/, "");
      return `${moduleStem}.default`;
    }
    return null;
  }

  // Property access: obj.method(...)
  // e.g., svc.deleteUser() where svc is a namespace import
  if (ts.isPropertyAccessExpression(expr)) {
    const obj = expr.expression;
    const prop = expr.name.text;

    if (ts.isIdentifier(obj)) {
      const binding = bindingTable.get(obj.text);
      if (binding && binding.kind === "namespace") {
        const moduleStem = path.basename(binding.resolvedModule).replace(/\.[^.]+$/, "");
        return `${moduleStem}.${prop}`;
      }
    }
    return null;
  }

  return null;
}

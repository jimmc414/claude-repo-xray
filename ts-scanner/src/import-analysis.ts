/**
 * Import analysis for TS/JS codebases.
 *
 * Mirrors lib/import_analysis.py: builds a dependency graph from
 * import declarations and require() calls, detects layers, circular
 * deps, orphans, hub modules, and external dependencies.
 */

import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";
import type { ImportAnalysis } from "./types.js";
import { getScriptKind, relativePath } from "./utils.js";

// =============================================================================
// Types
// =============================================================================

interface RawImport {
  specifier: string;
  kind: "default" | "named" | "namespace" | "side-effect" | "dynamic";
  isRelative: boolean;
}

interface GraphNode {
  imports: Set<string>;
  importedBy: Set<string>;
}

// =============================================================================
// Layer classification heuristics
// =============================================================================

const LAYER_PATTERNS: Array<[RegExp, string]> = [
  [/\b(api|routes?|controllers?|handlers?|endpoints?)\b/i, "api"],
  [/\b(services?|usecases?|use-cases?)\b/i, "services"],
  [/\b(models?|entities|schemas?|domain)\b/i, "models"],
  [/\b(utils?|helpers?|lib|common|shared)\b/i, "utils"],
  [/\b(types?|interfaces?|dtos?|contracts?)\b/i, "types"],
  [/\b(middleware|guards?|interceptors?|pipes?)\b/i, "middleware"],
  [/\b(components?|views?|pages?|screens?|layouts?)\b/i, "components"],
  [/\b(hooks?)\b/i, "hooks"],
  [/\b(stores?|state|redux|zustand)\b/i, "state"],
  [/\b(config|configs?|settings?)\b/i, "config"],
  [/\b(tests?|__tests__|spec|__spec__)\b/i, "tests"],
];

// =============================================================================
// Node.js builtin detection
// =============================================================================

const NODE_BUILTIN_MODULES = new Set([
  "assert", "buffer", "child_process", "cluster", "console", "crypto",
  "dgram", "dns", "events", "fs", "http", "http2", "https", "module",
  "net", "os", "path", "perf_hooks", "process", "querystring", "readline",
  "stream", "string_decoder", "timers", "tls", "tty", "url", "util",
  "v8", "vm", "worker_threads", "zlib",
]);

function isNodeBuiltin(specifier: string): boolean {
  if (specifier.startsWith("node:")) return true;
  return NODE_BUILTIN_MODULES.has(specifier);
}

// =============================================================================
// Public API
// =============================================================================

export function analyzeImports(
  files: string[],
  rootDir: string,
): ImportAnalysis {
  const absRoot = path.resolve(rootDir);

  // Step 1: Parse imports from every file
  const fileImports = new Map<string, RawImport[]>();
  for (const filePath of files) {
    fileImports.set(filePath, parseImports(filePath));
  }

  // Step 2: Build dependency graph
  const fileSet = new Set(files);
  const graph = new Map<string, GraphNode>();

  // Initialize all nodes
  for (const f of files) {
    graph.set(f, { imports: new Set(), importedBy: new Set() });
  }

  const externalDeps = new Set<string>();
  let internalEdges = 0;

  for (const [filePath, imports] of fileImports) {
    for (const imp of imports) {
      if (imp.isRelative) {
        const resolved = resolveRelativeImport(filePath, imp.specifier, fileSet);
        if (resolved) {
          const fromNode = graph.get(filePath)!;
          const toNode = graph.get(resolved)!;
          if (!fromNode.imports.has(resolved)) {
            fromNode.imports.add(resolved);
            toNode.importedBy.add(filePath);
            internalEdges++;
          }
        }
      } else {
        // Package import — extract base package name (skip Node builtins)
        if (!isNodeBuiltin(imp.specifier)) {
          const pkgName = getPackageName(imp.specifier);
          externalDeps.add(pkgName);
        }
      }
    }
  }

  // Step 3: Layer detection
  const layers = detectLayers(files, absRoot);

  // Step 4: Circular dependency detection
  const circular = detectCircularDeps(graph);

  // Step 5: Orphan detection
  const orphans = detectOrphans(graph, files, absRoot);

  // Step 6: Dependency distances
  const distances = calculateDistances(graph, files);

  // Build output
  const graphOutput: ImportAnalysis["graph"] = {};
  for (const [filePath, node] of graph) {
    const rel = relativePath(filePath, absRoot);
    graphOutput[rel] = {
      imports: [...node.imports].map(f => relativePath(f, absRoot)),
      imported_by: [...node.importedBy].map(f => relativePath(f, absRoot)),
    };
  }

  const layersOutput: Record<string, string[]> = {};
  for (const [layer, layerFiles] of Object.entries(layers)) {
    layersOutput[layer] = layerFiles.map(f => relativePath(f, absRoot));
  }

  const externalList = [...externalDeps].sort();

  return {
    graph: graphOutput,
    layers: layersOutput,
    aliases: {},
    alias_patterns: [],
    orphans: orphans.map(f => relativePath(f, absRoot)),
    circular: circular.map(pair => pair.map(f => relativePath(f, absRoot))),
    external_deps: externalList,
    distances: {
      max_depth: distances.maxDepth,
      avg_depth: distances.avgDepth,
      tightly_coupled: distances.tightlyCoupled.map(tc => ({
        modules: tc.modules.map(f => relativePath(f, absRoot)),
        score: tc.score,
      })),
      hub_modules: distances.hubModules.map(hm => ({
        module: relativePath(hm.module, absRoot),
        connections: hm.connections,
      })),
    },
    summary: {
      total_modules: files.length,
      internal_edges: internalEdges,
      circular_count: circular.length,
      orphan_count: orphans.length,
      external_deps_count: externalList.length,
    },
  };
}

// =============================================================================
// Import parsing
// =============================================================================

function parseImports(filePath: string): RawImport[] {
  let source: string;
  try {
    source = fs.readFileSync(filePath, "utf-8");
  } catch {
    return [];
  }

  const scriptKind = getScriptKind(filePath);
  let sourceFile: ts.SourceFile;
  try {
    sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, false, scriptKind);
  } catch {
    return [];
  }

  const imports: RawImport[] = [];

  function visit(node: ts.Node): void {
    // import ... from "specifier"
    if (ts.isImportDeclaration(node)) {
      const specNode = node.moduleSpecifier;
      if (ts.isStringLiteral(specNode)) {
        const specifier = specNode.text;
        const isRelative = specifier.startsWith(".");
        const kind = getImportKind(node);
        imports.push({ specifier, kind, isRelative });
      }
    }

    // export ... from "specifier" (re-exports)
    if (ts.isExportDeclaration(node) && node.moduleSpecifier) {
      if (ts.isStringLiteral(node.moduleSpecifier)) {
        const specifier = node.moduleSpecifier.text;
        const isRelative = specifier.startsWith(".");
        imports.push({ specifier, kind: "named", isRelative });
      }
    }

    // require("specifier")
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === "require" &&
      node.arguments.length === 1 &&
      ts.isStringLiteral(node.arguments[0])
    ) {
      const specifier = (node.arguments[0] as ts.StringLiteral).text;
      const isRelative = specifier.startsWith(".");
      imports.push({ specifier, kind: "default", isRelative });
    }

    // Dynamic import: import("specifier")
    if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments.length === 1 &&
      ts.isStringLiteral(node.arguments[0])
    ) {
      const specifier = (node.arguments[0] as ts.StringLiteral).text;
      const isRelative = specifier.startsWith(".");
      imports.push({ specifier, kind: "dynamic", isRelative });
    }

    ts.forEachChild(node, visit);
  }

  ts.forEachChild(sourceFile, visit);
  return imports;
}

function getImportKind(node: ts.ImportDeclaration): RawImport["kind"] {
  const clause = node.importClause;
  if (!clause) return "side-effect";
  if (clause.namedBindings) {
    if (ts.isNamespaceImport(clause.namedBindings)) return "namespace";
    return "named";
  }
  return "default";
}

// =============================================================================
// Import resolution
// =============================================================================

/**
 * Resolve a relative import specifier to an absolute file path.
 * Tries common TS/JS extensions and index files.
 */
function resolveRelativeImport(
  fromFile: string,
  specifier: string,
  knownFiles: Set<string>,
): string | null {
  const dir = path.dirname(fromFile);
  const target = path.resolve(dir, specifier);

  // Try exact match first (already has extension)
  if (knownFiles.has(target)) return target;

  // Try extensions
  const extensions = [".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs", ".cts", ".cjs"];
  for (const ext of extensions) {
    const candidate = target + ext;
    if (knownFiles.has(candidate)) return candidate;
  }

  // Try index files (./foo → ./foo/index.ts)
  for (const ext of extensions) {
    const candidate = path.join(target, "index" + ext);
    if (knownFiles.has(candidate)) return candidate;
  }

  return null;
}

/**
 * Extract the base package name from an import specifier.
 * "@scope/pkg/sub" → "@scope/pkg", "lodash/fp" → "lodash"
 */
function getPackageName(specifier: string): string {
  if (specifier.startsWith("@")) {
    // Scoped: @scope/pkg or @scope/pkg/sub
    const parts = specifier.split("/");
    return parts.slice(0, 2).join("/");
  }
  // Unscoped: pkg or pkg/sub
  return specifier.split("/")[0];
}

// =============================================================================
// Layer detection
// =============================================================================

function detectLayers(files: string[], rootDir: string): Record<string, string[]> {
  const layers: Record<string, string[]> = {};

  for (const filePath of files) {
    const rel = path.relative(rootDir, filePath);
    const parts = rel.split(path.sep);

    let assigned = false;
    for (const [pattern, layer] of LAYER_PATTERNS) {
      // Check directory components (not the filename itself)
      const dirParts = parts.slice(0, -1);
      if (dirParts.some(p => pattern.test(p))) {
        if (!layers[layer]) layers[layer] = [];
        layers[layer].push(filePath);
        assigned = true;
        break;
      }
    }

    if (!assigned) {
      if (!layers["other"]) layers["other"] = [];
      layers["other"].push(filePath);
    }
  }

  return layers;
}

// =============================================================================
// Circular dependency detection
// =============================================================================

/**
 * Detect circular dependencies using bidirectional edge detection.
 * Returns pairs of files that import each other (A→B and B→A).
 */
function detectCircularDeps(graph: Map<string, GraphNode>): string[][] {
  const circular: string[][] = [];
  const seen = new Set<string>();

  for (const [fileA, nodeA] of graph) {
    for (const fileB of nodeA.imports) {
      const key = [fileA, fileB].sort().join("\0");
      if (seen.has(key)) continue;
      seen.add(key);

      const nodeB = graph.get(fileB);
      if (nodeB && nodeB.imports.has(fileA)) {
        circular.push([fileA, fileB].sort());
      }
    }
  }

  return circular;
}

// =============================================================================
// Orphan detection
// =============================================================================

/**
 * Find modules with no imports and no importers.
 * Exclude likely entry points (index.ts, main.ts, app.ts, etc.)
 */
function detectOrphans(
  graph: Map<string, GraphNode>,
  files: string[],
  rootDir: string,
): string[] {
  const entryNames = new Set(["index", "main", "app", "server", "cli", "bin"]);

  return files.filter(filePath => {
    const node = graph.get(filePath);
    if (!node) return false;
    if (node.imports.size > 0 || node.importedBy.size > 0) return false;

    // Don't flag likely entry points
    const basename = path.basename(filePath).replace(/\.[^.]+$/, "");
    if (entryNames.has(basename)) return false;

    // Don't flag test files
    const rel = path.relative(rootDir, filePath);
    if (/\b(test|spec|__tests__|__spec__)\b/i.test(rel)) return false;

    // Don't flag config files at root
    const parts = rel.split(path.sep);
    if (parts.length === 1) return false;

    return true;
  });
}

// =============================================================================
// Dependency distance
// =============================================================================

interface DistanceResults {
  maxDepth: number;
  avgDepth: number;
  tightlyCoupled: Array<{ modules: string[]; score: number }>;
  hubModules: Array<{ module: string; connections: number }>;
}

function calculateDistances(
  graph: Map<string, GraphNode>,
  files: string[],
): DistanceResults {
  // BFS from each node to compute max reachable depth
  let totalMaxDepth = 0;
  let totalAvgDepth = 0;
  let nodesWithEdges = 0;

  for (const filePath of files) {
    const node = graph.get(filePath);
    if (!node || node.imports.size === 0) continue;

    nodesWithEdges++;
    const depth = bfsMaxDepth(filePath, graph);
    totalMaxDepth = Math.max(totalMaxDepth, depth);
    totalAvgDepth += depth;
  }

  const avgDepth = nodesWithEdges > 0
    ? Math.round((totalAvgDepth / nodesWithEdges) * 10) / 10
    : 0;

  // Hub modules: most total connections (imports + importedBy)
  const hubCandidates: Array<{ module: string; connections: number }> = [];
  for (const [filePath, node] of graph) {
    const connections = node.imports.size + node.importedBy.size;
    if (connections >= 3) {
      hubCandidates.push({ module: filePath, connections });
    }
  }
  hubCandidates.sort((a, b) => b.connections - a.connections);
  const hubModules = hubCandidates.slice(0, 10);

  // Tightly coupled: pairs with bidirectional edges + shared dependencies
  const tightlyCoupled: Array<{ modules: string[]; score: number }> = [];
  const seen = new Set<string>();

  for (const [fileA, nodeA] of graph) {
    for (const fileB of nodeA.imports) {
      const key = [fileA, fileB].sort().join("\0");
      if (seen.has(key)) continue;
      seen.add(key);

      const nodeB = graph.get(fileB);
      if (!nodeB) continue;

      // Score: 2 for bidirectional, +1 for each shared dependency
      let score = 0;
      if (nodeB.imports.has(fileA)) score += 2;

      // Shared imports
      for (const dep of nodeA.imports) {
        if (dep !== fileB && nodeB.imports.has(dep)) score++;
      }

      if (score >= 2) {
        tightlyCoupled.push({ modules: [fileA, fileB].sort(), score });
      }
    }
  }
  tightlyCoupled.sort((a, b) => b.score - a.score);

  return {
    maxDepth: totalMaxDepth,
    avgDepth,
    tightlyCoupled: tightlyCoupled.slice(0, 10),
    hubModules,
  };
}

function bfsMaxDepth(start: string, graph: Map<string, GraphNode>): number {
  const visited = new Set<string>([start]);
  let queue = [start];
  let depth = 0;

  while (queue.length > 0) {
    const next: string[] = [];
    for (const current of queue) {
      const node = graph.get(current);
      if (!node) continue;
      for (const dep of node.imports) {
        if (!visited.has(dep)) {
          visited.add(dep);
          next.push(dep);
        }
      }
    }
    if (next.length > 0) depth++;
    queue = next;
  }

  return depth;
}

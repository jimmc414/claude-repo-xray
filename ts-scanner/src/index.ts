#!/usr/bin/env node
/**
 * repo-xray TypeScript Scanner
 *
 * Static analysis frontend for TS/JS codebases.
 * Outputs JSON conforming to the XRayResults contract.
 *
 * Usage:
 *   node dist/index.js <target-dir> [--verbose]
 */

import * as path from "path";
import { discoverFiles } from "./file-discovery.js";
import { analyzeFile } from "./ast-analysis.js";
import { analyzeImports } from "./import-analysis.js";
import { analyzeCallGraph } from "./call-analysis.js";
import { analyzeTests } from "./test-analysis.js";
import { generateLogicMaps } from "./logic-maps.js";
import { analyzeConfig } from "./config-analysis.js";
import { analyzeCli } from "./cli-analysis.js";
import { analyzeRoutes } from "./route-analysis.js";
import { analyzeBlastRadius } from "./blast-analysis.js";
import { computeImportTimeSideEffects } from "./import-time-effects.js";
import { analyzeGit } from "./git-analysis.js";
import { analyzeTechDebt } from "./tech-debt.js";
import { computeInvestigationTargets } from "./investigation-targets.js";
import type {
  XRayResults, Structure, Summary, Complexity, TypeCoverage,
  DecoratorInventory, AsyncPatterns, Hotspot, FileAnalysis, ClassInfo, FunctionInfo,
  ImportAnalysis, CallAnalysis, SideEffects, SideEffectEntry, SecurityConcern, SilentFailure,
  SqlString, DeprecationMarker, AsyncViolation, EnvVar, TestAnalysis, LogicMap,
  CliAnalysis, ConfigRules, ResourceLeak, GitAnalysis, TechDebt, TsSpecific,
} from "./types.js";

const VERSION = "0.1.0";

function main(): void {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes("--help") || args.includes("-h")) {
    process.stderr.write(`repo-xray TS scanner v${VERSION}\n`);
    process.stderr.write(`Usage: node dist/index.js <target-dir> [--verbose]\n`);
    process.exit(args.length === 0 ? 1 : 0);
  }

  const verbose = args.includes("--verbose") || args.includes("-v");
  const targetDir = path.resolve(args.find(a => !a.startsWith("-")) || ".");

  if (verbose) {
    process.stderr.write(`TS Scanner v${VERSION}\n`);
    process.stderr.write(`Target: ${targetDir}\n`);
  }

  // Step 1: Discover files
  if (verbose) process.stderr.write("Discovering files...\n");
  const discovery = discoverFiles(targetDir);

  if (discovery.files.length === 0) {
    const result: XRayResults = {
      metadata: buildMetadata(targetDir, 0, discovery.tsconfigPath),
      summary: emptySummary(),
    };
    process.stdout.write(JSON.stringify(result, null, 2));
    process.stdout.write("\n");
    process.exit(0);
  }

  if (verbose) {
    process.stderr.write(`Found ${discovery.files.length} source files`);
    if (discovery.declarationFiles.length > 0) {
      process.stderr.write(` + ${discovery.declarationFiles.length} declaration files`);
    }
    process.stderr.write("\n");
  }

  // Step 2: Analyze each file (parse-discard pattern)
  if (verbose) process.stderr.write("Running AST analysis...\n");
  const fileResults: Record<string, FileAnalysis> = {};
  let hasErrors = false;

  for (const filePath of discovery.files) {
    const analysis = analyzeFile(filePath);
    fileResults[filePath] = analysis;
    if (analysis.parse_error) hasErrors = true;
    if (verbose && analysis.parse_error) {
      const rel = path.relative(targetDir, filePath);
      process.stderr.write(`  Warning: ${rel}: ${analysis.parse_error}\n`);
    }
  }

  // Step 3: Import analysis
  if (verbose) process.stderr.write("Running import analysis...\n");
  const importResults = analyzeImports(discovery.files, targetDir);

  // Step 4: Call analysis
  if (verbose) process.stderr.write("Running call analysis...\n");
  const callResults = analyzeCallGraph(fileResults, discovery.files, targetDir);

  // Step 5: Test analysis
  if (verbose) process.stderr.write("Running test analysis...\n");
  const testResults = analyzeTests(discovery.files, targetDir);

  // Step 6: Route analysis
  if (verbose) process.stderr.write("Detecting routes...\n");
  const routeResults = analyzeRoutes(fileResults, targetDir);

  // Step 6b: Blast radius analysis
  if (verbose) process.stderr.write("Computing blast radius...\n");

  // Step 6c: Import-time side effects
  if (verbose) process.stderr.write("Detecting import-time side effects...\n");
  const importTimeEffects = computeImportTimeSideEffects(fileResults, targetDir);

  // Step 7: Git analysis
  if (verbose) process.stderr.write("Running git analysis...\n");
  const gitResults = analyzeGit(targetDir, discovery.files, verbose);

  // Step 8: Tech debt scan
  if (verbose) process.stderr.write("Scanning for tech debt markers...\n");
  const techDebtResults = analyzeTechDebt(discovery.files, targetDir, verbose);

  // Step 9: Aggregate results
  if (verbose) process.stderr.write("Aggregating results...\n");
  const results = aggregateResults(targetDir, fileResults, discovery.tsconfigPath, importResults, callResults, testResults);

  // Step 7: Generate logic maps for hotspot functions
  if (results.hotspots && results.hotspots.length > 0) {
    if (verbose) process.stderr.write("Generating logic maps...\n");
    const logicMaps = generateLogicMaps(results.hotspots, fileResults, 10);
    if (logicMaps.length > 0) results.logic_maps = logicMaps;
  }

  // Step 8: Config rule extraction
  if (verbose) process.stderr.write("Analyzing config rules...\n");
  const configRules = analyzeConfig(targetDir, discovery.tsconfigPath);
  if (configRules.typescript || configRules.eslint || configRules.prettier) {
    results.config_rules = configRules;
  }

  // Step 9: CLI framework detection
  if (verbose) process.stderr.write("Detecting CLI framework...\n");
  const cliResult = analyzeCli(discovery.files);
  if (cliResult) results.cli = cliResult;

  // Step 12: Extended signals
  if (routeResults) results.routes = routeResults;

  if (results.imports && results.calls) {
    const blastResults = analyzeBlastRadius(results.imports, results.calls);
    if (blastResults.files.length > 0) results.blast_radius = blastResults;
  }

  // Git analysis
  if (gitResults) results.git = gitResults;

  // Tech debt
  if (techDebtResults.summary.total_count > 0) results.tech_debt = techDebtResults;

  // Investigation targets (combine all signals)
  if (verbose) process.stderr.write("Computing investigation targets...\n");
  const investigationTargets = computeInvestigationTargets(
    fileResults, results.calls, results.imports, gitResults, importTimeEffects, targetDir,
  );
  results.investigation_targets = investigationTargets;

  // Aggregate resource leaks
  const resourceLeaks: Record<string, ResourceLeak[]> = {};
  for (const [fp, fa] of Object.entries(fileResults)) {
    if (fa.resource_leaks && fa.resource_leaks.length > 0) {
      const rel = path.relative(targetDir, fp).replace(/\\/g, "/");
      resourceLeaks[rel] = fa.resource_leaks;
    }
  }
  if (Object.keys(resourceLeaks).length > 0) results.resource_leaks = resourceLeaks;

  // Aggregate ts_specific
  const tsSpecific = aggregateTsSpecific(fileResults, discovery.declarationFiles.length, targetDir);
  if (tsSpecific) results.ts_specific = tsSpecific;

  // Output JSON
  process.stdout.write(JSON.stringify(results, null, 2));
  process.stdout.write("\n");

  process.exit(hasErrors ? 2 : 0);
}

// =============================================================================
// Aggregation
// =============================================================================

function aggregateResults(
  targetDir: string,
  fileResults: Record<string, FileAnalysis>,
  tsconfigPath: string | null,
  importResults: ImportAnalysis,
  callResults: CallAnalysis,
  testResults: TestAnalysis,
): XRayResults {
  const files = Object.values(fileResults);

  // Summary
  let totalLines = 0;
  let totalTokens = 0;
  let totalFunctions = 0;
  let totalClasses = 0;
  let totalCC = 0;
  let typedFunctions = 0;
  let totalTypeFunctions = 0;

  // Aggregated lists
  const allClasses: ClassInfo[] = [];
  const allFunctions: FunctionInfo[] = [];
  const allHotspots: Hotspot[] = [];
  const globalDecorators: Record<string, number> = {};
  const globalAsync: AsyncPatterns = {
    async_functions: 0,
    sync_functions: 0,
    async_for_loops: 0,
    async_context_managers: 0,
  };

  // Behavioral signal aggregation
  const sideEffectsByType: SideEffects["by_type"] = {};
  const sideEffectsByFile: SideEffects["by_file"] = {};
  const securityConcerns: Record<string, SecurityConcern[]> = {};
  const silentFailures: Record<string, SilentFailure[]> = {};
  const sqlStrings: Record<string, SqlString[]> = {};
  const deprecationMarkers: DeprecationMarker[] = [];
  const asyncViolations: AsyncViolation[] = [];

  for (const fa of files) {
    totalLines += fa.line_count;
    totalTokens += fa.tokens.original;
    totalFunctions += fa.functions.length;
    totalClasses += fa.classes.length;
    totalCC += fa.complexity.total_cc;
    typedFunctions += fa.type_coverage.typed_functions;
    totalTypeFunctions += fa.type_coverage.total_functions;

    // Classes with file tag
    for (const cls of fa.classes) {
      allClasses.push({ ...cls, file: fa.filepath });
    }
    // Functions with file tag
    for (const fn of fa.functions) {
      allFunctions.push({ ...fn, file: fa.filepath });
    }
    // Hotspots
    for (const [funcName, cc] of Object.entries(fa.complexity.hotspots)) {
      allHotspots.push({ file: fa.filepath, function: funcName, complexity: cc });
    }
    // Decorators
    for (const [name, count] of Object.entries(fa.decorators)) {
      globalDecorators[name] = (globalDecorators[name] || 0) + count;
    }
    // Async
    globalAsync.async_functions += fa.async_patterns.async_functions;
    globalAsync.sync_functions += fa.async_patterns.sync_functions;
    globalAsync.async_for_loops += fa.async_patterns.async_for_loops;
    globalAsync.async_context_managers += fa.async_patterns.async_context_managers;

    // Side effects
    if (fa.side_effects.length > 0) {
      sideEffectsByFile[fa.filepath] = fa.side_effects;
      for (const se of fa.side_effects) {
        if (!sideEffectsByType[se.category]) sideEffectsByType[se.category] = [];
        sideEffectsByType[se.category].push({ file: fa.filepath, call: se.call, line: se.line });
      }
    }
    // Security concerns
    if (fa.security_concerns.length > 0) securityConcerns[fa.filepath] = fa.security_concerns;
    // Silent failures
    if (fa.silent_failures.length > 0) silentFailures[fa.filepath] = fa.silent_failures;
    // SQL strings
    if (fa.sql_strings.length > 0) sqlStrings[fa.filepath] = fa.sql_strings;
    // Deprecation markers
    for (const dm of fa.deprecation_markers) deprecationMarkers.push({ ...dm, file: fa.filepath });
    // Async violations
    for (const v of fa.async_violations) asyncViolations.push(v);
  }

  // Sort hotspots by complexity descending
  allHotspots.sort((a, b) => b.complexity - a.complexity);

  const typeCoverage = totalTypeFunctions > 0
    ? Math.round((typedFunctions / totalTypeFunctions) * 1000) / 10
    : 0;
  const averageCC = totalTypeFunctions > 0
    ? Math.round((totalCC / totalTypeFunctions) * 10) / 10
    : 0;

  const summary: Summary = {
    total_files: files.length,
    total_lines: totalLines,
    total_tokens: totalTokens,
    total_functions: totalFunctions,
    total_classes: totalClasses,
    type_coverage: typeCoverage,
    total_cc: totalCC,
    average_cc: averageCC,
    typed_functions: typedFunctions,
  };

  const structure: Structure = {
    files: fileResults,
    classes: allClasses,
    functions: allFunctions,
  };

  const complexity: Complexity = {
    hotspots: allHotspots.slice(0, 20),
    average_cc: averageCC,
    total_cc: totalCC,
  };

  const types: TypeCoverage = {
    coverage: typeCoverage,
    typed_functions: typedFunctions,
    total_functions: totalTypeFunctions,
  };

  const decorators: DecoratorInventory = {
    inventory: globalDecorators,
  };

  return {
    metadata: buildMetadata(targetDir, files.length, tsconfigPath),
    summary,
    structure,
    complexity,
    types,
    decorators,
    imports: importResults,
    calls: callResults,
    async_patterns: { ...globalAsync, violations: asyncViolations },
    hotspots: allHotspots,
    side_effects: { by_type: sideEffectsByType, by_file: sideEffectsByFile },
    security_concerns: securityConcerns,
    silent_failures: silentFailures,
    sql_strings: sqlStrings,
    deprecation_markers: deprecationMarkers,
    tests: testResults,
  };
}

// =============================================================================
// Helpers
// =============================================================================

function aggregateTsSpecific(
  fileResults: Record<string, FileAnalysis>,
  declarationFileCount: number,
  targetDir: string,
): TsSpecific | null {
  let explicitAny = 0;
  let asAnyAssertions = 0;
  let tsIgnoreCount = 0;
  let tsExpectErrorCount = 0;
  let esmCount = 0;
  let cjsCount = 0;
  const moduleAugmentations: TsSpecific["module_augmentations"] = [];
  const namespaces: TsSpecific["namespaces"] = [];

  for (const [fp, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, fp).replace(/\\/g, "/");
    if (fa.ts_any_counts) {
      explicitAny += fa.ts_any_counts.explicit_any;
      asAnyAssertions += fa.ts_any_counts.as_any_assertions;
      tsIgnoreCount += fa.ts_any_counts.ts_ignore_count;
      tsExpectErrorCount += fa.ts_any_counts.ts_expect_error_count;
    }
    if (fa.ts_module_style === "esm" || fa.ts_module_style === "mixed") esmCount++;
    if (fa.ts_module_style === "commonjs" || fa.ts_module_style === "mixed") cjsCount++;
    if (fa.ts_module_augmentations) {
      for (const aug of fa.ts_module_augmentations) {
        moduleAugmentations.push({ target_module: aug.target_module, file: rel, line: aug.line });
      }
    }
    if (fa.ts_namespaces) {
      for (const ns of fa.ts_namespaces) {
        namespaces.push({ name: ns.name, file: rel, line: ns.line, exported: ns.exported });
      }
    }
  }

  let moduleSystem: TsSpecific["module_system"];
  if (esmCount > 0 && cjsCount > 0) moduleSystem = "mixed";
  else if (cjsCount > 0) moduleSystem = "commonjs";
  else moduleSystem = "esm";

  const hasAnyCounts = explicitAny > 0 || asAnyAssertions > 0 || tsIgnoreCount > 0 || tsExpectErrorCount > 0;
  if (!hasAnyCounts && moduleAugmentations.length === 0 && namespaces.length === 0 && declarationFileCount === 0) {
    return null;
  }

  return {
    any_density: { explicit_any: explicitAny, as_any_assertions: asAnyAssertions, ts_ignore_count: tsIgnoreCount, ts_expect_error_count: tsExpectErrorCount },
    module_system: moduleSystem,
    declaration_file_count: declarationFileCount,
    module_augmentations: moduleAugmentations,
    namespaces: namespaces,
  };
}

function buildMetadata(targetDir: string, fileCount: number, tsconfigPath: string | null) {
  return {
    tool_version: VERSION,
    generated_at: new Date().toISOString(),
    target_directory: path.resolve(targetDir),
    preset: null,
    analysis_options: ["skeleton", "complexity", "types", "decorators"],
    file_count: fileCount,
    language: "typescript" as const,
    parser_tier: "syntax" as const,
    tsconfig_path: tsconfigPath,
  };
}

function emptySummary(): Summary {
  return {
    total_files: 0,
    total_lines: 0,
    total_tokens: 0,
    total_functions: 0,
    total_classes: 0,
    type_coverage: 0,
  };
}

main();

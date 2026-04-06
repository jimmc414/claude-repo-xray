/**
 * Test file detection and counting for TS/JS codebases.
 */

import * as fs from "fs";
import * as path from "path";
import type { TestAnalysis } from "./types.js";

const TEST_FILE_PATTERNS = [
  /\.test\.[tj]sx?$/,
  /\.spec\.[tj]sx?$/,
  /__tests__\//,
];

const TEST_CALL_RE = /\b(?:describe|it|test)\s*\(/g;

const FRAMEWORK_IMPORTS: Array<{ pattern: RegExp; name: string }> = [
  { pattern: /from\s+['"]vitest['"]/, name: "vitest" },
  { pattern: /from\s+['"]jest['"]|require\(['"]jest['"]\)/, name: "jest" },
  { pattern: /from\s+['"]mocha['"]|require\(['"]mocha['"]\)/, name: "mocha" },
  { pattern: /from\s+['"]@testing-library\//, name: "testing-library" },
];

function classifyTestType(filePath: string): string {
  const lower = filePath.toLowerCase();
  if (lower.includes("e2e") || lower.includes("end-to-end") || lower.includes("cypress") || lower.includes("playwright")) return "e2e";
  if (lower.includes("integration")) return "integration";
  return "unit";
}

export function analyzeTests(files: string[], targetDir: string): TestAnalysis {
  const testFiles: Array<{ path: string; tests: number }> = [];
  const coverageByType: Record<string, number> = {};
  let totalTests = 0;

  for (const filePath of files) {
    const rel = path.relative(targetDir, filePath);
    const isTest = TEST_FILE_PATTERNS.some(re => re.test(rel));
    if (!isTest) continue;

    let source: string;
    try {
      source = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }

    // Count test function calls
    const matches = source.match(TEST_CALL_RE);
    const testCount = matches ? matches.length : 0;
    totalTests += testCount;

    testFiles.push({ path: rel, tests: testCount });

    // Classify by type
    const testType = classifyTestType(rel);
    coverageByType[testType] = (coverageByType[testType] || 0) + testCount;
  }

  return {
    test_file_count: testFiles.length,
    test_function_count: totalTests,
    coverage_by_type: coverageByType,
    test_files: testFiles,
  };
}

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

const SETUP_TEARDOWN_RE = /\b(?:beforeAll|beforeEach|afterAll|afterEach)\s*\(/g;

const MOCKING_PATTERNS: Array<{ pattern: RegExp; name: string }> = [
  { pattern: /jest\.mock\s*\(/, name: "jest.mock" },
  { pattern: /jest\.fn\s*\(/, name: "jest.fn" },
  { pattern: /jest\.spyOn\s*\(/, name: "jest.spyOn" },
  { pattern: /vi\.mock\s*\(/, name: "vi.mock" },
  { pattern: /vi\.fn\s*\(/, name: "vi.fn" },
  { pattern: /vi\.spyOn\s*\(/, name: "vi.spyOn" },
  { pattern: /sinon\.stub\b/, name: "sinon.stub" },
  { pattern: /sinon\.mock\b/, name: "sinon.mock" },
  { pattern: /sinon\.spy\b/, name: "sinon.spy" },
  { pattern: /\bnock\s*\(/, name: "nock" },
  { pattern: /from\s+['"]msw['"]|require\(['"]msw['"]\)/, name: "msw" },
  { pattern: /\bsupertest\s*\(/, name: "supertest" },
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
  let totalSetupTeardown = 0;
  const allMockingPatterns = new Set<string>();

  // Track candidates for test_example selection
  const candidates: Array<{
    path: string;
    content: string;
    lineCount: number;
    patterns: string[];
    score: number;
  }> = [];

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

    // Setup/teardown detection
    const setupMatches = source.match(SETUP_TEARDOWN_RE);
    if (setupMatches) totalSetupTeardown += setupMatches.length;

    // Mocking pattern detection
    const filePatterns: string[] = [];
    for (const mp of MOCKING_PATTERNS) {
      if (mp.pattern.test(source)) {
        allMockingPatterns.add(mp.name);
        filePatterns.push(mp.name);
      }
    }

    // Test example candidate scoring
    const lineCount = source.split("\n").length;
    if (lineCount >= 10 && lineCount <= 80) {
      let score = 0;
      if (lineCount >= 15 && lineCount <= 50) score += 3;
      else score += 1;
      if (filePatterns.length > 0) score += 2;
      if (setupMatches && setupMatches.length > 0) score += 1;
      if (testCount >= 2) score += 1;
      candidates.push({ path: rel, content: source, lineCount, patterns: filePatterns, score });
    }
  }

  const result: TestAnalysis = {
    test_file_count: testFiles.length,
    test_function_count: totalTests,
    coverage_by_type: coverageByType,
    test_files: testFiles,
  };

  if (totalSetupTeardown > 0) result.setup_teardown_count = totalSetupTeardown;
  if (allMockingPatterns.size > 0) result.mocking_patterns = [...allMockingPatterns].sort();

  // Pick best test example
  if (candidates.length > 0) {
    candidates.sort((a, b) => b.score - a.score);
    const best = candidates[0];
    result.test_example = {
      file: best.path,
      content: best.content,
      line_count: best.lineCount,
      patterns: best.patterns,
    };
  }

  return result;
}

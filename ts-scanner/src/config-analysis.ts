/**
 * Project config rule extraction for TS/JS codebases.
 *
 * Reads tsconfig.json strict flags and detects ESLint/Prettier
 * config file presence. Reports which tools are configured
 * without attempting to parse JS-format config contents.
 */

import * as fs from "fs";
import * as path from "path";
import type { ConfigRules } from "./types.js";

// =============================================================================
// Strict-related tsconfig flags to extract
// =============================================================================

const TS_STRICT_FLAGS = [
  "strict",
  "noImplicitAny",
  "strictNullChecks",
  "strictFunctionTypes",
  "strictBindCallApply",
  "strictPropertyInitialization",
  "noImplicitReturns",
  "noFallthroughCasesInSwitch",
  "noUncheckedIndexedAccess",
  "noUnusedLocals",
  "noUnusedParameters",
  "exactOptionalPropertyTypes",
  "noImplicitOverride",
  "verbatimModuleSyntax",
];

// =============================================================================
// Config file candidates
// =============================================================================

const ESLINT_CONFIGS = [
  "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
  ".eslintrc", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
  ".eslintrc.js", ".eslintrc.cjs",
];

const PRETTIER_CONFIGS = [
  ".prettierrc", ".prettierrc.json", ".prettierrc.yml", ".prettierrc.yaml",
  ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.toml",
  "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs",
];

const KNOWN_ESLINT_FRAMEWORKS: Record<string, string> = {
  "eslint-config-airbnb": "airbnb",
  "eslint-config-standard": "standard",
  "eslint-config-next": "next",
  "eslint-config-prettier": "prettier",
  "@typescript-eslint": "typescript-eslint",
};

// =============================================================================
// Public API
// =============================================================================

export function analyzeConfig(rootDir: string, tsconfigPath: string | null): ConfigRules {
  return {
    typescript: extractTsConfig(tsconfigPath),
    eslint: detectEslint(rootDir),
    prettier: detectPrettier(rootDir),
  };
}

// =============================================================================
// tsconfig.json parsing
// =============================================================================

function extractTsConfig(tsconfigPath: string | null): ConfigRules["typescript"] {
  if (!tsconfigPath) return null;

  try {
    const content = fs.readFileSync(tsconfigPath, "utf-8");
    const parsed = JSON.parse(content);
    const compilerOptions = parsed.compilerOptions ?? {};

    const flags: Record<string, boolean | string> = {};
    for (const flag of TS_STRICT_FLAGS) {
      if (flag in compilerOptions) {
        flags[flag] = compilerOptions[flag];
      }
    }

    // Also capture target and module if present
    if (compilerOptions.target) flags["target"] = String(compilerOptions.target);
    if (compilerOptions.module) flags["module"] = String(compilerOptions.module);

    return {
      strict: compilerOptions.strict === true,
      flags,
      config_file: path.basename(tsconfigPath),
    };
  } catch {
    return null;
  }
}

// =============================================================================
// ESLint detection
// =============================================================================

function detectEslint(rootDir: string): ConfigRules["eslint"] {
  for (const candidate of ESLINT_CONFIGS) {
    const fullPath = path.join(rootDir, candidate);
    if (fs.existsSync(fullPath)) {
      let framework: string | null = null;

      // Try to detect framework from JSON-parseable configs
      if (candidate.endsWith(".json") || candidate === ".eslintrc") {
        try {
          const content = fs.readFileSync(fullPath, "utf-8");
          const parsed = JSON.parse(content);
          const extendsVal = parsed.extends;
          const extendsList = Array.isArray(extendsVal) ? extendsVal : extendsVal ? [extendsVal] : [];
          for (const ext of extendsList) {
            if (typeof ext !== "string") continue;
            for (const [pattern, name] of Object.entries(KNOWN_ESLINT_FRAMEWORKS)) {
              if (ext.includes(pattern)) {
                framework = name;
                break;
              }
            }
            if (framework) break;
          }
        } catch {
          // Malformed JSON or not actually JSON — skip framework detection
        }
      }

      return { config_file: candidate, framework };
    }
  }
  return null;
}

// =============================================================================
// Prettier detection
// =============================================================================

function detectPrettier(rootDir: string): ConfigRules["prettier"] {
  for (const candidate of PRETTIER_CONFIGS) {
    const fullPath = path.join(rootDir, candidate);
    if (fs.existsSync(fullPath)) {
      return { config_file: candidate };
    }
  }
  return null;
}

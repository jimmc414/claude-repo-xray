/**
 * CLI argument extraction for TS/JS codebases.
 *
 * Detects CLI framework from imports and pattern-matches
 * .option()/.command() calls for commander and yargs.
 * For other frameworks, reports the framework name only.
 *
 * Best-effort ~70% accuracy. Does not attempt exhaustive
 * extraction since the TS CLI landscape is fragmented.
 */

import * as fs from "fs";
import * as ts from "typescript";
import type { CliAnalysis } from "./types.js";
import { getScriptKind } from "./utils.js";

// =============================================================================
// Known CLI frameworks
// =============================================================================

const CLI_FRAMEWORKS = [
  "commander",
  "yargs",
  "meow",
  "cac",
  "gunshi",
  "clipanion",
];

const CLI_IMPORT_RE = new RegExp(
  `(?:from\\s+["'](${CLI_FRAMEWORKS.join("|")})["']|require\\(["'](${CLI_FRAMEWORKS.join("|")})["']\\))`,
);

// =============================================================================
// Public API
// =============================================================================

export function analyzeCli(files: string[]): CliAnalysis | null {
  // Quick scan: find the first file that imports a CLI framework
  for (const filePath of files) {
    let source: string;
    try {
      source = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }

    const match = CLI_IMPORT_RE.exec(source);
    if (!match) continue;

    const framework = match[1] || match[2];

    // Deep extraction for commander and yargs
    if (framework === "commander") {
      return extractCommander(source, filePath, framework);
    }
    if (framework === "yargs") {
      return extractYargs(source, filePath, framework);
    }
    if (framework === "gunshi") {
      // Gunshi uses define() across multiple files — scan all
      return extractGunshi(files);
    }

    // Other frameworks: report name only
    return { framework, commands: [], options: [] };
  }

  return null;
}

// =============================================================================
// Commander extraction
// =============================================================================

function extractCommander(source: string, filePath: string, framework: string): CliAnalysis {
  const scriptKind = getScriptKind(filePath);
  const sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, scriptKind);

  const commands: CliAnalysis["commands"] = [];
  const options: CliAnalysis["options"] = [];

  function walk(node: ts.Node): void {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const methodName = node.expression.name.text;

      if (methodName === "option" && node.arguments.length >= 1) {
        const flagArg = node.arguments[0];
        if (ts.isStringLiteral(flagArg)) {
          const description = node.arguments.length >= 2 && ts.isStringLiteral(node.arguments[1])
            ? node.arguments[1].text
            : null;
          options.push({ flag: flagArg.text, description });
        }
      }

      if (methodName === "command" && node.arguments.length >= 1) {
        const nameArg = node.arguments[0];
        if (ts.isStringLiteral(nameArg)) {
          const description = node.arguments.length >= 2 && ts.isStringLiteral(node.arguments[1])
            ? node.arguments[1].text
            : null;
          commands.push({ name: nameArg.text, description });
        }
      }

      // commander also uses .requiredOption()
      if (methodName === "requiredOption" && node.arguments.length >= 1) {
        const flagArg = node.arguments[0];
        if (ts.isStringLiteral(flagArg)) {
          const description = node.arguments.length >= 2 && ts.isStringLiteral(node.arguments[1])
            ? node.arguments[1].text
            : null;
          options.push({ flag: flagArg.text, description });
        }
      }
    }

    ts.forEachChild(node, walk);
  }

  walk(sourceFile);
  return { framework, commands, options };
}

// =============================================================================
// Yargs extraction
// =============================================================================

function extractYargs(source: string, filePath: string, framework: string): CliAnalysis {
  const scriptKind = getScriptKind(filePath);
  const sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, scriptKind);

  const commands: CliAnalysis["commands"] = [];
  const options: CliAnalysis["options"] = [];

  function walk(node: ts.Node): void {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const methodName = node.expression.name.text;

      // .option('name', { describe: ..., type: ... })
      if (methodName === "option" && node.arguments.length >= 1) {
        const nameArg = node.arguments[0];
        if (ts.isStringLiteral(nameArg)) {
          let description: string | null = null;
          let type: string | undefined;

          if (node.arguments.length >= 2 && ts.isObjectLiteralExpression(node.arguments[1])) {
            const props = node.arguments[1] as ts.ObjectLiteralExpression;
            for (const prop of props.properties) {
              if (!ts.isPropertyAssignment(prop) || !ts.isIdentifier(prop.name)) continue;
              const propName = prop.name.text;
              if ((propName === "describe" || propName === "description") && ts.isStringLiteral(prop.initializer)) {
                description = prop.initializer.text;
              }
              if (propName === "type" && ts.isStringLiteral(prop.initializer)) {
                type = prop.initializer.text;
              }
            }
          }

          options.push({ flag: nameArg.text, description, ...(type ? { type } : {}) });
        }
      }

      // .command('name', 'description', ...)
      if (methodName === "command" && node.arguments.length >= 1) {
        const nameArg = node.arguments[0];
        if (ts.isStringLiteral(nameArg)) {
          const description = node.arguments.length >= 2 && ts.isStringLiteral(node.arguments[1])
            ? node.arguments[1].text
            : null;
          commands.push({ name: nameArg.text, description });
        }
      }
    }

    ts.forEachChild(node, walk);
  }

  walk(sourceFile);
  return { framework, commands, options };
}

// =============================================================================
// Gunshi extraction (multi-file: define() calls spread across command files)
// =============================================================================

function extractGunshi(files: string[]): CliAnalysis {
  const commands: CliAnalysis["commands"] = [];
  const options: CliAnalysis["options"] = [];
  const seenFlags = new Set<string>();

  for (const filePath of files) {
    let source: string;
    try {
      source = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }

    if (!CLI_IMPORT_RE.test(source)) continue;

    const scriptKind = getScriptKind(filePath);
    const sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, scriptKind);

    function walk(node: ts.Node): void {
      // Match: define({ name: '...', description: '...', args: { ... } })
      if (
        ts.isCallExpression(node) &&
        ts.isIdentifier(node.expression) &&
        node.expression.text === "define" &&
        node.arguments.length >= 1 &&
        ts.isObjectLiteralExpression(node.arguments[0])
      ) {
        const obj = node.arguments[0] as ts.ObjectLiteralExpression;
        let cmdName: string | null = null;
        let cmdDesc: string | null = null;

        for (const prop of obj.properties) {
          if (!ts.isPropertyAssignment(prop) || !ts.isIdentifier(prop.name)) continue;

          if (prop.name.text === "name" && ts.isStringLiteral(prop.initializer)) {
            cmdName = prop.initializer.text;
          }
          if (prop.name.text === "description" && ts.isStringLiteral(prop.initializer)) {
            cmdDesc = prop.initializer.text;
          }
          if (prop.name.text === "args" && ts.isObjectLiteralExpression(prop.initializer)) {
            for (const argProp of prop.initializer.properties) {
              if (!ts.isPropertyAssignment(argProp) || !ts.isIdentifier(argProp.name)) continue;
              const argName = argProp.name.text;
              let argDesc: string | null = null;
              let argShort: string | null = null;

              if (ts.isObjectLiteralExpression(argProp.initializer)) {
                for (const detail of argProp.initializer.properties) {
                  if (!ts.isPropertyAssignment(detail) || !ts.isIdentifier(detail.name)) continue;
                  if (detail.name.text === "description" && ts.isStringLiteral(detail.initializer)) {
                    argDesc = detail.initializer.text;
                  }
                  if (detail.name.text === "short" && ts.isStringLiteral(detail.initializer)) {
                    argShort = detail.initializer.text;
                  }
                }
              }

              const flag = argShort ? `--${argName}, -${argShort}` : `--${argName}`;
              if (!seenFlags.has(flag)) {
                seenFlags.add(flag);
                options.push({ flag, description: argDesc });
              }
            }
          }
        }

        if (cmdName) {
          commands.push({ name: cmdName, description: cmdDesc });
        }
      }

      ts.forEachChild(node, walk);
    }

    walk(sourceFile);
  }

  return { framework: "gunshi", commands, options };
}

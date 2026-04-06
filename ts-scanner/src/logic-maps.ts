/**
 * Logic map generation for hotspot functions.
 *
 * Re-parses source files for the top-N complex functions and walks
 * their bodies to produce indented control-flow visualizations,
 * side-effect inventories, and heuristic summaries.
 *
 * Output shape matches the Python scanner's logic_maps exactly.
 */

import * as fs from "fs";
import * as ts from "typescript";
import type { LogicMap, FileAnalysis } from "./types.js";
import { getJSDocSummary, getLineNumber } from "./ast-analysis.js";
import { getScriptKind } from "./utils.js";

// =============================================================================
// Side-effect pattern tables
// =============================================================================

const SIDE_EFFECT_PATTERNS: Record<string, string[]> = {
  db: ["db.save", "db.commit", "session.commit", "cursor.execute", ".insert(", ".update(", ".delete("],
  api: ["requests.", "httpx.", "fetch(", ".post(", ".put(", ".patch("],
  file: ["fs.write", "fs.readFile", "writeFileSync", ".write("],
  cache: ["cache.set", "redis.set", "cache.invalidate"],
  logging: ["console.log", "console.error", "console.warn", "logger."],
};

const SAFE_PATTERNS = [".get(", "instanceof", "typeof", "hasOwnProperty", ".length", ".toString("];

// =============================================================================
// Public API
// =============================================================================

export function generateLogicMaps(
  hotspots: Array<{ file: string; function: string; complexity: number }>,
  fileResults: Record<string, FileAnalysis>,
  maxMaps: number = 10,
): LogicMap[] {
  const maps: LogicMap[] = [];
  const seen = new Set<string>();

  for (const hs of hotspots) {
    if (maps.length >= maxMaps) break;

    const key = `${hs.file}:${hs.function}`;
    if (seen.has(key)) continue;
    seen.add(key);

    const map = generateOneMap(hs.file, hs.function, hs.complexity);
    if (map) maps.push(map);
  }

  return maps;
}

// =============================================================================
// Single function map generation
// =============================================================================

function generateOneMap(
  filePath: string,
  funcName: string,
  complexity: number,
): LogicMap | null {
  let source: string;
  try {
    source = fs.readFileSync(filePath, "utf-8");
  } catch {
    return null;
  }

  const scriptKind = getScriptKind(filePath);
  const sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, scriptKind);

  // Find the target function/method node
  const target = findFunction(sourceFile, funcName);
  if (!target) return null;

  const body = getBody(target);
  if (!body) return null;

  const flow: string[] = [];
  const sideEffects: string[] = [];
  const stateMutations: string[] = [];
  const conditions: string[] = [];

  walkBody(body, sourceFile, 0, flow, sideEffects, stateMutations, conditions);

  const docstring = getJSDocSummary(target);
  const heuristic = generateHeuristic(body);
  const line = getLineNumber(target, sourceFile);

  return {
    method: funcName,
    file: filePath,
    line,
    complexity,
    flow,
    side_effects: [...new Set(sideEffects)],
    state_mutations: [...new Set(stateMutations)],
    conditions: [...new Set(conditions)],
    docstring,
    heuristic,
  };
}

// =============================================================================
// Function finder
// =============================================================================

function findFunction(sourceFile: ts.SourceFile, name: string): ts.Node | null {
  // Name may be "ClassName.methodName" or just "functionName"
  const parts = name.split(".");
  const isMethod = parts.length === 2;
  const className = isMethod ? parts[0] : null;
  const methodName = isMethod ? parts[1] : null;
  const funcName = isMethod ? null : parts[0];

  let found: ts.Node | null = null;

  function walk(node: ts.Node): void {
    if (found) return;

    // Top-level function declaration
    if (!isMethod && ts.isFunctionDeclaration(node) && node.name?.text === funcName) {
      found = node;
      return;
    }

    // Arrow/function expression assigned to const
    if (!isMethod && ts.isVariableStatement(node)) {
      for (const decl of node.declarationList.declarations) {
        if (ts.isIdentifier(decl.name) && decl.name.text === funcName &&
            decl.initializer && (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer))) {
          found = decl.initializer;
          return;
        }
      }
    }

    // Class method
    if (isMethod && (ts.isClassDeclaration(node) || ts.isClassExpression(node)) &&
        node.name?.text === className) {
      for (const member of node.members) {
        if ((ts.isMethodDeclaration(member) || ts.isConstructorDeclaration(member)) &&
            (ts.isConstructorDeclaration(member) ? "constructor" : member.name?.getText(sourceFile)) === methodName) {
          found = member;
          return;
        }
      }
    }

    ts.forEachChild(node, walk);
  }

  ts.forEachChild(sourceFile, walk);
  return found;
}

function getBody(node: ts.Node): ts.Node | null {
  if ("body" in node && (node as { body?: ts.Node }).body) {
    return (node as { body: ts.Node }).body;
  }
  return null;
}

// =============================================================================
// Body walker — emit flow lines
// =============================================================================

function walkBody(
  node: ts.Node,
  sf: ts.SourceFile,
  indent: number,
  flow: string[],
  sideEffects: string[],
  stateMutations: string[],
  conditions: string[],
): void {
  const prefix = "  ".repeat(indent);

  // If statement
  if (ts.isIfStatement(node)) {
    const cond = truncateText(node.expression.getText(sf), 60);
    flow.push(`${prefix}-> ${cond}?`);
    conditions.push(cond);
    walkBody(node.thenStatement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    if (node.elseStatement) {
      flow.push(`${prefix}-> else:`);
      walkBody(node.elseStatement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    }
    return;
  }

  // Switch statement
  if (ts.isSwitchStatement(node)) {
    const expr = truncateText(node.expression.getText(sf), 40);
    flow.push(`${prefix}-> switch(${expr})`);
    for (const clause of node.caseBlock.clauses) {
      if (ts.isCaseClause(clause)) {
        const val = truncateText(clause.expression.getText(sf), 30);
        flow.push(`${prefix}  case ${val}:`);
      } else {
        flow.push(`${prefix}  default:`);
      }
      for (const stmt of clause.statements) {
        walkBody(stmt, sf, indent + 2, flow, sideEffects, stateMutations, conditions);
      }
    }
    return;
  }

  // For statement
  if (ts.isForStatement(node)) {
    const init = node.initializer ? truncateText(node.initializer.getText(sf), 30) : "";
    const cond = node.condition ? truncateText(node.condition.getText(sf), 30) : "";
    const incr = node.incrementor ? truncateText(node.incrementor.getText(sf), 20) : "";
    flow.push(`${prefix}* for ${init}; ${cond}; ${incr}:`);
    walkBody(node.statement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    return;
  }

  // For-of statement
  if (ts.isForOfStatement(node)) {
    const varText = node.initializer.getText(sf);
    const exprText = truncateText(node.expression.getText(sf), 40);
    flow.push(`${prefix}* for ${varText} of ${exprText}:`);
    walkBody(node.statement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    return;
  }

  // For-in statement
  if (ts.isForInStatement(node)) {
    const varText = node.initializer.getText(sf);
    const exprText = truncateText(node.expression.getText(sf), 40);
    flow.push(`${prefix}* for ${varText} in ${exprText}:`);
    walkBody(node.statement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    return;
  }

  // While statement
  if (ts.isWhileStatement(node)) {
    const cond = truncateText(node.expression.getText(sf), 60);
    flow.push(`${prefix}* while ${cond}:`);
    walkBody(node.statement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    return;
  }

  // Do-while statement
  if (ts.isDoStatement(node)) {
    const cond = truncateText(node.expression.getText(sf), 60);
    flow.push(`${prefix}* do...while ${cond}:`);
    walkBody(node.statement, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    return;
  }

  // Try statement
  if (ts.isTryStatement(node)) {
    flow.push(`${prefix}try:`);
    walkBody(node.tryBlock, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    if (node.catchClause) {
      const param = node.catchClause.variableDeclaration
        ? node.catchClause.variableDeclaration.getText(sf)
        : "";
      flow.push(`${prefix}! catch ${param}`);
      walkBody(node.catchClause.block, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    }
    if (node.finallyBlock) {
      flow.push(`${prefix}finally:`);
      walkBody(node.finallyBlock, sf, indent + 1, flow, sideEffects, stateMutations, conditions);
    }
    return;
  }

  // Return statement
  if (ts.isReturnStatement(node)) {
    if (node.expression) {
      const expr = truncateText(node.expression.getText(sf), 60);
      flow.push(`${prefix}-> Return(${expr})`);
    } else {
      flow.push(`${prefix}-> Return`);
    }
    return;
  }

  // Throw statement
  if (ts.isThrowStatement(node)) {
    const expr = node.expression ? truncateText(node.expression.getText(sf), 60) : "";
    flow.push(`${prefix}-> Throw(${expr})`);
    return;
  }

  // Call expression — check for side effects
  if (ts.isCallExpression(node)) {
    const callText = node.expression.getText(sf);
    const category = classifySideEffect(callText);
    if (category) {
      const truncated = truncateText(callText + "()", 50);
      flow.push(`${prefix}[${category.toUpperCase()}: ${truncated}]`);
      sideEffects.push(`${category}: ${truncated}`);
    }
    // Still recurse into arguments
    for (const arg of node.arguments) {
      walkBody(arg, sf, indent, flow, sideEffects, stateMutations, conditions);
    }
    return;
  }

  // this.prop = value → state mutation
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isPropertyAccessExpression(node.left) &&
      node.left.expression.kind === ts.SyntaxKind.ThisKeyword) {
    const prop = node.left.name.text;
    stateMutations.push(`this.${prop}`);
    flow.push(`${prefix}{this.${prop}}`);
    return;
  }

  // Recurse into child statements
  ts.forEachChild(node, child => {
    walkBody(child, sf, indent, flow, sideEffects, stateMutations, conditions);
  });
}

// =============================================================================
// Side-effect classification
// =============================================================================

function classifySideEffect(callText: string): string | null {
  // Skip safe patterns
  for (const safe of SAFE_PATTERNS) {
    if (callText.includes(safe)) return null;
  }
  for (const [category, patterns] of Object.entries(SIDE_EFFECT_PATTERNS)) {
    for (const pat of patterns) {
      if (callText.includes(pat.replace("(", ""))) return category;
    }
  }
  return null;
}

// =============================================================================
// Heuristic summary generation
// =============================================================================

function generateHeuristic(body: ts.Node): string {
  let loops = 0;
  let branches = 0;
  let returns = 0;
  let tries = 0;

  function count(n: ts.Node): void {
    switch (n.kind) {
      case ts.SyntaxKind.ForStatement:
      case ts.SyntaxKind.ForOfStatement:
      case ts.SyntaxKind.ForInStatement:
      case ts.SyntaxKind.WhileStatement:
      case ts.SyntaxKind.DoStatement:
        loops++;
        break;
      case ts.SyntaxKind.IfStatement:
      case ts.SyntaxKind.CaseClause:
      case ts.SyntaxKind.ConditionalExpression:
        branches++;
        break;
      case ts.SyntaxKind.ReturnStatement:
        returns++;
        break;
      case ts.SyntaxKind.TryStatement:
        tries++;
        break;
    }
    ts.forEachChild(n, count);
  }
  count(body);

  const parts: string[] = [];
  if (loops > 0) parts.push(`Iterates over ${loops} collection${loops > 1 ? "s" : ""}.`);
  if (branches > 0) parts.push(`${branches} decision branch${branches > 1 ? "es" : ""}.`);
  if (returns > 1) parts.push(`${returns} return points.`);
  if (tries > 0) parts.push(`Handles ${tries} exception type${tries > 1 ? "s" : ""}.`);
  return parts.join(" ") || "Simple linear flow.";
}

// =============================================================================
// Helpers
// =============================================================================

function truncateText(text: string, maxLen: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= maxLen) return oneLine;
  return oneLine.substring(0, maxLen - 3) + "...";
}

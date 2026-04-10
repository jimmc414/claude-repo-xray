/**
 * Behavioral signal detectors for the TS scanner.
 *
 * Each function is pure: takes a TS AST node + SourceFile, returns
 * a detection result or null. Called from walkPass1 in ast-analysis.ts.
 */

import * as ts from "typescript";
import type {
  SilentFailure, SecurityConcern, SideEffect, SqlString,
  AsyncViolation, DeprecationMarker, EnvVar, InstanceVar, ResourceLeak,
} from "./types.js";

// =============================================================================
// 2B-1: Silent failure detection
// =============================================================================

const LOG_PREFIXES = new Set([
  "console", "logger", "log", "logging",
  "winston", "pino", "bunyan",
  "sentry", "Sentry",
]);

function isLogOnlyCall(stmt: ts.Statement): boolean {
  if (!ts.isExpressionStatement(stmt)) return false;
  const expr = stmt.expression;
  if (!ts.isCallExpression(expr)) return false;
  const callee = expr.expression;
  if (!ts.isPropertyAccessExpression(callee)) return false;
  return LOG_PREFIXES.has(callee.expression.getText());
}

export function detectSilentFailure(node: ts.CatchClause, sourceFile: ts.SourceFile): SilentFailure | null {
  const block = node.block;
  const stmts = block.statements;
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;

  if (stmts.length === 0) {
    return { type: "empty_catch", line, context: "catch with empty block" };
  }

  if (stmts.length <= 2 && stmts.every(s => isLogOnlyCall(s))) {
    return { type: "logged_catch", line, context: "catch only logs, does not rethrow" };
  }

  return null;
}

// =============================================================================
// 2B-2: Security concern detection
// =============================================================================

const SECURITY_CALL_PATTERNS: Array<{ pattern: string; type: string; severity: SecurityConcern["severity"] }> = [
  { pattern: "eval", type: "code_execution", severity: "high" },
  { pattern: "child_process.exec", type: "subprocess", severity: "high" },
  { pattern: "child_process.execSync", type: "subprocess", severity: "high" },
  { pattern: "document.write", type: "dom_injection", severity: "medium" },
  // Unsafe deserialization
  { pattern: "vm.runInContext", type: "unsafe_deserialization", severity: "high" },
  { pattern: "vm.runInNewContext", type: "unsafe_deserialization", severity: "high" },
  { pattern: "vm.runInThisContext", type: "unsafe_deserialization", severity: "high" },
  { pattern: "yaml.load", type: "unsafe_deserialization", severity: "medium" },
  { pattern: "deserialize", type: "unsafe_deserialization", severity: "medium" },
];

export function detectSecurityConcern(node: ts.CallExpression, sourceFile: ts.SourceFile): SecurityConcern | null {
  const callText = node.expression.getText(sourceFile);
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;

  // new Function(...)
  if (ts.isNewExpression(node.parent) === false && ts.isNewExpression(node as unknown as ts.Node) === false) {
    // Check for plain call matches
    for (const p of SECURITY_CALL_PATTERNS) {
      if (callText === p.pattern || callText.endsWith("." + p.pattern)) {
        return { type: p.type, call: callText, line, severity: p.severity };
      }
    }
  }

  return null;
}

export function detectSecurityNewExpression(node: ts.NewExpression, sourceFile: ts.SourceFile): SecurityConcern | null {
  const callText = node.expression.getText(sourceFile);
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;

  if (callText === "Function") {
    return { type: "code_execution", call: "new Function()", line, severity: "high" };
  }

  return null;
}

export function detectSecurityAssignment(node: ts.BinaryExpression, sourceFile: ts.SourceFile): SecurityConcern | null {
  if (node.operatorToken.kind !== ts.SyntaxKind.EqualsToken) return null;
  const left = node.left;
  if (!ts.isPropertyAccessExpression(left)) return null;
  const prop = left.name.text;
  if (prop === "innerHTML") {
    const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
    return { type: "dom_injection", call: "innerHTML assignment", line, severity: "medium" };
  }
  return null;
}

// =============================================================================
// 2B-3: Deprecation marker detection
// =============================================================================

export function detectDeprecationJSDoc(node: ts.Node, sourceFile: ts.SourceFile): { reason: string | null } | null {
  const tag = ts.getJSDocDeprecatedTag(node);
  if (!tag) return null;
  let reason: string | null = null;
  if (tag.comment) {
    reason = typeof tag.comment === "string"
      ? tag.comment
      : tag.comment.map(c => c.getText()).join("");
  }
  return { reason };
}

export function detectDeprecationDecorator(decorators: string[]): boolean {
  return decorators.some(d => d.toLowerCase() === "deprecated");
}

// =============================================================================
// 2B-4: Side effect detection
// =============================================================================

const SIDE_EFFECT_PATTERNS: Array<{ suffixes: string[]; category: string }> = [
  { suffixes: ["fs.readFileSync", "fs.writeFileSync", "fs.writeFile", "fs.readFile", "fs.mkdir", "fs.mkdirSync", "fs.unlink", "fs.unlinkSync", "fs.rmSync", "fs.appendFile", "fs.appendFileSync", "fs.copyFile", "fs.copyFileSync", "fs.rename", "fs.renameSync"], category: "file_io" },
  { suffixes: ["fetch", "axios.get", "axios.post", "axios.put", "axios.delete", "axios.patch", "axios.request", "http.request", "http.get", "https.request", "https.get"], category: "network" },
  { suffixes: ["child_process.exec", "child_process.execSync", "child_process.spawn", "child_process.spawnSync", "execSync", "spawnSync"], category: "subprocess" },
  { suffixes: ["process.exit", "process.kill"], category: "process" },
  { suffixes: ["console.log", "console.error", "console.warn", "console.info", "console.debug"], category: "console" },
];

// Database patterns that use prefix matching
const DB_PREFIXES = ["prisma.", "mongoose.", "knex("];

export function detectSideEffect(node: ts.CallExpression, sourceFile: ts.SourceFile): SideEffect | null {
  const callText = node.expression.getText(sourceFile);
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;

  for (const group of SIDE_EFFECT_PATTERNS) {
    for (const suffix of group.suffixes) {
      if (callText === suffix || callText.endsWith("." + suffix)) {
        return { category: group.category, call: callText, line };
      }
    }
  }

  // Database patterns (prefix match)
  for (const prefix of DB_PREFIXES) {
    if (callText.startsWith(prefix)) {
      return { category: "database", call: callText, line };
    }
  }

  // .query( pattern for database
  if (callText.endsWith(".query")) {
    return { category: "database", call: callText, line };
  }

  return null;
}

// =============================================================================
// 2B-6: SQL string detection
// =============================================================================

const SQL_PATTERNS = [
  /SELECT\s+\S+\s+FROM/i,
  /INSERT\s+INTO/i,
  /DELETE\s+FROM/i,
  /UPDATE\s+\S+\s+SET/i,
  /CREATE\s+(TABLE|INDEX|VIEW)/i,
];

function matchesSql(text: string): boolean {
  return SQL_PATTERNS.some(re => re.test(text));
}

export function detectSqlString(node: ts.StringLiteral | ts.NoSubstitutionTemplateLiteral, sourceFile: ts.SourceFile): SqlString | null {
  const text = node.text;
  if (!matchesSql(text)) return null;
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
  const snippet = text.length > 60 ? text.substring(0, 57) + "..." : text;
  return { line, sql: snippet, context: "string_literal", type: "query" };
}

export function detectSqlTemplate(node: ts.TemplateExpression, sourceFile: ts.SourceFile): SqlString | null {
  // Concatenate head + spans text for matching
  let text = node.head.text;
  for (const span of node.templateSpans) {
    text += "?" + span.literal.text;
  }
  if (!matchesSql(text)) return null;
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
  const snippet = text.length > 60 ? text.substring(0, 57) + "..." : text;
  return { line, sql: snippet, context: "template_literal", type: "template" };
}

export function detectSqlTaggedTemplate(node: ts.TaggedTemplateExpression, sourceFile: ts.SourceFile): SqlString | null {
  const tag = node.tag.getText(sourceFile);
  if (tag !== "sql" && tag !== "Prisma.sql") return null;
  let text: string;
  if (ts.isNoSubstitutionTemplateLiteral(node.template)) {
    text = node.template.text;
  } else {
    text = node.template.head.text;
    for (const span of node.template.templateSpans) {
      text += "?" + span.literal.text;
    }
  }
  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
  const snippet = text.length > 60 ? text.substring(0, 57) + "..." : text;
  return { line, sql: snippet, context: "tagged_template", type: "tagged" };
}

// =============================================================================
// 2B-7: Environment variable detection
// =============================================================================

export function detectEnvVar(node: ts.Node, sourceFile: ts.SourceFile): { variable: string; line: number } | null {
  // process.env.FOO (PropertyAccessExpression)
  if (ts.isPropertyAccessExpression(node)) {
    const expr = node.expression;
    if (ts.isPropertyAccessExpression(expr) &&
        expr.expression.getText(sourceFile) === "process" &&
        expr.name.text === "env") {
      const variable = node.name.text;
      const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
      return { variable, line };
    }
  }

  // process.env["FOO"] (ElementAccessExpression)
  if (ts.isElementAccessExpression(node)) {
    const expr = node.expression;
    if (ts.isPropertyAccessExpression(expr) &&
        expr.expression.getText(sourceFile) === "process" &&
        expr.name.text === "env") {
      const arg = node.argumentExpression;
      if (ts.isStringLiteral(arg)) {
        const variable = arg.text;
        const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
        return { variable, line };
      }
    }
  }

  return null;
}

export function extractEnvVarDefault(node: ts.Node): { default: string | null; fallback_type: EnvVar["fallback_type"] } {
  const parent = node.parent;
  if (!parent || !ts.isBinaryExpression(parent)) {
    return { default: null, fallback_type: "none" };
  }

  // Only match when the env access is on the left side
  if (parent.left !== node) {
    return { default: null, fallback_type: "none" };
  }

  if (parent.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken) {
    const right = parent.right;
    const val = ts.isStringLiteral(right) ? right.text
      : ts.isNumericLiteral(right) ? right.text
      : null;
    return { default: val, fallback_type: "nullish_coalesce" };
  }

  if (parent.operatorToken.kind === ts.SyntaxKind.BarBarToken) {
    const right = parent.right;
    const val = ts.isStringLiteral(right) ? right.text
      : ts.isNumericLiteral(right) ? right.text
      : null;
    return { default: val, fallback_type: "or_fallback" };
  }

  return { default: null, fallback_type: "none" };
}

// =============================================================================
// 2B-8: Async violation detection
// =============================================================================

const SYNC_BLOCKING_APIS = [
  "fs.readFileSync", "fs.writeFileSync", "fs.appendFileSync",
  "fs.mkdirSync", "fs.unlinkSync", "fs.rmSync", "fs.copyFileSync",
  "fs.renameSync", "fs.existsSync", "fs.statSync", "fs.readdirSync",
  "execSync", "spawnSync",
  "child_process.execSync", "child_process.spawnSync",
];

export function detectAsyncViolation(node: ts.CallExpression, sourceFile: ts.SourceFile): { violation_type: string; call: string } | null {
  const callText = node.expression.getText(sourceFile);

  for (const api of SYNC_BLOCKING_APIS) {
    if (callText === api || callText.endsWith("." + api)) {
      return { violation_type: "blocking_io", call: callText };
    }
  }

  return null;
}

// =============================================================================
// 2B-9: Class field extraction
// =============================================================================

function getVisibility(node: ts.Node): InstanceVar["visibility"] {
  const mods = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
  if (mods) {
    for (const m of mods) {
      if (m.kind === ts.SyntaxKind.PrivateKeyword) return "private";
      if (m.kind === ts.SyntaxKind.ProtectedKeyword) return "protected";
    }
  }
  return "public";
}

export function extractInstanceVars(node: ts.ClassDeclaration | ts.ClassExpression, sourceFile: ts.SourceFile): InstanceVar[] {
  const vars: InstanceVar[] = [];
  const seen = new Set<string>();

  // Property declarations
  for (const member of node.members) {
    if (ts.isPropertyDeclaration(member) && member.name) {
      const name = member.name.getText(sourceFile);
      const line = sourceFile.getLineAndCharacterOfPosition(member.getStart(sourceFile)).line + 1;
      const typeNode = member.type;
      const type = typeNode ? typeNode.getText(sourceFile) : null;
      const visibility = getVisibility(member);
      const hasDefault = !!member.initializer;
      vars.push({ name, type, visibility, has_default: hasDefault, line });
      seen.add(name);
    }
  }

  // Constructor this.X = Y assignments
  for (const member of node.members) {
    if (ts.isConstructorDeclaration(member) && member.body) {
      for (const stmt of member.body.statements) {
        if (ts.isExpressionStatement(stmt) && ts.isBinaryExpression(stmt.expression)) {
          const bin = stmt.expression;
          if (bin.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
              ts.isPropertyAccessExpression(bin.left) &&
              bin.left.expression.kind === ts.SyntaxKind.ThisKeyword) {
            const name = bin.left.name.text;
            if (!seen.has(name)) {
              const line = sourceFile.getLineAndCharacterOfPosition(stmt.getStart(sourceFile)).line + 1;
              vars.push({ name, type: null, visibility: "public", has_default: true, line });
              seen.add(name);
            }
          }
        }
      }
    }
  }

  return vars;
}

// =============================================================================
// Dynamic require detection (security concern)
// =============================================================================

export function detectDynamicRequire(node: ts.CallExpression, sourceFile: ts.SourceFile): SecurityConcern | null {
  const callText = node.expression.getText(sourceFile);
  if (callText !== "require") return null;
  // require() with a non-string-literal argument is dynamic
  if (node.arguments.length > 0 && !ts.isStringLiteral(node.arguments[0])) {
    const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
    return { type: "unsafe_deserialization", call: "dynamic require()", line, severity: "medium" };
  }
  return null;
}

// =============================================================================
// Resource leak detection
// =============================================================================

const RESOURCE_LEAK_PATTERNS = [
  "fs.openSync", "fs.createReadStream", "fs.createWriteStream",
  "openSync", "createReadStream", "createWriteStream",
];

const CLEANUP_METHODS = [".pipe(", ".close(", ".end(", ".destroy(", ".on('close'", '.on("close"', ".on('end'", '.on("end"'];

export function detectResourceLeak(node: ts.CallExpression, sourceFile: ts.SourceFile): ResourceLeak | null {
  const callText = node.expression.getText(sourceFile);
  let matched = false;
  for (const pattern of RESOURCE_LEAK_PATTERNS) {
    if (callText === pattern || callText.endsWith("." + pattern)) {
      matched = true;
      break;
    }
  }
  if (!matched) return null;

  // Check if the result is assigned to a variable and cleanup is performed
  const parent = node.parent;
  if (parent && ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) {
    const varName = parent.name.text;
    // Find the containing function or block scope
    const container = findContainingFunction(node);
    if (container) {
      const bodyText = container.getText(sourceFile);
      // Check if cleanup methods are called on this variable
      for (const cleanup of CLEANUP_METHODS) {
        if (bodyText.includes(varName + cleanup)) {
          return null; // Cleanup found, not a leak
        }
      }
    }
  }

  // Check if the call is chained with .pipe() directly (e.g., createReadStream().pipe(...))
  if (parent && ts.isPropertyAccessExpression(parent)) {
    const propName = parent.name.text;
    if (propName === "pipe" || propName === "on" || propName === "close" || propName === "destroy") {
      return null;
    }
  }

  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
  return { call: callText, line };
}

function findContainingFunction(node: ts.Node): ts.Node | null {
  let current = node.parent;
  while (current) {
    if (ts.isFunctionDeclaration(current) || ts.isArrowFunction(current) ||
        ts.isFunctionExpression(current) || ts.isMethodDeclaration(current) ||
        ts.isConstructorDeclaration(current) || ts.isSourceFile(current)) {
      return current;
    }
    current = current.parent;
  }
  return null;
}

// =============================================================================
// Route registration detection (Express/Fastify/Koa/Hono call-based routes)
// =============================================================================

const HTTP_METHODS = new Set(["get", "post", "put", "delete", "patch", "head", "options", "all"]);
const ROUTER_OBJECTS = new Set(["app", "router", "server", "api", "route", "fastify", "hono"]);

export function detectRouteRegistration(
  node: ts.CallExpression, sourceFile: ts.SourceFile,
): { method: string; path: string; handler: string; line: number; framework_hint: string } | null {
  // Match: app.get("/path", handler) or router.post("/path", handler)
  if (!ts.isPropertyAccessExpression(node.expression)) return null;
  const prop = node.expression;
  const methodName = prop.name.text.toLowerCase();
  if (!HTTP_METHODS.has(methodName)) return null;

  // Check the object prefix
  const objText = prop.expression.getText(sourceFile).toLowerCase();
  const objName = objText.split(".").pop() ?? objText;
  if (!ROUTER_OBJECTS.has(objName)) return null;

  // First arg should be a string literal (the path)
  if (node.arguments.length < 1) return null;
  const pathArg = node.arguments[0];
  if (!ts.isStringLiteral(pathArg) && !ts.isNoSubstitutionTemplateLiteral(pathArg)) return null;
  const routePath = ts.isStringLiteral(pathArg) ? pathArg.text : pathArg.text;

  // Try to get handler name from second arg
  let handler = "(anonymous)";
  if (node.arguments.length >= 2) {
    const handlerArg = node.arguments[node.arguments.length - 1];
    if (ts.isIdentifier(handlerArg)) {
      handler = handlerArg.text;
    } else if (ts.isArrowFunction(handlerArg) || ts.isFunctionExpression(handlerArg)) {
      handler = "(inline)";
    }
  }

  const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
  const framework_hint = objText.includes("fastify") ? "fastify"
    : objText.includes("hono") ? "hono"
    : "express";

  return {
    method: methodName === "all" ? "ALL" : methodName.toUpperCase(),
    path: routePath,
    handler,
    line,
    framework_hint,
  };
}

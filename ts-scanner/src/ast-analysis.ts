import * as fs from "fs";
import * as ts from "typescript";
import {
  FileAnalysis, ClassInfo, MethodInfo, FunctionInfo, ArgInfo,
  ConstantInfo, TsInterfaceInfo, TsTypeAliasInfo, TsEnumInfo,
  SharedMutableState, StateMutation,
} from "./types.js";
import { estimateTokens, getScriptKind } from "./utils.js";
import {
  detectSilentFailure, detectSecurityConcern, detectSecurityNewExpression,
  detectSecurityAssignment, detectDeprecationJSDoc, detectDeprecationDecorator,
  detectSideEffect, detectSqlString, detectSqlTemplate, detectSqlTaggedTemplate,
  detectEnvVar, extractEnvVarDefault, detectAsyncViolation, extractInstanceVars,
  detectDynamicRequire, detectResourceLeak, detectRouteRegistration,
} from "./detectors.js";
import type { DecoratorDetail } from "./types.js";

// =============================================================================
// Walk Context
// =============================================================================

interface WalkContext {
  currentFunction: string | null;
  currentClass: string | null;
  currentMethod: string | null;
  isAsync: boolean;
  depth: number; // 0 = top-level (module scope)
  sourceFile: ts.SourceFile;
}

// =============================================================================
// Public API
// =============================================================================

/**
 * Analyze a single TS/JS file. Parse-discard pattern: the SourceFile
 * AST is created, data is extracted, and the AST is eligible for GC
 * after this function returns.
 */
export function analyzeFile(filePath: string): FileAnalysis {
  const result = createEmptyFileAnalysis(filePath);

  let source: string;
  try {
    source = fs.readFileSync(filePath, "utf-8");
  } catch (e) {
    result.parse_error = `Read error: ${e instanceof Error ? e.message : String(e)}`;
    return result;
  }

  const scriptKind = getScriptKind(filePath);
  let sourceFile: ts.SourceFile;
  try {
    sourceFile = ts.createSourceFile(
      filePath,
      source,
      ts.ScriptTarget.Latest,
      true, // setParentNodes — required for context
      scriptKind,
    );
  } catch (e) {
    result.parse_error = `Parse error: ${e instanceof Error ? e.message : String(e)}`;
    return result;
  }

  // Check for parse diagnostics
  const diagnostics = (sourceFile as unknown as { parseDiagnostics?: ts.Diagnostic[] }).parseDiagnostics;
  if (diagnostics && diagnostics.length > 0) {
    // Still continue with partial AST — record the first error
    const first = diagnostics[0];
    const msg = ts.flattenDiagnosticMessageText(first.messageText, "\n");
    result.parse_error = `Parse warning: ${msg}`;
  }

  result.line_count = source.split("\n").length;
  result.tokens.original = estimateTokens(source);

  const ctx: WalkContext = {
    currentFunction: null,
    currentClass: null,
    currentMethod: null,
    isAsync: false,
    depth: 0,
    sourceFile,
  };

  // Track this.prop mutations per class during walk
  const classMutations = new Map<string, StateMutation[]>();

  walkPass1(sourceFile, ctx, result, classMutations);

  // Compute type coverage percentage
  if (result.type_coverage.total_functions > 0) {
    result.type_coverage.coverage_percent = Math.round(
      (result.type_coverage.typed_functions / result.type_coverage.total_functions) * 1000
    ) / 10;
  }

  // Compute skeleton token estimate (sum of declaration text)
  result.tokens.skeleton = estimateSkeletonTokens(result);

  return result;
}

// =============================================================================
// Pass 1: Structure Collection
// =============================================================================

function walkPass1(node: ts.Node, ctx: WalkContext, result: FileAnalysis, classMutations: Map<string, StateMutation[]>): void {
  // --- Function declarations ---
  if (ts.isFunctionDeclaration(node)) {
    const info = extractFunctionInfo(node, ctx);
    if (info && ctx.depth === 0) {
      result.functions.push(info);
      recordFunctionMetrics(info, result);
    }
    // Deprecation check
    if (info) {
      const dep = detectDeprecationJSDoc(node, ctx.sourceFile);
      if (dep || detectDeprecationDecorator(info.decorators)) {
        result.deprecation_markers.push({
          file: "", name: info.name, line: info.line,
          reason: dep?.reason ?? null, source: dep ? "jsdoc" : "decorator",
        });
      }
    }
    const childCtx = { ...ctx, currentFunction: info?.name ?? null, isAsync: info?.is_async ?? false, depth: ctx.depth + 1 };
    ts.forEachChild(node, child => walkPass1(child, childCtx, result, classMutations));
    return;
  }

  // --- Variable declarations (arrow functions, const, etc.) ---
  if (ts.isVariableStatement(node) && ctx.depth === 0) {
    handleVariableStatement(node, ctx, result, classMutations);
    return;
  }

  // --- Class declarations ---
  if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) {
    const info = extractClassInfo(node, ctx);
    if (info) {
      // Instance vars
      const instanceVars = extractInstanceVars(node, ctx.sourceFile);
      if (instanceVars.length > 0) info.instance_vars = instanceVars;
      // Deprecation check
      const dep = detectDeprecationJSDoc(node, ctx.sourceFile);
      if (dep || detectDeprecationDecorator(info.decorators)) {
        result.deprecation_markers.push({
          file: "", name: info.name, line: info.line,
          reason: dep?.reason ?? null, source: dep ? "jsdoc" : "decorator",
        });
      }
    }
    if (info && ctx.depth === 0) {
      result.classes.push(info);
      // Record method metrics
      for (const method of info.methods) {
        result.type_coverage.total_functions++;
        if (hasTypeInfo(method)) result.type_coverage.typed_functions++;
        result.complexity.total_cc += method.complexity;
        if (method.complexity > 3) {
          result.complexity.hotspots[`${info.name}.${method.name}`] = method.complexity;
        }
        if (method.is_async) result.async_patterns.async_functions++;
        else result.async_patterns.sync_functions++;
        for (const dec of method.decorators) {
          result.decorators[dec] = (result.decorators[dec] || 0) + 1;
        }
      }
      // Record class decorators
      for (const dec of info.decorators) {
        result.decorators[dec] = (result.decorators[dec] || 0) + 1;
      }
    }
    // Walk class body with class context, tracking method names for mutation detection
    const className = info?.name ?? null;
    for (const member of node.members) {
      const methodName = (ts.isMethodDeclaration(member) || ts.isConstructorDeclaration(member) ||
        ts.isGetAccessorDeclaration(member) || ts.isSetAccessorDeclaration(member))
        ? (ts.isConstructorDeclaration(member) ? "constructor" : member.name?.getText(ctx.sourceFile) ?? null)
        : null;
      const childCtx = { ...ctx, currentClass: className, currentMethod: methodName, depth: ctx.depth + 1 };
      ts.forEachChild(member, child => walkPass1(child, childCtx, result, classMutations));
    }
    // Attach collected state mutations to class info
    if (info && className && classMutations.has(className)) {
      const muts = classMutations.get(className)!;
      if (muts.length > 0) info.state_mutations = muts;
    }
    return;
  }

  // --- Interface declarations ---
  if (ts.isInterfaceDeclaration(node) && ctx.depth === 0) {
    const info = extractInterfaceInfo(node, ctx);
    if (info) {
      if (!result.ts_interfaces) result.ts_interfaces = [];
      result.ts_interfaces.push(info);
    }
    return; // Interfaces have no executable children to walk
  }

  // --- Type alias declarations ---
  if (ts.isTypeAliasDeclaration(node) && ctx.depth === 0) {
    const info = extractTypeAliasInfo(node, ctx);
    if (info) {
      if (!result.ts_type_aliases) result.ts_type_aliases = [];
      result.ts_type_aliases.push(info);
    }
    return;
  }

  // --- Enum declarations ---
  if (ts.isEnumDeclaration(node) && ctx.depth === 0) {
    const info = extractEnumInfo(node, ctx);
    if (info) {
      if (!result.ts_enums) result.ts_enums = [];
      result.ts_enums.push(info);
    }
    return;
  }

  // --- Async for-of loops ---
  if (ts.isForOfStatement(node) && node.awaitModifier) {
    result.async_patterns.async_for_loops++;
  }

  // --- Export declarations (unwrap and process the declaration inside) ---
  if (ts.isExportAssignment(node) || ts.isExportDeclaration(node)) {
    ts.forEachChild(node, child => walkPass1(child, ctx, result, classMutations));
    return;
  }

  // ==========================================================================
  // Behavioral signal detection (Phase 2B)
  // ==========================================================================

  // CatchClause → silent failures
  if (ts.isCatchClause(node)) {
    const f = detectSilentFailure(node, ctx.sourceFile);
    if (f) result.silent_failures.push(f);
  }

  // CallExpression → side effects, security, async violations, resource leaks, routes
  if (ts.isCallExpression(node)) {
    const se = detectSideEffect(node, ctx.sourceFile);
    if (se) result.side_effects.push(se);
    const sc = detectSecurityConcern(node, ctx.sourceFile);
    if (sc) result.security_concerns.push(sc);
    const dr = detectDynamicRequire(node, ctx.sourceFile);
    if (dr) result.security_concerns.push(dr);
    const rl = detectResourceLeak(node, ctx.sourceFile);
    if (rl) {
      if (!result.resource_leaks) result.resource_leaks = [];
      result.resource_leaks.push(rl);
    }
    // Route registration detection (Express/Fastify/Koa/Hono call-based routes)
    if (ctx.depth === 0) {
      const rr = detectRouteRegistration(node, ctx.sourceFile);
      if (rr) {
        if (!result.route_registrations) result.route_registrations = [];
        result.route_registrations.push({ ...rr, is_async: false });
      }
    }
    if (ctx.isAsync) {
      const av = detectAsyncViolation(node, ctx.sourceFile);
      if (av) result.async_violations.push({
        file: result.filepath, function: ctx.currentFunction ?? "(module)",
        violation_type: av.violation_type, call: av.call,
        line: getLineNumber(node, ctx.sourceFile),
      });
    }
  }

  // NewExpression → security (new Function)
  if (ts.isNewExpression(node)) {
    const sc = detectSecurityNewExpression(node, ctx.sourceFile);
    if (sc) result.security_concerns.push(sc);
  }

  // BinaryExpression (=) → innerHTML security + this.prop state mutations
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
    const sc = detectSecurityAssignment(node, ctx.sourceFile);
    if (sc) result.security_concerns.push(sc);
    // Detect this.prop = value mutations inside class methods
    if (ctx.currentClass && ctx.currentMethod &&
        ts.isPropertyAccessExpression(node.left) &&
        node.left.expression.kind === ts.SyntaxKind.ThisKeyword) {
      const propName = node.left.name.text;
      if (!classMutations.has(ctx.currentClass)) classMutations.set(ctx.currentClass, []);
      classMutations.get(ctx.currentClass)!.push({
        property: propName,
        method: ctx.currentMethod,
        line: getLineNumber(node, ctx.sourceFile),
      });
    }
  }

  // TaggedTemplate → SQL
  if (ts.isTaggedTemplateExpression(node)) {
    const sq = detectSqlTaggedTemplate(node, ctx.sourceFile);
    if (sq) result.sql_strings.push(sq);
  }

  // String/template literals → SQL
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    const sq = detectSqlString(node, ctx.sourceFile);
    if (sq) result.sql_strings.push(sq);
  }
  if (ts.isTemplateExpression(node)) {
    const sq = detectSqlTemplate(node, ctx.sourceFile);
    if (sq) result.sql_strings.push(sq);
  }

  // PropertyAccess/ElementAccess → env vars
  if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) {
    const ev = detectEnvVar(node, ctx.sourceFile);
    if (ev) {
      const defaults = extractEnvVarDefault(node);
      result.env_vars.push({
        variable: ev.variable,
        default: defaults.default,
        fallback_type: defaults.fallback_type,
        required: defaults.fallback_type === "none",
        line: ev.line,
      });
    }
  }

  // Default: recurse into children
  ts.forEachChild(node, child => walkPass1(child, ctx, result, classMutations));
}

// =============================================================================
// Function extraction
// =============================================================================

function extractFunctionInfo(node: ts.FunctionDeclaration, ctx: WalkContext): FunctionInfo | null {
  const name = node.name?.text ?? "(anonymous)";
  const isAsync = hasModifier(node, ts.SyntaxKind.AsyncKeyword);
  const params = extractParameters(node.parameters, ctx);
  const returns = node.type ? node.type.getText(ctx.sourceFile) : null;
  const decorators = extractDecorators(node);
  const decoratorDetails = extractDecoratorDetails(node);
  const cc = calculateComplexity(node);
  const docstring = getJSDocSummary(node);

  const info: FunctionInfo = {
    name,
    args: params,
    returns,
    decorators,
    is_async: isAsync,
    line: getLineNumber(node, ctx.sourceFile),
    complexity: cc,
    docstring,
  };
  if (decoratorDetails.length > 0) info.decorator_details = decoratorDetails;
  return info;
}

function extractArrowFunctionInfo(
  name: string,
  node: ts.ArrowFunction | ts.FunctionExpression,
  ctx: WalkContext,
): FunctionInfo {
  const isAsync = hasModifier(node, ts.SyntaxKind.AsyncKeyword);
  const params = extractParameters(node.parameters, ctx);
  const returns = node.type ? node.type.getText(ctx.sourceFile) : null;
  const decorators: string[] = [];
  const cc = calculateComplexity(node);
  const docstring = getJSDocSummary(node.parent);

  return {
    name,
    args: params,
    returns,
    decorators,
    is_async: isAsync,
    line: getLineNumber(node, ctx.sourceFile),
    complexity: cc,
    docstring,
  };
}

// =============================================================================
// Class extraction
// =============================================================================

function extractClassInfo(
  node: ts.ClassDeclaration | ts.ClassExpression,
  ctx: WalkContext,
): ClassInfo | null {
  const name = node.name?.text ?? "(anonymous)";
  const bases = extractHeritageClauses(node);
  const decorators = extractDecorators(node);
  const decoratorDetails = extractDecoratorDetails(node);
  const methods: MethodInfo[] = [];
  const docstring = getJSDocSummary(node);

  for (const member of node.members) {
    if (ts.isMethodDeclaration(member) || ts.isConstructorDeclaration(member)) {
      const methodInfo = extractMethodInfo(member, ctx);
      if (methodInfo) methods.push(methodInfo);
    }
    // Accessor (get/set) declarations
    if (ts.isGetAccessorDeclaration(member) || ts.isSetAccessorDeclaration(member)) {
      const methodInfo = extractMethodInfo(member, ctx);
      if (methodInfo) methods.push(methodInfo);
    }
  }

  const classInfo: ClassInfo = {
    name,
    bases,
    methods,
    decorators,
    line: getLineNumber(node, ctx.sourceFile),
    docstring,
    kind: "class",
  };
  if (decoratorDetails.length > 0) classInfo.decorator_details = decoratorDetails;
  return classInfo;
}

function extractMethodInfo(
  node: ts.MethodDeclaration | ts.ConstructorDeclaration | ts.GetAccessorDeclaration | ts.SetAccessorDeclaration,
  ctx: WalkContext,
): MethodInfo | null {
  let name: string;
  if (ts.isConstructorDeclaration(node)) {
    name = "constructor";
  } else if (node.name) {
    name = node.name.getText(ctx.sourceFile);
  } else {
    return null;
  }

  const isAsync = hasModifier(node, ts.SyntaxKind.AsyncKeyword);
  const params = extractParameters(node.parameters, ctx);
  const returns = ("type" in node && node.type) ? node.type.getText(ctx.sourceFile) : null;
  const decorators = extractDecorators(node);
  const decoratorDetails = extractDecoratorDetails(node);
  const cc = calculateComplexity(node);

  // Determine if this is a "dunder" equivalent (Symbol methods, toString, valueOf, etc.)
  const isDunder = TS_DUNDER_NAMES.has(name) || name.startsWith("[Symbol.");

  const methodInfo: MethodInfo = {
    name,
    args: params,
    returns,
    decorators,
    is_async: isAsync,
    line: getLineNumber(node, ctx.sourceFile),
    complexity: cc,
  };
  if (isDunder) methodInfo.is_dunder = true;
  if (decoratorDetails.length > 0) methodInfo.decorator_details = decoratorDetails;
  return methodInfo;
}

// =============================================================================
// Interface, TypeAlias, Enum extraction
// =============================================================================

function extractInterfaceInfo(node: ts.InterfaceDeclaration, ctx: WalkContext): TsInterfaceInfo {
  const name = node.name.text;
  const extendsClause = node.heritageClauses
    ?.filter(c => c.token === ts.SyntaxKind.ExtendsKeyword)
    .flatMap(c => c.types.map(t => t.getText(ctx.sourceFile))) ?? [];
  const members = node.members
    .filter(ts.isPropertySignature)
    .map(m => ({
      name: m.name?.getText(ctx.sourceFile) ?? "",
      type: m.type?.getText(ctx.sourceFile) ?? "unknown",
      optional: !!m.questionToken,
    }));
  const typeParams = node.typeParameters?.map(tp => tp.name.text) ?? [];
  const exported = hasModifier(node, ts.SyntaxKind.ExportKeyword);

  return { name, extends: extendsClause, members, type_parameters: typeParams, line: getLineNumber(node, ctx.sourceFile), exported };
}

function extractTypeAliasInfo(node: ts.TypeAliasDeclaration, ctx: WalkContext): TsTypeAliasInfo {
  const name = node.name.text;
  const typeParams = node.typeParameters?.map(tp => tp.name.text) ?? [];
  const exported = hasModifier(node, ts.SyntaxKind.ExportKeyword);
  const typeKind = classifyTypeNode(node.type);

  return { name, type_kind: typeKind, type_parameters: typeParams, line: getLineNumber(node, ctx.sourceFile), exported };
}

function extractEnumInfo(node: ts.EnumDeclaration, ctx: WalkContext): TsEnumInfo {
  const name = node.name.text;
  const isConst = hasModifier(node, ts.SyntaxKind.ConstKeyword);
  const exported = hasModifier(node, ts.SyntaxKind.ExportKeyword);
  const members = node.members.map(m => ({
    name: m.name.getText(ctx.sourceFile),
    value: m.initializer ? getLiteralValue(m.initializer) : null,
  }));

  return { name, members, is_const: isConst, line: getLineNumber(node, ctx.sourceFile), exported };
}

// =============================================================================
// Variable statements (constants + arrow functions)
// =============================================================================

function handleVariableStatement(node: ts.VariableStatement, ctx: WalkContext, result: FileAnalysis, classMutations: Map<string, StateMutation[]>): void {
  const isConst = (node.declarationList.flags & ts.NodeFlags.Const) !== 0;

  for (const decl of node.declarationList.declarations) {
    if (!ts.isIdentifier(decl.name)) continue;
    const name = decl.name.text;

    // Arrow function or function expression → treat as top-level function
    if (decl.initializer && (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer))) {
      const info = extractArrowFunctionInfo(name, decl.initializer, ctx);
      result.functions.push(info);
      recordFunctionMetrics(info, result);

      // Walk the function body for nested structures
      const childCtx = { ...ctx, currentFunction: name, isAsync: info.is_async, depth: ctx.depth + 1 };
      ts.forEachChild(decl.initializer, child => walkPass1(child, childCtx, result, classMutations));
      continue;
    }

    // UPPER_CASE const → constant
    if (isConst && /^[A-Z][A-Z0-9_]*$/.test(name)) {
      result.constants.push({
        name,
        value: decl.initializer ? getConstantRepr(decl.initializer, ctx.sourceFile) : null,
        line: getLineNumber(decl, ctx.sourceFile),
      });
    }

    // Module-level let/var → shared mutable state
    if (!isConst && !name.startsWith("_")) {
      if (!result.shared_mutable_state) result.shared_mutable_state = [];
      result.shared_mutable_state.push({
        name,
        kind: "module_variable",
        line: getLineNumber(decl, ctx.sourceFile),
      });
    }
  }

  // Walk any remaining children (non-function initializers)
  ts.forEachChild(node, child => walkPass1(child, ctx, result, classMutations));
}

// =============================================================================
// Complexity calculation
// =============================================================================

/**
 * Calculate cyclomatic complexity for a function/method body.
 * Matches the Python scanner's approach: base CC of 1, increment
 * for each branching construct.
 */
function calculateComplexity(node: ts.Node): number {
  let cc = 1;

  function walk(n: ts.Node): void {
    switch (n.kind) {
      case ts.SyntaxKind.IfStatement:
      case ts.SyntaxKind.ForStatement:
      case ts.SyntaxKind.ForInStatement:
      case ts.SyntaxKind.ForOfStatement:
      case ts.SyntaxKind.WhileStatement:
      case ts.SyntaxKind.DoStatement:
      case ts.SyntaxKind.CatchClause:
      case ts.SyntaxKind.ConditionalExpression: // ternary
      case ts.SyntaxKind.CaseClause:
        cc++;
        break;
      case ts.SyntaxKind.BinaryExpression: {
        const binExpr = n as ts.BinaryExpression;
        if (
          binExpr.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken ||
          binExpr.operatorToken.kind === ts.SyntaxKind.BarBarToken ||
          binExpr.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken
        ) {
          cc++;
        }
        break;
      }
    }
    ts.forEachChild(n, walk);
  }

  // Walk the body only, not the function signature
  if ("body" in node && node.body) {
    ts.forEachChild(node.body as ts.Node, walk);
  }

  return cc;
}

// =============================================================================
// Helpers
// =============================================================================

function extractParameters(params: ts.NodeArray<ts.ParameterDeclaration>, ctx: WalkContext): ArgInfo[] {
  return params.map(p => {
    const nameText = p.name.getText(ctx.sourceFile);
    const isRest = !!p.dotDotDotToken;
    const arg: ArgInfo = {
      name: isRest ? `...${nameText}` : nameText,
    };
    if (p.type) {
      arg.type = p.type.getText(ctx.sourceFile);
    }
    if (p.initializer) {
      arg.default = getConstantRepr(p.initializer, ctx.sourceFile);
    }
    return arg;
  });
}

function extractDecorators(node: ts.Node): string[] {
  const decorators: string[] = [];
  const mods = ts.canHaveDecorators(node) ? ts.getDecorators(node) : undefined;
  if (mods) {
    for (const dec of mods) {
      if (ts.isCallExpression(dec.expression)) {
        const callExpr = dec.expression.expression;
        decorators.push(callExpr.getText());
      } else {
        decorators.push(dec.expression.getText());
      }
    }
  }
  return decorators;
}

function extractDecoratorDetails(node: ts.Node): DecoratorDetail[] {
  const details: DecoratorDetail[] = [];
  const mods = ts.canHaveDecorators(node) ? ts.getDecorators(node) : undefined;
  if (!mods) return details;

  for (const dec of mods) {
    const detail: DecoratorDetail = { name: "", full_name: "", args: [], kwargs: {} };

    if (ts.isCallExpression(dec.expression)) {
      const callExpr = dec.expression;
      const fullName = callExpr.expression.getText();
      detail.full_name = fullName;
      detail.name = fullName.includes(".") ? fullName.split(".").pop()! : fullName;

      // Extract positional args
      for (const arg of callExpr.arguments) {
        if (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) {
          detail.args.push(arg.text);
        } else if (ts.isNumericLiteral(arg)) {
          detail.args.push(Number(arg.text));
        } else if (arg.kind === ts.SyntaxKind.TrueKeyword) {
          detail.args.push(true);
        } else if (arg.kind === ts.SyntaxKind.FalseKeyword) {
          detail.args.push(false);
        } else if (arg.kind === ts.SyntaxKind.NullKeyword) {
          detail.args.push(null);
        } else if (ts.isObjectLiteralExpression(arg)) {
          // Extract object literal properties as kwargs
          for (const prop of arg.properties) {
            if (ts.isPropertyAssignment(prop) && prop.name) {
              const key = prop.name.getText();
              const val = prop.initializer;
              if (ts.isStringLiteral(val)) detail.kwargs[key] = val.text;
              else if (ts.isNumericLiteral(val)) detail.kwargs[key] = Number(val.text);
              else if (val.kind === ts.SyntaxKind.TrueKeyword) detail.kwargs[key] = true;
              else if (val.kind === ts.SyntaxKind.FalseKeyword) detail.kwargs[key] = false;
              else detail.kwargs[key] = val.getText();
            }
          }
        } else {
          detail.args.push("...");
        }
      }
    } else {
      const text = dec.expression.getText();
      detail.full_name = text;
      detail.name = text.includes(".") ? text.split(".").pop()! : text;
    }

    details.push(detail);
  }
  return details;
}

// TS equivalents of Python dunder methods
const TS_DUNDER_NAMES = new Set([
  "constructor", "toString", "valueOf", "toJSON", "toPrimitive",
  "[Symbol.iterator]", "[Symbol.asyncIterator]", "[Symbol.toPrimitive]",
  "[Symbol.hasInstance]", "[Symbol.dispose]", "[Symbol.asyncDispose]",
  "[Symbol.toStringTag]",
]);

function extractHeritageClauses(node: ts.ClassDeclaration | ts.ClassExpression): string[] {
  const bases: string[] = [];
  if (node.heritageClauses) {
    for (const clause of node.heritageClauses) {
      for (const type of clause.types) {
        bases.push(type.expression.getText());
      }
    }
  }
  return bases;
}

function hasModifier(node: ts.Node, kind: ts.SyntaxKind): boolean {
  const mods = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
  return mods?.some(m => m.kind === kind) ?? false;
}

export function getLineNumber(node: ts.Node, sourceFile: ts.SourceFile): number {
  return sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
}

export function getJSDocSummary(node: ts.Node): string | null {
  const jsDocs = ts.getJSDocCommentsAndTags(node);
  for (const doc of jsDocs) {
    if (ts.isJSDoc(doc) && doc.comment) {
      const text = typeof doc.comment === "string"
        ? doc.comment
        : doc.comment.map(c => c.getText()).join("");
      const firstLine = text.trim().split("\n")[0];
      return firstLine.substring(0, 100) || null;
    }
  }
  return null;
}

function classifyTypeNode(node: ts.TypeNode): TsTypeAliasInfo["type_kind"] {
  if (ts.isTypeLiteralNode(node)) return "object";
  if (ts.isUnionTypeNode(node)) return "union";
  if (ts.isIntersectionTypeNode(node)) return "intersection";
  if (ts.isMappedTypeNode(node)) return "mapped";
  if (ts.isConditionalTypeNode(node)) return "conditional";
  if (
    node.kind === ts.SyntaxKind.StringKeyword ||
    node.kind === ts.SyntaxKind.NumberKeyword ||
    node.kind === ts.SyntaxKind.BooleanKeyword
  ) return "primitive";
  return "other";
}

function getLiteralValue(node: ts.Expression): string | number | null {
  if (ts.isNumericLiteral(node)) return Number(node.text);
  if (ts.isStringLiteral(node)) return node.text;
  if (ts.isPrefixUnaryExpression(node) && ts.isNumericLiteral(node.operand)) {
    return node.operator === ts.SyntaxKind.MinusToken ? -Number(node.operand.text) : Number(node.operand.text);
  }
  return null;
}

function getConstantRepr(node: ts.Expression, sourceFile: ts.SourceFile): string {
  if (ts.isStringLiteral(node)) {
    const val = node.text;
    if (val.length > 50) return `"${val.substring(0, 47)}..."`;
    return `"${val}"`;
  }
  if (ts.isNumericLiteral(node)) return node.text;
  if (node.kind === ts.SyntaxKind.TrueKeyword) return "true";
  if (node.kind === ts.SyntaxKind.FalseKeyword) return "false";
  if (node.kind === ts.SyntaxKind.NullKeyword) return "null";
  if (ts.isArrayLiteralExpression(node)) return "[...]";
  if (ts.isObjectLiteralExpression(node)) return "{...}";
  if (ts.isCallExpression(node)) {
    const fn = node.expression.getText(sourceFile);
    return `${fn}(...)`;
  }
  // Fallback: first 30 chars of the text
  const text = node.getText(sourceFile);
  if (text.length > 30) return text.substring(0, 27) + "...";
  return text;
}

function hasTypeInfo(method: MethodInfo): boolean {
  const hasParamTypes = method.args.some(a => !!a.type);
  return hasParamTypes || method.returns !== null;
}

function recordFunctionMetrics(info: FunctionInfo, result: FileAnalysis): void {
  result.type_coverage.total_functions++;
  if (info.returns !== null || info.args.some(a => !!a.type)) {
    result.type_coverage.typed_functions++;
  }
  result.complexity.total_cc += info.complexity;
  if (info.complexity > 3) {
    result.complexity.hotspots[info.name] = info.complexity;
  }
  if (info.is_async) result.async_patterns.async_functions++;
  else result.async_patterns.sync_functions++;
  for (const dec of info.decorators) {
    result.decorators[dec] = (result.decorators[dec] || 0) + 1;
  }
}

function estimateSkeletonTokens(result: FileAnalysis): number {
  // Rough estimate: count characters in function/class names and signatures
  let chars = 0;
  for (const fn of result.functions) {
    chars += fn.name.length + 20; // name + def/args overhead
    for (const arg of fn.args) {
      chars += arg.name.length + (arg.type?.length ?? 0) + 4;
    }
  }
  for (const cls of result.classes) {
    chars += cls.name.length + 10;
    for (const method of cls.methods) {
      chars += method.name.length + 20;
      for (const arg of method.args) {
        chars += arg.name.length + (arg.type?.length ?? 0) + 4;
      }
    }
  }
  return Math.floor(chars / 4);
}

// =============================================================================
// Empty result factory
// =============================================================================

function createEmptyFileAnalysis(filePath: string): FileAnalysis {
  return {
    filepath: filePath,
    line_count: 0,
    classes: [],
    functions: [],
    constants: [],
    complexity: { total_cc: 0, hotspots: {} },
    type_coverage: { total_functions: 0, typed_functions: 0, coverage_percent: 0 },
    decorators: {},
    async_patterns: { async_functions: 0, sync_functions: 0, async_for_loops: 0, async_context_managers: 0 },
    side_effects: [],
    security_concerns: [],
    silent_failures: [],
    async_violations: [],
    sql_strings: [],
    deprecation_markers: [],
    env_vars: [],
    internal_calls: [],
    tokens: { original: 0, skeleton: 0 },
    parse_error: null,
  };
}

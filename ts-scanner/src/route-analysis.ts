/**
 * HTTP Route Detection for TypeScript/JavaScript projects.
 *
 * Detects routes from two patterns:
 * 1. Call-based: Express/Fastify/Koa/Hono — app.get("/path", handler)
 * 2. Decorator-based: NestJS — @Get("/path") on class methods
 */

import * as path from "path";
import type { FileAnalysis, Route, RouteAnalysis } from "./types.js";

// NestJS HTTP method decorators
const NESTJS_METHOD_DECORATORS: Record<string, string> = {
  "Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE",
  "Patch": "PATCH", "Head": "HEAD", "Options": "OPTIONS", "All": "ALL",
};

/**
 * Analyze routes from file analysis results.
 * Combines call-based registrations and decorator-based routes.
 */
export function analyzeRoutes(
  fileResults: Record<string, FileAnalysis>,
  targetDir: string,
): RouteAnalysis | null {
  const routes: Route[] = [];
  const frameworks = new Set<string>();

  for (const [filePath, fa] of Object.entries(fileResults)) {
    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");

    // 1. Call-based routes (Express/Fastify/Koa/Hono)
    if (fa.route_registrations) {
      for (const reg of fa.route_registrations) {
        // Collect side effects within the file for this route
        const sideEffects = collectSideEffects(fa, reg.line);
        routes.push({
          method: reg.method,
          path: reg.path,
          handler: reg.handler,
          file: rel,
          line: reg.line,
          is_async: reg.is_async,
          framework_hint: reg.framework_hint,
          side_effects: sideEffects,
        });
        frameworks.add(reg.framework_hint);
      }
    }

    // 2. Decorator-based routes (NestJS)
    for (const cls of fa.classes) {
      // Check if class has @Controller decorator
      let controllerPath = "";
      if (cls.decorator_details) {
        for (const dec of cls.decorator_details) {
          if (dec.name === "Controller" || dec.full_name === "Controller") {
            controllerPath = typeof dec.args[0] === "string" ? dec.args[0] : "";
            frameworks.add("nestjs");
          }
        }
      }

      for (const method of cls.methods) {
        if (!method.decorator_details) continue;
        for (const dec of method.decorator_details) {
          const httpMethod = NESTJS_METHOD_DECORATORS[dec.name];
          if (!httpMethod) continue;
          const methodPath = typeof dec.args[0] === "string" ? dec.args[0] : "";
          const fullPath = controllerPath
            ? `${controllerPath}/${methodPath}`.replace(/\/+/g, "/")
            : methodPath || "/";

          routes.push({
            method: httpMethod,
            path: fullPath,
            handler: `${cls.name}.${method.name}`,
            file: rel,
            line: method.line,
            is_async: method.is_async,
            framework_hint: "nestjs",
            side_effects: collectSideEffects(fa, method.line),
          });
          frameworks.add("nestjs");
        }
      }
    }
  }

  if (routes.length === 0) return null;

  // Sort and cap at 50
  routes.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
  const capped = routes.slice(0, 50);

  // Build summary
  const byMethod: Record<string, number> = {};
  for (const r of capped) {
    byMethod[r.method] = (byMethod[r.method] || 0) + 1;
  }

  return {
    routes: capped,
    summary: {
      total_routes: capped.length,
      by_method: byMethod,
      frameworks_detected: [...frameworks],
    },
  };
}

function collectSideEffects(fa: FileAnalysis, routeLine: number): string[] {
  // Collect unique side effect categories near the route (within 50 lines)
  const cats = new Set<string>();
  for (const se of fa.side_effects) {
    if (Math.abs(se.line - routeLine) < 50 && se.category !== "console") {
      cats.add(se.category);
    }
  }
  return [...cats];
}

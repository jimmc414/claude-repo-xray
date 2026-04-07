/**
 * Import-time side effect detection.
 *
 * Identifies side effect calls at module scope (outside functions/classes)
 * that execute on import. Uses range-based scope checking: a side effect
 * is module-scope only if its line does NOT fall within any function/class
 * [start_line, end_line] range.
 */

import * as path from "path";
import type { FileAnalysis, ImportTimeSideEffect } from "./types.js";

const DANGEROUS_CATEGORIES = new Set([
  "file_io", "network", "subprocess", "database", "process",
]);

/**
 * Compute import-time side effects from per-file analysis results.
 * A side effect is "import-time" if it occurs outside any function or class body.
 */
export function computeImportTimeSideEffects(
  fileResults: Record<string, FileAnalysis>,
  targetDir: string,
): ImportTimeSideEffect[] {
  const results: ImportTimeSideEffect[] = [];

  for (const [filePath, fa] of Object.entries(fileResults)) {
    if (fa.side_effects.length === 0) continue;

    // Build excluded ranges from all functions and classes using [line, end_line]
    const excludedRanges: Array<{ start: number; end: number }> = [];

    for (const fn of fa.functions) {
      if (fn.end_line != null) {
        excludedRanges.push({ start: fn.line, end: fn.end_line });
      }
    }
    for (const cls of fa.classes) {
      if (cls.end_line != null) {
        excludedRanges.push({ start: cls.line, end: cls.end_line });
      } else {
        // Fallback: use last method line if no end_line
        const lastMethodLine = cls.methods.length > 0
          ? Math.max(...cls.methods.map(m => m.end_line ?? m.line))
          : cls.line;
        excludedRanges.push({ start: cls.line, end: lastMethodLine });
      }
    }

    for (const se of fa.side_effects) {
      if (!DANGEROUS_CATEGORIES.has(se.category)) continue;

      // Primary filter: if depth is tracked, only module-scope (depth 0) effects qualify
      if (se.depth != null && se.depth > 0) continue;

      // Secondary filter: line must not fall inside any function/class range
      const insideScope = excludedRanges.some(
        r => se.line >= r.start && se.line <= r.end,
      );
      if (insideScope) continue;

      const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");
      results.push({
        file: rel,
        line: se.line,
        call: se.call,
        category: se.category,
      });
    }
  }

  // Sort by file, then line; cap at 20
  results.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
  return results.slice(0, 20);
}

/**
 * Import-time side effect detection.
 *
 * Identifies side effect calls at module scope (outside functions/classes)
 * that execute on import. These are action-at-a-distance risks.
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

    // Build line ranges for functions and classes (these are NOT module scope)
    const scopeRanges: Array<{ start: number; end: number }> = [];

    for (const fn of fa.functions) {
      // Approximate: function starts at fn.line, extends ~50 lines (heuristic)
      // We don't have end lines, so use a heuristic: any side effect on the
      // same line as a function is inside it. For better accuracy we'd need
      // end lines, but this catches the common case of module-scope calls.
      scopeRanges.push({ start: fn.line, end: fn.line + 200 });
    }
    for (const cls of fa.classes) {
      const lastMethodLine = cls.methods.length > 0
        ? Math.max(...cls.methods.map(m => m.line))
        : cls.line;
      scopeRanges.push({ start: cls.line, end: lastMethodLine + 200 });
    }

    // A side effect is module-scope if its line is BEFORE any function/class
    // The heuristic: side effects at lines before the first function/class are module-scope
    const firstScopeLine = scopeRanges.length > 0
      ? Math.min(...scopeRanges.map(r => r.start))
      : Infinity;

    for (const se of fa.side_effects) {
      if (!DANGEROUS_CATEGORIES.has(se.category)) continue;
      // Module scope: before first function/class definition
      if (se.line < firstScopeLine) {
        const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");
        results.push({
          file: rel,
          line: se.line,
          call: se.call,
          category: se.category,
        });
      }
    }
  }

  // Sort by file, then line; cap at 20
  results.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
  return results.slice(0, 20);
}

import * as path from "path";
import * as ts from "typescript";

/**
 * Estimate token count for source text.
 * Same heuristic as Python scanner: ~4 characters per token.
 */
export function estimateTokens(text: string): number {
  return Math.floor(text.length / 4);
}

/**
 * Get the appropriate ScriptKind for a file based on its extension.
 *
 * CRITICAL: TSX mode misparses generics like <T> as JSX elements.
 * Always match ScriptKind to the actual file extension.
 */
export function getScriptKind(filePath: string): ts.ScriptKind {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case ".ts":
    case ".mts":
    case ".cts":
      return ts.ScriptKind.TS;
    case ".tsx":
      return ts.ScriptKind.TSX;
    case ".js":
    case ".mjs":
    case ".cjs":
      return ts.ScriptKind.JS;
    case ".jsx":
      return ts.ScriptKind.JSX;
    default:
      return ts.ScriptKind.TS;
  }
}

/**
 * Get a relative path from root, normalized to forward slashes.
 */
export function relativePath(filePath: string, rootDir: string): string {
  return path.relative(rootDir, filePath).replace(/\\/g, "/");
}

/**
 * Format a number as a token count string (e.g., "1.2K", "45K").
 */
export function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return String(tokens);
}

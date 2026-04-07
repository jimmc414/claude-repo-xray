/**
 * Tech debt marker detection for the TS scanner.
 *
 * Scans source files for TODO/FIXME/HACK/XXX/BUG/OPTIMIZE comment markers.
 * Ported from Python's tech_debt_analysis.py.
 */

import * as fs from "fs";
import * as path from "path";
import type { TechDebt, TechDebtMarker, TechDebtFileEntry } from "./types.js";

// Match single-line comments: // TODO: ..., // FIXME ...
const SINGLE_LINE_RE = /\/\/\s*(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE)\b[:\s]*(.*)/i;

// Match block comments: /* TODO: ... */ or lines within block comments
const BLOCK_COMMENT_RE = /(?:\/\*+|\*)\s*(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE)\b[:\s]*(.*)/i;

const MARKER_TYPES = ["TODO", "FIXME", "HACK", "XXX", "BUG", "OPTIMIZE"] as const;

export function analyzeTechDebt(
  files: string[], targetDir: string, verbose: boolean = false,
): TechDebt {
  const markers: Record<string, TechDebtMarker[]> = {};
  const byFile: Record<string, TechDebtFileEntry[]> = {};

  for (const type of MARKER_TYPES) {
    markers[type] = [];
  }

  for (const filePath of files) {
    let source: string;
    try {
      source = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }

    const rel = path.relative(targetDir, filePath).replace(/\\/g, "/");
    const fileMarkers: TechDebtFileEntry[] = [];

    const lines = source.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const lineNum = i + 1;

      // Try single-line comment first
      let match = SINGLE_LINE_RE.exec(line);
      if (!match) {
        match = BLOCK_COMMENT_RE.exec(line);
      }

      if (match) {
        const markerType = match[1].toUpperCase();
        const text = match[2].trim().substring(0, 80);

        if (markerType in markers) {
          markers[markerType].push({ file: rel, line: lineNum, text });
          fileMarkers.push({ type: markerType, line: lineNum, text });
        }
      }
    }

    if (fileMarkers.length > 0) {
      byFile[rel] = fileMarkers;
    }
  }

  // Summary
  let totalCount = 0;
  const byType: Record<string, number> = {};
  for (const [type, entries] of Object.entries(markers)) {
    if (entries.length > 0) {
      byType[type] = entries.length;
      totalCount += entries.length;
    }
  }

  // Filter empty marker types
  const filteredMarkers: Record<string, TechDebtMarker[]> = {};
  for (const [type, entries] of Object.entries(markers)) {
    if (entries.length > 0) filteredMarkers[type] = entries;
  }

  return {
    markers: filteredMarkers,
    by_file: byFile,
    summary: { total_count: totalCount, by_type: byType },
  };
}

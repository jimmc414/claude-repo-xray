/**
 * Git history analysis for the TS scanner.
 *
 * Extracts historical signals from git history:
 * - Risk scoring (churn, hotfixes, author entropy)
 * - Co-modification coupling (hidden coupling)
 * - Freshness tracking (active, aging, stale, dormant)
 * - Function-level churn
 * - Velocity trends
 * - Coupling clusters
 *
 * Ported from Python's git_analysis.py.
 */

import { execSync } from "child_process";
import * as path from "path";
import type {
  GitAnalysis, GitRiskEntry, GitCouplingEntry, GitCouplingCluster,
  GitFreshness, GitFreshnessEntry, GitFunctionChurnEntry, GitVelocityEntry,
} from "./types.js";

const TS_EXTENSIONS = [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs"];

function hasRelevantExtension(file: string): boolean {
  return TS_EXTENSIONS.some(ext => file.endsWith(ext));
}

function runGit(args: string[], cwd: string, verbose: boolean = false): string {
  try {
    const result = execSync(`git ${args.join(" ")}`, {
      cwd,
      encoding: "utf-8",
      maxBuffer: 50 * 1024 * 1024,
      timeout: 30000,
      stdio: ["pipe", "pipe", "pipe"],
    });
    return (result ?? "").trim();
  } catch (e) {
    if (verbose) {
      process.stderr.write(`Warning: git ${args.slice(0, 3).join(" ")}... failed\n`);
    }
    return "";
  }
}

// =============================================================================
// Risk Analysis
// =============================================================================

function analyzeRisk(
  cwd: string, files: string[], months: number = 6, verbose: boolean = false,
): GitRiskEntry[] {
  const log = runGit(
    ["log", `--since=${months}.months`, "--name-only", "--pretty=format:COMMIT::%an::%s"],
    cwd, verbose,
  );
  if (!log) return [];

  const fileSet = new Set(files);
  const stats = new Map<string, { commits: number; authors: Set<string>; hotfixes: number }>();
  const hotfixKeywords = ["fix", "bug", "urgent", "revert", "hotfix", "patch", "emergency"];

  let currentAuthor = "";
  let isHotfix = false;

  for (const line of log.split("\n")) {
    if (line.startsWith("COMMIT::")) {
      const parts = line.split("::");
      if (parts.length >= 3) {
        currentAuthor = parts[1];
        const subject = parts.slice(2).join("::").toLowerCase();
        isHotfix = hotfixKeywords.some(kw => subject.includes(kw));
      }
    } else if (line.trim() && hasRelevantExtension(line.trim())) {
      const f = line.trim();
      if (!fileSet.has(f)) continue;
      let s = stats.get(f);
      if (!s) {
        s = { commits: 0, authors: new Set(), hotfixes: 0 };
        stats.set(f, s);
      }
      s.commits++;
      s.authors.add(currentAuthor);
      if (isHotfix) s.hotfixes++;
    }
  }

  if (stats.size === 0) return [];

  const maxChurn = Math.max(...Array.from(stats.values()).map(s => s.commits));
  const results: GitRiskEntry[] = [];

  for (const [f, s] of stats) {
    const churnNorm = maxChurn > 0 ? s.commits / maxChurn : 0;
    const authorScore = Math.min(s.authors.size, 5) / 5.0;
    const hotfixScore = Math.min(s.hotfixes, 3) / 3.0;
    const risk = (churnNorm * 0.4) + (hotfixScore * 0.4) + (authorScore * 0.2);

    if (risk > 0.1) {
      results.push({
        file: f,
        risk_score: Math.round(risk * 100) / 100,
        churn: s.commits,
        hotfixes: s.hotfixes,
        authors: s.authors.size,
      });
    }
  }

  results.sort((a, b) => b.risk_score - a.risk_score);
  return results.slice(0, 50);
}

// =============================================================================
// Coupling Analysis
// =============================================================================

function analyzeCoupling(
  cwd: string, maxCommits: number = 200, minCooccurrences: number = 3, verbose: boolean = false,
): GitCouplingEntry[] {
  const log = runGit(
    ["log", "-n", String(maxCommits), "--name-only", "--pretty=format:COMMIT"],
    cwd, verbose,
  );
  if (!log) return [];

  const commits: string[][] = [];
  let currentFiles = new Set<string>();

  for (const line of log.split("\n")) {
    if (line === "COMMIT") {
      if (currentFiles.size > 0) {
        commits.push(Array.from(currentFiles));
      }
      currentFiles = new Set();
    } else if (line.trim() && hasRelevantExtension(line.trim())) {
      currentFiles.add(line.trim());
    }
  }
  if (currentFiles.size > 0) commits.push(Array.from(currentFiles));

  // Count co-occurrences
  const pairs = new Map<string, number>();
  for (const files of commits) {
    if (files.length > 20) continue; // Skip bulk refactors
    const sorted = files.slice().sort();
    for (let i = 0; i < sorted.length; i++) {
      for (let j = i + 1; j < sorted.length; j++) {
        const key = `${sorted[i]}\0${sorted[j]}`;
        pairs.set(key, (pairs.get(key) ?? 0) + 1);
      }
    }
  }

  const results: GitCouplingEntry[] = [];
  for (const [key, count] of pairs) {
    if (count >= minCooccurrences) {
      const [a, b] = key.split("\0");
      results.push({ file_a: a, file_b: b, count });
    }
  }

  results.sort((a, b) => b.count - a.count);
  return results.slice(0, 20);
}

// =============================================================================
// Coupling Clusters (Union-Find)
// =============================================================================

function analyzeCouplingClusters(pairs: GitCouplingEntry[]): GitCouplingCluster[] {
  if (pairs.length === 0) return [];

  // Build adjacency list
  const adj = new Map<string, Set<string>>();
  const edgeWeights = new Map<string, number>();

  for (const p of pairs) {
    if (!adj.has(p.file_a)) adj.set(p.file_a, new Set());
    if (!adj.has(p.file_b)) adj.set(p.file_b, new Set());
    adj.get(p.file_a)!.add(p.file_b);
    adj.get(p.file_b)!.add(p.file_a);
    edgeWeights.set(`${p.file_a}\0${p.file_b}`, p.count);
    edgeWeights.set(`${p.file_b}\0${p.file_a}`, p.count);
  }

  // BFS to find connected components
  const visited = new Set<string>();
  const clusters: GitCouplingCluster[] = [];

  for (const node of adj.keys()) {
    if (visited.has(node)) continue;

    const component: string[] = [];
    const queue = [node];
    let totalCochanges = 0;
    const seenEdges = new Set<string>();

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (visited.has(current)) continue;
      visited.add(current);
      component.push(current);

      for (const neighbor of adj.get(current) ?? []) {
        const edge = [current, neighbor].sort().join("\0");
        if (!seenEdges.has(edge)) {
          seenEdges.add(edge);
          totalCochanges += edgeWeights.get(`${current}\0${neighbor}`) ?? 0;
        }
        if (!visited.has(neighbor)) {
          queue.push(neighbor);
        }
      }
    }

    if (component.length >= 2) {
      clusters.push({
        cluster_id: clusters.length,
        files: component.sort(),
        total_cochanges: totalCochanges,
      });
    }
  }

  clusters.sort((a, b) => b.total_cochanges - a.total_cochanges);
  return clusters;
}

// =============================================================================
// Freshness Analysis
// =============================================================================

function analyzeFreshness(
  cwd: string, files: string[], verbose: boolean = false,
): GitFreshness {
  const empty: GitFreshness = { active: [], aging: [], stale: [], dormant: [] };
  const log = runGit(
    ["log", "--name-only", "--pretty=format:COMMIT::%ct"],
    cwd, verbose,
  );
  if (!log) return empty;

  const lastModified = new Map<string, number>();
  let currentTs = 0;

  for (const line of log.split("\n")) {
    if (line.startsWith("COMMIT::")) {
      const ts = parseInt(line.split("::")[1], 10);
      if (!isNaN(ts)) currentTs = ts;
    } else if (line.trim() && hasRelevantExtension(line.trim())) {
      const f = line.trim();
      if (!lastModified.has(f)) {
        lastModified.set(f, currentTs);
      }
    }
  }

  const now = Date.now() / 1000;
  const result: GitFreshness = { active: [], aging: [], stale: [], dormant: [] };

  for (const f of files) {
    const ts = lastModified.get(f) ?? now;
    const days = Math.floor((now - ts) / 86400);
    const entry: GitFreshnessEntry = { file: f, days };

    if (days < 30) result.active.push(entry);
    else if (days < 90) result.aging.push(entry);
    else if (days < 180) result.stale.push(entry);
    else result.dormant.push(entry);
  }

  result.dormant.sort((a, b) => b.days - a.days);
  return result;
}

// =============================================================================
// Function Churn
// =============================================================================

function analyzeFunctionChurn(
  cwd: string, files: string[], months: number = 6, verbose: boolean = false,
): GitFunctionChurnEntry[] {
  const log = runGit(
    ["log", `--since=${months}.months`, "-p", "--pretty=format:COMMIT::%an::%s"],
    cwd, verbose,
  );
  if (!log) return [];

  const hotfixKeywords = ["fix", "bug", "urgent", "revert", "hotfix", "patch", "emergency"];
  // Match @@ ... @@ context — extract TS/JS function/class names
  const hunkRe = /^@@ .+ @@\s+(?:(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)|(?:const|let|var)\s+)\s*(\w+)/;
  const diffFileRe = /^diff --git a\/.+ b\/(.+)$/;

  const fileSet = new Set(files);
  const stats = new Map<string, { commits: Set<number>; authors: Set<string>; hotfixes: number }>();

  let currentAuthor = "";
  let currentFile = "";
  let isHotfix = false;
  let commitId = 0;

  for (const line of log.split("\n")) {
    if (line.startsWith("COMMIT::")) {
      const parts = line.split("::");
      if (parts.length >= 3) {
        currentAuthor = parts[1];
        const subject = parts.slice(2).join("::").toLowerCase();
        isHotfix = hotfixKeywords.some(kw => subject.includes(kw));
        commitId++;
        currentFile = "";
      }
      continue;
    }

    const fileMatch = diffFileRe.exec(line);
    if (fileMatch) {
      currentFile = fileMatch[1];
      continue;
    }

    if (!currentFile || !fileSet.has(currentFile)) continue;

    const hunkMatch = hunkRe.exec(line);
    if (hunkMatch) {
      const funcName = hunkMatch[1];
      const key = `${currentFile}\0${funcName}`;
      let s = stats.get(key);
      if (!s) {
        s = { commits: new Set(), authors: new Set(), hotfixes: 0 };
        stats.set(key, s);
      }
      s.commits.add(commitId);
      s.authors.add(currentAuthor);
      if (isHotfix) s.hotfixes++;
    }
  }

  if (stats.size === 0) return [];

  const maxChurn = Math.max(...Array.from(stats.values()).map(s => s.commits.size));
  const results: GitFunctionChurnEntry[] = [];

  for (const [key, s] of stats) {
    const [file, func] = key.split("\0");
    const commitCount = s.commits.size;
    const authorCount = s.authors.size;
    const churnNorm = maxChurn > 0 ? commitCount / maxChurn : 0;
    const authorScore = Math.min(authorCount, 5) / 5.0;
    const hotfixScore = Math.min(s.hotfixes, 3) / 3.0;
    const risk = (churnNorm * 0.4) + (hotfixScore * 0.4) + (authorScore * 0.2);

    if (risk > 0.1) {
      results.push({
        file,
        function: func,
        commits: commitCount,
        hotfixes: s.hotfixes,
        authors: authorCount,
        risk_score: Math.round(risk * 100) / 100,
      });
    }
  }

  results.sort((a, b) => b.risk_score - a.risk_score);
  return results.slice(0, 20);
}

// =============================================================================
// Velocity
// =============================================================================

function analyzeVelocity(
  cwd: string, files: string[], months: number = 6, verbose: boolean = false,
): GitVelocityEntry[] {
  const log = runGit(
    ["log", `--since=${months}.months`, "--format=format:%ct", "--name-only"],
    cwd, verbose,
  );
  if (!log) return [];

  const fileSet = new Set(files);
  // Bucket commits by (file, year-month)
  const fileMonths = new Map<string, Map<string, number>>();
  let currentTs = 0;

  for (const line of log.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (/^\d+$/.test(trimmed)) {
      currentTs = parseInt(trimmed, 10);
      continue;
    }
    if (hasRelevantExtension(trimmed) && fileSet.has(trimmed) && currentTs) {
      const dt = new Date(currentTs * 1000);
      const monthKey = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
      let fm = fileMonths.get(trimmed);
      if (!fm) {
        fm = new Map();
        fileMonths.set(trimmed, fm);
      }
      fm.set(monthKey, (fm.get(monthKey) ?? 0) + 1);
    }
  }

  if (fileMonths.size === 0) return [];

  // Build sorted list of month slots
  const now = new Date();
  const monthSlots: string[] = [];
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    monthSlots.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  const results: GitVelocityEntry[] = [];
  for (const [f, monthsData] of fileMonths) {
    let total = 0;
    for (const v of monthsData.values()) total += v;
    if (total < 2) continue;

    const monthly = monthSlots.map(slot => monthsData.get(slot) ?? 0);

    // Trend: compare first half vs second half averages
    const mid = Math.floor(monthly.length / 2);
    const firstHalf = monthly.slice(0, mid);
    const secondHalf = monthly.slice(mid);
    const avgFirst = firstHalf.length > 0 ? firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length : 0;
    const avgSecond = secondHalf.length > 0 ? secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length : 0;

    let trend: "accelerating" | "decelerating" | "stable";
    if (avgFirst > 0 && avgSecond > avgFirst * 1.5) {
      trend = "accelerating";
    } else if (avgSecond > 0 && avgFirst > avgSecond * 1.5) {
      trend = "decelerating";
    } else if (avgFirst === 0 && avgSecond > 0) {
      trend = "accelerating";
    } else if (avgSecond === 0 && avgFirst > 0) {
      trend = "decelerating";
    } else {
      trend = "stable";
    }

    results.push({
      file: f,
      monthly_commits: monthly,
      trend,
      total_commits: total,
    });
  }

  results.sort((a, b) => b.total_commits - a.total_commits);
  return results.slice(0, 20);
}

// =============================================================================
// Orchestrator
// =============================================================================

export function analyzeGit(
  targetDir: string, files: string[], verbose: boolean = false,
): GitAnalysis | null {
  // Check if we're in a git repo
  const check = runGit(["rev-parse", "--git-dir"], targetDir, false);
  if (!check) return null;

  // Convert absolute paths to relative for git commands
  const relFiles = files.map(f => path.relative(targetDir, f).replace(/\\/g, "/"));

  if (verbose) process.stderr.write("  Analyzing git risk...\n");
  const risk = analyzeRisk(targetDir, relFiles, 6, verbose);

  if (verbose) process.stderr.write("  Analyzing git coupling...\n");
  const coupling = analyzeCoupling(targetDir, 200, 3, verbose);

  if (verbose) process.stderr.write("  Analyzing git freshness...\n");
  const freshness = analyzeFreshness(targetDir, relFiles, verbose);

  if (verbose) process.stderr.write("  Analyzing function churn...\n");
  const functionChurn = analyzeFunctionChurn(targetDir, relFiles, 6, verbose);

  if (verbose) process.stderr.write("  Analyzing velocity...\n");
  const velocity = analyzeVelocity(targetDir, relFiles, 6, verbose);

  const couplingClusters = analyzeCouplingClusters(coupling);

  return {
    risk,
    coupling,
    coupling_clusters: couplingClusters,
    freshness,
    function_churn: functionChurn,
    velocity,
  };
}

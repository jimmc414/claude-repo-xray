import * as fs from "fs";
import * as path from "path";

const TS_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts"]);
const JS_EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".cjs"]);
const ALL_EXTENSIONS = new Set([...TS_EXTENSIONS, ...JS_EXTENSIONS]);

const IGNORE_DIRS = new Set([
  "node_modules", "dist", "build", ".next", ".nuxt", ".output",
  "coverage", ".nyc_output", ".git", ".hg", ".svn",
  ".cache", ".parcel-cache", ".turbo",
  "__pycache__", ".venv", "venv",
]);

const IGNORE_FILES = new Set([
  ".DS_Store", "Thumbs.db",
]);

export interface DiscoveryResult {
  files: string[];
  declarationFiles: string[];
  tsconfigPath: string | null;
  packageJsonPath: string | null;
  packageJson: Record<string, unknown> | null;
}

/**
 * Discover TS/JS files in a directory, respecting ignore patterns.
 * Mirrors lib/file_discovery.py:discover_python_files().
 */
export function discoverFiles(rootDir: string): DiscoveryResult {
  const absRoot = path.resolve(rootDir);
  const files: string[] = [];
  const declarationFiles: string[] = [];

  walkDir(absRoot, files, declarationFiles);

  files.sort();
  declarationFiles.sort();

  // Detect tsconfig.json
  const tsconfigPath = findFile(absRoot, ["tsconfig.json", "jsconfig.json"]);

  // Read package.json
  const packageJsonPath = findFile(absRoot, ["package.json"]);
  let packageJson: Record<string, unknown> | null = null;
  if (packageJsonPath) {
    try {
      packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf-8"));
    } catch {
      // Malformed package.json — continue without it
    }
  }

  return { files, declarationFiles, tsconfigPath, packageJsonPath, packageJson };
}

function walkDir(dir: string, files: string[], declarationFiles: string[]): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return; // Permission denied or other read error
  }

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      if (!IGNORE_DIRS.has(entry.name) && !entry.name.startsWith(".")) {
        walkDir(fullPath, files, declarationFiles);
      }
      continue;
    }

    if (!entry.isFile()) continue;
    if (IGNORE_FILES.has(entry.name)) continue;

    const ext = path.extname(entry.name).toLowerCase();

    // Separate .d.ts files — scan for types only, not structure
    if (entry.name.endsWith(".d.ts") || entry.name.endsWith(".d.mts") || entry.name.endsWith(".d.cts")) {
      declarationFiles.push(fullPath);
      continue;
    }

    if (ALL_EXTENSIONS.has(ext)) {
      files.push(fullPath);
    }
  }
}

function findFile(dir: string, candidates: string[]): string | null {
  for (const name of candidates) {
    const fullPath = path.join(dir, name);
    if (fs.existsSync(fullPath)) {
      return fullPath;
    }
  }
  return null;
}

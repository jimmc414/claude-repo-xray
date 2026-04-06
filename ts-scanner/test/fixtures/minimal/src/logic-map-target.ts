/**
 * Complex function for logic map testing.
 * Has enough branching to appear in hotspots (CC > 3).
 */

interface Item {
  type: string;
  value: number;
}

interface ProcessOptions {
  enabled: boolean;
  threshold: number;
}

interface Result {
  data: unknown;
}

function transform(item: Item): Result {
  return { data: item };
}

/**
 * Process items with filtering, error handling, and branching.
 */
export function processItems(items: Item[], options: ProcessOptions): Result[] {
  const results: Result[] = [];
  if (!options.enabled) {
    return results;
  }
  for (const item of items) {
    if (item.type === "special") {
      try {
        const processed = transform(item);
        results.push(processed);
      } catch (e) {
        console.error("Failed to process", e);
      }
    } else if (item.value > options.threshold) {
      results.push({ data: item });
    }
  }
  return results;
}

export function simpleFunction(): string {
  return "hello";
}

/**
 * Shared mutable state fixture for testing.
 */

// Module-level let — should be detected as shared mutable state
let requestCount = 0;
let connectionPool: unknown[] = [];

// Module-level const — should NOT be detected
const MAX_CONNECTIONS = 10;

// Private-ish variable (starts with _) — should be skipped
let _internalCache = {};

export function incrementCounter(): void {
  requestCount++;
}

export function addConnection(conn: unknown): void {
  connectionPool.push(conn);
}

// Class with this.prop mutations
export class StatefulService {
  private count: number = 0;
  private name: string;

  constructor(name: string) {
    this.name = name;
    this.count = 0;
  }

  increment(): void {
    this.count = this.count + 1;
  }

  rename(newName: string): void {
    this.name = newName;
  }
}

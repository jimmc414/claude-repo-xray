/**
 * Utility functions and constants.
 */

export const MAX_RETRIES = 3;
export const API_BASE_URL = "https://api.example.com";

/**
 * Format a user's display name.
 */
export function formatName(first: string, last: string): string {
  return `${first.trim()} ${last.trim()}`;
}

/**
 * Validate an email address using a simple regex.
 */
export function isValidEmail(email: string): boolean {
  const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return pattern.test(email);
}

/**
 * Retry a function with exponential backoff.
 * Complex enough to have meaningful CC.
 */
export async function retry<T>(
  fn: () => Promise<T>,
  options: { maxRetries?: number; baseDelay?: number } = {},
): Promise<T> {
  const maxRetries = options.maxRetries ?? MAX_RETRIES;
  const baseDelay = options.baseDelay ?? 100;
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      if (attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError ?? new Error("Retry failed");
}

/** Identity function for type narrowing in pipelines. */
export const identity = <T>(x: T): T => x;

/** Clamp a number between min and max. */
export const clamp = (value: number, min: number, max: number): number => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

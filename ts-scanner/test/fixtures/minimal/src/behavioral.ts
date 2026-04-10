/**
 * Behavioral signals fixture — each section exercises one detector.
 */

import * as fs from "fs";
import { execSync } from "child_process";

// --- Silent failures ---
function riskyOperation(): void {
  try {
    JSON.parse("bad");
  } catch (e) {
    // empty catch — silent failure
  }
}

function loggedOnly(): void {
  try {
    JSON.parse("bad");
  } catch (e) {
    console.error("something failed", e);
  }
}

function loggerOnly(): void {
  try {
    JSON.parse("bad");
  } catch (e) {
    logger.error("something failed", e);
  }
}

// --- Security concerns ---
function dangerousEval(code: string): unknown {
  return eval(code);
}

const dynamicFn = new Function("x", "return x + 1");

// --- Side effects ---
function readConfig(): string {
  return fs.readFileSync("/etc/config", "utf-8");
}

async function fetchData(): Promise<unknown> {
  return fetch("https://example.com/api");
}

function runCommand(): string {
  return execSync("ls -la").toString();
}

// --- Environment variables ---
const dbHost = process.env.DB_HOST;
const port = process.env["PORT"] ?? 3000;
const secret = process.env.SECRET || "default-secret";

// --- SQL strings ---
const query = "SELECT id FROM users WHERE active = 1";
const insert = `INSERT INTO logs (message, level) VALUES ('hello', 'info')`;

// --- Async violation ---
async function loadConfig(): Promise<string> {
  return fs.readFileSync("/etc/config", "utf-8");
}

// --- Deprecation ---
/** @deprecated Use newMethod instead */
function oldMethod(): void {
  return;
}

// --- Class with instance vars ---
class ConfigService {
  private host: string;
  protected port: number = 3000;
  public debug = false;

  constructor(host: string) {
    this.host = host;
    this.connectionString = `http://${host}`;
  }

  getHost(): string {
    return this.host;
  }
}

declare const logger: { error: (...args: unknown[]) => void };

export { riskyOperation, loggedOnly, loggerOnly, dangerousEval, dynamicFn, readConfig, fetchData, runCommand, dbHost, port, secret, query, insert, loadConfig, oldMethod, ConfigService };

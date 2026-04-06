import { describe, it, expect, beforeAll, afterAll } from "vitest";
import * as fs from "fs";
import * as path from "path";
import { analyzeCli } from "../src/cli-analysis.js";

const TMP_DIR = path.resolve(__dirname, ".tmp-cli-test");

beforeAll(() => {
  fs.mkdirSync(TMP_DIR, { recursive: true });
});

afterAll(() => {
  fs.rmSync(TMP_DIR, { recursive: true, force: true });
});

function writeFixture(name: string, content: string): string {
  const filePath = path.join(TMP_DIR, name);
  fs.writeFileSync(filePath, content);
  return filePath;
}

describe("analyzeCli", () => {
  it("returns null when no CLI framework found", () => {
    const f = writeFixture("no-cli.ts", 'export function main() { return "hello"; }');
    expect(analyzeCli([f])).toBeNull();
  });

  describe("commander", () => {
    it("detects commander framework", () => {
      const f = writeFixture("cmd-basic.ts", `
import { Command } from "commander";
const program = new Command();
program.parse();
`);
      const result = analyzeCli([f]);
      expect(result).not.toBeNull();
      expect(result!.framework).toBe("commander");
    });

    it("extracts .option() flags", () => {
      const f = writeFixture("cmd-options.ts", `
import { Command } from "commander";
const program = new Command();
program
  .option('-p, --port <number>', 'port to listen on')
  .option('-H, --host <string>', 'hostname')
  .option('-v, --verbose', 'enable verbose logging');
program.parse();
`);
      const result = analyzeCli([f]);
      expect(result!.options.length).toBe(3);
      const flags = result!.options.map(o => o.flag);
      expect(flags).toContain("-p, --port <number>");
      expect(flags).toContain("-H, --host <string>");
      expect(flags).toContain("-v, --verbose");
      const port = result!.options.find(o => o.flag.includes("--port"));
      expect(port!.description).toBe("port to listen on");
    });

    it("extracts .command() entries", () => {
      const f = writeFixture("cmd-commands.ts", `
import { Command } from "commander";
const program = new Command();
program.command('serve', 'start the server');
program.command('build', 'compile the project');
program.parse();
`);
      const result = analyzeCli([f]);
      expect(result!.commands.length).toBe(2);
      expect(result!.commands[0].name).toBe("serve");
      expect(result!.commands[0].description).toBe("start the server");
    });

    it("extracts .requiredOption()", () => {
      const f = writeFixture("cmd-required.ts", `
import { Command } from "commander";
const program = new Command();
program.requiredOption('--config <path>', 'config file path');
program.parse();
`);
      const result = analyzeCli([f]);
      expect(result!.options.length).toBe(1);
      expect(result!.options[0].flag).toBe("--config <path>");
    });
  });

  describe("yargs", () => {
    it("detects yargs framework", () => {
      const f = writeFixture("yargs-basic.ts", `
import yargs from "yargs";
const argv = yargs(process.argv.slice(2)).parse();
`);
      const result = analyzeCli([f]);
      expect(result).not.toBeNull();
      expect(result!.framework).toBe("yargs");
    });

    it("extracts .option() with object config", () => {
      const f = writeFixture("yargs-options.ts", `
import yargs from "yargs";
yargs(process.argv.slice(2))
  .option('port', { describe: 'port to listen on', type: 'number' })
  .option('host', { description: 'hostname', type: 'string' })
  .parse();
`);
      const result = analyzeCli([f]);
      expect(result!.options.length).toBe(2);
      const port = result!.options.find(o => o.flag === "port");
      expect(port).toBeDefined();
      expect(port!.description).toBe("port to listen on");
      expect(port!.type).toBe("number");
      const host = result!.options.find(o => o.flag === "host");
      expect(host).toBeDefined();
      expect(host!.description).toBe("hostname");
    });

    it("extracts .command() entries", () => {
      const f = writeFixture("yargs-commands.ts", `
import yargs from "yargs";
yargs(process.argv.slice(2))
  .command('serve', 'start the server')
  .command('build', 'compile the project')
  .parse();
`);
      const result = analyzeCli([f]);
      expect(result!.commands.length).toBe(2);
      const names = result!.commands.map(c => c.name);
      expect(names).toContain("serve");
      expect(names).toContain("build");
    });
  });

  describe("other frameworks", () => {
    it("detects meow with framework name only", () => {
      const f = writeFixture("meow-basic.ts", `
import meow from "meow";
const cli = meow("Usage: tool <input>", { flags: {} });
`);
      const result = analyzeCli([f]);
      expect(result!.framework).toBe("meow");
      expect(result!.commands).toEqual([]);
      expect(result!.options).toEqual([]);
    });

    it("detects cac with framework name only", () => {
      const f = writeFixture("cac-basic.ts", `
import cac from "cac";
const cli = cac("my-tool");
`);
      const result = analyzeCli([f]);
      expect(result!.framework).toBe("cac");
    });
  });
});

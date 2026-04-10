import { describe, it, expect } from "vitest";
import * as path from "path";
import { analyzeFile } from "../src/ast-analysis.js";

const FIXTURE_PATH = path.resolve(__dirname, "fixtures/minimal/src/behavioral.ts");
const INTERNAL_CALLS_PATH = path.resolve(__dirname, "fixtures/minimal/src/internal-calls-target.ts");
const REACT_COMPONENT_PATH = path.resolve(__dirname, "fixtures/minimal/src/react-component.tsx");

describe("behavioral signals", () => {
  const result = analyzeFile(FIXTURE_PATH);

  describe("silent failures", () => {
    it("detects empty catch block", () => {
      const emptyCatch = result.silent_failures.find(f => f.type === "empty_catch");
      expect(emptyCatch).toBeDefined();
      expect(emptyCatch!.context).toContain("empty block");
    });

    it("detects logged-only catch block", () => {
      const loggedCatch = result.silent_failures.find(f => f.type === "logged_catch");
      expect(loggedCatch).toBeDefined();
      expect(loggedCatch!.context).toContain("does not rethrow");
    });

    it("detects logger.error catch as logged_catch", () => {
      const loggerCatches = result.silent_failures.filter(f => f.type === "logged_catch");
      expect(loggerCatches.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("security concerns", () => {
    it("detects eval with high severity", () => {
      const evalConcern = result.security_concerns.find(c => c.call === "eval");
      expect(evalConcern).toBeDefined();
      expect(evalConcern!.type).toBe("code_execution");
      expect(evalConcern!.severity).toBe("high");
    });

    it("detects new Function with high severity", () => {
      const fnConcern = result.security_concerns.find(c => c.call === "new Function()");
      expect(fnConcern).toBeDefined();
      expect(fnConcern!.type).toBe("code_execution");
      expect(fnConcern!.severity).toBe("high");
    });
  });

  describe("side effects", () => {
    it("detects file_io from fs.readFileSync", () => {
      const fileIo = result.side_effects.find(s => s.category === "file_io");
      expect(fileIo).toBeDefined();
      expect(fileIo!.call).toContain("readFileSync");
    });

    it("detects network from fetch", () => {
      const network = result.side_effects.find(s => s.category === "network");
      expect(network).toBeDefined();
      expect(network!.call).toBe("fetch");
    });

    it("detects subprocess from execSync", () => {
      const sub = result.side_effects.find(s => s.category === "subprocess");
      expect(sub).toBeDefined();
      expect(sub!.call).toContain("execSync");
    });
  });

  describe("environment variables", () => {
    it("detects DB_HOST as required (no fallback)", () => {
      const dbHost = result.env_vars.find(e => e.variable === "DB_HOST");
      expect(dbHost).toBeDefined();
      expect(dbHost!.required).toBe(true);
      expect(dbHost!.fallback_type).toBe("none");
    });

    it("detects PORT with nullish coalesce default", () => {
      const port = result.env_vars.find(e => e.variable === "PORT");
      expect(port).toBeDefined();
      expect(port!.fallback_type).toBe("nullish_coalesce");
      expect(port!.default).toBe("3000");
    });

    it("detects SECRET with or_fallback", () => {
      const secret = result.env_vars.find(e => e.variable === "SECRET");
      expect(secret).toBeDefined();
      expect(secret!.fallback_type).toBe("or_fallback");
      expect(secret!.default).toBe("default-secret");
    });
  });

  describe("SQL strings", () => {
    it("detects SELECT query", () => {
      const selectQ = result.sql_strings.find(s => s.sql.includes("SELECT"));
      expect(selectQ).toBeDefined();
      expect(selectQ!.type).toBe("query");
    });

    it("detects INSERT query", () => {
      const insertQ = result.sql_strings.find(s => s.sql.includes("INSERT"));
      expect(insertQ).toBeDefined();
    });
  });

  describe("async violations", () => {
    it("detects readFileSync in async function", () => {
      const violation = result.async_violations.find(v => v.violation_type === "blocking_io");
      expect(violation).toBeDefined();
      expect(violation!.call).toContain("readFileSync");
      expect(violation!.function).toBe("loadConfig");
    });
  });

  describe("deprecation markers", () => {
    it("detects @deprecated JSDoc on oldMethod", () => {
      const dep = result.deprecation_markers.find(d => d.name === "oldMethod");
      expect(dep).toBeDefined();
      expect(dep!.source).toBe("jsdoc");
      expect(dep!.reason).toContain("newMethod");
    });
  });

  describe("internal calls", () => {
    const icResult = analyzeFile(INTERNAL_CALLS_PATH);

    it("detects calls to local functions", () => {
      const callNames = icResult.internal_calls.map(c => c.call);
      expect(callNames).toContain("validateInput");
      expect(callNames).toContain("formatResult");
    });

    it("records correct line numbers", () => {
      const validate = icResult.internal_calls.find(c => c.call === "validateInput");
      expect(validate).toBeDefined();
      expect(validate!.line).toBeGreaterThan(0);
    });
  });

  describe("framework detection", () => {
    const rxResult = analyzeFile(REACT_COMPONENT_PATH);

    it("detects 'use client' directive", () => {
      expect(rxResult.ts_directive).toBe("use client");
    });

    it("sets framework_role for client component", () => {
      expect(rxResult.framework_role).toBe("react_client_component");
    });

    it("marks PascalCase functions as components in .tsx", () => {
      const counter = rxResult.functions.find(f => f.name === "Counter");
      expect(counter).toBeDefined();
      expect(counter!.is_component).toBe(true);
    });

    it("does not mark non-PascalCase functions as components", () => {
      const fmt = rxResult.functions.find(f => f.name === "formatLabel");
      expect(fmt).toBeDefined();
      expect(fmt!.is_component).toBeUndefined();
    });

    it("detects React hooks", () => {
      expect(rxResult.react_hooks).toBeDefined();
      const hookNames = rxResult.react_hooks!.map(h => h.name);
      expect(hookNames).toContain("useState");
      expect(hookNames).toContain("useEffect");
    });
  });

  describe("instance variables", () => {
    const configClass = result.classes.find(c => c.name === "ConfigService");

    it("finds ConfigService class", () => {
      expect(configClass).toBeDefined();
      expect(configClass!.instance_vars).toBeDefined();
    });

    it("extracts private host field", () => {
      const host = configClass!.instance_vars!.find(v => v.name === "host");
      expect(host).toBeDefined();
      expect(host!.visibility).toBe("private");
      expect(host!.type).toBe("string");
    });

    it("extracts protected port with default", () => {
      const port = configClass!.instance_vars!.find(v => v.name === "port");
      expect(port).toBeDefined();
      expect(port!.visibility).toBe("protected");
      expect(port!.has_default).toBe(true);
    });

    it("extracts public debug with default", () => {
      const debug = configClass!.instance_vars!.find(v => v.name === "debug");
      expect(debug).toBeDefined();
      expect(debug!.visibility).toBe("public");
      expect(debug!.has_default).toBe(true);
    });

    it("extracts constructor this.connectionString assignment", () => {
      const connStr = configClass!.instance_vars!.find(v => v.name === "connectionString");
      expect(connStr).toBeDefined();
      expect(connStr!.visibility).toBe("public");
      expect(connStr!.has_default).toBe(true);
    });
  });
});

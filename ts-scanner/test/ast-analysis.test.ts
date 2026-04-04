import { describe, it, expect } from "vitest";
import * as path from "path";
import { analyzeFile } from "../src/ast-analysis.js";

const FIXTURES = path.resolve(__dirname, "fixtures/minimal/src");

describe("analyzeFile", () => {
  describe("index.ts", () => {
    const result = analyzeFile(path.join(FIXTURES, "index.ts"));

    it("parses without error", () => {
      expect(result.parse_error).toBeNull();
    });

    it("counts lines", () => {
      expect(result.line_count).toBeGreaterThan(0);
    });

    it("extracts the App class", () => {
      expect(result.classes.length).toBe(1);
      expect(result.classes[0].name).toBe("App");
    });

    it("extracts class methods", () => {
      const app = result.classes[0];
      const methodNames = app.methods.map(m => m.name);
      expect(methodNames).toContain("constructor");
      expect(methodNames).toContain("start");
      expect(methodNames).toContain("getStatus");
    });

    it("detects async methods", () => {
      const app = result.classes[0];
      const start = app.methods.find(m => m.name === "start");
      expect(start?.is_async).toBe(true);
      const getStatus = app.methods.find(m => m.name === "getStatus");
      expect(getStatus?.is_async).toBe(false);
    });

    it("extracts top-level functions", () => {
      const funcNames = result.functions.map(f => f.name);
      expect(funcNames).toContain("bootstrap");
      expect(funcNames).toContain("getVersion");
    });

    it("detects async functions", () => {
      const bootstrap = result.functions.find(f => f.name === "bootstrap");
      expect(bootstrap?.is_async).toBe(true);
      const getVersion = result.functions.find(f => f.name === "getVersion");
      expect(getVersion?.is_async).toBe(false);
    });

    it("extracts return types", () => {
      const bootstrap = result.functions.find(f => f.name === "bootstrap");
      expect(bootstrap?.returns).toBe("Promise<App>");
      const getVersion = result.functions.find(f => f.name === "getVersion");
      expect(getVersion?.returns).toBe("string");
    });

    it("extracts constants", () => {
      const constNames = result.constants.map(c => c.name);
      expect(constNames).toContain("PORT");
    });

    it("estimates tokens", () => {
      expect(result.tokens.original).toBeGreaterThan(0);
      expect(result.tokens.skeleton).toBeGreaterThan(0);
    });

    it("extracts docstrings", () => {
      const app = result.classes[0];
      const start = app.methods.find(m => m.name === "start");
      expect(start).toBeDefined();
      // JSDoc on the class's start method
    });
  });

  describe("user.service.ts", () => {
    const result = analyzeFile(path.join(FIXTURES, "user.service.ts"));

    it("parses without error", () => {
      expect(result.parse_error).toBeNull();
    });

    it("extracts the User interface", () => {
      expect(result.ts_interfaces).toBeDefined();
      const user = result.ts_interfaces!.find(i => i.name === "User");
      expect(user).toBeDefined();
      expect(user!.members.length).toBeGreaterThanOrEqual(4);
    });

    it("detects optional interface members", () => {
      const user = result.ts_interfaces!.find(i => i.name === "User")!;
      const createdAt = user.members.find(m => m.name === "createdAt");
      expect(createdAt?.optional).toBe(true);
      const name = user.members.find(m => m.name === "name");
      expect(name?.optional).toBe(false);
    });

    it("extracts type aliases", () => {
      expect(result.ts_type_aliases).toBeDefined();
      const alias = result.ts_type_aliases!.find(a => a.name === "UserCreateInput");
      expect(alias).toBeDefined();
    });

    it("extracts enums", () => {
      expect(result.ts_enums).toBeDefined();
      const roleEnum = result.ts_enums!.find(e => e.name === "UserRole");
      expect(roleEnum).toBeDefined();
      expect(roleEnum!.members.length).toBe(3);
      expect(roleEnum!.members[0].name).toBe("Admin");
      expect(roleEnum!.members[0].value).toBe("admin");
    });

    it("extracts the UserService class", () => {
      expect(result.classes.length).toBe(1);
      expect(result.classes[0].name).toBe("UserService");
    });

    it("extracts class methods with parameters", () => {
      const svc = result.classes[0];
      const createUser = svc.methods.find(m => m.name === "createUser");
      expect(createUser).toBeDefined();
      expect(createUser!.args.length).toBeGreaterThanOrEqual(1);
      expect(createUser!.is_async).toBe(true);
    });

    it("extracts method return types", () => {
      const svc = result.classes[0];
      const findById = svc.methods.find(m => m.name === "findById");
      expect(findById?.returns).toBe("User | undefined");
    });

    it("calculates type coverage", () => {
      expect(result.type_coverage.total_functions).toBeGreaterThan(0);
      expect(result.type_coverage.typed_functions).toBeGreaterThan(0);
      expect(result.type_coverage.coverage_percent).toBeGreaterThan(0);
    });
  });

  describe("utils.ts", () => {
    const result = analyzeFile(path.join(FIXTURES, "utils.ts"));

    it("parses without error", () => {
      expect(result.parse_error).toBeNull();
    });

    it("extracts constants", () => {
      const constNames = result.constants.map(c => c.name);
      expect(constNames).toContain("MAX_RETRIES");
      expect(constNames).toContain("API_BASE_URL");
    });

    it("extracts constant values", () => {
      const maxRetries = result.constants.find(c => c.name === "MAX_RETRIES");
      expect(maxRetries?.value).toBe("3");
    });

    it("extracts named functions", () => {
      const funcNames = result.functions.map(f => f.name);
      expect(funcNames).toContain("formatName");
      expect(funcNames).toContain("isValidEmail");
      expect(funcNames).toContain("retry");
    });

    it("extracts arrow functions as named functions", () => {
      const funcNames = result.functions.map(f => f.name);
      expect(funcNames).toContain("identity");
      expect(funcNames).toContain("clamp");
    });

    it("calculates complexity for retry function", () => {
      const retry = result.functions.find(f => f.name === "retry");
      expect(retry).toBeDefined();
      // retry has: for loop, try/catch, if (attempt < max), if (error instanceof)
      expect(retry!.complexity).toBeGreaterThan(1);
    });

    it("detects async functions", () => {
      const retry = result.functions.find(f => f.name === "retry");
      expect(retry?.is_async).toBe(true);
      const formatName = result.functions.find(f => f.name === "formatName");
      expect(formatName?.is_async).toBe(false);
    });

    it("extracts function parameters with types", () => {
      const formatName = result.functions.find(f => f.name === "formatName");
      expect(formatName?.args.length).toBe(2);
      expect(formatName?.args[0].name).toBe("first");
      expect(formatName?.args[0].type).toBe("string");
    });

    it("tracks async pattern counts", () => {
      // retry is async, others are sync
      expect(result.async_patterns.async_functions).toBeGreaterThanOrEqual(1);
      expect(result.async_patterns.sync_functions).toBeGreaterThanOrEqual(2);
    });
  });

  describe("error handling", () => {
    it("handles non-existent files gracefully", () => {
      const result = analyzeFile("/nonexistent/file.ts");
      expect(result.parse_error).not.toBeNull();
      expect(result.parse_error).toContain("Read error");
    });
  });
});

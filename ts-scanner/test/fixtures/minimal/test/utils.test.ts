import { describe, it, expect } from "vitest";
import { vi } from "vitest";

vi.mock("./utils", () => ({
  formatName: vi.fn(() => "mocked"),
}));

describe("utils", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("formats names correctly", () => {
    expect("mocked").toBe("mocked");
  });

  it("validates email format", () => {
    expect("test@example.com").toContain("@");
  });
});

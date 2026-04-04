import { describe, expect, it } from "vitest";
import { formatTokens, formatUsd, formatUsd4 } from "./UsageView";

describe("formatUsd", () => {
  it("returns dash for zero", () => {
    expect(formatUsd(0)).toBe("—");
  });
  it("rounds $0.0567 to $0.06 (not truncate to $0.05)", () => {
    expect(formatUsd(0.0567)).toBe("$0.06");
  });
  it("rounds $0.051 to $0.05", () => {
    expect(formatUsd(0.051)).toBe("$0.05");
  });
  it("rounds $1.999 to $2.00", () => {
    expect(formatUsd(1.999)).toBe("$2.00");
  });
  it("keeps $0.10 as $0.10", () => {
    expect(formatUsd(0.1)).toBe("$0.10");
  });
});

describe("formatUsd4", () => {
  it("returns dash for zero", () => {
    expect(formatUsd4(0)).toBe("—");
  });
  it("rounds to 4 decimal places", () => {
    expect(formatUsd4(0.00056)).toBe("$0.0006");
  });
  it("keeps exact values", () => {
    expect(formatUsd4(0.0042)).toBe("$0.0042");
  });
});

describe("formatTokens", () => {
  it("formats millions", () => {
    expect(formatTokens(1_500_000)).toBe("1.5m");
  });
  it("formats thousands", () => {
    expect(formatTokens(357_000)).toBe("357k");
  });
  it("formats small thousands with decimal", () => {
    expect(formatTokens(5_200)).toBe("5.2k");
  });
  it("formats small numbers as-is", () => {
    expect(formatTokens(42)).toBe("42");
  });
});

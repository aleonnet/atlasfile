import { describe, expect, it, vi } from "vitest";
import { qk } from "./queryKeys";
import { queryClient } from "./queryClient";
import {
  invalidateAfterScan,
  invalidateAfterTriageDecision,
} from "./mutations";

vi.mock("../api", () => ({}));

describe("queryKeys", () => {
  it("chaves de projeto carregam o projectId (segregação de cache por projeto)", () => {
    expect(qk.triage.list("p1")).toEqual(["triage", "p1"]);
    expect(qk.triage.rejected("p1")).toEqual(["triage", "p1", "rejected"]);
    expect(qk.stats("p1")).toEqual(["stats", "p1"]);
    expect(qk.stats()).toEqual(["stats", null]);
    expect(qk.profile("p2")).toEqual(["profile", "p2"]);
  });

  it("prefixo de escopo cobre as chaves filhas (invalidation por prefixo)", () => {
    const scope = qk.triage.scope();
    expect(qk.triage.list("p1").slice(0, scope.length)).toEqual([...scope]);
    expect(qk.triage.rejected("p1").slice(0, scope.length)).toEqual([...scope]);
    const clsScope = qk.classifier.scope();
    expect(qk.classifier.reports().slice(0, clsScope.length)).toEqual([...clsScope]);
  });
});

describe("invalidations por domínio (F2)", () => {
  it("decisão de triagem derruba fila, stats, histórico, conflitos e classificador", () => {
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
    try {
      invalidateAfterTriageDecision();
      const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(keys).toContain(JSON.stringify(qk.triage.scope()));
      expect(keys).toContain(JSON.stringify(["stats"]));
      expect(keys).toContain(JSON.stringify(["ingest-history"]));
      expect(keys).toContain(JSON.stringify(qk.labelConflicts()));
      expect(keys).toContain(JSON.stringify(qk.classifier.scope()));
      expect(keys).toContain(JSON.stringify(["alias-suggestions"]));
    } finally {
      spy.mockRestore();
    }
  });

  it("scan derruba a fila da inbox além de triagem/stats/histórico", () => {
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
    try {
      invalidateAfterScan();
      const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(keys).toContain(JSON.stringify(["inbox-files"]));
      expect(keys).toContain(JSON.stringify(qk.triage.scope()));
    } finally {
      spy.mockRestore();
    }
  });
});

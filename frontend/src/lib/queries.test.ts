import { describe, expect, it, vi } from "vitest";
import { qk } from "./queryKeys";
import { queryClient } from "./queryClient";
import { emitDataRefresh, installRefreshBusQueryAdapter } from "./refreshBus";

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

describe("adaptador bus→invalidation (F1, transitório)", () => {
  it("emit legado marca as queries dos antigos assinantes como stale", () => {
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
    const uninstall = installRefreshBusQueryAdapter();
    try {
      emitDataRefresh();
      const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(keys).toContain(JSON.stringify(qk.triage.scope()));
      expect(keys).toContain(JSON.stringify(["stats"]));
      expect(keys).toContain(JSON.stringify(qk.projects()));
    } finally {
      uninstall();
      spy.mockRestore();
    }
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchProjects,
  fetchReconcileStatus,
  fetchSuggestions,
  getFileDownloadUrl,
  searchDocuments
} from "./api";

describe("getFileDownloadUrl", () => {
  it("returns URL with encoded path", () => {
    const url = getFileDownloadUrl("proj/_WORK/file.pdf");
    expect(url).toContain("/api/files/download");
    expect(url).toContain("path=");
    expect(url).toContain(encodeURIComponent("proj/_WORK/file.pdf"));
  });
});

describe("fetchProjects", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns projects on 200", async () => {
    const mockProjects = [{ project_id: "p1", project_label: "P1", initialized: true }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockProjects)
    } as Response);
    const result = await fetchProjects();
    expect(result).toEqual(mockProjects);
  });

  it("throws on !res.ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false } as Response);
    await expect(fetchProjects()).rejects.toThrow("Falha ao carregar projetos");
  });
});

describe("searchDocuments", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("includes q, page, size in URL", async () => {
    let capturedUrl = "";
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      capturedUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ total: 0, page: 1, page_size: 20, total_pages: 0, hits: [] })
      } as Response);
    });
    await searchDocuments("test query", undefined, 2, 10);
    expect(capturedUrl).toContain("q=test+query");
    expect(capturedUrl).toContain("page=2");
    expect(capturedUrl).toContain("size=10");
  });

  it("includes project_id when provided", async () => {
    let capturedUrl = "";
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      capturedUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ total: 0, page: 1, page_size: 20, total_pages: 0, hits: [] })
      } as Response);
    });
    await searchDocuments("q", "proj1");
    expect(capturedUrl).toContain("project_id=proj1");
  });

  it("throws on !res.ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false } as Response);
    await expect(searchDocuments("q")).rejects.toThrow("Falha na busca");
  });
});

describe("fetchSuggestions", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns suggest response on 200", async () => {
    const mockResponse = { total: 1, items: [{ doc_id: "d1", score: 1, project_id: "", original_filename: "", canonical_filename: "", path: "", matched_in: [], highlights: [] }] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse)
    } as Response);
    const result = await fetchSuggestions("doc");
    expect(result).toEqual(mockResponse);
  });

  it("throws on !res.ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false } as Response);
    await expect(fetchSuggestions("q")).rejects.toThrow("Falha no autocomplete");
  });
});

describe("fetchReconcileStatus", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns status on 200", async () => {
    const mockStatus = { running: false, phase: "idle", summary: {} };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockStatus)
    } as Response);
    const result = await fetchReconcileStatus();
    expect(result).toEqual(mockStatus);
  });
});

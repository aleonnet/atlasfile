import { afterEach, describe, expect, it, vi } from "vitest";
import {
  applyProjectLayout,
  fetchProjects,
  fetchProfileHistory,
  fetchProjectProfile,
  fetchReconcileStatus,
  fetchSuggestions,
  getFileDownloadUrl,
  planProjectLayout,
  searchDocuments,
  updateProjectProfile,
  validateProjectProfile
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

describe("profile/layout api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const profilePayload = {
    profile_version: 2 as const,
    project_id: "p1",
    project_label: "Projeto 1",
    project_root: "/tmp/p1",
    paths: {
      inbox: "_INBOX_DROP",
      triage: {
        pending: "_TRIAGE_REVIEW/pending",
        resolved: "_TRIAGE_REVIEW/resolved",
        rejected: "_TRIAGE_REVIEW/rejected"
      }
    },
    layout: {
      mode: "para_jd",
      roots: { projects: "01_PROJECTS", areas: "02_AREAS", resources: "03_RESOURCES", archive: "04_ARCHIVE" },
      areas_root: "02_AREAS",
      area_folders: [{ area_key: "juridica", folder: "02_juridica" }]
    },
    classification: {
      work_areas: [{ key: "juridica", aliases: ["juridico"] }],
      routing_rules: [],
      confidence_thresholds: { auto_route_min: 0.85, triage_min: 0.5 },
      llm_policy: {}
    },
    indexing: { topics_path: "config/topics_v1.yaml", extraction_max_chars: 20000, extraction_mode: "excerpt" as const },
    version: 1
  };

  it("fetchProjectProfile hits profile endpoint", async () => {
    let capturedUrl = "";
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      capturedUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ profile: profilePayload, etag: "e1", version: 1 })
      } as Response);
    });
    const result = await fetchProjectProfile("p1");
    expect(capturedUrl).toContain("/api/projects/p1/profile");
    expect(result.version).toBe(1);
  });

  it("validate/update/profile-history send expected payloads", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes("/validate")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { profile?: unknown };
        expect(body.profile).toBeTruthy();
      }
      if (url.endsWith("/profile") && init?.method === "PUT") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { if_match_version?: number };
        expect(body.if_match_version).toBe(3);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ entries: [] }) } as Response);
    });

    await validateProjectProfile("p1", profilePayload);
    await updateProjectProfile("p1", profilePayload, 3, "frontend:test");
    await fetchProfileHistory("p1");
    expect(fetchSpy).toHaveBeenCalledTimes(3);
  });

  it("plan/apply layout call layout endpoints", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes("/layout/plan")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              plan_id: "plan1",
              summary: { moves: 1, conflicts: 0, mkdirs: 0, ops: 1 },
              plan: {
                project_root: "/tmp/p1",
                from_areas_root: "/tmp/p1/02_AREAS",
                to_areas_root: "/tmp/p1/02_AREAS",
                ops: [],
                conflicts: 0,
                moves: 1,
                mkdirs: 0,
                strategy: "rename_with_suffix",
                cleanup_empty_dirs: false
              }
            })
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true, plan_id: "plan1", profile_version: 2, apply: {} })
      } as Response);
    });

    const plan = await planProjectLayout("p1", profilePayload);
    expect(plan.plan_id).toBe("plan1");
    const apply = await applyProjectLayout("p1", { profile: profilePayload, plan_id: "plan1", confirm: true, if_match_version: 2 });
    expect(apply.ok).toBe(true);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});

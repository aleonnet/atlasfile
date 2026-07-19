import i18n from "../../i18n";
import type { SearchEvidence } from "../../types";

export function formatLocationLabel(loc: string): string {
  const normalized = (loc || "").trim().toLowerCase();
  const docxMatch = normalized.match(/^docx_page(_est)?:([0-9]+):paragraph:([0-9]+)(?::part:([0-9]+))?$/);
  if (docxMatch) {
    const estimated = docxMatch[1] === "_est";
    const page = docxMatch[2];
    const paragraph = docxMatch[3];
    const part = docxMatch[4] ? i18n.t("painel:location.partSuffix", { part: docxMatch[4] }) : "";
    return i18n.t(estimated ? "painel:location.pageParagraphEstimated" : "painel:location.pageParagraph", { page, paragraph, part });
  }
  if (normalized.startsWith("sheet ")) {
    const m = normalized.match(/^sheet\s+(.+?)\s+row\s+(\d+)\s+col\s+([a-z]+)(?:\s+part\s+(\d+))?$/i);
    if (m) {
      const sheetName = m[1].charAt(0).toUpperCase() + m[1].slice(1);
      const part = m[4] ? i18n.t("painel:location.partSuffix", { part: m[4] }) : "";
      return i18n.t("painel:location.sheetRowCol", { sheet: sheetName, row: m[2], col: m[3].toUpperCase(), part });
    }
    return i18n.t("painel:location.sheetGeneric", { rest: normalized.replace(/^sheet\s+/i, "") });
  }
  if (normalized.startsWith("slide ")) return i18n.t("painel:location.slide", { rest: normalized.replace(/^slide\s+/i, "") });
  if (normalized.startsWith("page ")) return i18n.t("painel:location.page", { rest: normalized.replace(/^page\s+/i, "") });
  if (normalized.startsWith("section ")) return i18n.t("painel:location.section", { rest: normalized.replace(/^section\s+/i, "") });
  if (normalized === "content_chunk") return i18n.t("painel:location.contentChunk");
  if (normalized === "content") return i18n.t("painel:location.content");
  if (normalized === "title") return i18n.t("painel:location.title");
  if (normalized === "original_filename") return i18n.t("painel:location.originalFilename");
  if (normalized === "canonical_filename") return i18n.t("painel:location.canonicalFilename");
  return loc;
}

function pageKeyFromLocation(loc: string): string | null {
  const m = (loc || "").trim().toLowerCase().match(/^page:(\d+)(?::\d+)?$/);
  if (!m) return null;
  return `page:${m[1]}`;
}

function countSnippetMatches(snippet: string): number {
  const matches = (snippet || "").match(/<em>/gi);
  return matches?.length ?? 0;
}

function evidenceMatchCount(ev: SearchEvidence): number {
  return Math.max(1, Number(ev.match_count) || countSnippetMatches(ev.snippet));
}

function buildPageOccurrenceCounts(evidences: SearchEvidence[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const ev of evidences || []) {
    const key = pageKeyFromLocation(ev.location);
    if (!key) continue;
    const inc = evidenceMatchCount(ev);
    counts.set(key, (counts.get(key) ?? 0) + inc);
  }
  return counts;
}

function formatEvidenceLocation(loc: string, pageCounts: Map<string, number>): string {
  const key = pageKeyFromLocation(loc);
  if (key) {
    const total = pageCounts.get(key) ?? 0;
    if (total > 0) return i18n.t("painel:location.occurrences", { key, count: total });
    return key;
  }
  return formatLocationLabel(loc);
}

type EvidenceGroup = {
  key: string;
  label: string;
  count: number;
  snippets: string[];
  semantic: boolean;
};

export function buildEvidenceGroups(evidences: SearchEvidence[]): EvidenceGroup[] {
  const pageCounts = buildPageOccurrenceCounts(evidences);
  const groups = new Map<string, EvidenceGroup>();
  for (const ev of evidences || []) {
    const pageKey = pageKeyFromLocation(ev.location);
    const key = pageKey ?? ev.location;
    const label = formatEvidenceLocation(ev.location, pageCounts);
    const groupCount = pageKey ? pageCounts.get(pageKey) ?? evidenceMatchCount(ev) : evidenceMatchCount(ev);
    const isSemantic = ev.match_type === "semantic";
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, { key, label, count: groupCount, snippets: [ev.snippet], semantic: isSemantic });
      continue;
    }
    if (!existing.snippets.includes(ev.snippet) && existing.snippets.length < 2) {
      existing.snippets.push(ev.snippet);
    }
    // Grupo misto (lexical + semântico) mantém o rótulo lexical.
    existing.semantic = existing.semantic && isSemantic;
  }
  return Array.from(groups.values());
}

export function topLocations(locations: string[], max = 3): string[] {
  if (!locations?.length) return [];
  return locations.slice(0, max).map(formatLocationLabel);
}

import type { SearchEvidence } from "../../types";

export function formatLocationLabel(loc: string): string {
  const normalized = (loc || "").trim().toLowerCase();
  const docxMatch = normalized.match(/^docx_page(_est)?:([0-9]+):paragraph:([0-9]+)(?::part:([0-9]+))?$/);
  if (docxMatch) {
    const estimated = docxMatch[1] === "_est";
    const page = docxMatch[2];
    const paragraph = docxMatch[3];
    const part = docxMatch[4] ? ` (parte ${docxMatch[4]})` : "";
    if (estimated) return `Pagina ~${page} / ${paragraph}o paragrafo${part} (estimada)`;
    return `Pagina ${page} / ${paragraph}o paragrafo${part}`;
  }
  if (normalized.startsWith("sheet ")) {
    const m = normalized.match(/^sheet\s+(.+?)\s+row\s+(\d+)\s+col\s+([a-z]+)(?:\s+part\s+(\d+))?$/i);
    if (m) {
      const sheetName = m[1].charAt(0).toUpperCase() + m[1].slice(1);
      const part = m[4] ? ` (parte ${m[4]})` : "";
      return `${sheetName}, linha ${m[2]}, Coluna ${m[3].toUpperCase()}${part}`;
    }
    return normalized.replace(/^sheet\s+/i, "Planilha ");
  }
  if (normalized.startsWith("slide ")) return normalized.replace(/^slide\s+/i, "Slide ");
  if (normalized.startsWith("page ")) return normalized.replace(/^page\s+/i, "Pagina ");
  if (normalized.startsWith("section ")) return normalized.replace(/^section\s+/i, "Secao ");
  if (normalized === "content_chunk") return "Trecho de conteudo";
  if (normalized === "content") return "Conteudo";
  if (normalized === "title") return "Titulo";
  if (normalized === "original_filename") return "Nome original";
  if (normalized === "canonical_filename") return "Nome canonico";
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
    if (total > 0) return `${key} (${total} ocorrência${total === 1 ? "" : "s"})`;
    return key;
  }
  return formatLocationLabel(loc);
}

type EvidenceGroup = {
  key: string;
  label: string;
  count: number;
  snippets: string[];
};

export function buildEvidenceGroups(evidences: SearchEvidence[]): EvidenceGroup[] {
  const pageCounts = buildPageOccurrenceCounts(evidences);
  const groups = new Map<string, EvidenceGroup>();
  for (const ev of evidences || []) {
    const pageKey = pageKeyFromLocation(ev.location);
    const key = pageKey ?? ev.location;
    const label = formatEvidenceLocation(ev.location, pageCounts);
    const groupCount = pageKey ? pageCounts.get(pageKey) ?? evidenceMatchCount(ev) : evidenceMatchCount(ev);
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, { key, label, count: groupCount, snippets: [ev.snippet] });
      continue;
    }
    if (!existing.snippets.includes(ev.snippet) && existing.snippets.length < 2) {
      existing.snippets.push(ev.snippet);
    }
  }
  return Array.from(groups.values());
}

export function topLocations(locations: string[], max = 3): string[] {
  if (!locations?.length) return [];
  return locations.slice(0, max).map(formatLocationLabel);
}


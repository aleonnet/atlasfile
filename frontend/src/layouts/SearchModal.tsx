import { Search } from "lucide-react";
import { buildEvidenceGroups, topLocations } from "../features/search/searchFormatters";
import type { SearchHit } from "../types";

type Props = {
  open: boolean;
  query: string;
  onQueryChange: (value: string) => void;
  modalHits: SearchHit[];
  modalLoading: boolean;
  onClose: () => void;
  onClearSearch: () => void;
  onSubmitSearch: (query: string) => void;
  renderBreadcrumb: (projectId: string, path: string) => string;
  highlightTerm: (text: string, term: string) => React.ReactNode;
  extractSnippets: (highlights: string[]) => string[];
  getDocIcon: (contentType?: string | null, filename?: string) => React.ReactNode;
  getFileDownloadUrl: (path: string) => string;
};

export function SearchModal({
  open,
  query,
  onQueryChange,
  modalHits,
  modalLoading,
  onClose,
  onClearSearch,
  onSubmitSearch,
  renderBreadcrumb,
  highlightTerm,
  extractSnippets,
  getDocIcon,
  getFileDownloadUrl,
}: Props) {
  if (!open) return null;

  return (
    <div className="search-modal-overlay" role="dialog" aria-modal="true" aria-label="Busca global" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <div className="search-modal-input-wrap">
          <Search size={18} className="search-modal-input-icon" />
          <input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                if (query.trim()) onClearSearch();
                else onClose();
              }
              if (e.key === "Enter") {
                onSubmitSearch(query.trim());
              }
            }}
            placeholder="Search..."
            autoFocus
          />
          {query.trim().length > 0 && (
            <button type="button" className="search-modal-kbd esc-btn" onClick={onClearSearch} title="Limpar (ESC)">
              ESC
            </button>
          )}
        </div>

        {query.trim().length > 0 && (
          <div className="search-results-scroll">
            <ul className="list search-list">
              {modalHits.map((hit) => (
                <li key={`top-${hit.doc_id}`} className="list-item search-item">
                  <div className="search-item-content">
                    <div className="sub breadcrumb-line">{renderBreadcrumb(hit.project_id, hit.path)}</div>
                    <div className="title-row">
                      <span className="doc-icon-inline">{getDocIcon(hit.content_type, hit.original_filename)}</span>
                      <a className="result-link result-title" href={getFileDownloadUrl(hit.path)} target="_blank" rel="noreferrer">
                        {highlightTerm(hit.original_filename, query)}
                      </a>
                    </div>
                    {hit.evidences && hit.evidences.length > 0 ? (
                      <div className="snippet" dangerouslySetInnerHTML={{ __html: hit.evidences[0].snippet }} />
                    ) : (
                      extractSnippets(hit.highlights).map((snippet, idx) => (
                        <div key={`top-${hit.doc_id}-snippet-${idx}`} className="snippet" dangerouslySetInnerHTML={{ __html: snippet }} />
                      ))
                    )}
                    {(() => {
                      const totalEv = hit.total_evidences ?? 0;
                      const groups = buildEvidenceGroups(hit.evidences ?? []);
                      const locs =
                        (hit.evidences?.length ?? 0) > 0
                          ? groups.slice(0, 2).map((g) => g.label)
                          : topLocations(hit.match_locations, 2);
                      const extra =
                        totalEv > 2 ? ` e outras ${totalEv - 2} ocorrência${totalEv - 2 === 1 ? "" : "s"}` : "";
                      return locs.length > 0 ? (
                        <div className="sub">
                          Local: {locs.join(" | ")}
                          {extra}
                        </div>
                      ) : null;
                    })()}
                  </div>
                </li>
              ))}
            </ul>
            {modalHits.length === 0 && query.trim().length >= 2 && !modalLoading && (
              <p className="sub empty-search">Nenhum resultado para os termos digitados.</p>
            )}
          </div>
        )}

        {query.trim().length > 0 && (
          <div className="search-modal-footer">
            <span className="sub">
              Top {modalHits.length} resultado(s) em tempo real. Pressione Enter para listar todos.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

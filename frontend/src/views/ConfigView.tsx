import { useState } from "react";
import { getApiKey, setApiKey } from "../api";
import { IngestTriageCard } from "../features/ingest/IngestTriageCard";
import { ProfileLayoutWorkspace } from "../features/profile-layout/ProfileLayoutWorkspace";
import { TemplateEditorView } from "../features/templates/TemplateEditorView";
import type { Project, TriageItem } from "../types";

type ConfigTab = "perfil" | "classificador" | "templates" | "acesso";

function ApiAccessCard({ onStatus }: { onStatus: (msg: string) => void }) {
  const [keyValue, setKeyValue] = useState(getApiKey());

  const handleSave = () => {
    setApiKey(keyValue);
    onStatus(keyValue.trim() ? "API key do AtlasFile salva neste navegador." : "API key removida.");
  };

  return (
    <div className="card">
      <h3>Acesso à API</h3>
      <p className="sub">
        Necessária apenas quando o backend está com <code>API_AUTH_ENABLED=true</code>. A key é
        guardada somente neste navegador (localStorage) e enviada como <code>Authorization: Bearer</code>.
      </p>
      <div className="field-row" style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
        <input
          type="password"
          value={keyValue}
          onChange={(e) => setKeyValue(e.target.value)}
          placeholder="atlas_sk_..."
          autoComplete="off"
          style={{ flex: 1 }}
        />
        <button type="button" className="btn" onClick={handleSave}>
          Salvar
        </button>
      </div>
    </div>
  );
}

type Props = {
  selectedProject: string;
  selectedProjectLabel: string;
  projects: Project[];
  projectLabelById: Map<string, string>;
  triageItems: TriageItem[];
  initializingProjectId: string | null;
  onLoadTriage: () => Promise<void>;
  onStatus: (msg: string) => void;
  openaiApiKey: string;
  anthropicApiKey: string;
  onOpenSettings: () => void;
  selectedModelTriage: string;
  onChangeModelTriage: (model: string) => void;
};

const ALL_PROJECTS = "__all__";

export function ConfigView({
  selectedProject,
  selectedProjectLabel,
  projects,
  projectLabelById,
  triageItems,
  initializingProjectId,
  onLoadTriage,
  onStatus,
  openaiApiKey,
  anthropicApiKey,
  onOpenSettings,
  selectedModelTriage,
  onChangeModelTriage,
}: Props) {
  const [tab, setTab] = useState<ConfigTab>("perfil");

  return (
    <section className="config-view">
      <nav className="assistente-tabs" role="tablist">
        <div className="assistente-tabs-pill">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "perfil"}
            className={`assistente-tab${tab === "perfil" ? " assistente-tab--active" : ""}`}
            onClick={() => setTab("perfil")}
          >
            Perfil do projeto
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "classificador"}
            className={`assistente-tab${tab === "classificador" ? " assistente-tab--active" : ""}`}
            onClick={() => setTab("classificador")}
          >
            Classificador
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "templates"}
            className={`assistente-tab${tab === "templates" ? " assistente-tab--active" : ""}`}
            onClick={() => setTab("templates")}
          >
            Templates
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "acesso"}
            className={`assistente-tab${tab === "acesso" ? " assistente-tab--active" : ""}`}
            onClick={() => setTab("acesso")}
          >
            Acesso
          </button>
        </div>
      </nav>

      <div className="config-view-content">
        {tab === "perfil" && (
          <ProfileLayoutWorkspace
            projectRef={selectedProject}
            disabled={selectedProject === ALL_PROJECTS}
            onStatus={onStatus}
          />
        )}

        {tab === "classificador" && (
          <IngestTriageCard
            selectedProject={selectedProject}
            selectedProjectLabel={selectedProjectLabel}
            projects={projects}
            projectLabelById={projectLabelById}
            triageItems={triageItems}
            initializingProjectId={initializingProjectId}
            onLoadTriage={onLoadTriage}
            onStatus={onStatus}
            openaiApiKey={openaiApiKey}
            anthropicApiKey={anthropicApiKey}
            onOpenSettings={onOpenSettings}
            selectedModelTriage={selectedModelTriage}
            onChangeModelTriage={onChangeModelTriage}
          />
        )}

        {tab === "templates" && (
          <TemplateEditorView />
        )}

        {tab === "acesso" && <ApiAccessCard onStatus={onStatus} />}
      </div>
    </section>
  );
}

import { useState } from "react";
import { KeyRound } from "lucide-react";
import { getApiKey, setApiKey } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { IngestTriageCard } from "../features/ingest/IngestTriageCard";
import { ProfileLayoutWorkspace } from "../features/profile-layout/ProfileLayoutWorkspace";
import { TemplateEditorView } from "../features/templates/TemplateEditorView";
import type { Project, TriageItem } from "../types";

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

function ApiAccessCard({ onStatus }: { onStatus: (msg: string) => void }) {
  const [keyValue, setKeyValue] = useState(getApiKey());

  const handleSave = () => {
    setApiKey(keyValue);
    onStatus(keyValue.trim() ? "API key do AtlasFile salva neste navegador." : "API key removida.");
  };

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4 text-accent" />
          Acesso à API
        </CardTitle>
        <CardDescription>
          Necessária apenas quando o backend está com{" "}
          <code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">
            API_AUTH_ENABLED=true
          </code>
          . A key fica somente neste navegador (localStorage) e é enviada como{" "}
          <code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">
            Authorization: Bearer
          </code>
          .
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2">
          <Input
            type="password"
            value={keyValue}
            onChange={(e) => setKeyValue(e.target.value)}
            placeholder="atlas_sk_..."
            autoComplete="off"
            className="flex-1 font-mono"
          />
          <Button onClick={handleSave}>Salvar</Button>
        </div>
      </CardContent>
    </Card>
  );
}

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
  return (
    <section className="config-view">
      <Tabs defaultValue="perfil">
        <TabsList aria-label="Configurações">
          <TabsTrigger value="perfil">Perfil do projeto</TabsTrigger>
          <TabsTrigger value="classificador">Classificador</TabsTrigger>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          <TabsTrigger value="acesso">Acesso</TabsTrigger>
        </TabsList>

        <TabsContent value="perfil">
          <ProfileLayoutWorkspace
            projectRef={selectedProject}
            disabled={selectedProject === ALL_PROJECTS}
            onStatus={onStatus}
          />
        </TabsContent>

        <TabsContent value="classificador">
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
        </TabsContent>

        <TabsContent value="templates">
          <TemplateEditorView />
        </TabsContent>

        <TabsContent value="acesso">
          <ApiAccessCard onStatus={onStatus} />
        </TabsContent>
      </Tabs>
    </section>
  );
}

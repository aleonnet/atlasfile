import { useState } from "react";
import { STORAGE_KEYS, storageGet, storageSet } from "../lib/storage";
import { FolderTree, KeyRound, LayoutTemplate, Sparkles } from "lucide-react";
import { getApiKey, setApiKey } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { IngestTriageCard } from "../features/ingest/IngestTriageCard";
import { ProfileLayoutWorkspace } from "../features/profile-layout/ProfileLayoutWorkspace";
import { TemplateEditorView } from "../features/templates/TemplateEditorView";
import type { TriageItem } from "../types";

type Props = {
  selectedProject: string;
  selectedProjectLabel: string;
  triageItems: TriageItem[];
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
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-h-9 items-center gap-2">
          <KeyRound className="size-4 text-accent" />
          Acesso à API
        </CardTitle>
      </CardHeader>
      <CardContent>
        <CardDescription className="mb-3">
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
        <div className="mt-4 rounded-md border border-border bg-elevated px-3 py-2.5">
          <p className="m-0 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">Como habilitar a autenticação</p>
          <p className="m-0 mt-1.5 text-[0.8rem] text-muted-foreground">
            A autenticação é uma decisão de deployment — por segurança, não pode ser ligada por esta UI
            (uma interface sem auth não deve conseguir ativar auth). O caminho mais simples é re-executar
            o instalador no servidor, que gera a key, configura o <code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">.env</code> e reconstrói a API preservando seus dados:
          </p>
          <pre className="mt-1.5 overflow-x-auto rounded bg-panel-strong px-2.5 py-2 font-mono text-[0.7rem] text-accent-light">
            curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --enable-auth
          </pre>
          <p className="m-0 mt-1.5 text-[0.8rem] text-muted-foreground">
            Ou manualmente: keys em <code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">config/api_keys.json</code>,{" "}
            <code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">API_AUTH_ENABLED=true</code> no .env e{" "}
            <code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">docker compose up -d --build api mcp</code>.
            Ao final, a key gerada é exibida no terminal — cole-a acima em cada navegador que acessa o AtlasFile.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function ConfigView({
  selectedProject,
  selectedProjectLabel,
  triageItems,
  onStatus,
  openaiApiKey,
  anthropicApiKey,
  onOpenSettings,
  selectedModelTriage,
  onChangeModelTriage,
}: Props) {
  return (
    <section className="flex flex-col">
      <Tabs
        defaultValue={storageGet(STORAGE_KEYS.configTab) || "perfil"}
        onValueChange={(v) => storageSet(STORAGE_KEYS.configTab, v)}
      >
        <TabsList aria-label="Configurações">
          <TabsTrigger value="perfil"><FolderTree aria-hidden /> Perfil do projeto</TabsTrigger>
          <TabsTrigger value="templates"><LayoutTemplate aria-hidden /> Templates</TabsTrigger>
          <TabsTrigger value="acesso"><KeyRound aria-hidden /> Acesso</TabsTrigger>
        </TabsList>

        <TabsContent value="perfil" forceMount>
          <ProfileLayoutWorkspace
            projectRef={selectedProject}
            disabled={selectedProject === ALL_PROJECTS}
            onStatus={onStatus}
          />
        </TabsContent>

        <TabsContent value="templates" forceMount>
          <TemplateEditorView />
        </TabsContent>

        <TabsContent value="acesso" forceMount>
          <ApiAccessCard onStatus={onStatus} />
        </TabsContent>
      </Tabs>
    </section>
  );
}

import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { STORAGE_KEYS, storageGet, storageSet } from "../lib/storage";
import { FolderTree, KeyRound, Languages, LayoutTemplate } from "lucide-react";
import { getApiKey, setApiKey } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { nativeSelectClass } from "../components/ui/modal-shell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ProfileLayoutWorkspace } from "../features/profile-layout/ProfileLayoutWorkspace";
import { TemplateEditorView } from "../features/templates/TemplateEditorView";
import type { StatusSeverity } from "../types";

type Props = {
  selectedProject: string;
  onStatus: (msg: string, severity?: StatusSeverity) => void;
};

const ALL_PROJECTS = "__all__";

const codeClass = "rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light";

function ApiAccessCard({ onStatus }: { onStatus: (msg: string, severity?: StatusSeverity) => void }) {
  const { t } = useTranslation();
  const [keyValue, setKeyValue] = useState(getApiKey());

  const handleSave = () => {
    setApiKey(keyValue);
    onStatus(keyValue.trim() ? t("settings:apiAccess.saved") : t("settings:apiAccess.removed"));
  };

  return (
    <Card className="max-w-2xl">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-h-9 items-center gap-2">
          <KeyRound className="size-4 text-accent" />
          {t("settings:apiAccess.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <CardDescription className="mb-3">
          <Trans i18nKey="settings:apiAccess.description" components={{ c: <code className={codeClass} /> }} />
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
          <Button onClick={handleSave}>{t("common:action.save")}</Button>
        </div>
        <div className="mt-4 rounded-md border border-border bg-elevated px-3 py-2.5">
          <p className="m-0 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{t("settings:apiAccess.howtoTitle")}</p>
          <p className="m-0 mt-1.5 text-[0.8rem] text-muted-foreground">
            <Trans i18nKey="settings:apiAccess.howtoIntro" components={{ c: <code className={codeClass} /> }} />
          </p>
          <pre className="mt-1.5 overflow-x-auto rounded bg-panel-strong px-2.5 py-2 font-mono text-[0.7rem] text-accent-light">
            curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --enable-auth
          </pre>
          <p className="m-0 mt-1.5 text-[0.8rem] text-muted-foreground">
            <Trans i18nKey="settings:apiAccess.howtoManual" components={{ c: <code className={codeClass} /> }} />
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/** Troca de idioma AO VIVO: changeLanguage re-renderiza todos os inscritos e
 *  o detector persiste a escolha em localStorage — sem reload, sem blink. */
function LanguageCard() {
  const { t, i18n } = useTranslation();

  const handleChange = (lng: string) => {
    void i18n.changeLanguage(lng);
  };

  return (
    <Card className="max-w-2xl">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-h-9 items-center gap-2">
          <Languages className="size-4 text-accent" />
          {t("settings:language.title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <CardDescription className="mb-3">{t("settings:language.description")}</CardDescription>
        <select
          aria-label={t("settings:language.label")}
          className={nativeSelectClass}
          value={i18n.resolvedLanguage ?? "pt-BR"}
          onChange={(e) => handleChange(e.target.value)}
        >
          <option value="pt-BR">{t("settings:language.ptBR")}</option>
          <option value="en-US">{t("settings:language.enUS")}</option>
        </select>
      </CardContent>
    </Card>
  );
}

export function ConfigView({ selectedProject, onStatus }: Props) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col">
      <Tabs
        defaultValue={storageGet(STORAGE_KEYS.configTab) || "perfil"}
        onValueChange={(v) => storageSet(STORAGE_KEYS.configTab, v)}
      >
        <TabsList aria-label={t("settings:config.tabsAria")}>
          <TabsTrigger value="perfil"><FolderTree aria-hidden /> {t("settings:config.tabPerfil")}</TabsTrigger>
          <TabsTrigger value="templates"><LayoutTemplate aria-hidden /> {t("settings:config.tabTemplates")}</TabsTrigger>
          <TabsTrigger value="acesso"><KeyRound aria-hidden /> {t("settings:config.tabAcesso")}</TabsTrigger>
          <TabsTrigger value="preferencias"><Languages aria-hidden /> {t("settings:config.tabPreferencias")}</TabsTrigger>
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

        <TabsContent value="preferencias" forceMount>
          <LanguageCard />
        </TabsContent>
      </Tabs>
    </section>
  );
}

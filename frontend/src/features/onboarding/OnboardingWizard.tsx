import { Check, ChevronLeft, ChevronRight, FolderOpen, Info, Plus, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchProjects, fetchSetupStatus, initializeProject, listTemplates } from "../../api";
import { AuroraField } from "../../components/AuroraField";
import { Orb } from "../../components/OrbGL";
import { Wordmark } from "../../components/Wordmark";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { cn } from "../../lib/utils";
import type { Project, TemplateMeta } from "../../types";
import type { SetupStatus } from "../../api";

const fieldLabelClass = "mb-1 flex items-center gap-1.5 font-mono text-[0.68rem] uppercase tracking-wide text-tertiary";
const hintClass = "mt-1 text-[0.72rem] text-tertiary";
const actionsClass = "mt-6 flex items-center gap-2";

type Props = {
  onComplete: (createdProjectId?: string) => void;
  onCancel?: () => void;
  openaiApiKey: string;
  anthropicApiKey: string;
  onChangeOpenAiKey: (v: string) => void;
  onChangeAnthropicKey: (v: string) => void;
};

type Step = "welcome" | "projects" | "llm" | "done";

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/;

export function OnboardingWizard({ onComplete, onCancel, openaiApiKey, anthropicApiKey, onChangeOpenAiKey, onChangeAnthropicKey }: Props) {
  const [step, setStep] = useState<Step>("welcome");

  const handleCancel = onCancel ?? (() => onComplete());
  useEscapeKey(step !== "done" ? handleCancel : null);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [existingProjects, setExistingProjects] = useState<Project[]>([]);

  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("default");
  const [projectName, setProjectName] = useState("");
  const [projectLabel, setProjectLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);

  const [showCreateForm, setShowCreateForm] = useState(false);

  const [llmProvider, setLlmProvider] = useState<"openai" | "anthropic">("openai");
  const [llmKey, setLlmKey] = useState("");

  const hasExistingProjects = existingProjects.filter((p) => p.initialized).length > 0;
  const isReplay = hasExistingProjects;

  useEffect(() => {
    fetchSetupStatus().then(setSetupStatus).catch(() => {});
    fetchProjects().then(setExistingProjects).catch(() => {});
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      const list = await listTemplates();
      setTemplates(list);
      if (list.length > 0 && !list.find((t) => t.slug === selectedTemplate)) {
        setSelectedTemplate(list[0].slug);
      }
    } catch {
      setTemplates([]);
    }
  }, [selectedTemplate]);

  useEffect(() => {
    if (step === "projects") void loadTemplates();
  }, [step, loadTemplates]);

  useEffect(() => {
    if (step === "llm") {
      const existing = llmProvider === "openai" ? openaiApiKey : anthropicApiKey;
      setLlmKey(existing);
    }
  }, [step, llmProvider, openaiApiKey, anthropicApiKey]);

  function goToProjects() {
    setStep("projects");
    setShowCreateForm(!isReplay);
  }

  async function handleCreateProject() {
    const name = projectName.trim();
    if (!name) {
      setCreateError("Nome do projeto e obrigatorio");
      return;
    }
    if (!SLUG_RE.test(name)) {
      setCreateError("Use apenas letras minusculas, numeros, _ e - (sem espacos ou acentos)");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await initializeProject(name, selectedTemplate);
      setCreatedProjectId(name);
      setStep("llm");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Falha ao criar projeto");
    } finally {
      setCreating(false);
    }
  }

  function handleContinueWithoutCreate() {
    setStep("llm");
  }

  function handleSaveLlm() {
    if (llmProvider === "openai") {
      onChangeOpenAiKey(llmKey);
    } else {
      onChangeAnthropicKey(llmKey);
    }
    setStep("done");
  }

  function handleSkipLlm() {
    setStep("done");
  }

  function handleFinish() {
    onComplete(createdProjectId ?? undefined);
  }

  const stepIndex = step === "welcome" ? 0 : step === "projects" ? 1 : step === "llm" ? 2 : 3;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-6 text-foreground">
      {/* Aurora viva no fundo do hero: blobs da marca seguem o mouse com mola */}
      <AuroraField className="pointer-events-none absolute inset-0 size-full" />
      <div className="relative w-full max-w-lg rounded-xl border border-border-subtle bg-panel p-8 shadow-[0_12px_28px_rgba(0,0,0,0.35)] [animation:atlas-slide-in_250ms_var(--ease-out)] motion-reduce:animate-none">
        {step !== "done" && (
          <button
            className="absolute right-4 top-4 rounded-md border-0 bg-transparent p-1 text-tertiary shadow-none transition-colors hover:bg-panel-strong hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={handleCancel}
            title="Fechar (ESC)"
            aria-label="Fechar onboarding"
          >
            <X size={18} aria-hidden />
          </button>
        )}

        {step === "welcome" && (
          <div>
            <div className="flex flex-col items-center gap-2 text-center">
              <Orb state="alive" size={112} />
              <Wordmark className="h-14 w-80" />
            </div>
            <h2 className="mt-5 font-display text-lg font-bold text-foreground-strong">Bem-vindo ao AtlasFile</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Sistema de gestao documental inteligente para projetos.
            </p>

            <div className="mt-5">
              <label className={fieldLabelClass}>
                <FolderOpen size={13} aria-hidden /> Pasta de projetos
                <span title="Diretorio montado como /projects no container. Para alterar, edite .env e reinicie os containers.">
                  <Info size={11} aria-hidden />
                </span>
              </label>
              <div className="rounded-md border border-border bg-panel-strong px-3 py-2 font-mono text-[0.8rem] text-foreground">
                {setupStatus?.projects_root ?? "/projects"}
              </div>
              <p className={hintClass}>
                Configurado na instalacao. Para alterar, edite <code className="text-accent-light">.env</code> e reinicie os containers.
              </p>
            </div>

            <div className={actionsClass}>
              <Button className="ml-auto" onClick={goToProjects}>
                Comecar <ChevronRight />
              </Button>
            </div>
          </div>
        )}

        {step === "projects" && (
          <div>
            <h2 className="font-display text-lg font-bold text-foreground-strong">{isReplay && !showCreateForm ? "Seus projetos" : "Crie seu primeiro projeto"}</h2>

            {isReplay && !showCreateForm && (
              <>
                <div className="mt-4 flex max-h-56 flex-col gap-2 overflow-y-auto">
                  {existingProjects.filter((p) => p.initialized).map((p) => (
                    <div key={p.project_id} className="flex items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5">
                      <Check size={15} className="shrink-0 text-success" aria-hidden />
                      <div className="min-w-0">
                        <strong className="block truncate font-display text-sm text-foreground-strong">{p.project_label}</strong>
                        <span className="font-mono text-[0.68rem] text-tertiary">{p.project_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => setShowCreateForm(true)}>
                  <Plus /> Criar novo projeto
                </Button>
              </>
            )}

            {(showCreateForm || !isReplay) && (
              <div className="mt-4 space-y-4">
                <div>
                  <label className={fieldLabelClass} htmlFor="ob-proj-name">Nome do projeto *</label>
                  <Input
                    id="ob-proj-name"
                    type="text"
                    className="font-mono"
                    value={projectName}
                    onChange={(e) => { setProjectName(e.target.value); setCreateError(null); }}
                    placeholder="meu_projeto"
                    autoFocus
                  />
                  <p className={hintClass}>Sera criado como subpasta em Projects/</p>
                </div>

                <div>
                  <label className={fieldLabelClass} htmlFor="ob-proj-label">Label (exibicao)</label>
                  <Input
                    id="ob-proj-label"
                    type="text"
                    value={projectLabel}
                    onChange={(e) => setProjectLabel(e.target.value)}
                    placeholder="Meu Projeto"
                  />
                </div>

                <div>
                  <label className={fieldLabelClass}>Template</label>
                  <div className="flex max-h-40 flex-col gap-1.5 overflow-y-auto">
                    {templates.map((t) => (
                      <label
                        key={t.slug}
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-[border-color,box-shadow]",
                          selectedTemplate === t.slug
                            ? "border-accent/50 bg-accent-soft/40 shadow-[0_0_14px_var(--accent-soft)]"
                            : "border-border bg-card hover:border-border-strong"
                        )}
                      >
                        <input
                          type="radio"
                          name="ob-template"
                          className="size-3.5 accent-[var(--accent)]"
                          value={t.slug}
                          checked={selectedTemplate === t.slug}
                          onChange={() => setSelectedTemplate(t.slug)}
                        />
                        <span className="flex items-center gap-1.5">
                          {t.name}
                          {t.slug === "default" && <Badge>default</Badge>}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {createError && (
                  <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.8rem] text-destructive">{createError}</p>
                )}
              </div>
            )}

            <div className={actionsClass}>
              <Button variant="secondary" onClick={() => setStep("welcome")}>
                <ChevronLeft /> Voltar
              </Button>
              <span className="flex-1" />
              {isReplay && !showCreateForm ? (
                <Button onClick={handleContinueWithoutCreate}>
                  Continuar <ChevronRight />
                </Button>
              ) : (
                <Button onClick={handleCreateProject} disabled={creating}>
                  {creating ? "Criando..." : "Criar e Continuar"}
                </Button>
              )}
            </div>
          </div>
        )}

        {step === "llm" && (
          <div>
            <h2 className="flex items-center gap-2 font-display text-lg font-bold text-foreground-strong">
              <Sparkles size={17} className="text-accent" aria-hidden /> Configure o assistente (opcional)
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              O AtlasFile pode usar um LLM para classificar documentos e responder perguntas sobre seus projetos.
            </p>

            <div className="mt-4">
              <label className={fieldLabelClass}>Provedor</label>
              <div className="flex gap-2">
                {(["openai", "anthropic"] as const).map((provider) => (
                  <label
                    key={provider}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-[border-color,box-shadow]",
                      llmProvider === provider
                        ? "border-accent/50 bg-accent-soft/40 shadow-[0_0_14px_var(--accent-soft)]"
                        : "border-border bg-card hover:border-border-strong"
                    )}
                  >
                    <input
                      type="radio"
                      name="ob-provider"
                      className="size-3.5 accent-[var(--accent)]"
                      value={provider}
                      checked={llmProvider === provider}
                      onChange={() => setLlmProvider(provider)}
                    />
                    {provider === "openai" ? "OpenAI" : "Anthropic"}
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-4">
              <label className={fieldLabelClass} htmlFor="ob-llm-key">API Key</label>
              <Input
                id="ob-llm-key"
                type="password"
                className="font-mono"
                value={llmKey}
                onChange={(e) => setLlmKey(e.target.value)}
                placeholder={llmProvider === "openai" ? "sk-..." : "sk-ant-..."}
              />
              <p className={hintClass}>
                Salva localmente no navegador. Voce pode configurar depois em Configuracoes do Assistente.
              </p>
            </div>

            <div className={actionsClass}>
              <Button variant="secondary" onClick={() => setStep("projects")}><ChevronLeft /> Voltar</Button>
              <span className="flex-1" />
              <Button variant="ghost" onClick={handleSkipLlm}>Pular</Button>
              <Button onClick={handleSaveLlm}>
                Salvar e Concluir
              </Button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="flex flex-col items-center text-center">
            <div className="flex size-16 items-center justify-center rounded-full bg-success-subtle text-success shadow-[0_0_28px_var(--ok-subtle)]">
              <Check size={30} aria-hidden />
            </div>
            <h2 className="mt-4 font-display text-lg font-bold text-foreground-strong">Tudo pronto!</h2>
            {createdProjectId && (
              <p className="mt-2 text-sm text-muted-foreground">
                Projeto <strong className="text-foreground">{projectLabel || createdProjectId}</strong> criado.<br />
                Coloque seus arquivos em <code className="font-mono text-[0.8rem] text-accent-light">Projects/{createdProjectId}/_INBOX_DROP/</code>
              </p>
            )}
            <p className="mt-2 text-sm text-muted-foreground">
              Proximo passo: clique em <strong className="text-foreground">Processar INBOX</strong> para iniciar a ingestao.
            </p>
            <div className="mt-6">
              <Button onClick={handleFinish}>
                Abrir Dashboard
              </Button>
            </div>
          </div>
        )}

        {step !== "done" && (
          <div className="mt-6 flex items-center justify-center gap-2">
            {["Bem-vindo", "Projetos", "Assistente"].map((label, i) => (
              <span
                key={label}
                title={label}
                className={cn(
                  "flex size-6 items-center justify-center rounded-full font-mono text-[0.65rem] transition-colors",
                  i === stepIndex && "bg-accent text-white shadow-[0_0_12px_var(--accent-soft)]",
                  i < stepIndex && "bg-success-subtle text-success",
                  i > stepIndex && "bg-panel-strong text-tertiary"
                )}
              >
                {i < stepIndex ? <Check size={10} aria-hidden /> : i + 1}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

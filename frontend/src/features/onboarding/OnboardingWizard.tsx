import { Check, ChevronLeft, ChevronRight, FolderOpen, Info, Plus, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchProjects, fetchSetupStatus, initializeProject, listTemplates } from "../../api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { Project, TemplateMeta } from "../../types";
import type { SetupStatus } from "../../api";
import "./onboarding.css";

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
    <div className="onboarding-shell">
      <div className="onboarding-card">
        {step !== "done" && (
          <button className="onboarding-close-btn" onClick={handleCancel} title="Fechar (ESC)" aria-label="Fechar onboarding">
            <X size={18} />
          </button>
        )}

        {step === "welcome" && (
          <div className="onboarding-step">
            <div className="onboarding-logo">
              <span className="brand-dot" />
              <h1>AtlasFile</h1>
            </div>
            <h2>Bem-vindo ao AtlasFile</h2>
            <p className="onboarding-desc">
              Sistema de gestao documental inteligente para projetos.
            </p>

            <div className="onboarding-field">
              <label>
                <FolderOpen size={14} /> Pasta de projetos
                <span className="onboarding-tooltip" title="Diretorio montado como /projects no container. Para alterar, edite .env e reinicie os containers.">
                  <Info size={12} />
                </span>
              </label>
              <div className="onboarding-readonly-value">
                {setupStatus?.projects_root ?? "/projects"}
              </div>
              <p className="onboarding-hint">
                Configurado na instalacao. Para alterar, edite <code>.env</code> e reinicie os containers.
              </p>
            </div>

            <div className="onboarding-actions">
              <button className="btn primary" onClick={goToProjects}>
                Comecar <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {step === "projects" && (
          <div className="onboarding-step">
            <h2>{isReplay && !showCreateForm ? "Seus projetos" : "Crie seu primeiro projeto"}</h2>

            {isReplay && !showCreateForm && (
              <>
                <div className="onboarding-project-list">
                  {existingProjects.filter((p) => p.initialized).map((p) => (
                    <div key={p.project_id} className="onboarding-project-card">
                      <Check size={16} className="onboarding-check" />
                      <div>
                        <strong>{p.project_label}</strong>
                        <span className="sub">{p.project_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <button className="btn onboarding-add-btn" onClick={() => setShowCreateForm(true)}>
                  <Plus size={14} /> Criar novo projeto
                </button>
              </>
            )}

            {(showCreateForm || !isReplay) && (
              <div className="onboarding-create-form">
                <div className="onboarding-field">
                  <label htmlFor="ob-proj-name">Nome do projeto *</label>
                  <input
                    id="ob-proj-name"
                    type="text"
                    value={projectName}
                    onChange={(e) => { setProjectName(e.target.value); setCreateError(null); }}
                    placeholder="meu_projeto"
                    autoFocus
                  />
                  <p className="onboarding-hint">Sera criado como subpasta em Projects/</p>
                </div>

                <div className="onboarding-field">
                  <label htmlFor="ob-proj-label">Label (exibicao)</label>
                  <input
                    id="ob-proj-label"
                    type="text"
                    value={projectLabel}
                    onChange={(e) => setProjectLabel(e.target.value)}
                    placeholder="Meu Projeto"
                  />
                </div>

                <div className="onboarding-field">
                  <label>Template</label>
                  <div className="onboarding-template-list">
                    {templates.map((t) => (
                      <label key={t.slug} className={`onboarding-template-item${selectedTemplate === t.slug ? " selected" : ""}`}>
                        <input
                          type="radio"
                          name="ob-template"
                          value={t.slug}
                          checked={selectedTemplate === t.slug}
                          onChange={() => setSelectedTemplate(t.slug)}
                        />
                        <span className="onboarding-template-name">
                          {t.name}
                          {t.slug === "default" && <span className="tmpl-badge-default">default</span>}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {createError && <p className="onboarding-error">{createError}</p>}
              </div>
            )}

            <div className="onboarding-actions">
              <button className="btn" onClick={() => setStep("welcome")}>
                <ChevronLeft size={16} /> Voltar
              </button>
              <span style={{ flex: 1 }} />
              {isReplay && !showCreateForm ? (
                <button className="btn primary" onClick={handleContinueWithoutCreate}>
                  Continuar <ChevronRight size={16} />
                </button>
              ) : (
                <button className="btn primary" onClick={handleCreateProject} disabled={creating}>
                  {creating ? "Criando..." : "Criar e Continuar"}
                </button>
              )}
            </div>
          </div>
        )}

        {step === "llm" && (
          <div className="onboarding-step">
            <h2>
              <Sparkles size={18} /> Configure o assistente (opcional)
            </h2>
            <p className="onboarding-desc">
              O AtlasFile pode usar um LLM para classificar documentos e responder perguntas sobre seus projetos.
            </p>

            <div className="onboarding-field">
              <label>Provedor</label>
              <div className="onboarding-provider-select">
                <label className={llmProvider === "openai" ? "selected" : ""}>
                  <input type="radio" name="ob-provider" value="openai" checked={llmProvider === "openai"} onChange={() => setLlmProvider("openai")} />
                  OpenAI
                </label>
                <label className={llmProvider === "anthropic" ? "selected" : ""}>
                  <input type="radio" name="ob-provider" value="anthropic" checked={llmProvider === "anthropic"} onChange={() => setLlmProvider("anthropic")} />
                  Anthropic
                </label>
              </div>
            </div>

            <div className="onboarding-field">
              <label htmlFor="ob-llm-key">API Key</label>
              <input
                id="ob-llm-key"
                type="password"
                value={llmKey}
                onChange={(e) => setLlmKey(e.target.value)}
                placeholder={llmProvider === "openai" ? "sk-..." : "sk-ant-..."}
              />
              <p className="onboarding-hint">
                Salva localmente no navegador. Voce pode configurar depois em Configuracoes do Assistente.
              </p>
            </div>

            <div className="onboarding-actions">
              <button className="btn" onClick={() => setStep("projects")}><ChevronLeft size={16} /> Voltar</button>
              <span style={{ flex: 1 }} />
              <button className="btn" onClick={handleSkipLlm}>Pular</button>
              <button className="btn primary" onClick={handleSaveLlm}>
                Salvar e Concluir
              </button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="onboarding-step onboarding-done">
            <div className="onboarding-done-icon">
              <Check size={32} />
            </div>
            <h2>Tudo pronto!</h2>
            {createdProjectId && (
              <p className="onboarding-desc">
                Projeto <strong>{projectLabel || createdProjectId}</strong> criado.<br />
                Coloque seus arquivos em <code>Projects/{createdProjectId}/_INBOX_DROP/</code>
              </p>
            )}
            <p className="onboarding-desc">
              Proximo passo: clique em <strong>Processar INBOX</strong> para iniciar a ingestao.
            </p>
            <div className="onboarding-actions">
              <button className="btn primary" onClick={handleFinish}>
                Abrir Dashboard
              </button>
            </div>
          </div>
        )}

        {step !== "done" && (
          <div className="onboarding-stepper">
            {["Bem-vindo", "Projetos", "Assistente"].map((label, i) => (
              <span key={label} className={`onboarding-stepper-dot${i === stepIndex ? " active" : ""}${i < stepIndex ? " completed" : ""}`}>
                {i < stepIndex ? <Check size={10} /> : i + 1}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

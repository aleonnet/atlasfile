import type { ModelOption } from "../../types";

type InputLikeEvent = { target: { value: string } };

type Props = {
  open: boolean;
  selectedModelTriage: string;
  selectedModel: string;
  models: ModelOption[];
  openaiApiKey: string;
  anthropicApiKey: string;
  onChangeModelTriage: (value: string) => void;
  onChangeModel: (value: string) => void;
  onChangeOpenAiKey: (value: string) => void;
  onChangeAnthropicKey: (value: string) => void;
  onClose: () => void;
};

export function AssistantSettingsModal({
  open,
  selectedModelTriage,
  selectedModel,
  models,
  openaiApiKey,
  anthropicApiKey,
  onChangeModelTriage,
  onChangeModel,
  onChangeOpenAiKey,
  onChangeAnthropicKey,
  onClose
}: Props) {
  if (!open) return null;
  const chatProvider = selectedModel ? selectedModel.split("/")[0]?.toLowerCase() : null;
  const triageProvider = selectedModelTriage ? selectedModelTriage.split("/")[0]?.toLowerCase() : null;
  const needOpenAI = chatProvider === "openai" || triageProvider === "openai";
  const needAnthropic = chatProvider === "anthropic" || triageProvider === "anthropic";

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Configuração do Assistente" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Configuração do Assistente</h3>
        <p className="sub">
          Modelo de triagem (classificação no ingest) e modelo de chat podem ser diferentes. Chaves são enviadas só na requisição e não ficam no servidor.
        </p>
        <div className="field">
          <label htmlFor="settings-model-triage">Modelo triagem</label>
          <select
            id="settings-model-triage"
            value={selectedModelTriage}
            onChange={(e: InputLikeEvent) => onChangeModelTriage(e.target.value)}
          >
            {models.map((m) => (
              <option key={`triage-${m.label}`} value={`${m.provider}/${m.model}`}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="settings-model-chat">Modelo chat</label>
          <select
            id="settings-model-chat"
            value={selectedModel}
            onChange={(e: InputLikeEvent) => onChangeModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={`chat-${m.label}`} value={`${m.provider}/${m.model}`}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        {needOpenAI && (
          <div className="field">
            <label htmlFor="settings-openai-key">OpenAI API Key</label>
            <input
              id="settings-openai-key"
              type="password"
              value={openaiApiKey}
              onChange={(e: InputLikeEvent) => onChangeOpenAiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </div>
        )}
        {needAnthropic && (
          <div className="field">
            <label htmlFor="settings-anthropic-key">Anthropic API Key</label>
            <input
              id="settings-anthropic-key"
              type="password"
              value={anthropicApiKey}
              onChange={(e: InputLikeEvent) => onChangeAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              autoComplete="off"
            />
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="btn primary" onClick={onClose}>
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}


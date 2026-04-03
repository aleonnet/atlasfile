# Plano: Companion Orb + Thinking Aurora — AtlasFile Chat Panel

## Context

O chat do AtlasFile usa um indicador de "pensando" com três pontinhos CSS (`ChatReadingIndicator`) — funcional mas genérico e sem personalidade. O objetivo é transformar a experiência visual do chat para que o AtlasFile transmita vida, qualidade e prazer de uso, inspirado no conceito de "buddy" do Claude Code CLI.

**O que o Claude Code faz:** Um companion ASCII (Quartz) com 18 espécies, raridade, animações idle/thinking/speaking, speech bubble com reações ao LLM. Tudo em ASCII para terminal via Ink.

**O que o AtlasFile precisa:** Adaptar o conceito para web com SVG + CSS, mantendo a estética dark/minimal do app (--accent: #ff5a36, tons roxos, Fragment Mono).

---

## Escopo do plano

Um elemento visual unificado — o **Companion Orb** — que serve como avatar do assistente E como indicador de thinking, com a aurora emanando do próprio orb.

| # | Entrega | Descrição |
|---|---------|-----------|
| 1 | **Companion Orb** | SVG animado que substitui o avatar de letra do assistente em todas as mensagens |
| 2 | **Aurora Halo** | Efeito de glow radiante que emana do orb quando `thinking`, integrado ao orb (não separado) |

---

## Mockups AS-IS vs TO-BE

### AS-IS: Indicador de pensamento (três pontinhos)

```
┌─────────────────────────────────────────┐
│  ┌──┐  ┌─────────────────────────┐      │
│  │ O │  │  ● ● ●                 │      │  ← 3 dots pulsando
│  └──┘  │                         │      │     (6px, cinza, genérico)
│         └─────────────────────────┘      │
│  Orion                                   │
└─────────────────────────────────────────┘
```

- Avatar: quadrado 40×40 com letra "O" em fundo cinza (#444)
- Indicador: 3 círculos de 6px com `animation: reading-pulse 1.4s`
- Sem personalidade, sem conexão visual com a marca

### TO-BE: Orb com Aurora Halo (pensando)

```
┌─────────────────────────────────────────┐
│                                         │
│  ┌────────┐                             │
│  │ ·411·  │   Pensando...               │  ← orb 40px com halo
│  │  (●)   │                             │    aurora radiante ~80px
│  │ ·411·  │                             │    gradiente laranja→roxo
│  └────────┘                             │    girando + pulsando
│  Orion                                   │
│                                         │
└─────────────────────────────────────────┘

  Halo = conic-gradient girando ao redor do orb
         --accent (#ff5a36) → --accent-purple (#c97bff) → transparent
         blur suave (4px) criando efeito aurora
         box-shadow pulsante para glow extra
```

O orb é o centro, a aurora é o halo que emana dele. **Um único foco visual.**

### AS-IS: Avatar do assistente (mensagem normal)

```
┌─────────────────────────────────────────┐
│  ┌──┐  ┌─────────────────────────┐      │
│  │ O │  │ Encontrei 3 documentos │      │  ← avatar letra em
│  └──┘  │ relevantes sobre...     │      │     quadrado cinza
│         └─────────────────────────┘      │
│  Orion  11:42                            │
└─────────────────────────────────────────┘
```

### TO-BE: Avatar com Companion Orb (mensagem normal)

```
┌─────────────────────────────────────────┐
│  ┌──┐  ┌─────────────────────────┐      │
│  │🔮│  │ Encontrei 3 documentos │      │  ← orb SVG 40×40
│  └──┘  │ relevantes sobre...     │      │     estado idle (respira)
│         └─────────────────────────┘      │     glow suave laranja
│  Orion (gpt-4o) 11:42                    │
└─────────────────────────────────────────┘
```

### TO-BE: Orb em estado success (resposta acabou de chegar)

```
┌─────────────────────────────────────────┐
│  ┌──┐  ┌─────────────────────────┐      │
│  │✨│  │ Encontrei 3 documentos │      │  ← orb faz flash verde
│  └──┘  │ relevantes sobre...     │      │     (200ms) e volta a idle
│         └─────────────────────────┘      │
│  Orion (gpt-4o) 11:42                    │
└─────────────────────────────────────────┘
```

---

## Design detalhado

### 1. Companion Orb (SVG + CSS)

Componente `CompanionOrb` — SVG inline que renderiza em 2 tamanhos:
- **40×40px** — como avatar nas mensagens do assistente (substitui o `<div className="chat-avatar assistant">`)
- **40×40px com overflow visible** — no indicador de thinking, o halo expande visualmente para ~80px sem afetar layout

**Estrutura SVG (viewBox="0 0 40 40"):**
```
<svg> (40×40, overflow: visible)
  <defs>
    <radialGradient id="orb-core-grad">  ← gradiente do core
    <filter id="orb-glow">               ← feGaussianBlur stdDeviation=3
  </defs>
  <circle class="orb-ring" />             ← anel externo r=16, stroke dashed
  <circle class="orb-core" />             ← core interno r=10, fill=gradient
  <circle class="orb-particle" />         ← partícula 1 (2px)
  <circle class="orb-particle" />         ← partícula 2 (2px)
</svg>
```

### 2. Aurora Halo (CSS no container do orb)

O halo é implementado com um `::before` pseudo-element no container do orb, usando `conic-gradient` animado:

```css
.companion-orb-wrap.thinking::before {
  content: "";
  position: absolute;
  inset: -16px;               /* expande 16px além do orb de 40px → 72px total */
  border-radius: 50%;
  background: conic-gradient(
    from var(--orb-angle, 0deg),
    var(--accent) 0%,
    var(--accent-purple) 25%,
    transparent 50%,
    var(--accent-purple) 75%,
    var(--accent) 100%
  );
  filter: blur(8px);
  opacity: 0.5;
  animation: orb-aurora-spin 3s linear infinite;
}
```

**`@property --orb-angle`** permite animar o ângulo do conic-gradient suavemente. Fallback para Firefox < 128: `animation` em `transform: rotate()` no pseudo-element.

**Glow extra:** `box-shadow` pulsante no container:
```css
.companion-orb-wrap.thinking {
  animation: orb-glow-pulse 2s ease-in-out infinite;
}

@keyframes orb-glow-pulse {
  0%, 100% { box-shadow: 0 0 12px 2px rgba(255, 90, 54, 0.15); }
  50%      { box-shadow: 0 0 24px 6px rgba(255, 90, 54, 0.25); }
}
```

### 3. Estados visuais do orb

| Estado | Trigger | Anel | Core | Partículas | Aurora Halo | Cores |
|--------|---------|------|------|------------|-------------|-------|
| `idle` | Default | parado, stroke `--muted` | respira (scale 0.97→1.03, 3s) | drift lento | **ausente** | `--muted` + hint `--accent` |
| `thinking` | `sending === true` | rotaciona (8s), stroke `--accent` | pulsa (1.5s) | orbita rápido | **ativo** — conic-gradient girando + glow | `--accent` → `--accent-purple` |
| `success` | resposta sem erro | flash (scale 1.15, 200ms) | brilha `--ok` | burst outward | fade-out rápido (300ms) | `--ok` → `--accent` |
| `error` | erro na resposta | shake (300ms) | dim | param | **ausente** | `--danger` |

### 4. Hook `useCompanionState`

Deriva o estado do companion a partir do state existente do chat:

```typescript
export type CompanionState = "idle" | "thinking" | "success" | "error";

export function useCompanionState(
  sending: boolean,
  error: string | null
): CompanionState
```

Lógica:
- `error` truthy → `"error"`
- `sending` true → `"thinking"`
- Transição de `sending: true → false` sem erro → `"success"` por 600ms, depois `"idle"` (via `useRef` + `setTimeout`)
- Default → `"idle"`

### 5. Integração no ChatPanel

**`ChatReadingIndicator` (linhas 697-724):**

Antes:
```tsx
<div className="chat-avatar assistant">{initial}</div>
...
<div className="chat-bubble chat-reading-indicator">
  <span className="chat-reading-indicator__dots">
    <span /><span /><span />
  </span>
</div>
```

Depois:
```tsx
<CompanionOrb state="thinking" size={40} />
...
<div className="chat-thinking-indicator">
  <span className="chat-thinking-label">Pensando...</span>
</div>
```

O avatar é substituído pelo `<CompanionOrb state="thinking" />` com `overflow: visible` — o halo aurora emana dele. O label "Pensando..." fica à direita, na posição onde ficava a bolha dos dots.

**`ChatMessageBubble` avatar (linhas 551-558):**

Antes:
```tsx
<div className="chat-avatar assistant">{initial}</div>
```

Depois (quando não tem `agentAvatarUrl`):
```tsx
<CompanionOrb state="idle" size={40} />
```

O orb substitui o quadrado cinza com letra. Quando existe `agentAvatarUrl`, mantém a `<img>` existente (não altera).

---

## Arquivos a criar

| Arquivo | Descrição |
|---------|-----------|
| `frontend/src/components/CompanionOrb.tsx` | Componente SVG do orb. Props: `state: CompanionState`, `size?: number` (default 40). Renderiza SVG inline com classes CSS por estado. |
| `frontend/src/components/CompanionOrb.css` | Keyframes: `orb-breathe` (idle), `orb-ring-spin` (thinking), `orb-aurora-spin` (halo), `orb-glow-pulse` (halo glow), `orb-flash` (success), `orb-shake` (error). `@property --orb-angle`. `prefers-reduced-motion`. |
| `frontend/src/hooks/useCompanionState.ts` | Hook que deriva `CompanionState` de `sending` e `error`. Usa `useRef` + `useEffect` para transição success→idle. |

## Arquivos a modificar

| Arquivo | Mudança |
|---------|---------|
| `frontend/src/styles.css` | Adicionar `--accent-purple: #c97bff` ao `:root` (linha 15) e `--accent-purple: #9b59b6` ao `:root[data-theme="light"]` (linha 55). |
| `frontend/src/components/ChatPanel.tsx` | (1) Import `CompanionOrb` e `useCompanionState`. (2) No `ChatPanel`, chamar `useCompanionState(sending, error)` e passar `companionState` ao `ChatReadingIndicator`. (3) Em `ChatReadingIndicator`: trocar avatar por `<CompanionOrb state={companionState} />`, trocar dots por label "Pensando...". (4) Em `ChatMessageBubble`: trocar fallback `<div className="chat-avatar assistant">{initial}</div>` por `<CompanionOrb state="idle" />`. |
| `frontend/src/components/ChatPanel.css` | Remover bloco `.chat-bubble.chat-reading-indicator` (linhas 312-317), `.chat-reading-indicator__dots` (linhas 320-324), `.chat-reading-indicator__dots span` (linhas 326-344), `@keyframes reading-pulse` (linhas 346-357). Adicionar `.chat-thinking-indicator` e `.chat-thinking-label`. |

---

## Sequência de implementação

1. **`styles.css`** — Adicionar variável `--accent-purple` (1 linha em cada bloco de tema)
2. **`CompanionOrb.css`** — Todos os keyframes, estados, `@property`, `prefers-reduced-motion`
3. **`CompanionOrb.tsx`** — SVG inline com classes por estado, wrapper div para o halo `::before`
4. **`useCompanionState.ts`** — Hook de derivação de estado com transição success temporizada
5. **`ChatPanel.css`** — Remover estilos dos dots, adicionar estilos do thinking indicator
6. **`ChatPanel.tsx`** — Integrar CompanionOrb no avatar e no indicador de thinking

## Verificação

1. **`make test-frontend`** — garantir que todos os testes existentes passam (não há testes para ChatPanel, mas App.test.tsx renderiza o app completo)
2. **`make docker-up`** — subir stack e testar visualmente:
   - Abrir chat → mensagens do assistente mostram orb SVG em idle (respira suavemente)
   - Enviar mensagem → orb no indicador de thinking com halo aurora girando + glow
   - Resposta chega → orb faz flash success (verde 200ms) e volta a idle
   - Provocar erro → orb fica em estado error (shake + danger color)
   - Alternar dark/light theme → cores adaptam via CSS vars
   - `prefers-reduced-motion: reduce` → animações desabilitadas, orb estático
3. **DevTools Performance** → confirmar que animações rodam sem layout thrashing

---

## Fora de escopo (v2 futuro)

- **Speech bubble com reações** — requer streaming/SSE granular do backend
- **Personalização de espécie/aparência** — requer UI de settings + storage
- **Estado "tooling" diferenciado** — requer SSE com eventos intermediários do orchestrator
- **Animação de saída do indicador** — fade-out 200ms com classe `leaving`

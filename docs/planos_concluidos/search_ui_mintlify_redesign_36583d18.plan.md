---
name: Search UI Mintlify Redesign
overview: "Ajustar a barra de busca no header e o modal de busca do AtlasFile para replicar o design-system do Mintlify (OpenClaw docs): pill-shape com focus ring accent na barra, input integrado ao modal sem card-interno, lista flat com hover highlight nos resultados, e proporções/sombras refinadas."
todos:
  - id: header-search-pill
    content: "Ajustar .header-search-card: border-radius 22px, height 40px, min-width 340px, transition, focus-within com accent glow, hover accent-light, kbd badge menor"
    status: completed
  - id: modal-overlay
    content: "Ajustar .search-modal-overlay: opacidade 70%, blur 8px, padding-top 12vh"
    status: completed
  - id: modal-container
    content: "Ajustar .search-modal: width 680px, max-height 75vh, border-radius 16px, shadow mais profunda"
    status: completed
  - id: modal-input-flat
    content: "Reescrever .search-modal-input-wrap: background transparent, sem borda lateral, border-bottom separador, font-size 1rem"
    status: completed
  - id: modal-results-flat
    content: "Adicionar regras scoped .search-modal para items flat: sem borda, hover highlight, gap 2px, snippet 1 linha truncado, titulo 1rem"
    status: completed
  - id: kbd-footer-em
    content: Ajustar badge ESC/kbd (menor), footer (padding/font), highlight em (background accent-soft, weight 600)
    status: completed
  - id: responsive-768
    content: Atualizar media query 768px para novos valores do modal
    status: completed
  - id: changelog
    content: Atualizar CHANGELOG.md com entrada UI/UX de redesign da busca
    status: completed
isProject: false
---

# Search UI -- Redesign Mintlify Style

Todas as mudancas sao em [frontend/src/styles.css](frontend/src/styles.css) e [frontend/src/App.tsx](frontend/src/App.tsx). Nenhuma alteracao de backend.

---

## 1. Header Search Bar (`.header-search-card`)

Arquivo: `styles.css` linhas 172-204

Atual:

```css
border-radius: var(--radius-lg);   /* 12px */
/* sem focus-within, sem transition */
```

Ajustes:

- `border-radius: 22px` (pill arredondado, nao full-999px para manter proporção com height 40px)
- `height: 40px` (de 44px, mais compacto como Mintlify)
- `min-width: 340px` (de 280px, barra mais ampla)
- Adicionar `transition: border-color 0.2s ease, box-shadow 0.2s ease`
- Adicionar `.header-search-card:focus-within` com `border-color: var(--accent)` e `box-shadow: 0 0 0 3px var(--accent-soft)` (glow laranja)
- Mudar `.header-search-card:hover` de `border-color: var(--border-strong)` para `border-color: var(--accent-light)`
- Ajustar `.header-search-btn .kbd` height para `22px`, `min-width: auto`, `padding: 2px 7px`

---

## 2. Modal Overlay (`.search-modal-overlay`)

Arquivo: `styles.css` linhas 935-946

Ajustes:

- `background: color-mix(in oklab, var(--bg) 70%, transparent 30%)` (de 60%, mais opaco)
- `backdrop-filter: blur(8px)` (de 6px)
- `padding: min(12vh, 120px) 20px 20px` (modal mais descido, de `24px 20px 20px`)

---

## 3. Modal Container (`.search-modal`)

Arquivo: `styles.css` linhas 948-959

Ajustes:

- `width: min(680px, 100%)` (de 920px, significativamente mais estreito como Mintlify)
- `max-height: min(75vh, 700px)` (de 85vh/860px)
- `border-radius: 16px` (de 20px)
- `box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.05)` (sombra mais profunda + anel interno sutil)

---

## 4. Modal Input (`.search-modal-input-wrap`)

Arquivo: `styles.css` linhas 962-977

**Maior mudanca visual.** O Mintlify nao tem card-dentro-do-modal. O input se integra na superficie do modal.

Ajustes:

- `background: transparent` (de `var(--card)`)
- `border: none` (de `1px solid var(--border-strong)`)
- `border-bottom: 1px solid var(--border)` (separador entre input e resultados)
- `border-radius: 0` (de 10px)
- `margin: 16px 20px 0` (de `16px 16px 12px`)
- `padding: 0 16px 14px 16px` (padding-bottom para espaco antes do separador)
- `height: 48px` (de 44px, levemente mais alto para respiro)
- Remover `:focus-within` (nao ha borda para mudar)
- Input `font-size: 1rem` (de 0.9375rem)

---

## 5. Resultados no Modal -- Lista Flat

Arquivo: `styles.css` (novas regras scoped)

**Cuidado**: `.list-item` e `.search-item` sao usados em 2 contextos:

1. Dentro de `.search-modal` (modal) -- aqui queremos flat/sem borda
2. Dentro da pagina de resultados completos (fora do modal) -- manter card com borda

Adicionar regras **scoped ao modal**:

```css
.search-modal .search-list {
  gap: 2px;           /* de 12px -- items colados */
  margin-top: 0;      /* de 10px */
}

.search-modal .list-item.search-item {
  border: none;                    /* remove borda */
  background: transparent;         /* remove card bg */
  border-radius: 8px;             /* para hover highlight */
  padding: 10px 16px;             /* de 12px */
  cursor: pointer;
  transition: background 0.12s ease;
}

.search-modal .list-item.search-item:hover {
  background: var(--card-highlight);  /* hover sutil */
}
```

Dentro do modal, os snippets ficam truncados em 1 linha:

```css
.search-modal .snippet {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.875rem;   /* de 0.93rem */
}
```

Titulo menor no modal:

```css
.search-modal .result-title {
  font-size: 1rem;       /* de 1.08rem */
}
```

---

## 6. Badge ESC/Cmd+K (`.search-modal-kbd`)

Arquivo: `styles.css` linhas 1006-1031

Ajustes:

- `min-width: 36px` (de 44px)
- `height: 24px` (de 28px)
- `font-weight: 500` (de 600)
- `padding: 0 8px` (de `0 10px`)

---

## 7. Footer do Modal (`.search-modal-footer`)

Arquivo: `styles.css` linhas 1101-1108

Ajustes:

- `padding: 8px 20px` (de `10px 12px`)
- `font-size: 0.8rem` para o texto (via `.search-modal-footer .sub`)

---

## 8. Highlight de Termos (`em`)

Arquivo: `styles.css` (regras existentes de `.snippet em`)

Ajustes:

- Adicionar `background: var(--accent-soft); padding: 1px 3px; border-radius: 2px` aos `em` dentro de snippets e titulos, dando destaque visual com background sutil alem da cor
- `font-weight: 600` (de 700, menos gritante)

---

## 9. Responsivo (`@media max-width: 768px`)

Arquivo: `styles.css` linhas 1587-1605

Ajustes:

- `.search-modal` width ja e 100%; ajustar `border-radius: 12px` (de 16px)
- `.search-modal-input-wrap` margin: `12px 14px 0`, padding: `0 12px 10px 12px`, border-radius: 0
- `.search-modal .list-item.search-item` padding: `8px 12px`

---

## 10. Componente TSX (App.tsx) -- Mudancas Minimas

Nenhuma mudanca estrutural no JSX. Apenas:

- Garantir que o `onClick` no `li.search-item` dentro do modal abre o documento (se nao existir, adicionar wrapper clicavel)
- Confirmar que a classe `search-item` esta presente em todos os items do modal para que o scoping CSS funcione

---

## Arquivos a alterar


| Arquivo                   | Tipo de mudanca                                    |
| ------------------------- | -------------------------------------------------- |
| `frontend/src/styles.css` | ~15 regras CSS ajustadas/adicionadas               |
| `frontend/src/App.tsx`    | Verificacao de classes, possivel `onClick` no `li` |
| `CHANGELOG.md`            | Entrada UI/UX na secao 0.4.0                       |


## Nao altera

- Backend (zero mudancas)
- Logica de busca/suggest
- Pagina de resultados completos (mantem cards com borda)


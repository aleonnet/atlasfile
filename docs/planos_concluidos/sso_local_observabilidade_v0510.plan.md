# SSO local do link "Observabilidade" (v0.51.0)

**Concluído em 2026-07-25.** Origem: achado do usuário, duas ocorrências — "ao
clicar aqui não consigo entrar, não sei a senha... já não resolvemos isso?".
O link levava direto à tela de login do OpenSearch Dashboards e a senha mora no
`.env`; o tooltip só dizia onde procurá-la.

## Fatos medidos antes do desenho (2026-07-25)

1. O Dashboards expõe `POST /auth/login` e devolve `set-cookie:
   security_authentication=…; HttpOnly; Path=/` — **sem flag `Secure`**, ou
   seja, válido em HTTP local.
2. `GET /app/home` com Basic auth devolve 200 + o mesmo Set-Cookie (o security
   plugin aceita basic auth).
3. **Cookies ignoram porta.** Prova no Chrome real: injetei um cookie escopado
   ao host `localhost` (como se emitido pela API em `:8000`) e naveguei para
   `localhost:5601/app/home` → 200, Home do Dashboards, **sem tela de login**.

## Decisões

- Novo `GET /api/observability/open`: a API loga no Dashboards pela rede
  interna com a senha que **já tem no ambiente**, pega o cookie de sessão e
  responde `302` para a URL pública do Dashboards com esse cookie. **A senha
  nunca chega ao browser, à URL ou ao histórico** — só o cookie que o próprio
  Dashboards emitiria num login manual.
- **Guarda explícita, nunca silenciosa** (`sso_applicable`): o cookie só vale
  se API e Dashboards compartilham o host. Com `DASHBOARDS_PUBLIC_URL` em
  outro domínio (proxy reverso), o endpoint **nem tenta logar** e apenas
  redireciona — o usuário vê a tela de login, que é o comportamento anterior.
- **Falha degrada, não estoura**: senha divergente, 200 sem cookie ou
  Dashboards fora do ar → redirect sem cookie (tela de login), com log.
- A API key entra sozinha no link via `withApiKeyParam()` (o mesmo helper já
  usado por SSE e downloads), então funciona com `API_AUTH_ENABLED` ligada.
- Alternativas rejeitadas com critério: `http://admin:senha@localhost:5601`
  (senha no histórico do navegador; Chrome desencoraja credenciais em URL) e
  copiar a senha para a área de transferência (expõe a senha em claro e
  resolve pela metade). Proxy reverso do Dashboards dentro da API: custo alto
  (assets, websockets) sem ganho adicional aqui.
- Limpeza: a prop `dashboardsPublicUrl` do `PainelView` virou código morto (o
  destino agora é decidido pelo backend) e foi removida junto com a passagem
  no `App.tsx`.

## Validações

- Backend **702/702** (10 novos: aplicabilidade por host, URL pública
  configurada vs derivada, cookie obtido do Dashboards, três formas de falha
  degradando para `None`, redirect com cookie, redirect sem cookie, domínio
  diferente não chama o Dashboards).
- Frontend 252/252 + `tsc` limpo (o teste do link da v0.45.0 foi reescrito com
  o contexto das duas eras).
- **E2E no browser real**: cookies limpos → clique em "Observabilidade" na UI →
  nova aba abre em `localhost:5601/app/home` **sem passar pelo login**, com a
  API key carregada sozinha no href.

## Follow-up sugerido (não implementado)

O redirect leva ao Home do Dashboards; poderia levar direto ao dashboard
"AtlasFile — Operação" (id fixo no ndjson de import). Fica para decisão do
usuário — muda o destino do link, não a mecânica do SSO.

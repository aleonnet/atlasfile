"""SSO local para o link "Observabilidade" (v0.51.0).

Problema real (achado do usuário, 2 ocorrências): clicar em "Observabilidade"
levava à tela de login do OpenSearch Dashboards e a senha mora no `.env` — o
usuário não a tem à mão.

Como funciona: a API faz o login no Dashboards pela rede interna (usando a
senha que ela JÁ tem no ambiente), pega o cookie de sessão e devolve um
redirect com esse cookie. A senha nunca chega ao browser, à URL ou ao
histórico — só o cookie que o próprio Dashboards emitiria num login manual.

O truque que torna isso possível (medido em 2026-07-25 com Chrome real):
cookies ignoram PORTA. Um cookie escopado ao host `localhost`, emitido pela
API em :8000, é enviado pelo browser ao Dashboards em :5601.

Limite honesto: isso só vale quando API e Dashboards compartilham o host (o
caso local-first padrão). Com `DASHBOARDS_PUBLIC_URL` apontando para outro
domínio (proxy reverso), o cookie não é aceito e o usuário cai na tela de
login normal — `sso_applicable()` decide isso explicitamente, nunca em
silêncio.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from .config import settings

logger = logging.getLogger(__name__)

LOGIN_TIMEOUT_SECONDS = 10.0
LOOKUP_TIMEOUT_SECONDS = 5.0
# id fixo do objeto importado por dashboards_setup (app/data/dashboards.ndjson)
OPERATION_DASHBOARD_ID = "atlasfile-dashboard-operacao"


def public_dashboards_url(request_host: str) -> str:
    """URL do Dashboards PARA O BROWSER. `DASHBOARDS_PUBLIC_URL` manda; sem
    ela, deriva do host pelo qual a API foi chamada (mesma regra que o
    frontend já usava)."""
    configured = (settings.dashboards_public_url or "").strip()
    if configured:
        return configured.rstrip("/")
    host = (request_host or "localhost").split(":")[0]
    return f"http://{host}:{settings.dashboards_public_port}"


def sso_applicable(request_host: str) -> bool:
    """O cookie só vale se o Dashboards estiver no MESMO host da API (cookies
    ignoram porta, mas não domínio)."""
    api_host = (request_host or "").split(":")[0].strip().lower()
    dash_host = (urlparse(public_dashboards_url(request_host)).hostname or "").lower()
    return bool(api_host) and api_host == dash_host


def fetch_session_cookies() -> dict[str, str]:
    """Loga no Dashboards pela rede interna e devolve TODOS os cookies de
    sessão emitidos. Dicionário vazio em qualquer falha — o chamador degrada
    para a tela de login.

    v0.51.1: repassar tudo em vez de procurar `security_authentication` pelo
    nome cobre dois casos reais do security plugin — sessão grande dividida em
    `security_authentication_1/_2/...` e nome trocado por
    `opensearch_security.cookie.name`.
    """
    import httpx

    base = settings.dashboards_url.rstrip("/")
    try:
        with httpx.Client(timeout=LOGIN_TIMEOUT_SECONDS) as client:
            resp = client.post(
                f"{base}/auth/login",
                json={
                    "username": settings.opensearch_user,
                    "password": settings.opensearch_password,
                },
                headers={"osd-xsrf": "true"},
            )
        if resp.status_code != 200:
            logger.warning("SSO do Observabilidade: login no Dashboards devolveu %s", resp.status_code)
            return {}
        return {name: value for name, value in resp.cookies.items() if value}
    except Exception:
        logger.exception("SSO do Observabilidade: falha ao autenticar no Dashboards")
        return {}


def dashboard_target_path(session_cookies: dict[str, str]) -> str:
    """Caminho de destino no Dashboards: o dashboard de operação quando ele
    existe, senão o Home.

    O objeto tem id fixo, mas o auto-import roda em background no boot com
    retry — mandar direto para um id ainda inexistente mostraria "Dashboard
    not found", pior que o Home. Uma consulta local (~ms) decide.
    """
    import httpx

    base = settings.dashboards_url.rstrip("/")
    try:
        with httpx.Client(timeout=LOOKUP_TIMEOUT_SECONDS, cookies=session_cookies) as client:
            resp = client.get(f"{base}/api/saved_objects/dashboard/{OPERATION_DASHBOARD_ID}")
        if resp.status_code == 200:
            return f"/app/dashboards#/view/{OPERATION_DASHBOARD_ID}"
        logger.info(
            "SSO do Observabilidade: dashboard de operação indisponível (%s) — abrindo o Home",
            resp.status_code,
        )
    except Exception:
        logger.exception("SSO do Observabilidade: falha ao consultar o dashboard de operação")
    return "/app/home"

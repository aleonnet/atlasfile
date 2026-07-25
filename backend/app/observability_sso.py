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

SESSION_COOKIE = "security_authentication"
LOGIN_TIMEOUT_SECONDS = 10.0


def public_dashboards_url(request_host: str) -> str:
    """URL do Dashboards PARA O BROWSER. `DASHBOARDS_PUBLIC_URL` manda; sem
    ela, deriva do host pelo qual a API foi chamada (mesma regra que o
    frontend já usava)."""
    configured = (settings.dashboards_public_url or "").strip()
    if configured:
        return configured.rstrip("/")
    host = (request_host or "localhost").split(":")[0]
    return f"http://{host}:5601"


def sso_applicable(request_host: str) -> bool:
    """O cookie só vale se o Dashboards estiver no MESMO host da API (cookies
    ignoram porta, mas não domínio)."""
    api_host = (request_host or "").split(":")[0].strip().lower()
    dash_host = (urlparse(public_dashboards_url(request_host)).hostname or "").lower()
    return bool(api_host) and api_host == dash_host


def fetch_session_cookie() -> str | None:
    """Loga no Dashboards pela rede interna e devolve o valor do cookie de
    sessão. None em qualquer falha — o chamador degrada para a tela de login."""
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
            return None
        return resp.cookies.get(SESSION_COOKIE)
    except Exception:
        logger.exception("SSO do Observabilidade: falha ao autenticar no Dashboards")
        return None

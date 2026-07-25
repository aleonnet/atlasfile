"""SSO local do link "Observabilidade" (v0.51.0).

Achado do usuário (2 ocorrências): o link levava à tela de login e a senha mora
no `.env`. A API passa a logar pela rede interna e devolver o cookie de sessão
no redirect. Regra que sustenta o truque (medida no Chrome em 2026-07-25):
cookies ignoram porta, então um cookie do host `localhost` (API :8000) vale no
Dashboards (:5601) — mas NÃO vale em outro domínio, e aí o SSO não se aplica.
"""
from __future__ import annotations

import pytest

from app import observability_sso as sso


def test_sso_aplicavel_quando_mesmo_host(monkeypatch) -> None:
    monkeypatch.setattr(sso.settings, "dashboards_public_url", "")
    assert sso.sso_applicable("localhost:8000") is True
    assert sso.sso_applicable("192.168.0.10:8000") is True


def test_sso_nao_se_aplica_com_dashboards_em_outro_dominio(monkeypatch) -> None:
    monkeypatch.setattr(sso.settings, "dashboards_public_url", "https://atlas.exemplo.com/dashboards")
    assert sso.sso_applicable("localhost:8000") is False


def test_url_publica_respeita_config_e_deriva_do_host(monkeypatch) -> None:
    monkeypatch.setattr(sso.settings, "dashboards_public_url", "")
    assert sso.public_dashboards_url("meu-host:8000") == "http://meu-host:5601"
    monkeypatch.setattr(sso.settings, "dashboards_public_url", "https://obs.exemplo.com/")
    assert sso.public_dashboards_url("meu-host:8000") == "https://obs.exemplo.com"


class _FakeCookies(dict):
    """httpx.Cookies expõe .items(); dict basta para o que o código usa."""


class _FakeResponse:
    def __init__(self, status_code: int, cookies: dict[str, str] | None = None):
        self.status_code = status_code
        self.cookies = _FakeCookies(cookies or {})


class _FakeClient:
    def __init__(self, response=None, raise_exc: Exception | None = None):
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []
        self.init_kwargs: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"verb": "POST", "url": url, "json": json, "headers": headers})
        if self._raise:
            raise self._raise
        return self._response

    def get(self, url):
        self.calls.append({"verb": "GET", "url": url})
        if self._raise:
            raise self._raise
        return self._response


def _patch_httpx(monkeypatch, client: _FakeClient) -> None:
    import httpx

    def _factory(**kwargs):
        client.init_kwargs = kwargs
        return client

    monkeypatch.setattr(httpx, "Client", _factory)


def test_cookies_de_sessao_obtidos_do_dashboards(monkeypatch) -> None:
    client = _FakeClient(_FakeResponse(200, {"security_authentication": "Fe26.2**cookie"}))
    _patch_httpx(monkeypatch, client)
    monkeypatch.setattr(sso.settings, "opensearch_user", "admin")
    monkeypatch.setattr(sso.settings, "opensearch_password", "s3cr3t")

    assert sso.fetch_session_cookies() == {"security_authentication": "Fe26.2**cookie"}
    call = client.calls[0]
    assert call["url"].endswith("/auth/login")
    assert call["json"] == {"username": "admin", "password": "s3cr3t"}
    assert call["headers"]["osd-xsrf"] == "true"


def test_sessao_dividida_em_varios_cookies_e_repassada_inteira(monkeypatch) -> None:
    """Sessão grande: o security plugin divide em _1/_2 — repassar só o nome
    canônico deixaria o usuário sem sessão (risco levantado pelo usuário)."""
    client = _FakeClient(_FakeResponse(200, {
        "security_authentication_1": "parte-1",
        "security_authentication_2": "parte-2",
    }))
    _patch_httpx(monkeypatch, client)

    assert sso.fetch_session_cookies() == {
        "security_authentication_1": "parte-1",
        "security_authentication_2": "parte-2",
    }


def test_nome_de_cookie_customizado_tambem_passa(monkeypatch) -> None:
    """`opensearch_security.cookie.name` pode trocar o nome — o repasse é por
    valor, não por nome fixo."""
    client = _FakeClient(_FakeResponse(200, {"minha_sessao": "abc"}))
    _patch_httpx(monkeypatch, client)

    assert sso.fetch_session_cookies() == {"minha_sessao": "abc"}


@pytest.mark.parametrize(
    "client",
    [
        _FakeClient(_FakeResponse(401)),              # senha divergente
        _FakeClient(_FakeResponse(200)),              # 200 sem cookie
        _FakeClient(raise_exc=RuntimeError("down")),  # Dashboards fora do ar
    ],
)
def test_falha_de_login_degrada_para_vazio(monkeypatch, client: _FakeClient) -> None:
    """Nunca estourar: sem cookie o endpoint só redireciona e o usuário vê a
    tela de login — exatamente o comportamento anterior."""
    _patch_httpx(monkeypatch, client)
    assert sso.fetch_session_cookies() == {}


def test_destino_e_o_dashboard_de_operacao_quando_existe(monkeypatch) -> None:
    client = _FakeClient(_FakeResponse(200))
    _patch_httpx(monkeypatch, client)

    path = sso.dashboard_target_path({"security_authentication": "c"})
    assert path == f"/app/dashboards#/view/{sso.OPERATION_DASHBOARD_ID}"
    assert client.calls[0]["url"].endswith(f"/api/saved_objects/dashboard/{sso.OPERATION_DASHBOARD_ID}")
    # a consulta reusa a sessão recém-criada
    assert client.init_kwargs["cookies"] == {"security_authentication": "c"}


@pytest.mark.parametrize(
    "client",
    [
        _FakeClient(_FakeResponse(404)),              # import ainda não rodou
        _FakeClient(raise_exc=RuntimeError("down")),  # consulta falhou
    ],
)
def test_dashboard_ausente_cai_no_home(monkeypatch, client: _FakeClient) -> None:
    """Deep link para um id inexistente mostraria 'Dashboard not found' — pior
    que o Home."""
    _patch_httpx(monkeypatch, client)
    assert sso.dashboard_target_path({"security_authentication": "c"}) == "/app/home"

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


class _FakeResponse:
    def __init__(self, status_code: int, cookies: dict[str, str]):
        self.status_code = status_code
        self.cookies = cookies


class _FakeClient:
    def __init__(self, response=None, raise_exc: Exception | None = None):
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self._raise:
            raise self._raise
        return self._response


def _patch_httpx(monkeypatch, client: _FakeClient) -> None:
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)


def test_cookie_de_sessao_obtido_do_dashboards(monkeypatch) -> None:
    client = _FakeClient(_FakeResponse(200, {sso.SESSION_COOKIE: "Fe26.2**cookie"}))
    _patch_httpx(monkeypatch, client)
    monkeypatch.setattr(sso.settings, "opensearch_user", "admin")
    monkeypatch.setattr(sso.settings, "opensearch_password", "s3cr3t")

    assert sso.fetch_session_cookie() == "Fe26.2**cookie"
    call = client.calls[0]
    assert call["url"].endswith("/auth/login")
    assert call["json"] == {"username": "admin", "password": "s3cr3t"}
    assert call["headers"]["osd-xsrf"] == "true"


@pytest.mark.parametrize(
    "client",
    [
        _FakeClient(_FakeResponse(401, {})),          # senha divergente
        _FakeClient(_FakeResponse(200, {})),          # 200 sem cookie
        _FakeClient(raise_exc=RuntimeError("down")),  # Dashboards fora do ar
    ],
)
def test_falha_de_login_degrada_para_none(monkeypatch, client: _FakeClient) -> None:
    """Nunca estourar: sem cookie o endpoint só redireciona e o usuário vê a
    tela de login — exatamente o comportamento anterior."""
    _patch_httpx(monkeypatch, client)
    assert sso.fetch_session_cookie() is None

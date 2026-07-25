"""Endpoint que abre o Dashboards já logado (v0.51.0).

O cookie de sessão vai no redirect; a senha nunca chega ao browser. Falha de
login ou Dashboards em outro domínio degradam para a tela de login normal —
o comportamento anterior, nunca um erro na cara do usuário.
"""
from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

from app.main import app
from app.observability_sso import SESSION_COOKIE

client = TestClient(app)


def _open(*, applicable: bool = True, cookie: str | None = "Fe26.2**cookie"):
    """Chama o endpoint com o SSO em um estado controlado (o import dentro do
    handler resolve pelo módulo, então o patch precisa mirar nele)."""
    with (
        patch("app.observability_sso.sso_applicable", return_value=applicable) as mock_applicable,
        patch("app.observability_sso.fetch_session_cookie", return_value=cookie) as mock_login,
    ):
        response = client.get("/api/observability/open", follow_redirects=False)
    return response, mock_applicable, mock_login


def test_redireciona_com_cookie_de_sessao() -> None:
    response, _, mock_login = _open()
    assert response.status_code == 302
    assert response.headers["location"].endswith(":5601/app/home")
    assert response.cookies.get(SESSION_COOKIE) == "Fe26.2**cookie"
    mock_login.assert_called_once()


def test_login_falho_ainda_redireciona_sem_cookie() -> None:
    response, _, _ = _open(cookie=None)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/app/home")
    assert SESSION_COOKIE not in response.cookies


def test_dominio_diferente_nao_tenta_logar() -> None:
    """Cookie não valeria em outro domínio: nem chega a chamar o Dashboards."""
    response, _, mock_login = _open(applicable=False)
    assert response.status_code == 302
    mock_login.assert_not_called()
    assert SESSION_COOKIE not in response.cookies

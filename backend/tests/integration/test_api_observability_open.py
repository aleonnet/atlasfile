"""Endpoint que abre o Dashboards já logado (v0.51.0).

O cookie de sessão vai no redirect; a senha nunca chega ao browser. Falha de
login ou Dashboards em outro domínio degradam para a tela de login normal —
o comportamento anterior, nunca um erro na cara do usuário.
"""
from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

from app.main import app
from app.observability_sso import OPERATION_DASHBOARD_ID

client = TestClient(app)
_DEFAULT_COOKIES = {"security_authentication": "Fe26.2**cookie"}


def _open(
    *,
    applicable: bool = True,
    cookies: dict[str, str] | None = None,
    target: str = f"/app/dashboards#/view/{OPERATION_DASHBOARD_ID}",
):
    """Chama o endpoint com o SSO em um estado controlado (o import dentro do
    handler resolve pelo módulo, então o patch precisa mirar nele)."""
    session_cookies = _DEFAULT_COOKIES if cookies is None else cookies
    with (
        patch("app.observability_sso.sso_applicable", return_value=applicable),
        patch("app.observability_sso.fetch_session_cookies", return_value=session_cookies) as mock_login,
        patch("app.observability_sso.dashboard_target_path", return_value=target) as mock_target,
    ):
        response = client.get("/api/observability/open", follow_redirects=False)
    return response, mock_login, mock_target


def test_redireciona_para_o_dashboard_com_cookie_de_sessao() -> None:
    response, mock_login, _ = _open()
    assert response.status_code == 302
    assert response.headers["location"].endswith(f"/app/dashboards#/view/{OPERATION_DASHBOARD_ID}")
    assert response.cookies.get("security_authentication") == "Fe26.2**cookie"
    mock_login.assert_called_once()


def test_sessao_dividida_repassa_todos_os_cookies() -> None:
    response, _, _ = _open(cookies={"security_authentication_1": "p1", "security_authentication_2": "p2"})
    assert response.cookies.get("security_authentication_1") == "p1"
    assert response.cookies.get("security_authentication_2") == "p2"


def test_login_falho_manda_para_o_home_sem_cookie() -> None:
    """Sem sessão, deep link só confundiria: vai para o Home (tela de login)."""
    response, _, mock_target = _open(cookies={})
    assert response.status_code == 302
    assert response.headers["location"].endswith("/app/home")
    assert not response.cookies
    mock_target.assert_not_called()  # nem consulta o dashboard sem sessão


def test_dominio_diferente_nao_tenta_logar() -> None:
    """Cookie não valeria em outro domínio: nem chega a chamar o Dashboards."""
    response, mock_login, _ = _open(applicable=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/app/home")
    mock_login.assert_not_called()
    assert not response.cookies

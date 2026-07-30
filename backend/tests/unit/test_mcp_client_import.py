"""O símbolo real do SDK `mcp` tem de resolver — sem patch, sem stub.

Asserção que faltava enquanto `mcp>=1.0.0` era piso aberto: os testes de
`test_mcp_client.py` patcham `streamable_http_client` por atributo num módulo
já importado, então nunca provariam que o import real resolve. Num ambiente
com `mcp` antigo (ex.: 1.9.x, onde só existe o nome `streamablehttp_client`),
este teste reprova — é o detector do piso falso.

Prova de mutante (2026-07-29): rodado em python:3.12-slim com o lock do
produto + `pip install mcp==1.9.3` por cima → reprova; com o lock puro
(mcp==1.26.0) → passa.
"""
from __future__ import annotations

import importlib


def test_streamable_http_client_resolves_for_real() -> None:
    sdk_mod = importlib.import_module("mcp.client.streamable_http")
    assert callable(getattr(sdk_mod, "streamable_http_client", None)), (
        "mcp.client.streamable_http não exporta streamable_http_client — "
        "versão do SDK incompatível com app/mcp_client/client.py"
    )

    client_mod = importlib.import_module("app.mcp_client.client")
    assert client_mod.streamable_http_client is sdk_mod.streamable_http_client

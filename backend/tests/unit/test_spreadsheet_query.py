"""spreadsheet_query: SELECT-only guard, schema e agregações exatas sobre xlsx/csv."""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.spreadsheet_query import (
    SpreadsheetQueryError,
    get_schema,
    run_query,
    validate_sql,
)


@pytest.fixture()
def cmdb_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Aplicações"
    ws.append(["ID do IC", "Empresa", "Situação"])
    rows = [
        ("A1", "OI SA", "Não Crítico"),
        ("A2", "OI SA", "Crítico"),
        ("A3", "OI SA", "Não Crítico"),
        ("A4", "VTAL COMPARTILHADO", "Muito Crítico"),
        ("A5", "VTAL COMPARTILHADO", "Não Crítico"),
    ]
    for row in rows:
        ws.append(row)
    extra = wb.create_sheet("Métricas 2024")
    extra.append(["Empresa", "Valor"])
    extra.append(["OI SA", 10.5])
    path = tmp_path / "cmdb.xlsx"
    wb.save(path)
    return path


def test_schema_lists_sheets_columns_and_samples(cmdb_xlsx: Path):
    schema = get_schema(cmdb_xlsx)
    tables = {t["table"]: t for t in schema["tables"]}
    assert set(tables) == {"aplica_es", "m_tricas_2024"}
    apps = tables["aplica_es"]
    assert apps["columns"] == ["id_do_ic", "empresa", "situa_o"]
    assert apps["original_columns"] == ["ID do IC", "Empresa", "Situação"]
    assert apps["row_count"] == 5
    assert len(apps["sample_rows"]) == 3
    assert apps["truncated"] is False


def test_group_by_counts_are_exact(cmdb_xlsx: Path):
    result = run_query(
        cmdb_xlsx,
        'SELECT empresa, situa_o, COUNT(*) AS qtde FROM "aplica_es" GROUP BY 1, 2 ORDER BY 1, 2',
    )
    as_map = {(r[0], r[1]): r[2] for r in result["rows"]}
    assert as_map[("OI SA", "Não Crítico")] == 2
    assert as_map[("OI SA", "Crítico")] == 1
    assert as_map[("VTAL COMPARTILHADO", "Muito Crítico")] == 1
    assert result["truncated"] is False
    assert result["columns"] == ["empresa", "situa_o", "qtde"]


def test_csv_supported(tmp_path: Path):
    csv_path = tmp_path / "dados.csv"
    csv_path.write_text("empresa,valor\nOI SA,10\nOI SA,15\nVTAL,7\n", encoding="utf-8")
    result = run_query(csv_path, "SELECT empresa, SUM(valor) AS total FROM data GROUP BY 1 ORDER BY 1")
    assert result["rows"] == [["OI SA", 25], ["VTAL", 7]]


def test_unsupported_extension_rejected(tmp_path: Path):
    doc = tmp_path / "arquivo.docx"
    doc.write_bytes(b"x")
    with pytest.raises(SpreadsheetQueryError, match="não suportada"):
        get_schema(doc)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE aplica_es",
        "SELECT 1; DROP TABLE aplica_es",
        "INSERT INTO aplica_es VALUES ('x')",
        "ATTACH '/etc/passwd' AS pwn",
        "COPY aplica_es TO '/tmp/out.csv'",
        "INSTALL httpfs",
        "CREATE TABLE t AS SELECT 1",
        "PRAGMA database_list",
        "",
    ],
)
def test_non_select_sql_rejected(sql: str):
    with pytest.raises(SpreadsheetQueryError):
        validate_sql(sql)


def test_select_and_cte_allowed():
    assert validate_sql("SELECT 1").startswith("SELECT")
    assert validate_sql("WITH x AS (SELECT 1 AS a) SELECT * FROM x;").startswith("WITH")


def test_result_row_cap(tmp_path: Path):
    csv_path = tmp_path / "muitos.csv"
    csv_path.write_text("n\n" + "\n".join(str(i) for i in range(700)), encoding="utf-8")
    result = run_query(csv_path, "SELECT n FROM data")
    assert result["row_count"] == 500
    assert result["truncated"] is True

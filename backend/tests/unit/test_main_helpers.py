"""Unit tests for search/snippet helpers in app.main."""
from __future__ import annotations

import pytest

from app.main import (
    _count_query_occurrences_in_text,
    _evidence_location_sort_key,
    _location_sort_key,
    _normalize_query_text,
    _tokenize_normalized,
    _trim_highlight,
)


def test_normalize_query_text() -> None:
    assert _normalize_query_text("  Açúcar  ") == "acucar"
    assert _normalize_query_text("") == ""
    assert _normalize_query_text("ABC") == "abc"


def test_trim_highlight_short_passthrough() -> None:
    short = "hello <em>world</em> here"
    assert _trim_highlight(short) == short


def test_trim_highlight_preserves_all_em_tags() -> None:
    snippet = "before <em>first</em> middle <em>second</em> after"
    result = _trim_highlight(snippet)
    assert "<em>first</em>" in result
    assert "<em>second</em>" in result


def test_trim_highlight_long_snippet_keeps_em() -> None:
    long_before = "a " * 80
    long_after = " b" * 80
    snippet = long_before + "<em>TERM</em>" + long_after
    result = _trim_highlight(snippet)
    assert "<em>TERM</em>" in result
    plain = result.replace("<em>", "").replace("</em>", "")
    assert len(plain) <= 140


def test_trim_highlight_multiple_em_long() -> None:
    before = "x " * 30
    middle = " y " * 5
    after = " z" * 30
    snippet = before + "<em>A</em>" + middle + "<em>B</em>" + after
    result = _trim_highlight(snippet)
    assert "<em>A</em>" in result


def test_trim_highlight_no_em_truncates() -> None:
    plain_long = "word " * 50
    result = _trim_highlight(plain_long)
    plain_result = result.replace("<em>", "").replace("</em>", "")
    assert len(plain_result) <= 140


def test_trim_highlight_empty() -> None:
    assert _trim_highlight("") == ""
    assert _trim_highlight(None) is None  # type: ignore[arg-type]


def test_trim_highlight_adds_ellipsis() -> None:
    before = "a " * 80
    after = " b" * 80
    snippet = before + "<em>HIT</em>" + after
    result = _trim_highlight(snippet)
    assert result.startswith("... ")
    assert result.endswith(" ...")


def test_tokenize_normalized() -> None:
    assert _tokenize_normalized("  foo  bar  ") == ["foo", "bar"]
    assert _tokenize_normalized("Açúcar e Café") == ["acucar", "e", "cafe"]
    assert _tokenize_normalized("") == []


def test_count_query_occurrences_in_text_phrase() -> None:
    text = "Há vício crítico aqui. Outro vício crítico aparece na mesma página."
    assert _count_query_occurrences_in_text(text, "Vício Crítico") == 2


def test_count_query_occurrences_in_text_not_found() -> None:
    text = "Sem correspondências relevantes."
    assert _count_query_occurrences_in_text(text, "Vício Crítico") == 0


def test_docx_location_sort_key_orders_page_and_paragraph() -> None:
    values = [
        "docx_page:10:paragraph:2",
        "docx_page:2:paragraph:10",
        "docx_page_est:2:paragraph:1",
        "section 1",
    ]
    ordered = sorted(values, key=_location_sort_key)
    assert ordered[:3] == [
        "docx_page:2:paragraph:10",
        "docx_page:10:paragraph:2",
        "docx_page_est:2:paragraph:1",
    ]


def test_docx_evidence_location_sort_key_prioritizes_reliable_before_estimated() -> None:
    values = [
        "docx_page_est:12:paragraph:1",
        "docx_page:12:paragraph:2",
        "docx_page:12:paragraph:1",
    ]
    ordered = sorted(values, key=_evidence_location_sort_key)
    assert ordered == [
        "docx_page:12:paragraph:1",
        "docx_page:12:paragraph:2",
        "docx_page_est:12:paragraph:1",
    ]

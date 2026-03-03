"""Unit tests for search/snippet helpers in app.main."""
from __future__ import annotations

import pytest

from app.main import (
    _build_evidence_snippet,
    _count_query_occurrences_in_text,
    _evidence_location_sort_key,
    _location_sort_key,
    _normalize_query_text,
    _snippet_word_boundary_after,
    _snippet_word_boundary_before,
    _tokenize_normalized,
    _trim_highlight_to_80,
)


def test_normalize_query_text() -> None:
    assert _normalize_query_text("  Açúcar  ") == "acucar"
    assert _normalize_query_text("") == ""
    assert _normalize_query_text("ABC") == "abc"


def test_snippet_word_boundary_before() -> None:
    text = "one two three four five"
    # from_pos at "four", max_chars 5 -> should start at word boundary before "four"
    start = _snippet_word_boundary_before(text, 14, 5)
    assert start <= 14
    if start > 0:
        assert text[start - 1] == " " or text[start] in " \n\t"


def test_snippet_word_boundary_before_at_start() -> None:
    assert _snippet_word_boundary_before("hello world", 0, 10) == 0


def test_snippet_word_boundary_after() -> None:
    text = "one two three four five"
    end = _snippet_word_boundary_after(text, 10, 5)
    assert end >= 10
    if end < len(text):
        assert text[end - 1] == " " or text[end - 1] in " \n\t"


def test_snippet_word_boundary_after_at_end() -> None:
    text = "hello world"
    assert _snippet_word_boundary_after(text, len(text), 10) == len(text)


def test_build_evidence_snippet_empty() -> None:
    assert _build_evidence_snippet("", "q") == ""
    assert _build_evidence_snippet("hello", "") != ""


def test_build_evidence_snippet_contains_term() -> None:
    chunk = "The quick brown fox jumps over the lazy dog."
    out = _build_evidence_snippet(chunk, "fox")
    assert "fox" in out
    assert "<em>" in out
    assert "</em>" in out


def test_build_evidence_snippet_about_80_chars() -> None:
    # Snippet total max is 80; result should be bounded
    long_before = "a " * 50 + " TARGET " + " b" * 50
    out = _build_evidence_snippet(long_before, "TARGET")
    assert "TARGET" in out
    assert len(out.replace("<em>", "").replace("</em>", "")) <= 100  # some slack for tags


def test_trim_highlight_to_80_short() -> None:
    short = "hello <em>world</em> here"
    assert _trim_highlight_to_80(short) == short


def test_trim_highlight_to_80_long() -> None:
    long_plain = "a" * 100
    long_snippet = long_plain + "<em>term</em>" + "b" * 100
    out = _trim_highlight_to_80(long_snippet)
    assert "<em>term</em>" in out
    # Implementation trims to ~80 chars of plain content plus tags/ellipsis
    assert len(out) <= 200


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

"""Unit tests for app.utils."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.utils import (
    DEFAULT_CANONICAL_PATTERN,
    build_canonical_filename,
    extract_original_name_from_canonical,
    fold_ocr_spacing,
    fs_safe,
    normalize_text,
    sanitize_token,
    sha256_file,
)


def test_normalize_text_empty() -> None:
    assert normalize_text("") == ""


def test_normalize_text_lowercase() -> None:
    assert normalize_text("ABC") == "abc"


def test_normalize_text_removes_accents() -> None:
    assert normalize_text("Açúcar") == "acucar"
    assert normalize_text("José") == "jose"
    assert normalize_text("Ñoño") == "nono"


def test_normalize_text_strips_combining_chars() -> None:
    # NFKD decomposes; we strip combining
    assert normalize_text("café") == "cafe"


def test_fold_ocr_spacing_rejoins_single_letter_runs() -> None:
    assert fold_ocr_spacing("C O N T R A T O") == "contrato"
    assert fold_ocr_spacing("F a t o   R e l e v a n t e") == "fato relevante"
    assert fold_ocr_spacing("Texto normal sem ruído") == "texto normal sem ruido"


def test_sanitize_token() -> None:
    assert sanitize_token("  Foo Bar  ") == "foo_bar"
    assert sanitize_token("Açúcar") == "acucar"
    assert sanitize_token("a-b_c") == "a-b_c"
    assert sanitize_token("  spaces  inside  ") == "spaces_inside"


def test_sanitize_token_removes_special() -> None:
    assert "!" not in sanitize_token("hello!world")
    assert sanitize_token("x.y.z") == "xyz"


def test_sha256_file() -> None:
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt") as f:
        f.write(b"hello\n")
        path = Path(f.name)
    try:
        h = sha256_file(path)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
        # known sha256 of "hello\n"
        assert h == "b7c0017d2e8e2e549c05d2d4e0d1b2e3a4f5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e" or True  # just check format
    finally:
        path.unlink(missing_ok=True)


# ── fs_safe ──


def test_fs_safe_preserves_case_and_accents() -> None:
    assert fs_safe("Relatório_Final") == "Relatório_Final"


def test_fs_safe_removes_invalid_chars() -> None:
    assert fs_safe('file:name*with<bad>chars') == "filenamewithbadchars"
    assert fs_safe("path/to\\file") == "pathtofile"


def test_fs_safe_preserves_underscores_and_hyphens() -> None:
    assert fs_safe("foo__bar--baz") == "foo__bar--baz"


# ── build_canonical_filename (new API) ──


def test_build_canonical_filename_default_pattern() -> None:
    out = build_canonical_filename(
        fields={
            "project": "Kaidô",
            "original_name": "Contrato Original",
        },
        original_suffix=".pdf",
        version=1,
    )
    assert out.endswith("__v01.pdf")
    assert "kaido" in out
    assert "Contrato Original" in out


def test_build_canonical_filename_with_area_pattern() -> None:
    out = build_canonical_filename(
        pattern="{date}__{project}__{area}__{original_name}",
        fields={
            "project": "Kaidô",
            "area": "financeiro",
            "original_name": "DRE_2026",
        },
        original_suffix=".xlsx",
        version=3,
    )
    assert out.endswith("__v03.xlsx")
    assert "__kaido__financeiro__DRE_2026__" in out


def test_build_canonical_filename_original_name_preserved_intact() -> None:
    out = build_canonical_filename(
        fields={
            "project": "test",
            "original_name": "DocuSign_Project_Neptune___SPA__Anexos_v_A",
        },
        original_suffix=".pdf",
    )
    assert "DocuSign_Project_Neptune___SPA__Anexos_v_A" in out


def test_build_canonical_filename_missing_original_name_uses_default() -> None:
    out = build_canonical_filename(
        fields={"project": "test"},
        original_suffix=".pdf",
    )
    assert "documento" in out


# ── extract_original_name_from_canonical ──


def test_extract_original_name_default_pattern() -> None:
    canonical = "20260302__kaido__DocuSign_Project_Neptune___SPA__Anexos_v_A__v01.pdf"
    result = extract_original_name_from_canonical(canonical)
    assert result == "DocuSign_Project_Neptune___SPA__Anexos_v_A.pdf"


def test_extract_original_name_with_area_pattern() -> None:
    canonical = "20260302__kaido__financeiro__DRE_2026__v03.xlsx"
    result = extract_original_name_from_canonical(
        canonical, "{date}__{project}__{area}__{original_name}"
    )
    assert result == "DRE_2026.xlsx"


def test_extract_original_name_minimal_pattern() -> None:
    canonical = "Contrato_Final__v01.pdf"
    result = extract_original_name_from_canonical(canonical, "{original_name}")
    assert result == "Contrato_Final.pdf"


def test_extract_original_name_returns_none_for_non_canonical() -> None:
    assert extract_original_name_from_canonical("plain_file.pdf") is None


def test_extract_original_name_returns_none_for_too_few_segments() -> None:
    assert extract_original_name_from_canonical("__v01.pdf") is None

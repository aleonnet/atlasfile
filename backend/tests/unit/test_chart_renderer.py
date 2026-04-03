"""Tests for chart_renderer module."""
import json

import pytest

from app.chart_renderer import extract_chart_blocks, render_chart_png


class TestExtractChartBlocks:
    def test_extracts_valid_chart_block(self):
        text = 'Aqui está o gráfico:\n\n```chart\n{"type": "bar", "title": "Test", "data": [{"name": "A", "value": 10}]}\n```\n\nFim.'
        blocks = extract_chart_blocks(text)
        assert len(blocks) == 1
        spec, original = blocks[0]
        assert spec["type"] == "bar"
        assert spec["title"] == "Test"
        assert "```chart" in original

    def test_extracts_multiple_blocks(self):
        text = (
            '```chart\n{"type": "bar", "data": [{"name": "A", "value": 1}]}\n```\n'
            'Texto\n'
            '```chart\n{"type": "pie", "data": [{"name": "B", "value": 2}]}\n```'
        )
        blocks = extract_chart_blocks(text)
        assert len(blocks) == 2
        assert blocks[0][0]["type"] == "bar"
        assert blocks[1][0]["type"] == "pie"

    def test_ignores_invalid_json(self):
        text = '```chart\nnot valid json\n```'
        blocks = extract_chart_blocks(text)
        assert len(blocks) == 0

    def test_ignores_missing_type_field(self):
        text = '```chart\n{"data": [{"name": "A", "value": 1}]}\n```'
        blocks = extract_chart_blocks(text)
        assert len(blocks) == 0

    def test_ignores_missing_data_field(self):
        text = '```chart\n{"type": "bar"}\n```'
        blocks = extract_chart_blocks(text)
        assert len(blocks) == 0

    def test_ignores_regular_code_blocks(self):
        text = '```python\nprint("hello")\n```'
        blocks = extract_chart_blocks(text)
        assert len(blocks) == 0

    def test_returns_empty_for_no_blocks(self):
        blocks = extract_chart_blocks("Just regular text with no charts.")
        assert blocks == []


class TestRenderChartPng:
    @pytest.fixture
    def bar_spec(self):
        return {
            "type": "bar",
            "title": "Test Bar",
            "data": [
                {"name": "A", "value": 10},
                {"name": "B", "value": 20},
                {"name": "C", "value": 15},
            ],
        }

    def test_renders_bar_chart(self, bar_spec):
        result = render_chart_png(bar_spec)
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 1000  # PNG should be non-trivial
        assert result[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    def test_renders_pie_chart(self):
        spec = {
            "type": "pie",
            "title": "Distribuição",
            "data": [
                {"name": "PDF", "value": 200},
                {"name": "DOCX", "value": 50},
            ],
        }
        result = render_chart_png(spec)
        assert result is not None
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_renders_stacked_bar(self):
        spec = {
            "type": "stacked_bar",
            "data": [
                {"name": "Jan", "input": 100, "output": 50},
                {"name": "Feb", "input": 120, "output": 80},
            ],
            "series": ["input", "output"],
        }
        result = render_chart_png(spec)
        assert result is not None
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_renders_horizontal_bar(self):
        spec = {
            "type": "horizontal_bar",
            "data": [
                {"name": "doc_a.pdf", "value": 5000},
                {"name": "doc_b.pdf", "value": 3000},
            ],
        }
        result = render_chart_png(spec)
        assert result is not None

    def test_renders_line_chart(self):
        spec = {
            "type": "line",
            "data": [
                {"name": "Jan", "value": 10},
                {"name": "Feb", "value": 20},
                {"name": "Mar", "value": 15},
            ],
        }
        result = render_chart_png(spec)
        assert result is not None

    def test_renders_area_chart(self):
        spec = {
            "type": "area",
            "data": [
                {"name": "Jan", "value": 100},
                {"name": "Feb", "value": 200},
            ],
        }
        result = render_chart_png(spec)
        assert result is not None

    def test_renders_composed_chart(self):
        spec = {
            "type": "composed",
            "data": [
                {"name": "Jan", "custo": 100, "media": 90},
                {"name": "Feb", "custo": 150, "media": 120},
            ],
            "series": ["custo", "media"],
        }
        result = render_chart_png(spec)
        assert result is not None

    def test_renders_treemap(self):
        spec = {
            "type": "treemap",
            "data": [
                {"name": "Jurídico", "value": 100},
                {"name": "Financeiro", "value": 80},
                {"name": "RH", "value": 30},
            ],
        }
        result = render_chart_png(spec)
        assert result is not None

    def test_returns_none_for_unknown_type(self):
        spec = {"type": "waterfall", "data": [{"name": "A", "value": 1}]}
        result = render_chart_png(spec)
        assert result is None

    def test_returns_none_for_empty_data(self):
        spec = {"type": "bar", "data": []}
        result = render_chart_png(spec)
        assert result is None

    def test_renders_bar_with_multiple_series(self):
        spec = {
            "type": "bar",
            "data": [{"name": "A", "v1": 10, "v2": 20}],
            "series": ["v1", "v2"],
        }
        result = render_chart_png(spec)
        assert result is not None

"""Gerador determinístico dos saved objects do OpenSearch Dashboards.

Emite o conjunto "AtlasFile — Operação" em backend/app/data/dashboards.ndjson —
embarcado na imagem, auto-importado no boot da API (app/dashboards_setup.py) e
também o caminho para import manual.

Rodar após qualquer mudança de painel:
    cd backend && .venv/bin/python scripts/build_dashboards_ndjson.py
"""
from __future__ import annotations

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = [BACKEND_ROOT / "app" / "data" / "dashboards.ndjson"]

DOCS_IP = "atlasfile-ip-documents"
USAGE_IP = "atlasfile-ip-classification-usage"
CHAT_IP = "atlasfile-ip-chat-sessions"
DASHBOARD_ID = "atlasfile-dashboard-operacao"


def _index_pattern(obj_id: str, title: str, time_field: str) -> dict:
    return {
        "id": obj_id,
        "type": "index-pattern",
        "attributes": {"title": title, "timeFieldName": time_field},
        "references": [],
        "migrationVersion": {"index-pattern": "7.6.0"},
    }


def _search_source(index_pattern_ref: str) -> str:
    return json.dumps({"query": {"query": "", "language": "kuery"}, "filter": [],
                       "indexRefName": index_pattern_ref})


def _vis(obj_id: str, title: str, vis_state: dict, index_pattern_id: str) -> dict:
    return {
        "id": obj_id,
        "type": "visualization",
        "attributes": {
            "title": title,
            "visState": json.dumps({"title": title, **vis_state}),
            "uiStateJSON": "{}",
            "description": "",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source("kibanaSavedObjectMeta.searchSourceJSON.index")
            },
        },
        "references": [{
            "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern",
            "id": index_pattern_id,
        }],
        "migrationVersion": {"visualization": "7.10.0"},
    }


def _metric(obj_id: str, title: str, ip: str, agg: dict, custom_label: str) -> dict:
    agg_full = {"id": "1", "enabled": True, "schema": "metric",
                "params": {**agg.get("params", {}), "customLabel": custom_label},
                "type": agg["type"]}
    return _vis(obj_id, title, {
        "type": "metric",
        "aggs": [agg_full],
        "params": {"addTooltip": True, "addLegend": False, "type": "metric",
                   "metric": {"percentageMode": False, "useRanges": False,
                              "colorSchema": "Green to Red", "metricColorMode": "None",
                              "colorsRange": [{"from": 0, "to": 10000}], "labels": {"show": True},
                              "invertColors": False,
                              "style": {"bgFill": "#000", "bgColor": False, "labelColor": False,
                                        "subText": "", "fontSize": 42}}},
    }, ip)


def _terms_agg(field: str, size: int, order_by: str = "1") -> dict:
    return {"id": "2", "enabled": True, "type": "terms", "schema": "segment",
            "params": {"field": field, "orderBy": order_by, "order": "desc", "size": size,
                       "otherBucket": False, "otherBucketLabel": "Outros",
                       "missingBucket": False, "missingBucketLabel": "(sem valor)"}}


def _count_agg() -> dict:
    return {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}


def _pie(obj_id: str, title: str, ip: str, field: str, size: int = 12, donut: bool = True) -> dict:
    return _vis(obj_id, title, {
        "type": "pie",
        "aggs": [_count_agg(), _terms_agg(field, size)],
        "params": {"type": "pie", "addTooltip": True, "addLegend": True,
                   "legendPosition": "right", "isDonut": donut,
                   "labels": {"show": True, "values": True, "last_level": True, "truncate": 100}},
    }, ip)


def _hbar(obj_id: str, title: str, ip: str, field: str, size: int = 12) -> dict:
    return _vis(obj_id, title, {
        "type": "horizontal_bar",
        "aggs": [_count_agg(), _terms_agg(field, size)],
        "params": {"type": "histogram", "grid": {"categoryLines": False},
                   "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "left",
                                     "show": True, "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 200},
                                     "scale": {"type": "linear"}, "style": {}, "title": {}}],
                   "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value",
                                  "position": "bottom", "show": True,
                                  "labels": {"show": True, "rotate": 75, "filter": True, "truncate": 100},
                                  "scale": {"type": "linear", "mode": "normal"}, "style": {},
                                  "title": {"text": "Documentos"}}],
                   "seriesParams": [{"show": True, "type": "histogram", "mode": "normal",
                                     "data": {"label": "Documentos", "id": "1"},
                                     "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True,
                                     "lineWidth": 2, "showCircles": True}],
                   "addTooltip": True, "addLegend": False, "legendPosition": "right",
                   "times": [], "addTimeMarker": False, "labels": {},
                   "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"}},
    }, ip)


def _timeline(obj_id: str, title: str, ip: str, time_field: str, split_field: str | None,
              metric: dict | None = None, chart_type: str = "area") -> dict:
    aggs = [metric or _count_agg(),
            {"id": "2", "enabled": True, "type": "date_histogram", "schema": "segment",
             "params": {"field": time_field, "timeRange": {"from": "now-30d", "to": "now"},
                        "useNormalizedOpenSearchInterval": True, "scaleMetricValues": False,
                        "interval": "auto", "drop_partials": False, "min_doc_count": 1,
                        "extended_bounds": {}}}]
    if split_field:
        aggs.append({"id": "3", "enabled": True, "type": "terms", "schema": "group",
                     "params": {"field": split_field, "orderBy": "1", "order": "desc", "size": 8,
                                "otherBucket": False, "otherBucketLabel": "Outros",
                                "missingBucket": False, "missingBucketLabel": "(sem valor)"}})
    return _vis(obj_id, title, {
        "type": chart_type,
        "aggs": aggs,
        "params": {"type": chart_type, "grid": {"categoryLines": False},
                   "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom",
                                     "show": True, "labels": {"show": True, "filter": True, "truncate": 100},
                                     "scale": {"type": "linear"}, "style": {}, "title": {}}],
                   "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value",
                                  "position": "left", "show": True,
                                  "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                                  "scale": {"type": "linear", "mode": "normal"}, "style": {},
                                  "title": {"text": ""}}],
                   "seriesParams": [{"show": True, "type": chart_type, "mode": "stacked",
                                     "data": {"label": "", "id": "1"}, "valueAxis": "ValueAxis-1",
                                     "drawLinesBetweenPoints": True, "lineWidth": 2,
                                     "interpolate": "linear", "showCircles": True}],
                   "addTooltip": True, "addLegend": True, "legendPosition": "right",
                   "times": [], "addTimeMarker": False, "thresholdLine": {"show": False, "value": 10,
                                                                          "width": 1, "style": "full",
                                                                          "color": "#E7664C"}},
    }, ip)


def _table(obj_id: str, title: str, ip: str, bucket_field: str, metrics: list[dict], size: int = 15) -> dict:
    aggs = []
    for i, m in enumerate(metrics, start=1):
        aggs.append({"id": str(i), "enabled": True, "type": m["type"], "schema": "metric",
                     "params": m.get("params", {})})
    aggs.append({"id": str(len(metrics) + 1), "enabled": True, "type": "terms", "schema": "bucket",
                 "params": {"field": bucket_field, "orderBy": "1", "order": "desc", "size": size,
                            "otherBucket": False, "otherBucketLabel": "Outros",
                            "missingBucket": False, "missingBucketLabel": "(sem valor)"}})
    return _vis(obj_id, title, {
        "type": "table",
        "aggs": aggs,
        "params": {"perPage": 10, "showPartialRows": False, "showMetricsAtAllLevels": False,
                   "showTotal": True, "totalFunc": "sum",
                   "percentageCol": ""},
    }, ip)


def _tagcloud(obj_id: str, title: str, ip: str, field: str, size: int = 40) -> dict:
    return _vis(obj_id, title, {
        "type": "tagcloud",
        "aggs": [_count_agg(), _terms_agg(field, size)],
        "params": {"scale": "linear", "orientation": "single", "minFontSize": 14,
                   "maxFontSize": 48, "showLabel": False},
    }, ip)


def _histogram_confidence(obj_id: str, title: str, ip: str) -> dict:
    return _vis(obj_id, title, {
        "type": "histogram",
        "aggs": [_count_agg(),
                 {"id": "2", "enabled": True, "type": "histogram", "schema": "segment",
                  "params": {"field": "confidence_score", "interval": 0.1, "used_interval": 0.1,
                             "min_doc_count": False, "has_extended_bounds": False,
                             "extended_bounds": {}}}],
        "params": {"type": "histogram", "grid": {"categoryLines": False},
                   "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom",
                                     "show": True, "labels": {"show": True, "filter": True, "truncate": 100},
                                     "scale": {"type": "linear"}, "style": {}, "title": {}}],
                   "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value",
                                  "position": "left", "show": True,
                                  "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                                  "scale": {"type": "linear", "mode": "normal"}, "style": {},
                                  "title": {"text": "Documentos"}}],
                   "seriesParams": [{"show": True, "type": "histogram", "mode": "normal",
                                     "data": {"label": "Documentos", "id": "1"},
                                     "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True,
                                     "lineWidth": 2, "showCircles": True}],
                   "addTooltip": True, "addLegend": False, "legendPosition": "right",
                   "times": [], "addTimeMarker": False, "thresholdLine": {"show": False, "value": 10,
                                                                          "width": 1, "style": "full",
                                                                          "color": "#E7664C"}},
    }, ip)


def build_objects() -> list[dict]:
    objs: list[dict] = [
        _index_pattern(DOCS_IP, "atlasfile_documents", "ingested_at"),
        _index_pattern(USAGE_IP, "atlasfile_classification_usage", "timestamp"),
        _index_pattern(CHAT_IP, "atlasfile_chat_sessions", "updatedAt"),
    ]

    # ── Linha 1: pulso ──
    objs.append(_metric("atlasfile-viz-total-docs", "Documentos indexados", DOCS_IP,
                        {"type": "count"}, "Documentos"))
    objs.append(_metric("atlasfile-viz-projetos", "Projetos", DOCS_IP,
                        {"type": "cardinality", "params": {"field": "project_id"}}, "Projetos"))
    objs.append(_metric("atlasfile-viz-confianca-media", "Confiança média", DOCS_IP,
                        {"type": "avg", "params": {"field": "confidence_score"}}, "Confiança média"))
    objs.append(_metric("atlasfile-viz-custo-llm", "Custo LLM (classificação)", USAGE_IP,
                        {"type": "sum", "params": {"field": "estimated_cost_usd"}}, "USD no período"))
    objs.append(_metric("atlasfile-viz-chats", "Sessões de chat", CHAT_IP,
                        {"type": "count"}, "Sessões"))

    # ── Linha 2: acervo ──
    objs.append(_pie("atlasfile-viz-dominios", "Domínios de negócio", DOCS_IP, "business_domain"))
    objs.append(_pie("atlasfile-viz-doc-kind", "Formato (doc_kind)", DOCS_IP, "doc_kind"))
    objs.append(_hbar("atlasfile-viz-tipos", "Tipos documentais", DOCS_IP, "document_type", 14))
    objs.append(_table("atlasfile-viz-tabela-projetos", "Projetos — volume e confiança", DOCS_IP,
                       "project_id",
                       [{"type": "count"},
                        {"type": "avg", "params": {"field": "confidence_score"}}]))

    # ── Linha 3: fluxo e saúde do pipeline ──
    objs.append(_timeline("atlasfile-viz-ingestao-tempo", "Ingestão por dia × decisão", DOCS_IP,
                          "ingested_at", "decision"))
    objs.append(_pie("atlasfile-viz-decisoes", "Decisões", DOCS_IP, "decision", donut=False))
    objs.append(_histogram_confidence("atlasfile-viz-confianca-dist", "Distribuição de confiança", DOCS_IP))
    objs.append(_pie("atlasfile-viz-classifier-mode", "Modo do classificador", DOCS_IP, "classifier_mode"))
    objs.append(_hbar("atlasfile-viz-extraction-status", "Saúde da extração", DOCS_IP, "extraction_status", 8))
    objs.append(_hbar("atlasfile-viz-embedding-status", "Saúde dos embeddings", DOCS_IP, "embedding_status", 8))

    # ── Linha 4: LLM e vocabulário ──
    objs.append(_timeline("atlasfile-viz-custo-tempo", "Custo LLM por dia × modelo", USAGE_IP,
                          "timestamp", "model",
                          metric={"id": "1", "enabled": True, "type": "sum", "schema": "metric",
                                  "params": {"field": "estimated_cost_usd", "customLabel": "USD"}},
                          chart_type="line"))
    objs.append(_table("atlasfile-viz-tabela-llm", "Uso LLM por modelo", USAGE_IP, "model",
                       [{"type": "count"},
                        {"type": "sum", "params": {"field": "input_tokens"}},
                        {"type": "sum", "params": {"field": "output_tokens"}},
                        {"type": "sum", "params": {"field": "estimated_cost_usd"}}]))
    objs.append(_tagcloud("atlasfile-viz-topicos", "Tópicos do acervo", DOCS_IP, "topics"))

    # ── Dashboard ──
    vis_ids = [o["id"] for o in objs if o["type"] == "visualization"]
    # grade 48 colunas; (id, x, y, w, h)
    layout = [
        ("atlasfile-viz-total-docs", 0, 0, 9, 7),
        ("atlasfile-viz-projetos", 9, 0, 9, 7),
        ("atlasfile-viz-confianca-media", 18, 0, 10, 7),
        ("atlasfile-viz-custo-llm", 28, 0, 10, 7),
        ("atlasfile-viz-chats", 38, 0, 10, 7),
        ("atlasfile-viz-dominios", 0, 7, 16, 13),
        ("atlasfile-viz-doc-kind", 16, 7, 16, 13),
        ("atlasfile-viz-tipos", 32, 7, 16, 13),
        ("atlasfile-viz-ingestao-tempo", 0, 20, 32, 13),
        ("atlasfile-viz-decisoes", 32, 20, 16, 13),
        ("atlasfile-viz-confianca-dist", 0, 33, 16, 12),
        ("atlasfile-viz-classifier-mode", 16, 33, 16, 12),
        ("atlasfile-viz-tabela-projetos", 32, 33, 16, 12),
        ("atlasfile-viz-extraction-status", 0, 45, 16, 10),
        ("atlasfile-viz-embedding-status", 16, 45, 16, 10),
        ("atlasfile-viz-topicos", 32, 45, 16, 10),
        ("atlasfile-viz-custo-tempo", 0, 55, 32, 12),
        ("atlasfile-viz-tabela-llm", 32, 55, 16, 12),
    ]
    assert {vid for vid, *_ in layout} == set(vis_ids), "layout e visualizações divergem"

    panels = []
    references = []
    for i, (vid, x, y, w, h) in enumerate(layout, start=1):
        panels.append({"version": "2.11.0", "gridData": {"x": x, "y": y, "w": w, "h": h, "i": str(i)},
                       "panelIndex": str(i), "embeddableConfig": {}, "panelRefName": f"panel_{i}"})
        references.append({"name": f"panel_{i}", "type": "visualization", "id": vid})

    objs.append({
        "id": DASHBOARD_ID,
        "type": "dashboard",
        "attributes": {
            "title": "AtlasFile — Operação",
            "hits": 0,
            "description": "Observabilidade do AtlasFile: acervo, fluxo de ingestão, saúde do pipeline e custo LLM. Gerado por backend/scripts/build_dashboards_ndjson.py — edite lá, não aqui.",
            "panelsJSON": json.dumps(panels),
            "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
            "version": 1,
            "timeRestore": True,
            "timeTo": "now",
            "timeFrom": "now-30d",
            "refreshInterval": {"pause": True, "value": 0},
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []})
            },
        },
        "references": references,
        "migrationVersion": {"dashboard": "7.9.3"},
    })
    return objs


def render_ndjson() -> str:
    return "\n".join(json.dumps(o, ensure_ascii=False, sort_keys=True) for o in build_objects()) + "\n"


def main() -> None:
    content = render_ndjson()
    for out in OUTPUTS:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        print(f"gravado: {out}")


if __name__ == "__main__":
    main()

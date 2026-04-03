"""Server-side chart renderer using matplotlib.

Generates PNG images from the same chart JSON schema used by the frontend
ChartBlock component. Used for Telegram channel where interactive charts
are not available.
"""

from __future__ import annotations

import json
import logging
import re
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

# Regex to find ```chart ... ``` blocks in markdown text
_CHART_BLOCK_RE = re.compile(
    r"```chart\s*\n(.*?)\n```",
    re.DOTALL,
)

# Dark theme colors matching the frontend
_BG_COLOR = "#1e1e2e"
_TEXT_COLOR = "#f5f4f8"
_MUTED_COLOR = "#a8a4b3"
_GRID_COLOR = "#2a2630"
_PALETTE = [
    "#ff5a36",  # accent
    "#c97bff",  # purple
    "#f39c12",  # orange
    "#00bcd4",  # cyan
    "#2ecc71",  # green
    "#e74c3c",  # red
    "#7dd3fc",  # blue
    "#fbbf24",  # amber
]


def extract_chart_blocks(text: str) -> list[tuple[dict[str, Any], str]]:
    """Extract chart JSON blocks from markdown text.

    Returns list of (parsed_json, original_block_string) tuples.
    Invalid JSON blocks are skipped.
    """
    results: list[tuple[dict[str, Any], str]] = []
    for m in _CHART_BLOCK_RE.finditer(text):
        raw_json = m.group(1).strip()
        full_match = m.group(0)
        try:
            spec = json.loads(raw_json)
            if isinstance(spec, dict) and "type" in spec and "data" in spec:
                results.append((spec, full_match))
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def render_chart_png(chart_spec: dict[str, Any], dpi: int = 150) -> bytes | None:
    """Render a chart spec to PNG bytes using matplotlib.

    Returns None if rendering fails.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        logger.warning("matplotlib not available for chart rendering")
        return None

    chart_type = chart_spec.get("type", "bar")
    data = chart_spec.get("data", [])
    title = chart_spec.get("title", "")
    series = chart_spec.get("series")
    x_key = chart_spec.get("xKey", "name")
    y_key = chart_spec.get("yKey", "value")

    if not data:
        return None

    try:
        fig, ax = plt.subplots(figsize=(8, 5), facecolor=_BG_COLOR)
        ax.set_facecolor(_BG_COLOR)
        ax.tick_params(colors=_MUTED_COLOR, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(_GRID_COLOR)
        ax.grid(True, color=_GRID_COLOR, linewidth=0.5, alpha=0.5)

        if chart_type == "bar":
            _render_bar(ax, data, x_key, y_key, series)
        elif chart_type == "stacked_bar":
            _render_stacked_bar(ax, data, x_key, series or [y_key])
        elif chart_type == "horizontal_bar":
            _render_horizontal_bar(ax, data, x_key, y_key, series)
        elif chart_type == "pie":
            ax.clear()
            ax.set_facecolor(_BG_COLOR)
            _render_pie(ax, data, x_key, y_key)
        elif chart_type == "line":
            _render_line(ax, data, x_key, y_key, series)
        elif chart_type == "area":
            _render_area(ax, data, x_key, y_key, series)
        elif chart_type == "composed":
            _render_composed(ax, data, x_key, series or [y_key])
        elif chart_type == "treemap":
            ax.clear()
            ax.set_facecolor(_BG_COLOR)
            _render_treemap(ax, data, x_key, y_key, FancyBboxPatch)
        else:
            plt.close(fig)
            return None

        if title:
            fig.suptitle(title, color=_TEXT_COLOR, fontsize=13, fontweight="bold", y=0.97)

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=_BG_COLOR, pad_inches=0.3)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        logger.exception("Failed to render chart")
        try:
            plt.close(fig)
        except Exception:
            pass
        return None


def _get_series_keys(data: list[dict], y_key: str, series: list[str] | None) -> list[str]:
    if series and len(series) > 0:
        return series
    return [y_key]


def _render_bar(ax: Any, data: list[dict], x_key: str, y_key: str, series: list[str] | None) -> None:
    import numpy as np

    keys = _get_series_keys(data, y_key, series)
    labels = [str(d.get(x_key, "")) for d in data]
    x = np.arange(len(labels))
    width = 0.8 / len(keys)

    for i, k in enumerate(keys):
        values = [float(d.get(k, 0)) for d in data]
        offset = (i - len(keys) / 2 + 0.5) * width
        ax.bar(x + offset, values, width, color=_PALETTE[i % len(_PALETTE)], label=k)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8, color=_MUTED_COLOR)
    ax.yaxis.label.set_color(_MUTED_COLOR)
    if len(keys) > 1:
        ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, labelcolor=_MUTED_COLOR, fontsize=8)


def _render_stacked_bar(ax: Any, data: list[dict], x_key: str, keys: list[str]) -> None:
    import numpy as np

    labels = [str(d.get(x_key, "")) for d in data]
    x = np.arange(len(labels))
    bottom = np.zeros(len(data))

    for i, k in enumerate(keys):
        values = np.array([float(d.get(k, 0)) for d in data])
        ax.bar(x, values, 0.6, bottom=bottom, color=_PALETTE[i % len(_PALETTE)], label=k)
        bottom += values

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8, color=_MUTED_COLOR)
    ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, labelcolor=_MUTED_COLOR, fontsize=8)


def _render_horizontal_bar(ax: Any, data: list[dict], x_key: str, y_key: str, series: list[str] | None) -> None:
    keys = _get_series_keys(data, y_key, series)
    labels = [str(d.get(x_key, "")) for d in data]
    values = [float(d.get(keys[0], 0)) for d in data]

    y_pos = range(len(labels))
    ax.barh(y_pos, values, color=_PALETTE[0], height=0.6)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=8, color=_MUTED_COLOR)
    ax.invert_yaxis()


def _render_pie(ax: Any, data: list[dict], x_key: str, y_key: str) -> None:
    labels = [str(d.get(x_key, "")) for d in data]
    values = [float(d.get(y_key, 0)) for d in data]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(data))]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        textprops={"color": _TEXT_COLOR, "fontsize": 9},
    )
    for t in autotexts:
        t.set_fontsize(8)
        t.set_color(_TEXT_COLOR)


def _render_line(ax: Any, data: list[dict], x_key: str, y_key: str, series: list[str] | None) -> None:
    import numpy as np

    keys = _get_series_keys(data, y_key, series)
    labels = [str(d.get(x_key, "")) for d in data]
    x = np.arange(len(labels))

    for i, k in enumerate(keys):
        values = [float(d.get(k, 0)) for d in data]
        ax.plot(x, values, color=_PALETTE[i % len(_PALETTE)], linewidth=2, marker="o", markersize=4, label=k)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8, color=_MUTED_COLOR)
    if len(keys) > 1:
        ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, labelcolor=_MUTED_COLOR, fontsize=8)


def _render_area(ax: Any, data: list[dict], x_key: str, y_key: str, series: list[str] | None) -> None:
    import numpy as np

    keys = _get_series_keys(data, y_key, series)
    labels = [str(d.get(x_key, "")) for d in data]
    x = np.arange(len(labels))

    for i, k in enumerate(keys):
        values = [float(d.get(k, 0)) for d in data]
        color = _PALETTE[i % len(_PALETTE)]
        ax.fill_between(x, values, alpha=0.2, color=color)
        ax.plot(x, values, color=color, linewidth=2, label=k)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8, color=_MUTED_COLOR)
    if len(keys) > 1:
        ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, labelcolor=_MUTED_COLOR, fontsize=8)


def _render_composed(ax: Any, data: list[dict], x_key: str, keys: list[str]) -> None:
    import numpy as np

    labels = [str(d.get(x_key, "")) for d in data]
    x = np.arange(len(labels))
    bar_keys = keys[:-1] if len(keys) > 1 else keys
    line_keys = keys[-1:] if len(keys) > 1 else []

    for i, k in enumerate(bar_keys):
        values = [float(d.get(k, 0)) for d in data]
        ax.bar(x, values, 0.6, color=_PALETTE[i % len(_PALETTE)], label=k, alpha=0.8)

    for i, k in enumerate(line_keys):
        values = [float(d.get(k, 0)) for d in data]
        ci = len(bar_keys) + i
        ax.plot(x, values, color=_PALETTE[ci % len(_PALETTE)], linewidth=2, marker="o", markersize=4, label=k)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8, color=_MUTED_COLOR)
    ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, labelcolor=_MUTED_COLOR, fontsize=8)


def _render_treemap(ax: Any, data: list[dict], x_key: str, y_key: str, FancyBboxPatch: Any) -> None:
    """Simple treemap using squarified layout."""
    import matplotlib.pyplot as plt

    labels = [str(d.get(x_key, "")) for d in data]
    values = [max(float(d.get(y_key, 0)), 0) for d in data]
    total = sum(values) or 1

    # Simple squarified treemap in a unit rectangle
    rects = _squarify(values, 0, 0, 1, 1)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")

    for i, (x, y, w, h) in enumerate(rects):
        color = _PALETTE[i % len(_PALETTE)]
        rect = plt.Rectangle((x, y), w, h, facecolor=color, edgecolor=_BG_COLOR, linewidth=2)
        ax.add_patch(rect)
        if w > 0.08 and h > 0.06:
            label = labels[i] if i < len(labels) else ""
            if len(label) > int(w * 40):
                label = label[: int(w * 40)] + "…"
            ax.text(
                x + w / 2, y + h / 2, label,
                ha="center", va="center", color=_TEXT_COLOR, fontsize=9,
                fontweight="bold",
            )


def _squarify(values: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Simple squarified treemap layout. Returns list of (x, y, w, h) rects."""
    total = sum(values) or 1
    if len(values) == 0:
        return []
    if len(values) == 1:
        return [(x, y, w, h)]

    # Lay out in rows along the longer side
    rects: list[tuple[float, float, float, float]] = []
    remaining = list(enumerate(values))
    remaining.sort(key=lambda t: t[1], reverse=True)
    indices = [i for i, _ in remaining]
    sorted_vals = [v for _, v in remaining]

    result: list[tuple[int, float, float, float, float]] = []
    _squarify_recursive(sorted_vals, indices, x, y, w, h, total, result)

    # Re-order by original index
    result.sort(key=lambda t: t[0])
    return [(rx, ry, rw, rh) for _, rx, ry, rw, rh in result]


def _squarify_recursive(
    values: list[float],
    indices: list[int],
    x: float, y: float, w: float, h: float,
    total: float,
    result: list[tuple[int, float, float, float, float]],
) -> None:
    if not values:
        return
    if len(values) == 1:
        result.append((indices[0], x, y, w, h))
        return

    # Slice: first element takes its proportion, rest fills remaining
    frac = values[0] / total if total > 0 else 0
    if w >= h:
        col_w = frac * w
        result.append((indices[0], x, y, col_w, h))
        _squarify_recursive(values[1:], indices[1:], x + col_w, y, w - col_w, h, total - values[0], result)
    else:
        row_h = frac * h
        result.append((indices[0], x, y, w, row_h))
        _squarify_recursive(values[1:], indices[1:], x, y + row_h, w, h - row_h, total - values[0], result)

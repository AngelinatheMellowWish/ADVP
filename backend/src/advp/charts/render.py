"""Build Plotly figure JSON from a persisted chart selection."""

from __future__ import annotations

import json
import math
from typing import Any, cast

import numpy as np
import plotly.graph_objects as go  # type: ignore[import-untyped]
import plotly.io as pio  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from advp.charts.errors import RenderError as RenderError
from advp.charts.registry import get_chart
from advp.config import get_settings
from advp.ingest.files import read_preview
from advp.models import ChartSelection, Dataset

MAX_RENDER_ROWS = 100_000
ARRAY_RENDER_LIMIT = 1_000_000


def render_selection(session: Session, selection: ChartSelection) -> dict[str, Any]:
    """Render a persisted selection to Plotly JSON."""
    dataset = session.get(Dataset, selection.dataset_id)
    if dataset is None:
        raise RenderError("dataset_not_found", "selection dataset no longer exists", 404)
    result = selection.result_json or {}
    selected = result.get("selected") or {}
    chart_id = str(selected.get("chart_id") or selection.selected_chart_id)
    spec = get_chart(chart_id)
    renderer = spec.backend if spec is not None else "plotly"
    fields = {str(key): str(value) for key, value in (selected.get("fields") or {}).items()}
    style = selected.get("style") if isinstance(selected.get("style"), dict) else {}
    settings = get_settings()
    render_limit = min(max(settings.render_sample_rows, 1), MAX_RENDER_ROWS)

    if dataset.kind == "array":
        if chart_id == "image_slice":
            figure = _image_slice_payload(dataset, selected)
        else:
            figure = _array_figure(dataset, chart_id)
        row_count = int(result.get("row_count") or dataset.row_count)
        sampled = dataset.sampled
    else:
        rows = read_preview(
            dataset.source_path,
            dataset.options,
            limit=render_limit,
            offset=0,
            max_file_bytes=settings.max_file_bytes,
            schema=dataset.schema_json,
            max_limit=render_limit,
        )
        figure = build_table_figure(
            chart_id=chart_id,
            fields=fields,
            rows=rows,
            schema=dataset.schema_json,
            title=f"{dataset.name} · {chart_id}",
            style=style,
        )
        row_count = len(rows)
        sampled = dataset.sampled or row_count < dataset.row_count
    return {
        "selection_id": selection.id,
        "dataset_id": dataset.id,
        "chart_id": chart_id,
        "renderer": renderer,
        "figure": figure,
        "row_count": row_count,
        "sampled": sampled,
        "max_rows": render_limit if dataset.kind != "array" else ARRAY_RENDER_LIMIT,
    }


def build_table_figure(
    *,
    chart_id: str,
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    schema: dict[str, Any],
    title: str,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Plotly figure for one registered 2D chart."""
    if not rows:
        raise RenderError("empty_data", "the dataset preview has no rows to render")
    if chart_id == "network_graph":
        from advp.charts.render_cytoscape import build_network_payload

        return build_network_payload(fields=fields, rows=rows, title=title, style=style)
    if chart_id == "sankey_flow":
        from advp.charts.render_echarts import build_sankey_option

        return build_sankey_option(fields=fields, rows=rows, title=title, style=style)
    if chart_id == "sunburst_hierarchy":
        from advp.charts.render_echarts import build_sunburst_option

        return build_sunburst_option(fields=fields, rows=rows, title=title, style=style)
    if chart_id in {"geo_scatter", "geo_trajectory", "geo_density", "geo_region"}:
        from advp.charts.render_deck import build_deck_payload

        return build_deck_payload(
            chart_id=chart_id,
            fields=fields,
            rows=rows,
            title=title,
            style=style,
        )
    if chart_id == "bar":
        fig = _bar(rows, fields, orientation="v")
    elif chart_id == "bar_horizontal":
        fig = _bar(rows, fields, orientation="h")
    elif chart_id == "line_timeseries":
        fig = _line(rows, fields, fill=None)
    elif chart_id == "area_timeseries":
        fig = _line(rows, fields, fill="tozeroy")
    elif chart_id == "scatter":
        fig = _scatter(rows, fields, bubble=False)
    elif chart_id == "bubble":
        fig = _scatter(rows, fields, bubble=True)
    elif chart_id == "histogram":
        fig = _histogram(rows, fields)
    elif chart_id == "box":
        fig = _distribution(rows, fields, kind="box")
    elif chart_id == "violin":
        fig = _distribution(rows, fields, kind="violin")
    elif chart_id == "heatmap":
        fig = _heatmap(rows, fields)
    elif chart_id in {"pie", "donut"}:
        fig = _pie(rows, fields, hole=0.45 if chart_id == "donut" else 0.0)
    elif chart_id == "radar":
        fig = _radar(rows, fields)
    elif chart_id == "parallel":
        fig = _parallel(rows, fields, schema)
    elif chart_id == "regression":
        fig = _regression(rows, fields)
    else:
        raise RenderError(
            "unsupported_render",
            f"renderer for chart {chart_id!r} is not implemented",
        )

    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(12,20,38,0.55)",
        margin={"l": 56, "r": 24, "t": 56, "b": 48},
        legend={"orientation": "h", "y": -0.18},
    )
    _apply_style(fig, style)
    return cast(dict[str, Any], json.loads(pio.to_json(fig, validate=False)))


def _apply_style(fig: go.Figure, style: dict[str, Any] | None) -> None:
    if not style:
        return
    if style.get("title"):
        fig.update_layout(title=str(style["title"]))
    if style.get("x_title"):
        fig.update_layout(xaxis_title=str(style["x_title"]))
    if style.get("y_title"):
        fig.update_layout(yaxis_title=str(style["y_title"]))
    if style.get("log_x"):
        fig.update_layout(xaxis_type="log")
    if style.get("log_y"):
        fig.update_layout(yaxis_type="log")
    if style.get("show_legend") is not None:
        fig.update_layout(showlegend=bool(style["show_legend"]))
    barmode = style.get("barmode")
    if barmode in {"group", "stack", "overlay"}:
        fig.update_layout(barmode=barmode)
    if style.get("dual_y"):
        fig.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
    if style.get("colorblind_palette"):
        fig.update_layout(
            colorway=[
                "#0072B2",
                "#E69F00",
                "#009E73",
                "#CC79A7",
                "#56B4E9",
                "#D55E00",
                "#F0E442",
                "#000000",
            ]
        )
    extra_annotations: list[dict[str, Any]] = []
    shapes: list[dict[str, Any]] = []
    reference_lines = style.get("reference_lines")
    if isinstance(reference_lines, list):
        for item in reference_lines[:5]:
            if not isinstance(item, dict) or not isinstance(item.get("value"), (int, float)):
                continue
            value = float(item["value"])
            axis = str(item.get("axis", "y"))
            if axis == "x":
                shapes.append(
                    {
                        "type": "line",
                        "x0": value,
                        "x1": value,
                        "y0": 0,
                        "y1": 1,
                        "yref": "paper",
                        "line": {"color": "#f59e0b", "width": 1, "dash": "dash"},
                    }
                )
            else:
                shapes.append(
                    {
                        "type": "line",
                        "x0": 0,
                        "x1": 1,
                        "xref": "paper",
                        "y0": value,
                        "y1": value,
                        "line": {"color": "#f59e0b", "width": 1, "dash": "dash"},
                    }
                )
            if item.get("label"):
                extra_annotations.append(
                    {
                        "text": str(item["label"]),
                        "x": 0.01 if axis == "y" else value,
                        "xref": "paper" if axis == "y" else "x",
                        "y": value if axis == "y" else 0.98,
                        "yref": "y" if axis == "y" else "paper",
                        "showarrow": False,
                        "font": {"size": 10, "color": "#fbbf24"},
                    }
                )
    if shapes:
        fig.update_layout(shapes=shapes)
    source_note = style.get("source_note")
    if isinstance(source_note, str) and source_note:
        extra_annotations.append(
            {
                "text": source_note,
                "x": 0,
                "xref": "paper",
                "y": -0.26,
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 10, "color": "#93a7c4"},
            }
        )
    color = style.get("color")
    if isinstance(color, str):
        fig.update_layout(colorway=[color])
        fig.update_traces(marker_color=color, selector={"type": "bar"})
        fig.update_traces(
            marker_color=color,
            line_color=color,
            selector={"type": "scatter"},
        )
        fig.update_traces(marker_color=color, selector={"type": "scattergeo"})
        fig.update_traces(marker_color=color, selector={"type": "box"})
        fig.update_traces(marker_color=color, selector={"type": "violin"})
    colorscale = style.get("colorscale")
    if isinstance(colorscale, str):
        fig.update_traces(colorscale=colorscale, selector={"type": "heatmap"})
        fig.update_traces(colorscale=colorscale, selector={"type": "scattergeo"})
    colorscale_min = style.get("colorscale_min")
    colorscale_max = style.get("colorscale_max")
    if isinstance(colorscale_min, (int, float)):
        fig.update_traces(zmin=colorscale_min, selector={"type": "heatmap"})
        fig.update_traces(cmin=colorscale_min, selector={"type": "scattergeo"})
    if isinstance(colorscale_max, (int, float)):
        fig.update_traces(zmax=colorscale_max, selector={"type": "heatmap"})
        fig.update_traces(cmax=colorscale_max, selector={"type": "scattergeo"})
    legend_position = style.get("legend_position")
    if isinstance(legend_position, str):
        positions = {
            "top": {"orientation": "h", "y": 1.05, "x": 0.5, "xanchor": "center"},
            "bottom": {"orientation": "h", "y": -0.18},
            "left": {"orientation": "v", "x": -0.1},
            "right": {"orientation": "v", "x": 1.02},
        }
        fig.update_layout(legend=positions.get(legend_position, positions["bottom"]))
    annotations = style.get("annotations")
    if isinstance(annotations, list):
        for item in annotations[:10]:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            annotation: dict[str, Any] = {
                "text": str(item["text"]),
                "showarrow": bool(item.get("showarrow", True)),
            }
            if isinstance(item.get("x"), (int, float)):
                annotation["x"] = item["x"]
                annotation["xref"] = "x"
            if isinstance(item.get("y"), (int, float)):
                annotation["y"] = item["y"]
                annotation["yref"] = "y"
            if "x" not in annotation:
                annotation["x"] = 0.02
                annotation["xref"] = "paper"
            if "y" not in annotation:
                annotation["y"] = 0.98
                annotation["yref"] = "paper"
            extra_annotations.append(annotation)
    if extra_annotations:
        fig.update_layout(annotations=extra_annotations)


def _bar(rows: list[dict[str, Any]], fields: dict[str, str], *, orientation: str) -> go.Figure:
    x_field = fields.get("x")
    y_field = fields.get("y")
    if not x_field or not y_field:
        raise RenderError("invalid_fields", "bar charts require x and y fields")
    fig = go.Figure()
    y2_field = fields.get("y2")
    error_field = fields.get("error_y")
    for name, group in _grouped(rows, fields.get("series")):
        x_values = _categories(_values(group, x_field))
        y_values = _numbers(_values(group, y_field))
        error = _error_bars(group, error_field)
        if orientation == "h":
            fig.add_trace(go.Bar(x=y_values, y=x_values, orientation="h", name=name or y_field))
        else:
            fig.add_trace(
                go.Bar(
                    x=x_values,
                    y=y_values,
                    name=name or y_field,
                    error_y=error,
                )
            )
            if y2_field:
                fig.add_trace(
                    go.Bar(
                        x=x_values,
                        y=_numbers(_values(group, y2_field)),
                        name=f"{name or y2_field} (右轴)",
                        yaxis="y2",
                        opacity=0.55,
                    )
                )
    fig.update_layout(xaxis_title=y_field if orientation == "h" else x_field)
    fig.update_layout(yaxis_title=x_field if orientation == "h" else y_field)
    return fig


def _line(rows: list[dict[str, Any]], fields: dict[str, str], *, fill: str | None) -> go.Figure:
    x_field = fields.get("x")
    y_field = fields.get("y")
    if not x_field or not y_field:
        raise RenderError("invalid_fields", "line charts require x and y fields")
    fig = go.Figure()
    y2_field = fields.get("y2")
    error_field = fields.get("error_y")
    for name, group in _grouped(rows, fields.get("series")):
        ordered = sorted(
            group,
            key=lambda row: (row.get(x_field) is None, str(row.get(x_field))),
        )
        x_values = _values(ordered, x_field)
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=_numbers(_values(ordered, y_field)),
                mode="lines+markers",
                fill=fill,
                name=name or y_field,
                error_y=_error_bars(ordered, error_field),
            )
        )
        if y2_field:
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=_numbers(_values(ordered, y2_field)),
                    mode="lines+markers",
                    name=f"{name or y2_field} (右轴)",
                    yaxis="y2",
                    line={"dash": "dot"},
                )
            )
    fig.update_layout(xaxis_title=x_field, yaxis_title=y_field)
    return fig


def _scatter(rows: list[dict[str, Any]], fields: dict[str, str], *, bubble: bool) -> go.Figure:
    x_field = fields.get("x")
    y_field = fields.get("y")
    if not x_field or not y_field:
        raise RenderError("invalid_fields", "scatter charts require x and y fields")
    fig = go.Figure()
    y2_field = fields.get("y2")
    error_field = fields.get("error_y")
    for name, group in _grouped(rows, fields.get("series")):
        marker: dict[str, Any] = {"size": 8 if not bubble else 12, "opacity": 0.8}
        if bubble:
            marker["size"] = _numbers(_values(group, fields.get("size", "")), default=8)
            marker["sizemode"] = "area"
        fig.add_trace(
            go.Scatter(
                x=_numbers(_values(group, x_field)),
                y=_numbers(_values(group, y_field)),
                mode="markers",
                marker=marker,
                name=name or y_field,
                error_y=_error_bars(group, error_field),
            )
        )
        if y2_field:
            fig.add_trace(
                go.Scatter(
                    x=_numbers(_values(group, x_field)),
                    y=_numbers(_values(group, y2_field)),
                    mode="markers",
                    name=f"{name or y2_field} (右轴)",
                    yaxis="y2",
                    marker={"symbol": "diamond", "size": 7, "opacity": 0.7},
                )
            )
    fig.update_layout(xaxis_title=x_field, yaxis_title=y_field)
    return fig


def _histogram(rows: list[dict[str, Any]], fields: dict[str, str]) -> go.Figure:
    x_field = fields.get("x")
    if not x_field:
        raise RenderError("invalid_fields", "histogram requires an x field")
    fig = go.Figure(go.Histogram(x=_numbers(_values(rows, x_field)), name=x_field))
    fig.update_layout(xaxis_title=x_field, yaxis_title="count")
    return fig


def _distribution(
    rows: list[dict[str, Any]],
    fields: dict[str, str],
    *,
    kind: str,
) -> go.Figure:
    y_field = fields.get("y")
    if not y_field:
        raise RenderError("invalid_fields", f"{kind} requires a y field")
    fig = go.Figure()
    for name, group in _grouped(rows, fields.get("x")):
        y_values = _numbers(_values(group, y_field))
        trace = (
            go.Box(y=y_values, name=name or y_field, boxpoints="outliers")
            if kind == "box"
            else go.Violin(y=y_values, name=name or y_field, box_visible=True)
        )
        fig.add_trace(trace)
    fig.update_layout(yaxis_title=y_field)
    return fig


def _heatmap(rows: list[dict[str, Any]], fields: dict[str, str]) -> go.Figure:
    x_field = fields.get("x")
    y_field = fields.get("y")
    value_field = fields.get("value")
    if not x_field or not y_field or not value_field:
        raise RenderError("invalid_fields", "heatmap requires x, y, and value fields")
    x_categories = sorted({str(value) for value in _values(rows, x_field) if value is not None})[
        :100
    ]
    y_categories = sorted({str(value) for value in _values(rows, y_field) if value is not None})[
        :100
    ]
    sums: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        x_value = row.get(x_field)
        y_value = row.get(y_field)
        value = _number(row.get(value_field))
        if x_value is None or y_value is None or value is None:
            continue
        key = (str(x_value), str(y_value))
        if str(x_value) in x_categories and str(y_value) in y_categories:
            sums.setdefault(key, []).append(value)
    z = [
        [sum(sums[(x, y)]) / len(sums[(x, y)]) if sums.get((x, y)) else None for x in x_categories]
        for y in y_categories
    ]
    fig = go.Figure(go.Heatmap(x=x_categories, y=y_categories, z=z, colorscale="Viridis"))
    fig.update_layout(xaxis_title=x_field, yaxis_title=y_field)
    return fig


def _pie(rows: list[dict[str, Any]], fields: dict[str, str], *, hole: float) -> go.Figure:
    label_field = fields.get("label")
    value_field = fields.get("value")
    if not label_field or not value_field:
        raise RenderError("invalid_fields", "pie charts require label and value fields")
    totals: dict[str, float] = {}
    for row in rows:
        label = row.get(label_field)
        value = _number(row.get(value_field))
        if label is None or value is None:
            continue
        totals[str(label)] = totals.get(str(label), 0.0) + value
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:20]
    fig = go.Figure(
        go.Pie(
            labels=[item[0] for item in ordered],
            values=[item[1] for item in ordered],
            hole=hole,
        )
    )
    return fig


def _radar(rows: list[dict[str, Any]], fields: dict[str, str]) -> go.Figure:
    label_field = fields.get("label")
    value_field = fields.get("value")
    if not label_field or not value_field:
        raise RenderError("invalid_fields", "radar requires label and value fields")
    totals: dict[str, list[float]] = {}
    for row in rows:
        label = row.get(label_field)
        value = _number(row.get(value_field))
        if label is None or value is None:
            continue
        totals.setdefault(str(label), []).append(value)
    labels = list(totals)
    values = [sum(totals[label]) / len(totals[label]) for label in labels]
    fig = go.Figure(go.Scatterpolar(r=values, theta=labels, fill="toself", name=value_field))
    fig.update_layout(polar={"radialaxis": {"visible": True}})
    return fig


def _parallel(
    rows: list[dict[str, Any]],
    fields: dict[str, str],
    schema: dict[str, Any],
) -> go.Figure:
    numeric_columns = [
        str(column.get("name"))
        for column in schema.get("columns", [])
        if column.get("semantic_type") in {"integer", "number"}
    ]
    value_field = fields.get("value")
    if value_field and value_field not in numeric_columns:
        numeric_columns.insert(0, value_field)
    numeric_columns = numeric_columns[:6]
    if len(numeric_columns) < 3:
        raise RenderError(
            "invalid_fields",
            "parallel coordinates require at least 3 numeric fields",
        )
    dimensions = []
    for column in numeric_columns:
        values = _numbers(_values(rows, column))
        finite = [value for value in values if value is not None]
        dimensions.append(
            {
                "label": column,
                "values": values,
                "range": [min(finite), max(finite)] if finite else [0, 1],
            }
        )
    fig = go.Figure(go.Parcoords(dimensions=dimensions))
    return fig


def _regression(rows: list[dict[str, Any]], fields: dict[str, str]) -> go.Figure:
    x_field = fields.get("x")
    y_field = fields.get("y")
    if not x_field or not y_field:
        raise RenderError("invalid_fields", "regression requires x and y fields")
    pairs = [
        (x, y)
        for x, y in zip(
            _numbers(_values(rows, x_field)),
            _numbers(_values(rows, y_field)),
            strict=False,
        )
        if x is not None and y is not None
    ]
    if len(pairs) < 2:
        raise RenderError("empty_data", "regression requires at least two numeric pairs")
    x_values = [item[0] for item in pairs]
    y_values = [item[1] for item in pairs]
    slope, intercept = np.polyfit(x_values, y_values, 1)
    line_x = [min(x_values), max(x_values)]
    line_y = [slope * x + intercept for x in line_x]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="markers", name="data"))
    fig.add_trace(go.Scatter(x=line_x, y=line_y, mode="lines", name="fit"))
    fig.update_layout(xaxis_title=x_field, yaxis_title=y_field)
    return fig


def _image_slice_payload(
    dataset: Dataset,
    selected: dict[str, Any],
) -> dict[str, Any]:
    schema = dataset.schema_json or {}
    shape = [int(size) for size in schema.get("shape", [])]
    dims = [str(dim) for dim in schema.get("dims", [])]
    if len(shape) < 2:
        raise RenderError("empty_array", "imaging requires at least a 2D array")
    mapping = selected.get("array_mapping") if isinstance(selected, dict) else None
    axis = int(mapping.get("axis", 0)) if isinstance(mapping, dict) else 0
    index = int(mapping.get("index", 0)) if isinstance(mapping, dict) else 0
    style = selected.get("style") if isinstance(selected, dict) else None
    annotations = style.get("annotations") if isinstance(style, dict) else None
    return {
        "imaging": {
            "dataset_id": dataset.id,
            "format": dataset.format,
            "shape": shape,
            "dims": dims,
            "dtype": schema.get("dtype"),
            "units": schema.get("units"),
            "axis": axis,
            "index": index,
            "window": {"min": None, "max": None},
            "annotations": annotations or [],
        }
    }


def _array_figure(dataset: Dataset, chart_id: str) -> dict[str, Any]:
    if chart_id != "array_heatmap":
        raise RenderError("unsupported_render", "array datasets only support array_heatmap")
    schema = dataset.schema_json or {}
    shape = [int(size) for size in schema.get("shape", [])]
    dims = [str(dim) for dim in schema.get("dims", [])]
    if not shape or any(size <= 0 for size in shape):
        raise RenderError("empty_array", "array shape is empty")
    if math.prod(shape) > ARRAY_RENDER_LIMIT:
        raise RenderError(
            "array_too_large",
            "array preview is too large for the first rendering slice",
        )
    values = [
        _number(row.get("value")) for row in dataset.preview_json or [] if isinstance(row, dict)
    ]
    if len(values) < math.prod(shape):
        raise RenderError(
            "array_preview_insufficient",
            "the stored array preview does not contain enough values to render",
        )
    array = np.asarray(values[: math.prod(shape)], dtype=float).reshape(shape)
    if array.ndim == 3:
        array = array[0]
        y_title = dims[-2] if len(dims) >= 2 else "row"
        x_title = dims[-1] if len(dims) >= 1 else "col"
    elif array.ndim == 2:
        y_title = dims[-2] if len(dims) >= 2 else "row"
        x_title = dims[-1] if len(dims) >= 1 else "col"
    elif array.ndim == 1:
        array = array.reshape(1, -1)
        y_title = "value"
        x_title = dims[0] if dims else "index"
    else:
        raise RenderError("array_dim_unsupported", "only 1D-3D arrays are renderable")
    fig = go.Figure(go.Heatmap(z=array.tolist(), colorscale="Viridis"))
    fig.update_layout(
        title=f"{dataset.name} · array_heatmap",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(12,20,38,0.55)",
        margin={"l": 56, "r": 24, "t": 56, "b": 48},
        xaxis_title=x_title,
        yaxis_title=y_title,
    )
    return cast(dict[str, Any], json.loads(pio.to_json(fig, validate=False)))


def _grouped(
    rows: list[dict[str, Any]],
    series_field: str | None,
) -> list[tuple[str, list[dict[str, Any]]]]:
    if not series_field:
        return [("", rows)]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(series_field) if row.get(series_field) is not None else "missing")
        groups.setdefault(key, []).append(row)
    return list(groups.items())


def _values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    return [row.get(field) for row in rows]


def _categories(values: list[Any]) -> list[str]:
    return ["missing" if value is None else str(value) for value in values]


def _error_bars(
    group: list[dict[str, Any]],
    field: str | None,
) -> dict[str, Any] | None:
    if not field:
        return None
    values = _numbers(_values(group, field))
    if all(value is None for value in values):
        return None
    return {"type": "data", "array": values, "visible": True}


def _numbers(values: list[Any], *, default: float | None = None) -> list[float | None]:
    result: list[float | None] = []
    for value in values:
        result.append(_number(value, default=default))
    return result


def _number(value: Any, *, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

"""Build ECharts options for Sankey, Sunburst, and live time series."""

from __future__ import annotations

from typing import Any

from advp.charts.errors import RenderError


def build_sankey_option(
    *,
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    title: str,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an ECharts Sankey option aggregated by source/target."""
    source_field = fields.get("source")
    target_field = fields.get("target")
    weight_field = fields.get("weight")
    if not source_field or not target_field or not weight_field:
        raise RenderError("invalid_fields", "sankey requires source, target, and weight fields")
    if source_field == target_field:
        raise RenderError("invalid_fields", "sankey source and target must be different fields")

    links: dict[tuple[str, str], float] = {}
    node_totals: dict[str, float] = {}
    for row in rows:
        source = _text(row.get(source_field))
        target = _text(row.get(target_field))
        weight = _number(row.get(weight_field))
        if not source or not target or weight is None or weight <= 0:
            continue
        links[(source, target)] = links.get((source, target), 0.0) + weight
        node_totals[source] = node_totals.get(source, 0.0) + weight
        node_totals[target] = node_totals.get(target, 0.0) + weight
    if not links:
        raise RenderError("empty_data", "sankey has no positive source/target weights")

    node_limit = 200
    if len(node_totals) > node_limit:
        kept = {
            name
            for name, _ in sorted(node_totals.items(), key=lambda item: (-item[1], item[0]))[
                :node_limit
            ]
        }
        links = {key: value for key, value in links.items() if key[0] in kept and key[1] in kept}
        node_totals = {name: value for name, value in node_totals.items() if name in kept}
    if not links:
        raise RenderError("empty_data", "sankey nodes exceed the display limit")

    option = {
        "title": {"text": _title(title, style)},
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "type": "sankey",
                "data": [{"name": name} for name in sorted(node_totals)],
                "links": [
                    {"source": source, "target": target, "value": round(weight, 6)}
                    for (source, target), weight in sorted(links.items())
                ],
                "emphasis": {"focus": "adjacency"},
                "lineStyle": {"curveness": 0.5, "opacity": 0.45},
                "label": {"color": "#dbeafe", "fontSize": 11},
            }
        ],
    }
    return {
        "option": option,
        "meta": {"node_count": len(node_totals), "link_count": len(links)},
        "title": title,
    }


def build_sunburst_option(
    *,
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    title: str,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an ECharts Sunburst option from 1-3 hierarchy levels."""
    level_fields = [fields[role] for role in ("level1", "level2", "level3") if fields.get(role)]
    value_field = fields.get("value")
    if not level_fields or not value_field:
        raise RenderError(
            "invalid_fields",
            "sunburst requires level1 and value fields",
        )
    if len(level_fields) != len(set(level_fields)):
        raise RenderError("invalid_fields", "sunburst levels must be distinct fields")

    tree: dict[str, Any] = {"children": {}, "value": 0.0}
    for row in rows:
        value = _number(row.get(value_field))
        if value is None:
            continue
        node = tree
        node["value"] = float(node["value"]) + value
        for field in level_fields:
            name = _text(row.get(field))
            if not name:
                break
            child = node["children"].setdefault(name, {"children": {}, "value": 0.0})
            child["value"] = float(child["value"]) + value
            node = child

    data = _sunburst_children(tree)
    if not data:
        raise RenderError("empty_data", "sunburst has no hierarchy values")
    option = {
        "title": {"text": _title(title, style)},
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "type": "sunburst",
                "data": data,
                "radius": ["12%", "92%"],
                "label": {"rotate": "radial", "color": "#e5eefc", "fontSize": 11},
                "itemStyle": {"borderColor": "#0b1529", "borderWidth": 1},
                "emphasis": {"focus": "ancestor"},
            }
        ],
    }
    return {
        "option": option,
        "meta": {"levels": len(level_fields)},
        "title": title,
    }


def build_live_option(
    *,
    fields: dict[str, str],
    records: list[dict[str, Any]],
    title: str,
    style: dict[str, Any] | None = None,
    max_points: int = 500,
) -> dict[str, Any]:
    """Return an ECharts line option for a live bounded window."""
    x_field = fields.get("x")
    y_field = fields.get("y")
    if not x_field or not y_field:
        raise RenderError("invalid_fields", "live time series requires x and y fields")
    series_field = fields.get("series")
    points = records[-max_points:]
    categories: list[str] = []
    series_values: dict[str, list[float | None]] = {}
    for record in points:
        x_value = record.get(x_field)
        if x_value is None:
            continue
        categories.append(str(x_value))
        y_value = _number(record.get(y_field))
        key = str(record.get(series_field)) if series_field else "value"
        series_values.setdefault(key, []).append(y_value)
    if not categories:
        raise RenderError("empty_data", "live window has no x values")
    option = {
        "title": {"text": _title(title, style)},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"color": "#93a7c4"}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#93a7c4"}},
        "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 16}],
        "series": [
            {
                "name": name,
                "type": "line",
                "showSymbol": False,
                "smooth": False,
                "data": values,
            }
            for name, values in series_values.items()
        ],
    }
    return {"option": option, "meta": {"points": len(categories)}, "title": title}


def _sunburst_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node["children"]
    result: list[dict[str, Any]] = []
    for name in sorted(children):
        child = children[name]
        result.append(
            {
                "name": name,
                "value": round(float(child["value"]), 6),
                "children": _sunburst_children(child) or None,
            }
        )
    return result


def _title(title: str, style: dict[str, Any] | None) -> str:
    if isinstance(style, dict) and style.get("title"):
        return str(style["title"])
    return title


def _text(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

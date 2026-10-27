"""Build deck.gl payloads for map-family charts."""

from __future__ import annotations

import math
from typing import Any

from advp.charts.errors import RenderError

MAP_CHARTS = frozenset({"geo_scatter", "geo_trajectory", "geo_density", "geo_region"})


def build_deck_payload(
    *,
    chart_id: str,
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    title: str,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return layer data and an initial view state for deck.gl."""
    if chart_id == "geo_region":
        return _region_payload(fields=fields, rows=rows, title=title, style=style)
    points = _geo_points(fields, rows)
    if not points:
        raise RenderError("empty_geo", "no rows contain a valid latitude/longitude pair")
    view_state = _view_state([(lon, lat) for _, lat, lon in points])
    if chart_id == "geo_scatter":
        return _scatter_payload(points, fields, view_state, title, style)
    if chart_id == "geo_trajectory":
        return _trajectory_payload(fields, rows, points, view_state, title, style)
    if chart_id == "geo_density":
        return _density_payload(fields, points, view_state, title, style)
    raise RenderError("unsupported_render", f"unsupported deck.gl chart {chart_id!r}")


def _geo_points(
    fields: dict[str, str],
    rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], float, float]]:
    latitude_field = fields.get("latitude")
    longitude_field = fields.get("longitude")
    if not latitude_field or not longitude_field:
        raise RenderError(
            "missing_geo_fields",
            "map charts require latitude and longitude field mappings",
        )
    points: list[tuple[dict[str, Any], float, float]] = []
    for row in rows:
        latitude = _number(row.get(latitude_field))
        longitude = _number(row.get(longitude_field))
        if latitude is None or longitude is None:
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        points.append((row, latitude, longitude))
    return points


def _scatter_payload(
    points: list[tuple[dict[str, Any], float, float]],
    fields: dict[str, str],
    view_state: dict[str, float],
    title: str,
    style: dict[str, Any] | None,
) -> dict[str, Any]:
    data = []
    for row, latitude, longitude in points:
        item: dict[str, Any] = {"position": [longitude, latitude]}
        for role in ("value", "size", "label"):
            field = fields.get(role)
            if field and row.get(field) is not None:
                item[role] = row[field]
        data.append(item)
    return {
        "layers": [
            {
                "type": "scatter",
                "data": data,
                "radiusMinPixels": 3,
                "radiusMaxPixels": 26,
            }
        ],
        "viewState": view_state,
        "style": _style(style),
        "title": title,
    }


def _trajectory_payload(
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    points: list[tuple[dict[str, Any], float, float]],
    view_state: dict[str, float],
    title: str,
    style: dict[str, Any] | None,
) -> dict[str, Any]:
    track_field = fields.get("track")
    time_field = fields.get("time")
    value_field = fields.get("value")
    label_field = fields.get("label")
    groups: dict[str, list[tuple[dict[str, Any], float, float]]] = {}
    for item in points:
        row = item[0]
        key = (
            str(row.get(track_field))
            if track_field and row.get(track_field) is not None
            else "path"
        )
        groups.setdefault(key, []).append(item)

    paths = []
    for key, group in sorted(groups.items()):
        if time_field:
            group.sort(
                key=lambda item: (item[0].get(time_field) is None, str(item[0].get(time_field)))
            )
        path = [[longitude, latitude] for _, latitude, longitude in group]
        if len(path) < 2:
            continue
        entry: dict[str, Any] = {"path": path, "label": key}
        if value_field:
            values = [_number(row.get(value_field)) for row, _, _ in group]
            entry["values"] = values
        if label_field and group[0][0].get(label_field) is not None:
            entry["label"] = str(group[0][0][label_field])
        paths.append(entry)
    if not paths:
        raise RenderError("empty_geo", "trajectory requires at least two points per track")
    return {
        "layers": [
            {
                "type": "path",
                "data": paths,
                "widthMinPixels": 1,
                "widthMaxPixels": 8,
            }
        ],
        "viewState": view_state,
        "style": _style(style),
        "title": title,
        "meta": {"track_count": len(paths)},
    }


def _density_payload(
    fields: dict[str, str],
    points: list[tuple[dict[str, Any], float, float]],
    view_state: dict[str, float],
    title: str,
    style: dict[str, Any] | None,
) -> dict[str, Any]:
    weight_field = fields.get("weight")
    data = []
    for row, latitude, longitude in points:
        weight = _number(row.get(weight_field)) if weight_field else 1.0
        data.append(
            {
                "position": [longitude, latitude],
                "weight": abs(weight) if weight is not None else 1.0,
            }
        )
    return {
        "layers": [
            {
                "type": "hexagon",
                "data": data,
                "radius": 20000,
                "elevationScale": 4,
            }
        ],
        "viewState": view_state,
        "style": _style(style),
        "title": title,
        "meta": {"point_count": len(data)},
    }


def _region_payload(
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    title: str,
    style: dict[str, Any] | None,
) -> dict[str, Any]:
    region_field = fields.get("region")
    value_field = fields.get("value")
    if not region_field or not value_field:
        raise RenderError("invalid_fields", "region map requires region and value fields")
    totals: dict[str, float] = {}
    for row in rows:
        region = row.get(region_field)
        value = _number(row.get(value_field))
        if region is None or value is None:
            continue
        key = str(region)
        totals[key] = totals.get(key, 0.0) + value
    if not totals:
        raise RenderError("empty_geo", "region map has no valid region/value pairs")
    return {
        "layers": [
            {
                "type": "region",
                "data": [
                    {"region": region, "value": round(value, 6)}
                    for region, value in sorted(totals.items())
                ],
            }
        ],
        "viewState": {"longitude": 0.0, "latitude": 20.0, "zoom": 1.15, "pitch": 0, "bearing": 0},
        "regionMode": "country",
        "style": _style(style),
        "title": title,
        "meta": {"region_count": len(totals)},
    }


def _view_state(coordinates: list[tuple[float, float]]) -> dict[str, float]:
    longitudes = [lon for lon, _ in coordinates]
    latitudes = [lat for _, lat in coordinates]
    center_lon = (min(longitudes) + max(longitudes)) / 2
    center_lat = (min(latitudes) + max(latitudes)) / 2
    span_lon = max(longitudes) - min(longitudes)
    span_lat = max(latitudes) - min(latitudes)
    span = max(span_lon, span_lat, 0.05)
    zoom = max(0.8, min(8.0, 7.0 - math.log2(span / 0.1)))
    return {
        "longitude": round(center_lon, 6),
        "latitude": round(center_lat, 6),
        "zoom": round(zoom, 3),
        "pitch": 0,
        "bearing": 0,
    }


def _style(style: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(style, dict):
        return {}
    return {
        key: style[key]
        for key in ("title", "color", "colorscale", "colorscale_min", "colorscale_max")
        if key in style
    }


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

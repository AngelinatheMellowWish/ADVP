"""Build Cytoscape.js network payloads from table rows."""

from __future__ import annotations

from typing import Any

from advp.charts.errors import RenderError


def build_network_payload(
    *,
    fields: dict[str, str],
    rows: list[dict[str, Any]],
    title: str,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return Cytoscape elements plus layout and display hints."""
    source_field = fields.get("source")
    target_field = fields.get("target")
    if not source_field or not target_field:
        raise RenderError(
            "invalid_fields",
            "network graphs require source and target fields",
        )
    if source_field == target_field:
        raise RenderError(
            "invalid_fields",
            "network source and target must be different fields",
        )

    weight_field = fields.get("weight")
    label_field = fields.get("label")
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        source = _text(row.get(source_field))
        target = _text(row.get(target_field))
        if not source or not target:
            continue
        nodes.setdefault(source, {"data": {"id": source, "label": source}})
        nodes.setdefault(target, {"data": {"id": target, "label": target}})
        data: dict[str, Any] = {
            "id": f"edge-{index}",
            "source": source,
            "target": target,
        }
        weight = _number(row.get(weight_field)) if weight_field else None
        if weight is not None:
            data["weight"] = weight
        if label_field and row.get(label_field) is not None:
            data["label"] = str(row.get(label_field))
        edges.append({"data": data})

    if not edges:
        raise RenderError("empty_data", "network graph has no valid source/target pairs")

    node_limit = 500
    if len(nodes) > node_limit:
        kept = _top_nodes(nodes, edges, node_limit)
        nodes = {key: value for key, value in nodes.items() if key in kept}
        edges = [
            edge
            for edge in edges
            if edge["data"]["source"] in kept and edge["data"]["target"] in kept
        ]

    payload = {
        "elements": {
            "nodes": sorted(nodes.values(), key=lambda item: item["data"]["id"]),
            "edges": edges,
        },
        "layouts": ["cose", "circle", "grid", "breadthfirst"],
        "style": {
            "title": style.get("title") if isinstance(style, dict) else None,
            "color": style.get("color") if isinstance(style, dict) else None,
        },
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "truncated_nodes": len(nodes) >= node_limit,
        },
        "title": title,
    }
    return payload


def _top_nodes(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    limit: int,
) -> set[str]:
    totals: dict[str, float] = {node_id: 0.0 for node_id in nodes}
    for edge in edges:
        weight = abs(float(edge["data"].get("weight", 1.0)))
        totals[edge["data"]["source"]] += weight
        totals[edge["data"]["target"]] += weight
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return {node_id for node_id, _ in ordered[:limit]}


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

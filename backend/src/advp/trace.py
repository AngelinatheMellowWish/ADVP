"""Read-only traceability, lineage, and run comparison projections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from advp import __version__, pipelines
from advp.models import ChartSelection, Dataset, PipelineRun, PipelineStep


def build_trace(session: Session, run: PipelineRun) -> dict[str, Any]:
    """Build a traceability view for one pipeline run."""
    steps = pipelines.list_steps(session, run.id)
    source_dataset = session.get(Dataset, run.dataset_id)
    working_dataset = session.get(
        Dataset,
        str(run.options.get("working_dataset_id") or run.dataset_id),
    )
    selection = _selection_for_steps(session, steps)
    nodes = [_node(step, selection) for step in steps]
    lineage = _lineage(source_dataset, working_dataset, selection, steps, run)
    report_step = next((step for step in steps if step.key == "report"), None)
    artifacts = _artifacts(run, selection, report_step)
    total_duration = _duration_ms(run.started_at, run.finished_at)
    usage = (selection.result_json or {}).get("usage") if selection else {}
    return {
        "run": {
            "id": run.id,
            "project_id": run.project_id,
            "dataset_id": run.dataset_id,
            "parent_run_id": run.parent_run_id,
            "status": run.status,
            "current_step": run.current_step,
            "error": run.error,
            "created_at": _iso(run.created_at),
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
            "duration_ms": total_duration,
            "options": _safe_options(run.options),
        },
        "summary": {
            "node_count": len(nodes),
            "succeeded": sum(1 for node in nodes if node["status"] == "succeeded"),
            "failed": sum(1 for node in nodes if node["status"] == "failed"),
            "duration_ms": total_duration,
            "selection_id": selection.id if selection else None,
            "chart_id": selection.selected_chart_id if selection else None,
            "provider_name": selection.provider_name if selection else None,
            "model": selection.model if selection else None,
            "prompt_version": selection.prompt_version if selection else None,
            "input_tokens": int(usage.get("input_tokens") or 0) if usage else 0,
            "output_tokens": int(usage.get("output_tokens") or 0) if usage else 0,
            "estimated_cost": float(usage.get("estimated_cost") or 0.0) if usage else 0.0,
            "currency": str(usage.get("currency") or "USD") if usage else "USD",
            "retries": sum(max(0, step.attempts - 1) for step in steps),
        },
        "nodes": nodes,
        "edges": [
            {"from": steps[index - 1].key, "to": steps[index].key} for index in range(1, len(steps))
        ],
        "lineage": lineage,
        "artifacts": artifacts,
        "app_version": __version__,
    }


def trace_markdown(trace: dict[str, Any]) -> str:
    """Render a traceability view as Markdown for export or a report appendix."""
    run = trace["run"]
    summary = trace["summary"]
    lines = [
        "# ADVP 追溯报告",
        "",
        f"- 运行：`{run['id']}`",
        f"- 状态：`{run['status']}`",
        f"- 总耗时：{summary['duration_ms']} ms",
        f"- 应用版本：{trace['app_version']}",
        f"- Provider：`{summary['provider_name'] or '无'}`",
        f"- 模型：`{summary['model'] or '无'}`",
        f"- 提示词版本：`{summary['prompt_version'] or '无'}`",
        f"- Token：{summary['input_tokens']} / {summary['output_tokens']}",
        f"- 估算费用：{summary['estimated_cost']} {summary['currency']}",
        "",
        "## 步骤",
        "",
        "| 步骤 | 状态 | 耗时(ms) | 尝试 | 模型 | Token | 费用 | 错误 |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ]
    for node in trace["nodes"]:
        tokens = f"{node['input_tokens']} / {node['output_tokens']}"
        lines.append(
            f"| {node['name']} | {node['status']} | {node['duration_ms']} | "
            f"{node['attempts']} | {node['model'] or '-'} | {tokens} | "
            f"{node['estimated_cost']} {node['currency']} | {_md(node['error'] or '')} |"
        )
    lines.extend(["", "## 数据血缘", ""])
    if trace["lineage"]:
        for index, item in enumerate(trace["lineage"], start=1):
            detail = f"{item['kind']} · {item['name']} · `{item['id']}`"
            if item.get("row_count") is not None:
                detail += f" · {item['row_count']} 行/元素"
            if item.get("sampled"):
                detail += " · 采样"
            lines.append(f"{index}. {detail}")
    else:
        lines.append("暂无血缘记录。")
    lines.extend(["", "## 产物", ""])
    for name, value in trace["artifacts"].items():
        if value:
            lines.append(f"- {name}：`{value}`")
    lines.extend(
        [
            "",
            "## 限制",
            "",
            "- 追溯信息来自本地运行记录；删除运行或数据集后无法还原。",
            "- 费用为按 Provider 价格表估算，不代表供应商账单。",
            "- 日志与追溯默认不包含 API Key 或完整敏感样本。",
            "",
        ]
    )
    return "\n".join(lines)


def compare_runs(
    session: Session,
    left: PipelineRun,
    right: PipelineRun,
) -> dict[str, Any]:
    """Compare step status, duration, and cost between two runs."""
    left_steps = {step.key: step for step in pipelines.list_steps(session, left.id)}
    right_steps = {step.key: step for step in pipelines.list_steps(session, right.id)}
    keys = [key for key, _ in pipelines.STEP_DEFINITIONS]
    left_selection = _selection_for_steps(session, list(left_steps.values()))
    right_selection = _selection_for_steps(session, list(right_steps.values()))
    rows = []
    for key in keys:
        left_step = left_steps.get(key)
        right_step = right_steps.get(key)
        left_cost = _selection_cost(left_selection) if key == "selection" else 0.0
        right_cost = _selection_cost(right_selection) if key == "selection" else 0.0
        rows.append(
            {
                "key": key,
                "left": _compare_step(left_step, left_cost),
                "right": _compare_step(right_step, right_cost),
                "duration_delta_ms": _step_duration(right_step) - _step_duration(left_step),
                "cost_delta": round(right_cost - left_cost, 8),
                "changed": bool(
                    (left_step.status if left_step else None)
                    != (right_step.status if right_step else None)
                ),
            }
        )
    return {
        "left_run_id": left.id,
        "right_run_id": right.id,
        "steps": rows,
        "changed": any(row["changed"] for row in rows),
        "left_status": left.status,
        "right_status": right.status,
        "left_duration_ms": _duration_ms(left.started_at, left.finished_at),
        "right_duration_ms": _duration_ms(right.started_at, right.finished_at),
        "left_cost": round(_selection_cost(left_selection), 8),
        "right_cost": round(_selection_cost(right_selection), 8),
    }


def _node(step: PipelineStep, selection: ChartSelection | None) -> dict[str, Any]:
    usage = (selection.result_json or {}).get("usage") if selection else {}
    is_selection = step.key == "selection"
    return {
        "id": step.id,
        "key": step.key,
        "name": step.name,
        "position": step.position,
        "status": step.status,
        "attempts": step.attempts,
        "retries": max(0, step.attempts - 1),
        "placeholder": step.placeholder,
        "duration_ms": _duration_ms(step.started_at, step.finished_at),
        "started_at": _iso(step.started_at),
        "finished_at": _iso(step.finished_at),
        "error": step.error,
        "output_summary": _output_summary(step.key, step.output_json),
        "provider_name": selection.provider_name if is_selection and selection else None,
        "model": selection.model if is_selection and selection else None,
        "prompt_version": selection.prompt_version if is_selection and selection else None,
        "selection_id": selection.id if is_selection and selection else None,
        "input_tokens": int(usage.get("input_tokens") or 0) if usage else 0,
        "output_tokens": int(usage.get("output_tokens") or 0) if usage else 0,
        "estimated_cost": float(usage.get("estimated_cost") or 0.0) if usage else 0.0,
        "currency": str(usage.get("currency") or "USD") if usage else "USD",
    }


def _output_summary(key: str, output: dict[str, Any]) -> dict[str, Any]:
    if key == "profile":
        return _pick(output, "row_count", "column_count", "quality_score", "sampled")
    if key == "clean":
        return _pick(
            output,
            "skipped",
            "before_rows",
            "after_rows",
            "derived_dataset_id",
            "truncated",
        )
    if key == "candidates":
        return _pick(output, "candidate_count")
    if key == "analyze":
        return _pick(output, "summary", "sample_size", "sampled")
    if key == "selection":
        return _pick(
            output,
            "selection_id",
            "chart_id",
            "score",
            "degraded",
            "needs_confirmation",
            "provider_name",
        )
    if key == "render":
        return _pick(output, "selection_id", "chart_id", "renderer", "row_count", "sampled")
    if key == "report":
        return _pick(output, "bytes", "selection_id", "summary")
    return {"keys": sorted(output)}


def _lineage(
    source: Dataset | None,
    working: Dataset | None,
    selection: ChartSelection | None,
    steps: list[PipelineStep],
    run: PipelineRun,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if source is not None:
        items.append(_dataset_item(source, "source"))
    clean_step = next((step for step in steps if step.key == "clean"), None)
    derived_id = (clean_step.output_json or {}).get("derived_dataset_id") if clean_step else None
    if working is not None and working.id != (source.id if source else None):
        items.append(_dataset_item(working, "derived"))
    elif derived_id and source is not None and derived_id != source.id:
        items.append(
            {
                "kind": "derived",
                "id": str(derived_id),
                "name": "cleaned dataset",
                "format": source.format,
                "row_count": None,
                "sha256": None,
                "sampled": False,
            }
        )
    if selection is not None:
        items.append(
            {
                "kind": "chart",
                "id": selection.id,
                "name": selection.selected_chart_id,
                "format": "chart",
                "row_count": None,
                "sha256": None,
                "sampled": False,
            }
        )
    report_step = next((step for step in steps if step.key == "report"), None)
    if report_step is not None and report_step.status == "succeeded":
        items.append(
            {
                "kind": "report",
                "id": run.id,
                "name": "Markdown 报告",
                "format": "markdown",
                "row_count": None,
                "sha256": None,
                "sampled": False,
            }
        )
    return items


def _dataset_item(dataset: Dataset, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": dataset.id,
        "name": dataset.name,
        "format": dataset.format,
        "row_count": dataset.row_count,
        "sha256": dataset.source_sha256,
        "sampled": dataset.sampled,
    }


def _artifacts(
    run: PipelineRun,
    selection: ChartSelection | None,
    report_step: PipelineStep | None,
) -> dict[str, Any]:
    return {
        "trace": f"/api/pipeline-runs/{run.id}/trace",
        "trace_markdown": f"/api/pipeline-runs/{run.id}/trace/export?format=markdown",
        "report": f"/api/pipeline-runs/{run.id}/report"
        if report_step is not None and report_step.status == "succeeded"
        else None,
        "figure": f"/api/chart-selections/{selection.id}/figure" if selection else None,
        "code": f"/api/chart-selections/{selection.id}/code" if selection else None,
    }


def _selection_for_steps(
    session: Session,
    steps: list[PipelineStep],
) -> ChartSelection | None:
    selection_step = next((step for step in steps if step.key == "selection"), None)
    selection_id = (
        (selection_step.output_json or {}).get("selection_id") if selection_step else None
    )
    if not selection_id:
        return None
    return session.get(ChartSelection, str(selection_id))


def _selection_cost(selection: ChartSelection | None) -> float:
    return float(selection.estimated_cost) if selection else 0.0


def _compare_step(step: PipelineStep | None, cost: float) -> dict[str, Any]:
    if step is None:
        return {"status": None, "duration_ms": 0, "attempts": 0, "cost": cost, "error": None}
    return {
        "status": step.status,
        "duration_ms": _duration_ms(step.started_at, step.finished_at),
        "attempts": step.attempts,
        "cost": cost,
        "error": step.error,
    }


def _step_duration(step: PipelineStep | None) -> int:
    return _duration_ms(step.started_at, step.finished_at) if step else 0


def _duration_ms(start: datetime | None, end: datetime | None) -> int:
    if start is None or end is None:
        return 0
    return max(0, int((_aware(end) - _aware(start)).total_seconds() * 1000))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).isoformat()


def _pick(values: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: values.get(key) for key in keys if key in values}


def _safe_options(options: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "intent",
        "provider_id",
        "max_reselects",
        "confirm_high_risk",
        "working_dataset_id",
        "rerun_from_step",
        "rerun_source_run_id",
        "report_language",
        "report_template",
    }
    return {key: options.get(key) for key in allowed if key in options}


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")

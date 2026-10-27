"""Markdown and HTML report generation from a completed pipeline run."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from advp import __version__
from advp.config import get_settings
from advp.models import ChartSelection, Dataset, PipelineRun, PipelineStep

LANGUAGES = {"zh", "en"}
TEMPLATES = {"standard", "compact"}
TEXT: dict[str, dict[str, str]] = {
    "zh": {
        "title": "ADVP 分析报告",
        "dataset": "数据集",
        "generated": "生成时间",
        "app_version": "应用版本",
        "run": "管线运行",
        "source": "源数据集",
        "working": "工作数据集",
        "sha": "源 SHA-256",
        "text_stats_source": "文本统计抽取",
        "overview": "数据概览",
        "metric": "指标",
        "value": "值",
        "rows": "行数",
        "columns": "列数",
        "quality": "质量评分",
        "missing": "缺失单元",
        "sampled": "采样画像",
        "yes": "是",
        "no": "否",
        "quality_section": "数据质量",
        "issue_counts": "问题计数",
        "cleaning": "清洗",
        "analysis": "分析摘要",
        "no_analysis": "暂无分析摘要。",
        "summary": "摘要",
        "correlations": "相关列",
        "strength": "强度",
        "temporal": "时间列",
        "geo": "地理范围",
        "array": "数组",
        "chart": "图表选型",
        "no_selection": "暂无选型结果。",
        "fields": "字段",
        "aggregation": "聚合",
        "score": "评分",
        "confidence": "置信度",
        "reason": "理由",
        "style": "样式",
        "pipeline": "管线与成本",
        "step": "步骤",
        "status": "状态",
        "attempts": "尝试",
        "placeholder": "占位",
        "provider": "Provider",
        "tokens": "输入/输出 Token",
        "cost": "估算费用",
        "degraded": "降级",
        "conclusion": "结论",
        "default_conclusion": (
            "本报告由规则筛选与 AI 选型结果自动生成；请结合领域知识复核图表结论与数据限制。"
        ),
        "repro": "复现与限制",
        "selection_record": "选型记录",
        "figure_json": "图表 JSON",
        "report_formats": "报告同时提供 Markdown、HTML 与 PDF（PDF 由 HTML 打印）。",
        "sampling_note": "渲染使用 ADVP_RENDER_SAMPLE_ROWS（默认 20,000，上限 100,000）；"
        "分析使用 ADVP_ANALYSIS_SAMPLE_ROWS（默认 10,000，上限 100,000）；"
        "清洗最多使用 100,000 行预览。",
        "pricing_note": "模型与价格见选型记录与 Provider 配置；估算费用不代表供应商账单。",
        "appendix": "附录：追溯与血缘",
        "duration": "耗时",
        "retries": "重试",
        "error": "错误",
        "lineage": "数据血缘",
        "limitations": "限制：追溯来自本地运行记录；费用为估算值；日志不包含 API Key。",
        "chart_alt": "图表",
    },
    "en": {
        "title": "ADVP Analysis Report",
        "dataset": "Dataset",
        "generated": "Generated at",
        "app_version": "App version",
        "run": "Pipeline run",
        "source": "Source dataset",
        "working": "Working dataset",
        "sha": "Source SHA-256",
        "text_stats_source": "Text statistics extraction",
        "overview": "Data overview",
        "metric": "Metric",
        "value": "Value",
        "rows": "Rows",
        "columns": "Columns",
        "quality": "Quality score",
        "missing": "Missing cells",
        "sampled": "Sampled profile",
        "yes": "yes",
        "no": "no",
        "quality_section": "Data quality",
        "issue_counts": "Issue counts",
        "cleaning": "Cleaning",
        "analysis": "Analysis summary",
        "no_analysis": "No analysis summary.",
        "summary": "Summary",
        "correlations": "Correlations",
        "strength": "Strength",
        "temporal": "Temporal",
        "geo": "Geographic range",
        "array": "Array",
        "chart": "Chart selection",
        "no_selection": "No selection result.",
        "fields": "Fields",
        "aggregation": "Aggregation",
        "score": "Score",
        "confidence": "Confidence",
        "reason": "Reason",
        "style": "Style",
        "pipeline": "Pipeline and cost",
        "step": "Step",
        "status": "Status",
        "attempts": "Attempts",
        "placeholder": "Placeholder",
        "provider": "Provider",
        "tokens": "Input/output tokens",
        "cost": "Estimated cost",
        "degraded": "Degraded",
        "conclusion": "Conclusion",
        "default_conclusion": "This report is generated from rule candidates and AI selection. "
        "Review the chart conclusions and data limitations with domain knowledge.",
        "repro": "Reproducibility and limitations",
        "selection_record": "Selection record",
        "figure_json": "Figure JSON",
        "report_formats": (
            "Reports are available as Markdown, HTML, and PDF (PDF printed from HTML)."
        ),
        "sampling_note": "Rendering uses ADVP_RENDER_SAMPLE_ROWS (default 20,000, max 100,000); "
        "analysis uses ADVP_ANALYSIS_SAMPLE_ROWS (default 10,000, max 100,000); "
        "cleaning uses at most 100,000 preview rows.",
        "pricing_note": "Models and prices come from the selection record and provider settings; "
        "estimated cost is not a provider invoice.",
        "appendix": "Appendix: traceability and lineage",
        "duration": "Duration",
        "retries": "Retries",
        "error": "Error",
        "lineage": "Lineage",
        "limitations": (
            "Limitations: trace data is local; cost is estimated; logs exclude API keys."
        ),
        "chart_alt": "Chart",
    },
}


def report_directory(run: PipelineRun) -> Path:
    """Return the report output directory for a run."""
    directory = get_settings().workspace_dir / "exports" / run.project_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_report_bundle(
    dataset: Dataset,
    run: PipelineRun,
    prior: dict[str, dict[str, Any]],
    selection: ChartSelection | None,
    steps: list[PipelineStep],
    *,
    language: str = "zh",
    template: str = "standard",
    conclusion: str | None = None,
    chart_image: Path | None = None,
    chart_note: str | None = None,
) -> dict[str, Any]:
    """Write Markdown, HTML, and manifest files and return their paths and sizes."""
    directory = report_directory(run)
    markdown = build_report(
        dataset,
        run,
        prior,
        selection,
        steps,
        language=language,
        template=template,
        conclusion=conclusion,
        chart_image=chart_image.name if chart_image else None,
        chart_note=chart_note,
    )
    md_path = directory / f"report_{run.id}.md"
    html_path = directory / f"report_{run.id}.html"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(build_report_html(markdown, language=language), encoding="utf-8")
    result = (selection.result_json or {}) if selection else {}
    selected = result.get("selected") or {}
    manifest = {
        "app_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run.id,
        "project_id": run.project_id,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "source_sha256": dataset.source_sha256,
        "chart_id": selected.get("chart_id")
        or (selection.selected_chart_id if selection else None),
        "provider_name": selection.provider_name if selection else None,
        "model": selection.model if selection else None,
        "prompt_version": selection.prompt_version if selection else None,
        "language": language,
        "template": template,
        "custom_conclusion": bool(conclusion and conclusion.strip()),
        "parameters": {
            "report_language": language,
            "report_template": template,
            "report_include_chart": chart_image is not None,
        },
        "files": {
            "markdown": md_path.name,
            "html": html_path.name,
            "chart": chart_image.name if chart_image else None,
        },
        "trace_url": f"/api/pipeline-runs/{run.id}/trace",
    }
    manifest_path = directory / f"manifest_{run.id}.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "directory": str(directory),
        "md_path": str(md_path),
        "html_path": str(html_path),
        "manifest_path": str(manifest_path),
        "chart_path": str(chart_image) if chart_image else None,
        "bytes": md_path.stat().st_size,
        "html_bytes": html_path.stat().st_size,
        "language": language,
        "template": template,
        "manifest": manifest,
    }


def write_report(
    dataset: Dataset,
    run: PipelineRun,
    prior: dict[str, dict[str, Any]],
    selection: ChartSelection | None,
    steps: list[PipelineStep],
    **kwargs: Any,
) -> Path:
    """Write a Markdown report into the workspace and return its path."""
    return Path(write_report_bundle(dataset, run, prior, selection, steps, **kwargs)["md_path"])


def build_report(
    dataset: Dataset,
    run: PipelineRun,
    prior: dict[str, dict[str, Any]],
    selection: ChartSelection | None,
    steps: list[PipelineStep],
    *,
    language: str = "zh",
    template: str = "standard",
    conclusion: str | None = None,
    chart_image: str | None = None,
    chart_note: str | None = None,
) -> str:
    """Build a Markdown report with profile, analysis, selection, and lineage."""
    lang = language if language in LANGUAGES else "zh"
    mode = template if template in TEMPLATES else "standard"
    text = TEXT[lang]
    profile = prior.get("profile") or {}
    analysis = prior.get("analyze", {}).get("analysis") or {}
    result = (selection.result_json or {}) if selection else {}
    selected = result.get("selected")
    top3 = result.get("top3") or []
    lines: list[str] = [
        f"# {text['title']}",
        "",
        f"- {text['dataset']}：{_md(dataset.name)}",
        f"- {text['generated']}：{datetime.now(UTC).isoformat()}",
        f"- {text['app_version']}：{__version__}",
        f"- {text['run']}：`{run.id}`",
        f"- {text['source']}：`{run.dataset_id}`",
        f"- {text['working']}：`{dataset.id}`",
        f"- {text['sha']}：`{dataset.source_sha256}`",
    ]
    source_kind = (dataset.options or {}).get("source_kind")
    if source_kind == "text_stats":
        stats = (dataset.options or {}).get("text_stats") or {}
        if lang == "zh":
            method = "AI 增强" if stats.get("ai_used") else "本地规则"
            lines.append(
                f"- {text['text_stats_source']}：{stats.get('shape', 'long')}表 / "
                f"{method}；导入前须人工确认，原文件不复制。"
            )
        else:
            method = "AI-enhanced" if stats.get("ai_used") else "rule-based"
            lines.append(
                f"- {text['text_stats_source']}：{stats.get('shape', 'long')} table / "
                f"{method}; manual confirmation is required and the source file is not copied."
            )
    lines.extend(
        [
            "",
            f"## 1. {text['overview']}",
            "",
            f"| {text['metric']} | {text['value']} |",
            "|---|---|",
            f"| {text['rows']} | {profile.get('row_count', dataset.row_count)} |",
            f"| {text['columns']} | {profile.get('column_count', dataset.column_count)} |",
            f"| {text['quality']} | {profile.get('quality_score', '—')} |",
            f"| {text['missing']} | {profile.get('missing_cells', '—')} |",
            f"| {text['sampled']} | "
            f"{text['yes'] if profile.get('sampled', dataset.sampled) else text['no']} |",
            "",
            f"## 2. {text['quality_section']}",
            "",
            f"- {text['issue_counts']}：`{profile.get('issue_counts') or {}}`",
            f"- {text['cleaning']}：`{prior.get('clean') or {'skipped': True}}`",
            "",
            f"## 3. {text['analysis']}",
            "",
        ]
    )
    lines.extend(_analysis_lines(analysis, lang, text))
    lines.extend(["", f"## 4. {text['chart']}", ""])
    if chart_image:
        lines.extend([f"![{text['chart_alt']}]({chart_image})", ""])
    elif chart_note:
        figure_url = f"/api/chart-selections/{selection.id}/figure" if selection else ""
        lines.extend(
            [
                f"- {text['chart_alt']}：未嵌入（{_md(chart_note)}）",
                f"- {text['figure_json']}：`{figure_url}`" if figure_url else "",
                "",
            ]
        )
    lines.extend(_selection_lines(selected, top3, lang, text, compact=mode == "compact"))
    lines.extend(
        [
            "",
            f"## 5. {text['pipeline']}",
            "",
            f"| {text['step']} | {text['status']} | {text['attempts']} | {text['placeholder']} |",
            "|---|---|---:|---|",
        ]
    )
    for step in steps:
        lines.append(
            f"| {_md(step.name)} | {step.status} | {step.attempts} | "
            f"{text['yes'] if step.placeholder else text['no']} |"
        )
    usage = prior.get("selection", {}).get("usage") or {}
    lines.extend(
        [
            "",
            f"- {text['provider']}：`{prior.get('selection', {}).get('provider_name') or '—'}`",
            f"- {text['tokens']}：{usage.get('input_tokens', 0)} / {usage.get('output_tokens', 0)}",
            f"- {text['cost']}：{usage.get('estimated_cost', 0)} {usage.get('currency', 'USD')}",
            f"- {text['degraded']}："
            f"{text['yes'] if prior.get('selection', {}).get('degraded') else text['no']}",
            "",
            f"## 6. {text['repro']}",
            "",
            f"- {text['selection_record']}：`{selection.id if selection else '—'}`",
            f"- {text['figure_json']}：`GET /api/chart-selections/"
            f"{selection.id if selection else '—'}/figure`",
            f"- {text['report_formats']}",
            f"- {text['sampling_note']}",
            f"- {text['pricing_note']}",
            f"- {text['limitations']}",
            "",
        ]
    )
    if mode == "standard":
        lines.extend(_trace_appendix(steps, selection, text))
    lines.extend(["", f"## 7. {text['conclusion']}", ""])
    lines.append(
        conclusion.strip() if conclusion and conclusion.strip() else text["default_conclusion"]
    )
    lines.append("")
    return "\n".join(lines)


def build_report_html(markdown: str, *, language: str = "zh") -> str:
    """Render the controlled report Markdown as a standalone HTML document."""
    lang = language if language in LANGUAGES else "zh"
    body = _markdown_to_html(markdown)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ADVP Report</title>
  <style>
    body {{ margin: 0; background: #f7f9fc; color: #142033;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 40px 64px; background: #ffffff; }}
    h1 {{ font-size: 28px; margin: 0 0 16px; }}
    h2 {{ font-size: 20px; margin-top: 28px; border-bottom: 1px solid #dce5f0;
      padding-bottom: 6px; }}
    h3 {{ font-size: 16px; margin-top: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
    th, td {{ border: 1px solid #dce5f0; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef4fb; }}
    code {{ background: #eef2f7; padding: 1px 4px; border-radius: 4px; font-size: 12px; }}
    pre {{ background: #0f172a; color: #e2e8f0; padding: 12px;
      border-radius: 8px; overflow: auto; }}
    figure {{ margin: 16px 0; }}
    img {{ max-width: 100%; border: 1px solid #dce5f0; border-radius: 8px; }}
    ul, ol {{ padding-left: 22px; }}
    li {{ margin: 4px 0; }}
    @media print {{ main {{ max-width: none; padding: 0; }} body {{ background: #ffffff; }} }}
  </style>
</head>
<body><main>
{body}
</main></body>
</html>
"""


def _analysis_lines(
    analysis: dict[str, Any],
    lang: str,
    text: dict[str, str],
) -> list[str]:
    if not analysis:
        return [text["no_analysis"]]
    lines = [f"- {text['summary']}：{analysis.get('summary', '—')}", ""]
    correlations = analysis.get("correlations") or []
    if correlations:
        lines.extend([f"| {text['correlations']} | r | {text['strength']} |", "|---|---:|---|"])
        for item in correlations:
            lines.append(
                f"| {_md(str(item.get('left')))} × {_md(str(item.get('right')))} | "
                f"{item.get('r')} | {item.get('strength')} |"
            )
        lines.append("")
    for item in analysis.get("temporal") or []:
        lines.append(
            f"- {text['temporal']} {_md(str(item.get('name')))}：{item.get('start')} → "
            f"{item.get('end')}，max gap {item.get('max_gap_seconds')} s"
        )
    if analysis.get("geo"):
        lines.append(f"- {text['geo']}：`{analysis['geo']}`")
    if analysis.get("array"):
        lines.append(f"- {text['array']}：`{analysis['array']}`")
    return lines


def _selection_lines(
    selected: dict[str, Any] | None,
    top3: list[dict[str, Any]],
    lang: str,
    text: dict[str, str],
    *,
    compact: bool,
) -> list[str]:
    if not selected:
        return [text["no_selection"]]
    name = selected.get("name") or {}
    chart_name = name.get(lang) or name.get("zh") or selected.get("chart_id")
    lines = [
        f"- {text['chart']}：**{_md(str(chart_name))}** (`{selected.get('chart_id')}`)",
        f"- {text['fields']}：`{selected.get('fields')}`",
        f"- {text['aggregation']}：`{selected.get('aggregation')}`",
        f"- {text['score']}：{selected.get('score')} · "
        f"{text['confidence']}：{selected.get('confidence')}",
        f"- {text['reason']}：{_md(str(selected.get('reason')))}",
    ]
    if selected.get("style"):
        lines.append(f"- {text['style']}：`{selected.get('style')}`")
    if top3 and not compact:
        lines.extend(["", "### Top3", ""])
        for index, item in enumerate(top3, start=1):
            item_name = item.get("name") or {}
            label = item_name.get(lang) or item_name.get("zh") or item.get("chart_id")
            lines.append(
                f"{index}. {_md(str(label))} · {item.get('score')} — {_md(str(item.get('reason')))}"
            )
    return lines


def _trace_appendix(
    steps: list[PipelineStep],
    selection: ChartSelection | None,
    text: dict[str, str],
) -> list[str]:
    lines = ["", f"## 6.1 {text['appendix']}", ""]
    lines.extend(
        [
            f"| {text['step']} | {text['status']} | {text['duration']} | "
            f"{text['attempts']} | {text['error']} |",
            "|---|---|---:|---:|---|",
        ]
    )
    for step in steps:
        duration = 0
        if step.started_at is not None and step.finished_at is not None:
            duration = max(
                0,
                int((_aware(step.finished_at) - _aware(step.started_at)).total_seconds() * 1000),
            )
        lines.append(
            f"| {_md(step.name)} | {step.status} | {duration} ms | {step.attempts} | "
            f"{_md(step.error or '')} |"
        )
    lines.extend(["", f"- {text['lineage']}：`{selection.id if selection else '—'}`"])
    lines.append(f"- {text['limitations']}")
    return lines


def _markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("```"):
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(block))}</code></pre>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        image = re.match(r"^!\[(.*?)\]\((.*?)\)$", line.strip())
        if image:
            alt = html.escape(image.group(1))
            src = html.escape(image.group(2), quote=True)
            out.append(f'<figure><img src="{src}" alt="{alt}" /></figure>')
            index += 1
            continue
        if line.lstrip().startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            out.append(_table_html(table_lines))
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items: list[str] = []
            while index < len(lines) and re.match(r"^\s*[-*]\s+", lines[index]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[index]))
                index += 1
            out.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>")
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            items = []
            while index < len(lines) and re.match(r"^\s*\d+\.\s+", lines[index]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[index]))
                index += 1
            out.append("<ol>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ol>")
            continue
        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip():
            if lines[index].startswith("#") or lines[index].startswith("```"):
                break
            if lines[index].lstrip().startswith("|") or re.match(r"^\s*[-*]\s+", lines[index]):
                break
            if re.match(r"^\s*\d+\.\s+", lines[index]):
                break
            paragraph.append(lines[index].strip())
            index += 1
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
    return "\n".join(out)


def _table_html(lines: list[str]) -> str:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in lines
        if not re.match(r"^\|?[\s:|-]+\|?$", line.strip())
    ]
    if not rows:
        return ""
    header, *body = rows
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in header)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in body
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body_html}</tbody></table>"


def _inline(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', escaped)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def export_filename(
    dataset: Dataset,
    selection: ChartSelection | None,
    extension: str,
) -> str:
    """Build a safe export name with dataset, chart, version, and timestamp."""
    chart = selection.selected_chart_id if selection is not None else "report"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw = f"ADVP_{dataset.name}_{chart}_v{__version__}_{stamp}.{extension}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")

"""Deterministic rule-based extraction of statistical facts from document text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from advp.config import get_settings
from advp.ingest.files import IngestError
from advp.ingest.text_readers import (
    BULLET_RE,
    TextBlock,
    TextDocument,
    TextLine,
)

NUMBER_TOKEN = r"\d[\d,]*(?:\.\d+)?"
MAGNITUDE = r"(?:万|亿)?"
RANGE_RE = re.compile(
    rf"(?P<low>{NUMBER_TOKEN}\s*{MAGNITUDE})\s*(?:—|–|－|-|至|~|～)\s*"
    rf"(?P<high>{NUMBER_TOKEN}\s*{MAGNITUDE})(?P<suffix>[^\d,;。]*)"
)
NUMBER_RE = re.compile(rf"(?P<num>{NUMBER_TOKEN}\s*{MAGNITUDE})")
PARENTHESIS_RE = re.compile(r"[（(]([^（）()]*)[)）]")
GENERIC_HEADING_RE = re.compile(r"(总量|说明|对比|分类|概况|概述|统计|背景|备注)")
UNIT_SUFFIXES = [
    "个合成集团军",
    "个集团军",
    "个师",
    "个旅",
    "个军",
    "亿美元",
    "平方米",
    "平方公里",
    "公里",
    "千米",
    "公斤",
    "千克",
    "美元",
    "小时",
    "个",
    "门",
    "辆",
    "架",
    "艘",
    "枚",
    "发",
    "台",
    "套",
    "件",
    "张",
    "所",
    "次",
    "吨",
    "人",
    "%",
    "倍",
    "元",
    "天",
    "年",
    "月",
    "日",
]
QUALIFIER_PREFIXES = {
    "at_least": ("超过", "至少", "以上", "不低于"),
    "at_most": ("最多", "不超过", "以内", "以下", "低于"),
    "estimated": ("估计", "估算"),
    "approx": ("约", "大约", "近", "余"),
}
METRIC_PREFIXES = (
    "另有材料称",
    "另有来源作",
    "另有来源称",
    "另有资料称",
    "其中",
    "编成内",
    "下辖",
    "共",
    "约",
    "仅",
    "即达",
)
METRIC_SUFFIXES = ("大约", "即达", "超过", "至少", "最多", "约", "为", "达", "共", "仅", "即")
CONTINUATION_PREFIXES = ("下辖", "其中", "另有", "含", "及", "又", "并")


class TextFactInvalidError(IngestError):
    code = "text_fact_invalid"
    status_code = 400


class TextSourceChangedError(IngestError):
    code = "text_source_changed"
    status_code = 409


@dataclass(slots=True)
class TextFact:
    fact_id: str
    subject_path: str
    metric: str
    value_text: str
    value_number: float | None
    value_low: float | None
    value_high: float | None
    unit: str | None
    qualifier: str | None
    relation: str
    note: str | None
    source: dict[str, object]
    confidence: float
    include: bool = True
    edited: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "subject_path": self.subject_path,
            "metric": self.metric,
            "value_text": self.value_text,
            "value_number": self.value_number,
            "value_low": self.value_low,
            "value_high": self.value_high,
            "unit": self.unit,
            "qualifier": self.qualifier,
            "relation": self.relation,
            "note": self.note,
            "source": self.source,
            "confidence": self.confidence,
            "include": self.include,
            "edited": self.edited,
        }


@dataclass(slots=True)
class TextExtraction:
    facts: list[TextFact]
    warnings: list[dict[str, str]]
    long_rows: list[dict[str, Any]]
    wide_headers: list[str]
    wide_rows: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "facts": [fact.as_dict() for fact in self.facts],
            "warnings": self.warnings,
            "long": {"rows": self.long_rows},
            "wide": {"headers": self.wide_headers, "rows": self.wide_rows},
        }


def extract_facts(document: TextDocument, *, max_facts: int | None = None) -> TextExtraction:
    """Extract numeric facts, warnings, and long/wide previews from a text document."""
    limit = max_facts if max_facts is not None else get_settings().text_max_facts
    facts: list[TextFact] = []
    warnings: list[dict[str, str]] = []
    active_subjects: list[str] = []

    for block_index, block in enumerate(document.blocks):
        heading_subject = _subject_from_heading(block.heading)
        if heading_subject and heading_subject not in active_subjects:
            active_subjects.append(heading_subject)
        base_subject = heading_subject or (
            active_subjects[-1] if len(active_subjects) == 1 else None
        )
        for line_index, line in enumerate(block.lines):
            for fact in _facts_from_line(
                line,
                block=block,
                block_index=block_index,
                line_index=line_index,
                base_subject=base_subject,
                active_subjects=active_subjects,
            ):
                facts.append(fact)

    facts = _deduplicate(facts, warnings)
    facts = _mark_alternatives(facts, warnings)
    _check_total_mismatch(facts, warnings)

    if len(facts) > limit:
        facts = facts[:limit]
        warnings.append(
            {
                "code": "text_fact_limit",
                "severity": "warning",
                "message": f"extracted facts were truncated to {limit}",
            }
        )
    if not facts:
        warnings.append(
            {
                "code": "no_numeric_facts",
                "severity": "warning",
                "message": "no numeric statistical facts were detected",
            }
        )

    for index, fact in enumerate(facts, start=1):
        fact.fact_id = f"fact-{index}"

    long_rows = [_long_row(fact) for fact in facts]
    wide_headers, wide_rows = _wide_preview(facts, warnings)
    return TextExtraction(
        facts=facts,
        warnings=warnings,
        long_rows=long_rows,
        wide_headers=wide_headers,
        wide_rows=wide_rows,
    )


def _facts_from_line(
    line: TextLine,
    *,
    block: TextBlock,
    block_index: int,
    line_index: int,
    base_subject: str | None,
    active_subjects: list[str],
) -> list[TextFact]:
    text = BULLET_RE.sub("", line.text).strip().rstrip("。")
    if not text or not _is_fact_line(line.text, text):
        return []
    subject_override, body = _split_subject_prefix(text, active_subjects)
    facts: list[TextFact] = []
    for clause in _split_clauses(body):
        facts.extend(
            _facts_from_clause(
                clause,
                line=line,
                block=block,
                block_index=block_index,
                line_index=line_index,
                base_subject=subject_override or base_subject,
                subject_override=subject_override,
            )
        )
    return facts


def _is_fact_line(raw: str, text: str) -> bool:
    if BULLET_RE.match(raw):
        return bool(NUMBER_RE.search(text))
    if ":" in text:
        metric, rest = text.split(":", 1)
        return len(metric.strip()) <= 30 and bool(NUMBER_RE.search(rest))
    return False


def _split_subject_prefix(text: str, active_subjects: list[str]) -> tuple[str | None, str]:
    if ":" not in text:
        return None, text
    left, right = text.split(":", 1)
    candidate = left.strip()
    if candidate in active_subjects:
        return candidate, right.strip()
    return None, text


def _split_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for piece in re.split(r"[;。]", text):
        piece = piece.strip(" ,;。")
        if not piece:
            continue
        if "其中" in piece or "另有" in piece:
            clauses.append(piece)
            continue
        parts = [part.strip() for part in re.split(r",\s+(?=\D*\d)", piece) if part.strip()]
        if parts:
            clauses.append(parts[0])
        clauses.extend(part for part in parts[1:] if not part.startswith(CONTINUATION_PREFIXES))
    return clauses


def _facts_from_clause(
    clause: str,
    *,
    line: TextLine,
    block: TextBlock,
    block_index: int,
    line_index: int,
    base_subject: str | None,
    subject_override: str | None,
) -> list[TextFact]:
    clause = clause.strip(" ,;。")
    if not clause or not NUMBER_RE.search(clause):
        return []

    metric_hint: str | None = None
    content = clause
    if ":" in clause:
        left, right = clause.split(":", 1)
        left = left.strip()
        if subject_override is None and left in (base_subject or "",):
            content = right.strip()
        else:
            metric_hint = left
            content = right.strip()

    outside, notes = _split_parentheses(content)
    value = _parse_value(outside)
    if value is None:
        value = _parse_value(content)
        if value is None:
            return []
    metric = _clean_metric(
        metric_hint or _metric_before_number(outside) or _metric_after_number(outside)
    )
    subject = subject_override or base_subject or "未命名"
    note_parts = list(notes)
    if value["note"]:
        note_parts.append(str(value["note"]))
    note = "；".join(part for part in note_parts if part) or None
    source = _source(line, block, block_index, line_index)
    confidence = _confidence(line.text, outside, value["unit"], block.heading)
    fact = TextFact(
        fact_id="",
        subject_path=subject,
        metric=metric,
        value_text=str(value["value_text"]),
        value_number=value["value_number"],
        value_low=value["value_low"],
        value_high=value["value_high"],
        unit=value["unit"],
        qualifier=value["qualifier"],
        relation="standalone",
        note=note,
        source=source,
        confidence=confidence,
    )
    facts = [fact]
    facts.extend(
        _parse_parts(
            notes,
            base_subject=subject,
            metric=metric,
            base_unit=value["unit"],
            source=source,
            confidence=confidence,
        )
    )
    facts.extend(
        _parse_alternatives(
            notes,
            base_subject=subject,
            base_metric=metric,
            base_unit=value["unit"],
            source=source,
            confidence=confidence,
        )
    )
    return facts


def _parse_value(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    range_match = RANGE_RE.search(text)
    if range_match is not None:
        low_token = range_match.group("low")
        high_token = range_match.group("high")
        low = _number(low_token)
        high = _number(high_token)
        if low is None or high is None:
            return None
        if high < low:
            low, high = high, low
        unit = _match_unit(range_match.group("suffix"))
        middle = (low + high) / 2
        qualifier = "range"
        original = f"{low_token.strip()}—{high_token.strip()}{unit or ''}"
        note = "区间取中值"
        return {
            "value_text": original,
            "value_number": middle,
            "value_low": low,
            "value_high": high,
            "unit": unit,
            "qualifier": qualifier,
            "note": note,
        }
    match = NUMBER_RE.search(text)
    if match is None:
        return None
    number = _number(match.group("num"))
    if number is None:
        return None
    suffix = text[match.end() :]
    unit = _match_unit(suffix)
    prefix = text[: match.start()]
    single_qualifier = _qualifier(prefix)
    value_text = f"{match.group('num').strip()}{unit or ''}"
    return {
        "value_text": value_text,
        "value_number": number,
        "value_low": None,
        "value_high": None,
        "unit": unit,
        "qualifier": single_qualifier,
        "note": None,
    }


def _parse_parts(
    notes: list[str],
    *,
    base_subject: str,
    metric: str,
    base_unit: str | None,
    source: dict[str, object],
    confidence: float,
) -> list[TextFact]:
    facts: list[TextFact] = []
    for note in notes:
        if "其中" not in note:
            continue
        part_text = note.split("其中", 1)[1]
        for part in re.split(r",\s+|、", part_text):
            if not NUMBER_RE.search(part):
                continue
            value = _parse_value(part)
            if value is None:
                continue
            name = _part_subject(part)
            if not name:
                continue
            facts.append(
                TextFact(
                    fact_id="",
                    subject_path=f"{base_subject} / {name}",
                    metric=metric,
                    value_text=str(value["value_text"]),
                    value_number=value["value_number"],
                    value_low=value["value_low"],
                    value_high=value["value_high"],
                    unit=value["unit"] or base_unit,
                    qualifier=value["qualifier"],
                    relation="part",
                    note=note,
                    source=source,
                    confidence=max(0.5, confidence - 0.05),
                )
            )
    return facts


def _parse_alternatives(
    notes: list[str],
    *,
    base_subject: str,
    base_metric: str,
    base_unit: str | None,
    source: dict[str, object],
    confidence: float,
) -> list[TextFact]:
    facts: list[TextFact] = []
    for note in notes:
        markers = ("另有来源作", "另有来源称", "另有资料称", "另有材料称")
        marker = next((item for item in markers if item in note), None)
        if marker is None:
            continue
        alternative_text = note.split(marker, 1)[1]
        for piece in re.split(r"\+|,\s+", alternative_text):
            if not NUMBER_RE.search(piece):
                continue
            value = _parse_value(piece)
            if value is None:
                continue
            derived = _clean_metric(_metric_before_number(piece))
            metric = derived if derived != "数量" else base_metric
            facts.append(
                TextFact(
                    fact_id="",
                    subject_path=base_subject,
                    metric=metric,
                    value_text=str(value["value_text"]),
                    value_number=value["value_number"],
                    value_low=value["value_low"],
                    value_high=value["value_high"],
                    unit=value["unit"] or base_unit,
                    qualifier=value["qualifier"],
                    relation="alternative",
                    note=alternative_text.strip(),
                    source=source,
                    confidence=max(0.5, confidence - 0.1),
                )
            )
    return facts


def _subject_from_heading(heading: str | None) -> str | None:
    if not heading:
        return None
    label = heading.strip()
    if GENERIC_HEADING_RE.search(label):
        return None
    return label


def _split_parentheses(text: str) -> tuple[str, list[str]]:
    notes = [match.group(1).strip() for match in PARENTHESIS_RE.finditer(text)]
    outside = PARENTHESIS_RE.sub("", text).strip()
    return outside, [note for note in notes if note]


def _number(token: str) -> float | None:
    compact = token.replace(",", "").replace(" ", "")
    multiplier = 1
    if compact.endswith("亿"):
        multiplier = 100_000_000
        compact = compact[:-1]
    elif compact.endswith("万"):
        multiplier = 10_000
        compact = compact[:-1]
    try:
        return float(compact) * multiplier
    except ValueError:
        return None


def _match_unit(suffix: str) -> str | None:
    cleaned = suffix.lstrip()
    for unit in UNIT_SUFFIXES:
        if cleaned.startswith(unit):
            return unit
    return None


def _qualifier(prefix: str) -> str | None:
    for qualifier, markers in QUALIFIER_PREFIXES.items():
        if any(marker in prefix for marker in markers):
            return qualifier
    return None


def _metric_before_number(text: str) -> str:
    match = RANGE_RE.search(text) or NUMBER_RE.search(text)
    if match is None:
        return ""
    return _clean_metric(text[: match.start()])


def _metric_after_number(text: str) -> str:
    match = RANGE_RE.search(text) or NUMBER_RE.search(text)
    if match is None:
        return ""
    suffix = text[match.end() :]
    unit = _match_unit(suffix)
    if unit:
        suffix = suffix[len(unit) :]
    return _clean_metric(suffix)


def _clean_metric(value: str) -> str:
    metric = PARENTHESIS_RE.sub("", value).strip(" :,;。()（）")
    for prefix in METRIC_PREFIXES:
        if metric.startswith(prefix):
            metric = metric[len(prefix) :].strip()
    changed = True
    while changed:
        changed = False
        for suffix in METRIC_SUFFIXES:
            if metric.endswith(suffix):
                metric = metric[: -len(suffix)].strip()
                changed = True
    metric = re.sub(r"\s+", " ", metric).strip()
    return metric or "数量"


def _part_subject(text: str) -> str:
    match = NUMBER_RE.search(text)
    if match is None:
        return ""
    name = _clean_metric(text[: match.start()])
    return "" if name == "数量" else name


def _confidence(raw: str, content: str, unit: str | None, heading: str | None) -> float:
    score = 0.55
    if BULLET_RE.match(raw):
        score += 0.15
    if ":" in raw:
        score += 0.1
    if unit:
        score += 0.1
    if heading:
        score += 0.1
    if not unit or len(content) > 120:
        score -= 0.1
    return round(max(0.3, min(score, 0.95)), 2)


def _source(
    line: TextLine,
    block: TextBlock,
    block_index: int,
    line_index: int,
) -> dict[str, object]:
    return {
        "line_no": line.line_no,
        "page": line.page,
        "heading": block.heading,
        "block_index": block_index,
        "line_index": line_index,
        "snippet": line.text[:300],
    }


def _deduplicate(facts: list[TextFact], warnings: list[dict[str, str]]) -> list[TextFact]:
    seen: set[tuple[object, ...]] = set()
    result: list[TextFact] = []
    for fact in facts:
        key = (
            fact.subject_path,
            fact.metric,
            fact.value_text,
            fact.unit,
            fact.note,
        )
        if key in seen:
            warnings.append(
                {
                    "code": "duplicate_fact",
                    "severity": "info",
                    "message": f"removed duplicate fact: {fact.subject_path} / {fact.metric}",
                }
            )
            continue
        seen.add(key)
        result.append(fact)
    return result


def _mark_alternatives(facts: list[TextFact], warnings: list[dict[str, str]]) -> list[TextFact]:
    groups: dict[tuple[str, str, str | None], list[TextFact]] = {}
    for fact in facts:
        groups.setdefault((fact.subject_path, fact.metric, fact.unit), []).append(fact)
    for group in groups.values():
        standalone = [fact for fact in group if fact.relation == "standalone"]
        values = {fact.value_text for fact in standalone}
        if len(values) < 2:
            continue
        for fact in standalone[1:]:
            fact.relation = "alternative"
        warnings.append(
            {
                "code": "alternative_source",
                "severity": "info",
                "message": f"kept {len(values)} differing values for {group[0].metric}",
            }
        )
    return facts


def _check_total_mismatch(facts: list[TextFact], warnings: list[dict[str, str]]) -> None:
    for fact in facts:
        if "/" in fact.subject_path or fact.value_number is None:
            continue
        children = [
            child
            for child in facts
            if child.subject_path.startswith(f"{fact.subject_path} / ")
            and child.metric == fact.metric
            and child.unit == fact.unit
            and child.relation == "part"
            and child.value_number is not None
        ]
        if not children:
            continue
        total = 0.0
        for child in children:
            if child.value_number is not None:
                total += float(child.value_number)
        reference = float(fact.value_number)
        if reference == 0:
            continue
        if abs(reference - total) / reference > 0.01:
            warnings.append(
                {
                    "code": "total_mismatch",
                    "severity": "warning",
                    "message": (
                        f"{fact.subject_path} / {fact.metric} total {reference:g} "
                        f"differs from parts {total:g}"
                    ),
                }
            )


def _long_row(fact: TextFact) -> dict[str, Any]:
    value = fact.value_number if fact.value_number is not None else fact.value_text
    return {
        "主体": fact.subject_path,
        "指标": fact.metric,
        "数值": value,
        "单位": fact.unit or "",
        "备注": fact.note or "",
    }


def _wide_preview(
    facts: list[TextFact],
    warnings: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, Any]]]:
    subjects: list[str] = []
    for fact in facts:
        if fact.subject_path not in subjects:
            subjects.append(fact.subject_path)
    headers = ["指标", "单位", *subjects]
    rows: list[dict[str, Any]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in facts:
        key = (fact.metric, fact.unit or "")
        row = index.get(key)
        if row is None:
            row = {"指标": fact.metric, "单位": fact.unit or ""}
            index[key] = row
            rows.append(row)
        value = fact.value_number if fact.value_number is not None else fact.value_text
        if fact.subject_path in row and row[fact.subject_path] != value:
            warnings.append(
                {
                    "code": "wide_conflict",
                    "severity": "warning",
                    "message": f"kept the first value for {fact.metric} / {fact.subject_path}",
                }
            )
            continue
        row[fact.subject_path] = value
    return headers, rows


__all__ = [
    "TextExtraction",
    "TextFact",
    "TextFactInvalidError",
    "TextSourceChangedError",
    "extract_facts",
]

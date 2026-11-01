"""Chart capability registry.

The registry is the single source of truth for which charts the rule engine may
emit. AI selection must only return ids that exist here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

REGISTRY_VERSION = 3

VALID_ROLES = frozenset(
    {
        "x",
        "y",
        "y2",
        "error_y",
        "latitude",
        "longitude",
        "value",
        "size",
        "series",
        "facet",
        "label",
        "source",
        "target",
        "weight",
        "level1",
        "level2",
        "level3",
        "region",
        "track",
        "time",
    }
)
VALID_GROUPS = frozenset({"numeric", "temporal", "categorical", "boolean", "text", "geo", "any"})
VALID_FAMILIES = frozenset({"2d", "3d", "map", "network", "stream", "imaging"})
VALID_BACKENDS = frozenset({"plotly", "echarts", "vtk", "mayavi", "deckgl", "cytoscape"})

SEMANTIC_GROUPS: dict[str, frozenset[str]] = {
    "integer": frozenset({"numeric"}),
    "number": frozenset({"numeric"}),
    "duration": frozenset({"numeric"}),
    "datetime": frozenset({"temporal"}),
    "date": frozenset({"temporal"}),
    "time": frozenset({"temporal"}),
    "categorical": frozenset({"categorical"}),
    "boolean": frozenset({"categorical", "boolean"}),
    "string": frozenset({"categorical", "text"}),
    "email": frozenset({"categorical", "text"}),
    "phone": frozenset({"categorical", "text"}),
    "id_card_number": frozenset({"categorical", "text"}),
    "address": frozenset({"categorical", "text"}),
    "url": frozenset({"categorical", "text"}),
    "geo_coordinate": frozenset({"numeric", "geo"}),
    "array": frozenset({"array"}),
    "object": frozenset(),
    "binary": frozenset(),
    "null": frozenset(),
    "unknown": frozenset(),
}

GROUP_PREFERENCE: dict[str, tuple[str, ...]] = {
    "temporal": ("datetime", "date", "time"),
    "numeric": ("number", "integer", "duration", "geo_coordinate"),
    "categorical": (
        "categorical",
        "boolean",
        "string",
        "email",
        "phone",
        "id_card_number",
        "address",
        "url",
    ),
    "boolean": ("boolean",),
    "geo": ("geo_coordinate",),
    "text": ("string", "email", "phone", "id_card_number", "address", "url"),
    "any": (
        "categorical",
        "number",
        "integer",
        "datetime",
        "date",
        "time",
        "boolean",
        "string",
        "geo_coordinate",
    ),
}


class ChartIntent(StrEnum):
    """Supported first-slice analysis intents."""

    TREND = "trend"
    DISTRIBUTION = "distribution"
    COMPARISON = "comparison"
    CORRELATION = "correlation"
    COMPOSITION = "composition"
    TIMELINE = "timeline"


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """Immutable chart capability entry."""

    id: str
    name_zh: str
    name_en: str
    family: str
    backend: str
    data_kinds: tuple[str, ...]
    required_types: dict[str, str]
    optional: tuple[str, ...]
    max_rows: int
    max_cardinality: dict[str, int]
    intents: tuple[ChartIntent, ...]
    supports: tuple[str, ...]
    perceptual_score: float
    accessibility_notes: str
    notes: str
    array_dims: tuple[int, int] | None = None
    min_numeric_fields: int = 0
    min_rows: int = 2

    def to_dict(self) -> dict[str, Any]:
        """Return the documented camelCase registry contract."""
        return {
            "id": self.id,
            "name": {"zh": self.name_zh, "en": self.name_en},
            "family": self.family,
            "backend": self.backend,
            "dataKinds": list(self.data_kinds),
            "requiredTypes": dict(self.required_types),
            "optional": list(self.optional),
            "maxRows": self.max_rows,
            "maxCardinality": dict(self.max_cardinality),
            "arrayDims": (
                {"min": self.array_dims[0], "max": self.array_dims[1]}
                if self.array_dims is not None
                else None
            ),
            "constraints": {
                "minNumericFields": self.min_numeric_fields,
                "minRows": self.min_rows,
            },
            "intents": [intent.value for intent in self.intents],
            "supports": list(self.supports),
            "perceptualScore": self.perceptual_score,
            "accessibilityNotes": self.accessibility_notes,
            "notes": self.notes,
        }


TREND = ChartIntent.TREND
DISTRIBUTION = ChartIntent.DISTRIBUTION
COMPARISON = ChartIntent.COMPARISON
CORRELATION = ChartIntent.CORRELATION
COMPOSITION = ChartIntent.COMPOSITION
TIMELINE = ChartIntent.TIMELINE

_COMMON_SUPPORTS = ("zoom", "hover", "legendFilter", "exportSvg")
_PERCEPTUAL_NOTE = "系列同时使用标记或线型区分，避免仅靠颜色传达信息。"

CHARTS: tuple[ChartSpec, ...] = (
    ChartSpec(
        id="bar",
        name_zh="柱状图",
        name_en="Bar chart",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "categorical", "y": "numeric"},
        optional=("series", "y2", "error_y"),
        max_rows=200_000,
        max_cardinality={"x": 200, "series": 50},
        intents=(COMPARISON, COMPOSITION),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.85,
        accessibility_notes=_PERCEPTUAL_NOTE,
        notes="适合类别比较；类别过多时改用横向条形图或先聚合。",
    ),
    ChartSpec(
        id="bar_horizontal",
        name_zh="条形图",
        name_en="Horizontal bar chart",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "numeric", "y": "categorical"},
        optional=("series", "y2", "error_y"),
        max_rows=200_000,
        max_cardinality={"y": 200, "series": 50},
        intents=(COMPARISON,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.82,
        accessibility_notes=_PERCEPTUAL_NOTE,
        notes="长类别标签或类别较多时优先使用。",
    ),
    ChartSpec(
        id="line_timeseries",
        name_zh="时序折线图",
        name_en="Time series line",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "temporal", "y": "numeric"},
        optional=("series", "y2", "error_y"),
        max_rows=200_000,
        max_cardinality={"series": 50},
        intents=(TREND, TIMELINE),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.9,
        accessibility_notes=_PERCEPTUAL_NOTE,
        notes="适合连续时间趋势；采样数据需在图中标注。",
    ),
    ChartSpec(
        id="area_timeseries",
        name_zh="时序面积图",
        name_en="Time series area",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "temporal", "y": "numeric"},
        optional=("series", "y2", "error_y"),
        max_rows=200_000,
        max_cardinality={"series": 30},
        intents=(TREND, COMPOSITION, TIMELINE),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.8,
        accessibility_notes=_PERCEPTUAL_NOTE,
        notes="适合累计量或构成随时间变化；多系列时避免面积遮挡。",
    ),
    ChartSpec(
        id="scatter",
        name_zh="散点图",
        name_en="Scatter plot",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "numeric", "y": "numeric"},
        optional=("series", "y2", "error_y"),
        max_rows=100_000,
        max_cardinality={"series": 50},
        intents=(CORRELATION,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.86,
        accessibility_notes=_PERCEPTUAL_NOTE,
        notes="用于两个连续变量的关系；点过多时建议采样或改用密度图。",
    ),
    ChartSpec(
        id="bubble",
        name_zh="气泡图",
        name_en="Bubble chart",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "numeric", "y": "numeric", "size": "numeric"},
        optional=("series", "y2", "error_y"),
        max_rows=50_000,
        max_cardinality={"series": 30},
        intents=(CORRELATION,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.75,
        accessibility_notes="气泡大小需有图例说明，并避免用面积表达精确数值。",
        notes="用于第三个连续变量的关系；面积感知不适合精确比较。",
    ),
    ChartSpec(
        id="histogram",
        name_zh="直方图",
        name_en="Histogram",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "numeric"},
        optional=(),
        max_rows=200_000,
        max_cardinality={},
        intents=(DISTRIBUTION,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.84,
        accessibility_notes="分箱数需可配置，并标明分箱规则。",
        notes="用于单变量分布；分箱数会影响形态判断。",
    ),
    ChartSpec(
        id="box",
        name_zh="箱线图",
        name_en="Box plot",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"y": "numeric"},
        optional=("x",),
        max_rows=200_000,
        max_cardinality={"x": 50},
        intents=(DISTRIBUTION, COMPARISON),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.85,
        accessibility_notes="需同时展示离群点与样本量。",
        notes="用于分布与组间比较；默认不隐藏离群值。",
    ),
    ChartSpec(
        id="violin",
        name_zh="小提琴图",
        name_en="Violin plot",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"y": "numeric"},
        optional=("x",),
        max_rows=200_000,
        max_cardinality={"x": 50},
        intents=(DISTRIBUTION, COMPARISON),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.8,
        accessibility_notes="需同时提供箱线或分位点，避免仅凭轮廓判断。",
        notes="用于分布形状比较；小样本时优先箱线图。",
    ),
    ChartSpec(
        id="heatmap",
        name_zh="热力图",
        name_en="Heatmap",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "categorical", "y": "categorical", "value": "numeric"},
        optional=(),
        max_rows=200_000,
        max_cardinality={"x": 100, "y": 100},
        intents=(CORRELATION, COMPOSITION),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.75,
        accessibility_notes="提供数值标签或等值线，避免仅靠颜色判读。",
        notes="用于两个类别维度与一个数值的矩阵；类别过多时先聚合。",
    ),
    ChartSpec(
        id="pie",
        name_zh="饼图",
        name_en="Pie chart",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"label": "categorical", "value": "numeric"},
        optional=(),
        max_rows=20_000,
        max_cardinality={"label": 20},
        intents=(COMPOSITION,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.55,
        accessibility_notes="同时显示百分比数值；不建议用于精确比较。",
        notes="仅用于少量类别的构成；类别过多时改用条形图。",
    ),
    ChartSpec(
        id="donut",
        name_zh="环形图",
        name_en="Donut chart",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"label": "categorical", "value": "numeric"},
        optional=(),
        max_rows=20_000,
        max_cardinality={"label": 20},
        intents=(COMPOSITION,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.55,
        accessibility_notes="中心留白不承载数据；同时显示百分比数值。",
        notes="仅用于少量类别的构成；类别过多时改用条形图。",
    ),
    ChartSpec(
        id="radar",
        name_zh="雷达图",
        name_en="Radar chart",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"label": "categorical", "value": "numeric"},
        optional=(),
        max_rows=20_000,
        max_cardinality={"label": 20},
        intents=(COMPARISON,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.6,
        accessibility_notes="需提供数值表；雷达面积不适合精确比较。",
        notes="用于少量类别的多指标比较，至少需要 3 个数值字段。",
        min_numeric_fields=3,
    ),
    ChartSpec(
        id="parallel",
        name_zh="平行坐标图",
        name_en="Parallel coordinates",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"value": "numeric"},
        optional=("series",),
        max_rows=100_000,
        max_cardinality={"series": 20},
        intents=(CORRELATION,),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.65,
        accessibility_notes="提供轴顺序与筛选说明；避免过多透明线条。",
        notes="用于多变量关系，至少需要 3 个数值字段。",
        min_numeric_fields=3,
    ),
    ChartSpec(
        id="regression",
        name_zh="回归趋势图",
        name_en="Regression trend",
        family="2d",
        backend="plotly",
        data_kinds=("table",),
        required_types={"x": "numeric", "y": "numeric"},
        optional=(),
        max_rows=100_000,
        max_cardinality={},
        intents=(TREND, CORRELATION),
        supports=_COMMON_SUPPORTS,
        perceptual_score=0.8,
        accessibility_notes="显示拟合方法与置信区间说明。",
        notes="用于两个连续变量的趋势与相关；需标注拟合类型。",
    ),
    ChartSpec(
        id="geo_scatter",
        name_zh="地理散点图",
        name_en="Geographic scatter",
        family="map",
        backend="deckgl",
        data_kinds=("table",),
        required_types={"latitude": "geo", "longitude": "geo"},
        optional=("value", "size", "label"),
        max_rows=50_000,
        max_cardinality={"label": 50},
        intents=(COMPARISON, CORRELATION, COMPOSITION),
        supports=("zoom", "hover", "legendFilter", "exportSvg"),
        perceptual_score=0.8,
        accessibility_notes="提供坐标精度、投影与色标说明；颜色和大小不能是唯一编码。",
        notes="用于经纬度点位；超量点位应聚合或采样，底图可离线使用。",
    ),
    ChartSpec(
        id="geo_trajectory",
        name_zh="地理轨迹图",
        name_en="Geographic trajectory",
        family="map",
        backend="deckgl",
        data_kinds=("table",),
        required_types={"latitude": "geo", "longitude": "geo"},
        optional=("track", "time", "value", "label"),
        max_rows=100_000,
        max_cardinality={"track": 200, "label": 100},
        intents=(TREND, TIMELINE, CORRELATION),
        supports=("zoom", "hover", "pan", "reset", "exportSvg", "exportPng"),
        perceptual_score=0.82,
        accessibility_notes="提供轨迹分组、点序与时间说明；颜色不能是唯一编码。",
        notes="用于按轨迹分组的经纬度点序列；无时间列时按行序连接。",
    ),
    ChartSpec(
        id="geo_density",
        name_zh="地理密度图",
        name_en="Geographic density",
        family="map",
        backend="deckgl",
        data_kinds=("table",),
        required_types={"latitude": "geo", "longitude": "geo"},
        optional=("weight",),
        max_rows=200_000,
        max_cardinality={},
        intents=(DISTRIBUTION, CORRELATION),
        supports=("zoom", "hover", "pan", "reset", "exportSvg", "exportPng"),
        perceptual_score=0.78,
        accessibility_notes="提供网格大小、聚合方式与色标说明；避免仅靠颜色判读。",
        notes="使用离线六边形聚合展示点位密度；适合大规模点位。",
    ),
    ChartSpec(
        id="geo_region",
        name_zh="地理区域填色图",
        name_en="Geographic region fill",
        family="map",
        backend="deckgl",
        data_kinds=("table",),
        required_types={"region": "categorical", "value": "numeric"},
        optional=("label",),
        max_rows=200_000,
        max_cardinality={"region": 300, "label": 50},
        intents=(COMPARISON, COMPOSITION),
        supports=("zoom", "hover", "pan", "reset", "exportSvg", "exportPng"),
        perceptual_score=0.76,
        accessibility_notes="提供区域匹配规则、未匹配项与色标说明。",
        notes="按国家名称或数字代码匹配离线国界；未匹配区域会明确提示。",
    ),
    ChartSpec(
        id="network_graph",
        name_zh="关系网络图",
        name_en="Network graph",
        family="network",
        backend="cytoscape",
        data_kinds=("table",),
        required_types={"source": "categorical", "target": "categorical"},
        optional=("weight", "label"),
        max_rows=20_000,
        max_cardinality={"source": 500, "target": 500, "label": 500},
        intents=(CORRELATION, COMPOSITION),
        supports=("zoom", "hover", "layoutSwitch", "nodeFilter", "exportPng"),
        perceptual_score=0.72,
        accessibility_notes="提供节点/边数量、布局与筛选说明；大图需聚合或过滤。",
        notes="用于节点-边关系；source 与 target 必须是不同类别列。",
    ),
    ChartSpec(
        id="sankey_flow",
        name_zh="桑基流向图",
        name_en="Sankey flow",
        family="network",
        backend="echarts",
        data_kinds=("table",),
        required_types={"source": "categorical", "target": "categorical", "weight": "numeric"},
        optional=(),
        max_rows=20_000,
        max_cardinality={"source": 200, "target": 200},
        intents=(COMPOSITION, CORRELATION),
        supports=("zoom", "hover", "exportPng"),
        perceptual_score=0.7,
        accessibility_notes="流量必须标注权重；节点过多时先聚合。",
        notes="用于来源到去向的权重流；只保留有限的 source/target 节点。",
    ),
    ChartSpec(
        id="sunburst_hierarchy",
        name_zh="旭日层级图",
        name_en="Sunburst hierarchy",
        family="network",
        backend="echarts",
        data_kinds=("table",),
        required_types={"level1": "categorical", "value": "numeric"},
        optional=("level2", "level3"),
        max_rows=100_000,
        max_cardinality={"level1": 100, "level2": 100, "level3": 100},
        intents=(COMPOSITION,),
        supports=("zoom", "hover", "exportPng"),
        perceptual_score=0.68,
        accessibility_notes="层级与数值需同时可读；层级过深时提供表格替代。",
        notes="用于 2–3 层层级构成；level1 必需，level2/level3 可选。",
    ),
    ChartSpec(
        id="image_slice",
        name_zh="影像切片",
        name_en="Image slice",
        family="imaging",
        backend="vtk",
        data_kinds=("array",),
        required_types={"value": "numeric"},
        optional=(),
        max_rows=50_000_000,
        max_cardinality={},
        intents=(DISTRIBUTION, COMPOSITION),
        supports=("slice", "windowLevel", "pseudocolor", "annotations", "exportPng"),
        perceptual_score=0.8,
        accessibility_notes="提供切片位置、窗宽窗位、伪彩与单位说明。",
        notes="用于 2D/3D/4D 数值影像；3D 提供轴位/冠状/矢状联动。",
        array_dims=(2, 4),
    ),
    ChartSpec(
        id="live_timeseries",
        name_zh="实时时序折线图",
        name_en="Live time series",
        family="stream",
        backend="echarts",
        data_kinds=("table",),
        required_types={"x": "temporal", "y": "numeric"},
        optional=("series",),
        max_rows=5_000,
        max_cardinality={"series": 50},
        intents=(TREND, TIMELINE),
        supports=("live", "pauseResume", "window", "sampling", "reconnect", "exportPng"),
        perceptual_score=0.86,
        accessibility_notes="显示连接状态、窗口范围与采样频率；断线时明确提示。",
        notes="用于 WebSocket/Kafka 实时窗口；保存窗口后可转为普通时序数据集。",
    ),
    ChartSpec(
        id="array_heatmap",
        name_zh="数组热图",
        name_en="Array heatmap",
        family="2d",
        backend="plotly",
        data_kinds=("array",),
        required_types={"value": "numeric"},
        optional=(),
        max_rows=20_000_000,
        max_cardinality={},
        intents=(DISTRIBUTION, COMPOSITION),
        supports=("zoom", "hover", "exportSvg"),
        perceptual_score=0.75,
        accessibility_notes="提供色标数值与切片位置说明。",
        notes="数值 1D/2D 数组直接显示；3D 数组默认沿第一维切片。",
        array_dims=(1, 3),
    ),
)


def list_charts() -> list[dict[str, Any]]:
    """Return all registry entries using the documented contract."""
    return [spec.to_dict() for spec in CHARTS]


def get_chart(chart_id: str) -> ChartSpec | None:
    """Return one chart spec or None."""
    return next((spec for spec in CHARTS if spec.id == chart_id), None)

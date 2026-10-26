"""Versioned Scene JSON contract for browser and server 3D renderers."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from advp.models import Dataset

SCENE_VERSION = "1.0"
SUPPORTED_BACKENDS = {"auto", "webgl", "mayavi", "trame"}
SUPPORTED_GEOMETRIES = {
    "points",
    "surface",
    "slice",
    "volume",
    "isosurface",
    "streamlines",
}


class SceneError(Exception):
    """Scene JSON is invalid or incompatible with the dataset."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class SceneCoordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: str | None = None
    y: str | None = None
    z: str | None = None
    units: str | None = None


class SceneData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasetId: str = Field(min_length=1)
    fields: list[str] = Field(default_factory=list)
    coordinates: SceneCoordinates = Field(default_factory=SceneCoordinates)


class SceneGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "points",
        "surface",
        "slice",
        "volume",
        "isosurface",
        "streamlines",
    ] = "points"
    dimensions: list[int] | None = None
    spacing: list[float] | None = None
    origin: list[float] | None = None
    axis: int | None = Field(default=None, ge=0, le=3)
    index: int | None = Field(default=None, ge=0)
    level: float | None = None
    variable: str | None = None


class SceneCamera(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    focalPoint: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    viewUp: list[float] = Field(default_factory=lambda: [0.0, 0.0, 1.0])


class SceneLighting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambient: float = Field(default=0.2, ge=0, le=1)
    diffuse: float = Field(default=0.8, ge=0, le=1)


class SceneColormap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "viridis"
    range: list[float] = Field(default_factory=lambda: [0.0, 1.0])
    nanColor: str = "#808080"


class SceneTransferFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: list[list[float]] = Field(
        default_factory=lambda: [[0.0, 0.0], [0.5, 0.4], [1.0, 0.9]],
        max_length=32,
    )


class SceneClipping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    planes: list[dict[str, Any]] = Field(default_factory=list, max_length=6)


class SceneAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    color: str | None = None


class SceneAnimation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: int = Field(default=1, ge=1, le=2000)
    fps: int = Field(default=30, ge=1, le=120)
    resolution: list[int] = Field(default_factory=lambda: [1280, 720])
    cameraPath: list[list[float]] = Field(default_factory=list, max_length=1000)
    startFrame: int = Field(default=0, ge=0, le=2000)


class SceneSampling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maxElements: int = Field(default=50_000_000, ge=1)
    mode: Literal["stride", "none"] = "stride"


class SceneScientific(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinateReference: str | None = None
    units: str | None = None
    dataRange: list[float] | None = None


class SceneDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = SCENE_VERSION
    data: SceneData
    geometry: SceneGeometry = Field(default_factory=SceneGeometry)
    camera: SceneCamera = Field(default_factory=SceneCamera)
    lighting: SceneLighting = Field(default_factory=SceneLighting)
    colormap: SceneColormap = Field(default_factory=SceneColormap)
    transferFunction: SceneTransferFunction = Field(default_factory=SceneTransferFunction)
    clipping: SceneClipping = Field(default_factory=SceneClipping)
    annotations: list[SceneAnnotation] = Field(default_factory=list, max_length=50)
    animation: SceneAnimation = Field(default_factory=SceneAnimation)
    backend: Literal["auto", "webgl", "mayavi", "trame"] = "auto"
    sampling: SceneSampling = Field(default_factory=SceneSampling)
    scientific: SceneScientific = Field(default_factory=SceneScientific)


def normalize_scene(payload: dict[str, Any], dataset: Dataset) -> SceneDocument:
    """Validate a raw Scene JSON payload against a stored dataset."""
    migrated = migrate_scene(payload)
    try:
        scene = SceneDocument.model_validate(migrated)
    except Exception as exc:
        raise SceneError("invalid_scene", f"scene validation failed: {exc}") from exc
    _validate_scene(scene, dataset)
    return scene


def migrate_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate a known older Scene JSON version to the current version."""
    if not isinstance(payload, dict):
        raise SceneError("invalid_scene", "scene must be a JSON object")
    scene = deepcopy(payload)
    version = str(scene.get("version") or "")
    if version == SCENE_VERSION:
        return scene
    if version == "0.9":
        scene["version"] = SCENE_VERSION
        scene.setdefault("sampling", {"maxElements": 50_000_000, "mode": "stride"})
        scene.setdefault(
            "scientific",
            {"coordinateReference": None, "units": None, "dataRange": None},
        )
        scene.setdefault("backend", "auto")
        return scene
    if version and version > SCENE_VERSION:
        raise SceneError(
            "unsupported_scene_version",
            f"scene version {version!r} is newer than supported {SCENE_VERSION!r}",
        )
    raise SceneError(
        "unsupported_scene_version",
        f"scene version {version!r} is not supported",
    )


def scene_hash(scene: SceneDocument | dict[str, Any]) -> str:
    """Return a stable SHA-256 for a Scene JSON document."""
    payload = scene.model_dump() if isinstance(scene, SceneDocument) else scene
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def scene_manifest(scene: SceneDocument, dataset: Dataset) -> dict[str, Any]:
    """Build a traceability manifest for a scene."""
    return {
        "scene_version": scene.version,
        "scene_hash": scene_hash(scene),
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "dataset_format": dataset.format,
        "source_sha256": dataset.source_sha256,
        "geometry": scene.geometry.type,
        "backend": scene.backend,
        "fields": list(scene.data.fields),
        "units": scene.scientific.units or scene.data.coordinates.units,
        "data_range": scene.scientific.dataRange,
        "colormap": scene.colormap.model_dump(),
        "transfer_function": scene.transferFunction.model_dump(),
        "sampling": scene.sampling.model_dump(),
    }


def _validate_scene(scene: SceneDocument, dataset: Dataset) -> None:
    if scene.backend not in SUPPORTED_BACKENDS:
        raise SceneError("invalid_backend", f"backend {scene.backend!r} is not supported")
    if scene.data.datasetId != dataset.id:
        raise SceneError(
            "dataset_mismatch",
            f"scene dataset {scene.data.datasetId!r} does not match {dataset.id!r}",
        )
    available = _dataset_fields(dataset)
    unknown = [field for field in scene.data.fields if field not in available]
    if unknown:
        raise SceneError(
            "unknown_field",
            f"scene fields do not exist in the dataset: {', '.join(sorted(unknown))}",
        )
    for axis in (scene.data.coordinates.x, scene.data.coordinates.y, scene.data.coordinates.z):
        if axis and axis not in available:
            raise SceneError("unknown_field", f"coordinate field {axis!r} does not exist")
    geometry = scene.geometry
    if geometry.dimensions is not None and len(geometry.dimensions) not in (2, 3):
        raise SceneError("invalid_geometry", "geometry.dimensions must have 2 or 3 values")
    for values in (geometry.spacing, geometry.origin):
        if values is not None and len(values) not in (2, 3):
            raise SceneError("invalid_geometry", "spacing/origin must have 2 or 3 values")
    if (
        geometry.type in {"volume", "isosurface", "slice", "streamlines"}
        and dataset.kind != "array"
    ):
        raise SceneError(
            "geometry_kind_mismatch",
            f"geometry {geometry.type!r} requires an array dataset",
        )
    colormap = scene.colormap
    if len(colormap.range) != 2 or colormap.range[0] >= colormap.range[1]:
        raise SceneError("invalid_colormap", "colormap.range must be [min, max] with min < max")
    if not (colormap.nanColor.startswith("#") and len(colormap.nanColor) == 7):
        raise SceneError("invalid_colormap", "colormap.nanColor must be a #RRGGBB value")
    previous_x = -1.0
    for point in scene.transferFunction.points:
        if len(point) != 2:
            raise SceneError("invalid_transfer_function", "transfer points must be [x, y]")
        x_value, y_value = point
        if not (0 <= x_value <= 1 and 0 <= y_value <= 1):
            raise SceneError(
                "invalid_transfer_function",
                "transfer points must be in the 0..1 range",
            )
        if x_value < previous_x:
            raise SceneError(
                "invalid_transfer_function",
                "transfer points must be sorted by x",
            )
        previous_x = x_value
    if scene.animation.resolution and len(scene.animation.resolution) != 2:
        raise SceneError("invalid_animation", "animation.resolution must have 2 values")
    if scene.sampling.maxElements <= 0:
        raise SceneError("invalid_sampling", "sampling.maxElements must be positive")


def _dataset_fields(dataset: Dataset) -> set[str]:
    schema = dataset.schema_json or {}
    if dataset.kind == "array":
        names = {str(schema.get("variable", ""))}
        names.update(str(dim) for dim in schema.get("dims", []))
        return {name for name in names if name}
    return {
        str(column.get("name"))
        for column in schema.get("columns", [])
        if isinstance(column, dict) and column.get("name")
    }

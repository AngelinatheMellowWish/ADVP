#!/usr/bin/env python3
"""Offscreen 3D renderer worker for ADVP.

The main backend spawns this script with a separate Python environment that has
VTK/Mayavi/PySide6 installed. It reads a JSON job and writes a JSON result.

Usage:
  python render3d_worker.py --probe
  python render3d_worker.py --job job.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def configure_offscreen() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("ETS_TOOLKIT", "qt")
    os.environ.setdefault("QT_API", "pyside6")
    os.environ.setdefault("VTK_DEFAULT_OPENGL_WINDOW", "vtkWin32OpenGLRenderWindow")


def probe() -> dict[str, Any]:
    configure_offscreen()
    report: dict[str, Any] = {
        "ok": True,
        "python": sys.version.split()[0],
        "vtk": None,
        "mayavi": None,
        "pyside6": None,
        "trame": False,
        "imageio": False,
    }
    try:
        import vtk  # type: ignore[import-not-found]

        report["vtk"] = vtk.vtkVersion.GetVTKVersion()
        renderer = vtk.vtkRenderer()
        window = vtk.vtkRenderWindow()
        window.SetOffScreenRendering(1)
        window.AddRenderer(renderer)
        window.SetSize(64, 64)
        renderer.SetBackground(0.05, 0.06, 0.09)
        window.Render()
        capabilities = window.ReportCapabilities()
        for line in capabilities.splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "OpenGL renderer string":
                report["gl_renderer"] = value.strip()
            elif key.strip() == "OpenGL vendor string":
                report["gl_vendor"] = value.strip()
            elif key.strip() == "OpenGL version string":
                report["gl_version"] = value.strip()
        renderer_name = str(report.get("gl_renderer", "")).lower()
        report["software_rendering"] = any(
            marker in renderer_name
            for marker in ("llvmpipe", "softpipe", "swiftshader", "gdi generic", "osmesa")
        )
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["vtk_error"] = str(exc)
    for name in ("mayavi", "PySide6", "trame", "imageio"):
        try:
            module = __import__(name)
            report[name] = getattr(module, "__version__", True)
        except Exception:
            pass
    return report


def render(job: dict[str, Any]) -> dict[str, Any]:
    configure_offscreen()
    import vtk

    started = time.perf_counter()
    geometry = job.get("geometry") or {}
    scene = job.get("scene") or {}
    transfer = job.get("transferFunction") or {}
    output_dir = Path(job["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    width = int(job.get("width") or 1280)
    height = int(job.get("height") or 720)
    mode = str(geometry.get("mode") or job.get("mode") or "points")
    value_range = _value_range(geometry)
    color_transfer = _color_transfer_function(vtk, transfer, value_range)
    opacity_transfer = _opacity_transfer_function(vtk, transfer, value_range)

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.04, 0.08, 0.15)
    _apply_lighting(renderer, scene)
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.AddRenderer(renderer)
    window.SetSize(width, height)

    if mode in {"points", "surface"}:
        points = geometry.get("points") or []
        if not points:
            raise ValueError("point payload is empty")
        vtk_points = vtk.vtkPoints()
        values = vtk.vtkFloatArray()
        values.SetName("value")
        for point in points:
            position = point.get("position") or [0, 0, 0]
            vtk_points.InsertNextPoint(float(position[0]), float(position[1]), float(position[2]))
            values.InsertNextValue(float(point.get("value", 0)))
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(vtk_points)
        polydata.GetPointData().SetScalars(values)
        mapper = vtk.vtkPointGaussianMapper()
        mapper.SetInputData(polydata)
        mapper.SetScaleFactor(0.04)
        mapper.SetScalarVisibility(1)
        mapper.SetLookupTable(color_transfer)
        mapper.SetScalarRange(*value_range)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        renderer.AddActor(actor)
    elif mode == "slice":
        image = _image_data(vtk, geometry, flat=False)
        mapper = vtk.vtkImageSliceMapper()
        mapper.SetInputData(image)
        mapper.SetSliceNumber(0)
        mapper.SetLookupTable(color_transfer)
        mapper.SetScalarRange(*value_range)
        actor = vtk.vtkImageSlice()
        actor.SetMapper(mapper)
        renderer.AddActor(actor)
    elif mode == "isosurface":
        image = _image_data(vtk, geometry, flat=True)
        contour = vtk.vtkMarchingCubes()
        contour.SetInputData(image)
        contour.SetValue(0, float(job.get("isovalue", 0.5)))
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(contour.GetOutputPort())
        mapper.SetLookupTable(color_transfer)
        mapper.SetScalarRange(*value_range)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0.35, 0.7, 1.0)
        renderer.AddActor(actor)
    elif mode == "volume":
        image = _image_data(vtk, geometry, flat=True)
        mapper = vtk.vtkSmartVolumeMapper()
        mapper.SetInputData(image)
        volume_property = vtk.vtkVolumeProperty()
        volume_property.ShadeOn()
        volume_property.SetInterpolationTypeToLinear()
        volume_property.SetColor(color_transfer)
        volume_property.SetScalarOpacity(opacity_transfer)
        actor = vtk.vtkVolume()
        actor.SetMapper(mapper)
        actor.SetProperty(volume_property)
        renderer.AddActor(actor)
    else:
        raise ValueError(f"unsupported render mode: {mode}")

    renderer.ResetCamera()
    _apply_camera(renderer, scene)
    _apply_clipping(vtk, renderer, scene)
    _apply_annotations(vtk, renderer, scene)
    renderer.ResetCameraClippingRange()
    window.Render()
    output_path = output_dir / "render.png"
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output_path))
    window_to_image = vtk.vtkWindowToImageFilter()
    window_to_image.SetInput(window)
    writer.SetInputConnection(window_to_image.GetOutputPort())
    writer.Write()

    outputs = [
        {
            "kind": "png",
            "path": str(output_path),
            "bytes": output_path.stat().st_size,
        }
    ]
    animation = job.get("animation") or {}
    frames = int(animation.get("frames") or 1)
    if frames > 1:
        fps = int(animation.get("fps") or 30)
        camera_path = animation.get("cameraPath") or animation.get("camera_path") or []
        start_frame = int(animation.get("start_frame") or animation.get("startFrame") or 0)
        start_frame = max(0, min(frames - 1, start_frame))
        frame_dir = output_dir / "frames"
        frame_dir.mkdir(exist_ok=True)
        camera = renderer.GetActiveCamera()
        base_camera = {
            "position": list(camera.GetPosition()),
            "focal": list(camera.GetFocalPoint()),
            "up": list(camera.GetViewUp()),
        }
        for index in range(start_frame, frames):
            _position_camera(camera, base_camera, camera_path, index, frames)
            renderer.ResetCameraClippingRange()
            window.Render()
            frame_path = frame_dir / f"frame-{index:04d}.png"
            frame_writer = vtk.vtkPNGWriter()
            frame_writer.SetFileName(str(frame_path))
            frame_writer.SetInputConnection(window_to_image.GetOutputPort())
            frame_writer.Write()
            outputs.append(
                {
                    "kind": "frame",
                    "path": str(frame_path),
                    "bytes": frame_path.stat().st_size,
                }
            )
        frame_paths = sorted(frame_dir.glob("frame-*.png"))
        _compose_animation(output_dir, frame_paths, fps)
        for name in ("animation.mp4", "animation.gif"):
            animation_path = output_dir / name
            if animation_path.is_file():
                outputs.append(
                    {
                        "kind": "animation",
                        "path": str(animation_path),
                        "bytes": animation_path.stat().st_size,
                    }
                )

    elapsed = round((time.perf_counter() - started) * 1000, 1)
    return {
        "ok": True,
        "outputs": outputs,
        "elapsed_ms": elapsed,
        "renderer": {
            "mode": mode,
            "vtk": vtk.vtkVersion.GetVTKVersion(),
        },
    }


def _value_range(geometry: dict[str, Any]) -> tuple[float, float]:
    values = geometry.get("range") or [0.0, 1.0]
    try:
        low = float(values[0]) if values[0] is not None else 0.0
        high = float(values[1]) if values[1] is not None else 1.0
    except (TypeError, ValueError):
        return 0.0, 1.0
    if high <= low:
        high = low + 1.0
    return low, high


def _mapped_x(x: float, value_range: tuple[float, float]) -> float:
    low, high = value_range
    return low + max(0.0, min(1.0, x)) * (high - low)


def _color_transfer_function(
    vtk: Any,
    transfer: dict[str, Any],
    value_range: tuple[float, float],
) -> Any:
    color = vtk.vtkColorTransferFunction()
    raw = transfer.get("colorPoints") or [
        {"x": 0.0, "rgb": [0.0, 0.0, 0.0]},
        {"x": 1.0, "rgb": [1.0, 1.0, 1.0]},
    ]
    points = [
        (float(point.get("x", 0)), tuple(float(value) for value in point.get("rgb") or [0, 0, 0]))
        for point in raw
    ]
    if transfer.get("interpolation") == "smooth":
        points = _smooth_sequence(points)
    for x, rgb in points:
        red, green, blue = (list(rgb) + [0.0, 0.0, 0.0])[:3]
        color.AddRGBPoint(_mapped_x(x, value_range), red, green, blue)
    return color


def _opacity_transfer_function(
    vtk: Any,
    transfer: dict[str, Any],
    value_range: tuple[float, float],
) -> Any:
    opacity = vtk.vtkPiecewiseFunction()
    raw = transfer.get("opacityPoints") or [
        {"x": 0.0, "opacity": 0.0},
        {"x": 1.0, "opacity": 1.0},
    ]
    points = [
        (
            float(point.get("x", 0)),
            (max(0.0, min(1.0, float(point.get("opacity", 0)))),),
        )
        for point in raw
    ]
    if transfer.get("interpolation") == "smooth":
        points = _smooth_sequence(points)
    for x, values in points:
        opacity.AddPoint(_mapped_x(x, value_range), values[0])
    return opacity


def _smooth_sequence(
    points: list[tuple[float, tuple[float, ...]]],
    steps: int = 8,
) -> list[tuple[float, tuple[float, ...]]]:
    if len(points) < 2:
        return points
    result: list[tuple[float, tuple[float, ...]]] = []
    for (x0, value0), (x1, value1) in zip(points, points[1:], strict=False):
        for index in range(steps):
            fraction = index / steps
            eased = fraction * fraction * (3 - 2 * fraction)
            width = min(len(value0), len(value1))
            value = tuple(
                value0[item] + (value1[item] - value0[item]) * eased for item in range(width)
            )
            result.append((x0 + (x1 - x0) * fraction, value))
    result.append(points[-1])
    return result


def _apply_lighting(renderer: Any, scene: dict[str, Any]) -> None:
    lighting = scene.get("lighting") or {}
    if hasattr(renderer, "SetAmbient"):
        renderer.SetAmbient(float(lighting.get("ambient", 0.2)))
    if hasattr(renderer, "SetDiffuse"):
        renderer.SetDiffuse(float(lighting.get("diffuse", 0.8)))


def _apply_camera(renderer: Any, scene: dict[str, Any]) -> None:
    camera_config = scene.get("camera") or {}
    camera = renderer.GetActiveCamera()
    position = camera_config.get("position")
    focal = camera_config.get("focalPoint")
    view_up = camera_config.get("viewUp")
    if isinstance(position, list) and len(position) == 3:
        camera.SetPosition(*(float(value) for value in position))
    if isinstance(focal, list) and len(focal) == 3:
        camera.SetFocalPoint(*(float(value) for value in focal))
    if isinstance(view_up, list) and len(view_up) == 3:
        camera.SetViewUp(*(float(value) for value in view_up))
    camera.OrthogonalizeViewUp()


def _apply_clipping(vtk: Any, renderer: Any, scene: dict[str, Any]) -> None:
    clipping = scene.get("clipping") or {}
    if not clipping.get("enabled"):
        return
    planes = []
    for item in clipping.get("planes") or []:
        if not isinstance(item, dict):
            continue
        origin = item.get("origin") or item.get("position") or [0.0, 0.0, 0.0]
        normal = item.get("normal") or [1.0, 0.0, 0.0]
        if len(origin) != 3 or len(normal) != 3:
            continue
        plane = vtk.vtkPlane()
        plane.SetOrigin(*(float(value) for value in origin))
        plane.SetNormal(*(float(value) for value in normal))
        planes.append(plane)
    if not planes:
        return
    for collection_name in ("GetActors", "GetVolumes"):
        collection = getattr(renderer, collection_name, None)
        if collection is None:
            continue
        collection.InitTraversal()
        get_next = (
            getattr(collection, "GetNextActor", None)
            or getattr(collection, "GetNextVolume", None)
            or getattr(collection, "GetNextItemAsObject", None)
        )
        if get_next is None:
            continue
        item = get_next()
        while item is not None:
            mapper = item.GetMapper()
            if mapper is not None and hasattr(mapper, "AddClippingPlane"):
                for plane in planes:
                    mapper.AddClippingPlane(plane)
            item = get_next()


def _apply_annotations(vtk: Any, renderer: Any, scene: dict[str, Any]) -> None:
    for annotation in scene.get("annotations") or []:
        text_value = str(annotation.get("text") or "").strip()
        if not text_value:
            continue
        position = annotation.get("position") or [0.0, 0.0, 0.0]
        actor = vtk.vtkBillboardTextActor3D()
        actor.SetInput(text_value)
        actor.SetPosition(*(float(value) for value in position))
        red, green, blue = _hex_rgb(str(annotation.get("color") or "#ffffff"))
        actor.GetTextProperty().SetColor(red, green, blue)
        actor.GetTextProperty().SetFontSize(18)
        renderer.AddActor(actor)


def _hex_rgb(value: str) -> tuple[float, float, float]:
    if len(value) != 7 or not value.startswith("#"):
        return 1.0, 1.0, 1.0
    try:
        return (
            int(value[1:3], 16) / 255,
            int(value[3:5], 16) / 255,
            int(value[5:7], 16) / 255,
        )
    except ValueError:
        return 1.0, 1.0, 1.0


def _image_data(vtk: Any, geometry: dict[str, Any], *, flat: bool) -> Any:
    values = geometry.get("values")
    shape = geometry.get("display_shape") or geometry.get("shape") or []
    if flat:
        if not values or len(shape) < 2:
            raise ValueError("volume/isosurface requires inline values")
        dims = [int(shape[0]), int(shape[1]), int(shape[2]) if len(shape) > 2 else 1]
        flat_values = [float(value or 0) for value in values]
    else:
        rows = int(geometry.get("rows") or 0)
        cols = int(geometry.get("cols") or 0)
        dims = [cols, rows, 1]
        flat_values = [float(value or 0) for row in values or [] for value in row]
    if len(flat_values) < dims[0] * dims[1] * dims[2]:
        raise ValueError("inline values do not match image dimensions")
    image = vtk.vtkImageData()
    image.SetDimensions(*dims)
    image.SetSpacing(1, 1, 1)
    array = vtk.vtkFloatArray()
    array.SetNumberOfComponents(1)
    array.SetNumberOfTuples(dims[0] * dims[1] * dims[2])
    for index in range(dims[0] * dims[1] * dims[2]):
        array.SetValue(index, flat_values[index])
    image.GetPointData().SetScalars(array)
    return image


def _position_camera(
    camera: Any,
    base: dict[str, list[float]],
    path: list[Any],
    index: int,
    frames: int,
) -> None:
    if path:
        entry = _camera_at(path, index, frames)
        if len(entry) >= 3:
            camera.SetPosition(*entry[:3])
        if len(entry) >= 6:
            camera.SetFocalPoint(*entry[3:6])
        else:
            camera.SetFocalPoint(*base["focal"])
        if len(entry) >= 9:
            camera.SetViewUp(*entry[6:9])
        else:
            camera.SetViewUp(*base["up"])
        camera.OrthogonalizeViewUp()
        return
    camera.SetPosition(*base["position"])
    camera.SetFocalPoint(*base["focal"])
    camera.SetViewUp(*base["up"])
    camera.Azimuth(360.0 * (index + 1) / frames)


def _camera_at(path: list[Any], index: int, frames: int) -> list[float]:
    entries = [
        [float(value) for value in item]
        for item in path
        if isinstance(item, (list, tuple)) and len(item) >= 3
    ]
    if not entries:
        return []
    if len(entries) == 1 or frames <= 1:
        return entries[0]
    position = index / (frames - 1) * (len(entries) - 1)
    lower = min(int(position), len(entries) - 2)
    fraction = position - lower
    start, end = entries[lower], entries[lower + 1]
    length = min(len(start), len(end))
    return [start[i] + (end[i] - start[i]) * fraction for i in range(length)]


def _compose_animation(output_dir: Path, frame_paths: list[Path], fps: int) -> None:
    try:
        import imageio.v2 as imageio  # type: ignore[import-not-found]
    except Exception:
        return
    images = []
    for frame_path in frame_paths:
        try:
            images.append(imageio.imread(frame_path))
        except Exception:
            continue
    if not images:
        return
    try:
        imageio.mimsave(output_dir / "animation.mp4", images, fps=fps)
    except Exception:
        with contextlib.suppress(Exception):
            imageio.mimsave(output_dir / "animation.gif", images, fps=fps)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--job", type=Path)
    args = parser.parse_args()
    if args.probe:
        result = probe()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if args.job is None:
        parser.error("--job is required unless --probe is used")
    job = json.loads(args.job.read_text(encoding="utf-8"))
    try:
        result = render(job)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}
    output = Path(job.get("result_path") or args.job.with_suffix(".result.json"))
    output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Minimal trame + VTK SciView session for ADVP.

The main backend starts this script with an isolated renderer environment and
passes a scene job JSON. It binds to loopback only and prints the URL as JSON.

Usage:
  python trame_viewer.py --scene job.json --port 9123 --token abc
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ETS_TOOLKIT", "qt")
os.environ.setdefault("QT_API", "pyside6")


def build_render_window(job: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    import vtk  # type: ignore[import-not-found]

    geometry = job.get("geometry") or {}
    mode = str(geometry.get("mode") or "volume")
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.04, 0.08, 0.15)
    window = vtk.vtkRenderWindow()
    window.AddRenderer(renderer)
    window.SetSize(1280, 720)
    controls: dict[str, Any] = {}

    if mode in {"points", "surface"} and geometry.get("points"):
        points = vtk.vtkPoints()
        values = vtk.vtkFloatArray()
        for point in geometry["points"]:
            position = point.get("position") or [0, 0, 0]
            points.InsertNextPoint(*position)
            values.InsertNextValue(float(point.get("value", 0)))
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.GetPointData().SetScalars(values)
        mapper = vtk.vtkPointGaussianMapper()
        mapper.SetInputData(polydata)
        mapper.SetScaleFactor(0.04)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        renderer.AddActor(actor)
    else:
        image = _volume_image(vtk, geometry)
        if image is not None:
            mapper = vtk.vtkSmartVolumeMapper()
            mapper.SetInputData(image)
            prop = vtk.vtkVolumeProperty()
            prop.ShadeOn()
            value_range = geometry.get("range") or [0.0, 1.0]
            minimum = float(value_range[0] or 0.0)
            maximum = float(value_range[1] or 1.0)
            if maximum <= minimum:
                maximum = minimum + 1.0
            color = vtk.vtkColorTransferFunction()
            color.AddRGBPoint(minimum, 0.02, 0.02, 0.1)
            color.AddRGBPoint((minimum + maximum) / 2.0, 0.1, 0.6, 0.8)
            color.AddRGBPoint(maximum, 1.0, 0.95, 0.7)
            opacity = vtk.vtkPiecewiseFunction()
            transfer = (job.get("scene") or {}).get("transferFunction") or {}
            points = transfer.get("points") or [[0.0, 0.0], [0.2, 0.02], [1.0, 0.35]]
            for point in points:
                if isinstance(point, (list, tuple)) and len(point) == 2:
                    x_value = float(point[0])
                    y_value = float(point[1])
                    opacity.AddPoint(minimum + x_value * (maximum - minimum), y_value)
            prop.SetColor(color)
            prop.SetScalarOpacity(opacity)
            volume = vtk.vtkVolume()
            volume.SetMapper(mapper)
            volume.SetProperty(prop)
            renderer.AddActor(volume)
            controls.update(
                {
                    "volume": prop,
                    "color": color,
                    "opacity": opacity,
                    "range": [minimum, maximum],
                    "opacity_value": float(points[-1][1]) if points else 0.35,
                }
            )
        else:
            source = vtk.vtkSphereSource()
            source.SetRadius(1.0)
            source.SetThetaResolution(64)
            source.SetPhiResolution(64)
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(source.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            renderer.AddActor(actor)
    renderer.ResetCamera()
    return window, controls


def _volume_image(vtk: Any, geometry: dict[str, Any]) -> Any | None:
    values = geometry.get("values")
    shape = geometry.get("display_shape") or geometry.get("shape") or []
    if not values or len(shape) < 3:
        return None
    dims = [int(shape[0]), int(shape[1]), int(shape[2])]
    flat = [float(value or 0) for value in values]
    if len(flat) < dims[0] * dims[1] * dims[2]:
        return None
    image = vtk.vtkImageData()
    image.SetDimensions(*dims)
    array = vtk.vtkFloatArray()
    array.SetNumberOfComponents(1)
    array.SetNumberOfTuples(dims[0] * dims[1] * dims[2])
    for index in range(dims[0] * dims[1] * dims[2]):
        array.SetValue(index, flat[index])
    image.GetPointData().SetScalars(array)
    return image


def _apply_window(
    window: Any,
    controls: dict[str, Any],
    window_min: float,
    window_max: float,
    opacity: float,
) -> None:
    color = controls.get("color")
    opacity_fn = controls.get("opacity")
    if color is None or opacity_fn is None:
        return
    minimum = float(window_min)
    maximum = float(window_max)
    if maximum <= minimum:
        maximum = minimum + 1.0
    color.RemoveAllPoints()
    color.AddRGBPoint(minimum, 0.02, 0.02, 0.1)
    color.AddRGBPoint((minimum + maximum) / 2.0, 0.1, 0.6, 0.8)
    color.AddRGBPoint(maximum, 1.0, 0.95, 0.7)
    opacity_fn.RemoveAllPoints()
    opacity_fn.AddPoint(minimum, 0.0)
    opacity_fn.AddPoint(maximum, max(0.0, min(1.0, float(opacity))))
    window.Render()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    job = json.loads(args.scene.read_text(encoding="utf-8"))
    window, controls = build_render_window(job)

    from trame.app import get_server  # type: ignore[import-not-found]
    from trame.ui.vuetify3 import SinglePageLayout  # type: ignore[import-not-found]
    from trame.widgets import vtk as vtk_widgets  # type: ignore[import-not-found]
    from trame.widgets import vuetify3 as v3

    server = get_server()
    server.client_type = "vue3"
    state = server.state
    value_range = controls.get("range") or [0.0, 1.0]
    minimum = float(value_range[0] or 0.0)
    maximum = float(value_range[1] or 1.0)
    if maximum <= minimum:
        maximum = minimum + 1.0
    state.opacity = max(0.0, min(1.0, float(controls.get("opacity_value") or 0.35)))
    state.window_min = minimum
    state.window_max = maximum

    @state.change("window_min", "window_max")  # type: ignore[untyped-decorator]
    def _window_changed(window_min: float, window_max: float, **kwargs: Any) -> None:
        _apply_window(window, controls, window_min, window_max, state.opacity)

    @state.change("opacity")  # type: ignore[untyped-decorator]
    def _opacity_changed(opacity: float, **kwargs: Any) -> None:
        _apply_window(window, controls, state.window_min, state.window_max, opacity)

    with SinglePageLayout(server) as layout:
        layout.title.set_text("ADVP SciView")
        with layout.content:
            v3.VSlider(
                v_model=("window_min", minimum),
                min=minimum,
                max=maximum,
                step=(maximum - minimum) / 100.0 or 1.0,
                label="窗宽下限",
                hide_details=True,
                density="compact",
                disabled=not bool(controls),
            )
            v3.VSlider(
                v_model=("window_max", maximum),
                min=minimum,
                max=maximum,
                step=(maximum - minimum) / 100.0 or 1.0,
                label="窗宽上限",
                hide_details=True,
                density="compact",
                disabled=not bool(controls),
            )
            v3.VSlider(
                v_model=("opacity", state.opacity),
                min=0.0,
                max=1.0,
                step=0.01,
                label="不透明度",
                hide_details=True,
                density="compact",
                disabled=not bool(controls),
            )
            vtk_widgets.VtkLocalView(window, style="width: 100%; height: 80vh;")
    print(
        json.dumps(
            {
                "ok": True,
                "port": args.port,
                "url": f"http://127.0.0.1:{args.port}/?token={args.token}",
                "token": args.token,
            }
        ),
        flush=True,
    )
    server.start(port=args.port, open_browser=False, show_connection_info=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

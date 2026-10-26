# ruff: noqa: E501
"""Generate reproducible Python scripts and notebooks for chart selections."""

from __future__ import annotations

import json
from typing import Any

from advp.models import ChartSelection, Dataset

TABLE_FORMATS = {"csv", "tsv", "json", "jsonl", "parquet", "xlsx", "xls"}
ARRAY_FORMATS = {"hdf5", "netcdf", "fits", "nifti", "dicom", "raw"}


def build_python_script(
    *,
    dataset: Dataset,
    selection: ChartSelection,
    render: dict[str, Any],
) -> str:
    """Return a standalone Python script with data loading and chart reproduction."""
    result = selection.result_json or {}
    selected = result.get("selected") or {}
    chart_id = str(selected.get("chart_id") or selection.selected_chart_id)
    fields = {str(key): str(value) for key, value in (selected.get("fields") or {}).items()}
    style_value = selected.get("style")
    style: dict[str, Any] = style_value if isinstance(style_value, dict) else {}
    renderer = str(render.get("renderer") or "plotly")
    figure = render.get("figure") or {}
    payload = {
        "chart_id": chart_id,
        "renderer": renderer,
        "fields": fields,
        "style": style,
        "figure": figure,
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "kind": dataset.kind,
            "format": dataset.format,
            "source_path": dataset.source_path,
            "options": dataset.options,
            "schema": dataset.schema_json,
        },
    }
    lines = [
        '"""ADVP reproducible chart export.',
        "",
        f"Dataset: {dataset.name} ({dataset.format})",
        f"Chart: {chart_id} ({renderer})",
        '"""',
        "",
        "# Requirements: pandas, plotly, networkx, matplotlib,",
        "# nibabel, pydicom, h5py, xarray, astropy",
        "# Install: pip install pandas plotly networkx matplotlib nibabel pydicom h5py xarray astropy",
        "",
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "",
        "PAYLOAD = json.loads(r'''"
        + json.dumps(payload, ensure_ascii=False).replace("'''", "\\'\\'\\'")
        + "''')",
        "",
        "SOURCE = Path(PAYLOAD['dataset']['source_path'])",
        "",
        "def load_data():",
    ]
    lines.extend(_data_loader(dataset))
    lines.extend(
        [
            "",
            "def build_chart():",
            "    data = load_data()",
        ]
    )
    lines.extend(_chart_code(chart_id=chart_id, renderer=renderer, fields=fields, style=style))
    lines.extend(
        [
            "",
            "if __name__ == '__main__':",
            "    chart = build_chart()",
            "    chart.write_html('advp-chart.html')",
            "    print('wrote advp-chart.html')",
            "",
        ]
    )
    return "\n".join(lines)


def build_notebook(script: str) -> dict[str, Any]:
    """Return a Jupyter notebook wrapping the generated script."""
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# ADVP reproducible chart\n",
                    "\n",
                    "Generated from a persisted selection.\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": script.splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _data_loader(dataset: Dataset) -> list[str]:
    if dataset.format == "csv":
        return [
            "    import pandas as pd",
            "    return pd.read_csv(SOURCE)",
        ]
    if dataset.format == "tsv":
        return [
            "    import pandas as pd",
            "    return pd.read_csv(str(SOURCE), sep='\\t')",
        ]
    if dataset.format in {"json", "jsonl"}:
        return [
            "    import pandas as pd",
            "    return pd.read_json(str(SOURCE), lines=SOURCE.suffix.lower() == '.jsonl')",
        ]
    if dataset.format == "parquet":
        return [
            "    import pandas as pd",
            "    return pd.read_parquet(SOURCE)",
        ]
    if dataset.format in {"xlsx", "xls"}:
        return [
            "    import pandas as pd",
            "    return pd.read_excel(SOURCE)",
        ]
    if dataset.format == "hdf5":
        return [
            "    import h5py",
            "    with h5py.File(SOURCE, 'r') as handle:",
            "        return handle[PAYLOAD['dataset']['schema'].get('variable')][()]",
        ]
    if dataset.format == "netcdf":
        return [
            "    import xarray as xr",
            "    with xr.open_dataset(SOURCE, decode_times=False) as data:",
            "        return data[PAYLOAD['dataset']['schema'].get('variable')].values",
        ]
    if dataset.format == "fits":
        return [
            "    from astropy.io import fits",
            "    with fits.open(SOURCE, memmap=True) as hdul:",
            "        for hdu in hdul:",
            "            if getattr(hdu, 'name', '') == PAYLOAD['dataset']['schema'].get('variable'):",
            "                return hdu.data",
            "    raise ValueError('FITS HDU not found')",
        ]
    if dataset.format == "nifti":
        return [
            "    import nibabel as nib",
            "    return nib.load(str(SOURCE)).get_fdata()",
        ]
    if dataset.format == "dicom":
        return [
            "    import pydicom",
            "    from pathlib import Path as _Path",
            "    files = sorted(_Path(SOURCE).rglob('*.dcm')) if SOURCE.is_dir() else [SOURCE]",
            "    return [pydicom.dcmread(str(item), force=True).pixel_array for item in files]",
        ]
    if dataset.format == "raw":
        return [
            "    import numpy as np",
            "    options = PAYLOAD['dataset']['options']",
            "    dtype = np.dtype(options['dtype'])",
            "    if options.get('byte_order') == 'little':",
            "        dtype = dtype.newbyteorder('<')",
            "    elif options.get('byte_order') == 'big':",
            "        dtype = dtype.newbyteorder('>')",
            "    return np.memmap(SOURCE, dtype=dtype, mode='r', offset=int(options.get('raw_offset', 0)), shape=tuple(options['shape']))",
        ]
    return ["    raise ValueError(f\"unsupported dataset format: {PAYLOAD['dataset']['format']}\")"]


def _chart_code(
    *,
    chart_id: str,
    renderer: str,
    fields: dict[str, str],
    style: dict[str, Any],
) -> list[str]:
    if renderer == "plotly":
        return [
            "    import plotly.graph_objects as go",
            "    figure = go.Figure(PAYLOAD['figure'])",
            "    figure.update_layout(template='plotly_dark')",
            "    return figure",
        ]
    if chart_id == "sankey_flow":
        return [
            "    import pandas as pd",
            "    import plotly.graph_objects as go",
            "    source = PAYLOAD['fields']['source']",
            "    target = PAYLOAD['fields']['target']",
            "    weight = PAYLOAD['fields']['weight']",
            "    frame = data[[source, target, weight]].dropna()",
            "    links = frame.groupby([source, target], as_index=False)[weight].sum()",
            "    nodes = list(dict.fromkeys(list(links[source]) + list(links[target])))",
            "    index = {name: position for position, name in enumerate(nodes)}",
            "    figure = go.Figure(go.Sankey(",
            "        node={'label': nodes},",
            "        link={",
            "            'source': links[source].map(index),",
            "            'target': links[target].map(index),",
            "            'value': links[weight],",
            "        },",
            "    ))",
            "    return figure",
        ]
    if chart_id == "sunburst_hierarchy":
        return [
            "    import pandas as pd",
            "    import plotly.graph_objects as go",
            "    levels = [",
            "        PAYLOAD['fields'][role]",
            "        for role in ('level1', 'level2', 'level3')",
            "        if role in PAYLOAD['fields']",
            "    ]",
            "    value_field = PAYLOAD['fields']['value']",
            "    tree = {}",
            "    for _, row in data.iterrows():",
            "        parent = ''",
            "        path = []",
            "        for level in levels:",
            "            name = str(row[level])",
            "            path.append(name)",
            "            label = '/'.join(path)",
            "            node = tree.setdefault(label, {'parent': parent, 'value': 0.0})",
            "            node['value'] += float(row[value_field])",
            "            parent = label",
            "    labels = list(tree)",
            "    parents = [tree[label]['parent'] for label in labels]",
            "    values = [tree[label]['value'] for label in labels]",
            "    return go.Figure(go.Sunburst(labels=labels, parents=parents, values=values))",
        ]
    if chart_id == "network_graph":
        return [
            "    import matplotlib.pyplot as plt",
            "    import networkx as nx",
            "    graph = nx.from_pandas_edgelist(",
            "        data,",
            "        source=PAYLOAD['fields']['source'],",
            "        target=PAYLOAD['fields']['target'],",
            "        edge_attr=PAYLOAD['fields'].get('weight'),",
            "    )",
            "    nx.draw(graph, with_labels=True, node_size=300, font_size=8)",
            "    class _Figure:",
            "        def write_html(self, path):",
            "            plt.savefig(str(path).replace('.html', '.png'), dpi=200, bbox_inches='tight')",
            "    return _Figure()",
        ]
    if renderer == "deckgl":
        return [
            "    import plotly.express as px",
            "    fields = PAYLOAD['fields']",
            "    chart = PAYLOAD['chart_id']",
            "    if chart == 'geo_region':",
            "        region = data[fields['region']].astype(str)",
            "        mode = 'ISO-3' if region.str.len().eq(3).all() else 'country names'",
            "        return px.choropleth(data, locations=fields['region'], color=fields['value'], locationmode=mode)",
            "    if chart == 'geo_trajectory':",
            "        sort_fields = [item for item in (fields.get('track'), fields.get('time')) if item]",
            "        if sort_fields:",
            "            data = data.sort_values(sort_fields)",
            "        return px.line_geo(",
            "            data,",
            "            lat=fields['latitude'],",
            "            lon=fields['longitude'],",
            "            line_group=fields.get('track'),",
            "            color=fields.get('value'),",
            "        )",
            "    if chart == 'geo_density':",
            "        return px.scatter_geo(",
            "            data,",
            "            lat=fields['latitude'],",
            "            lon=fields['longitude'],",
            "            size=fields.get('weight'),",
            "            opacity=0.35,",
            "            title='Density approximated with sized points',",
            "        )",
            "    return px.scatter_geo(",
            "        data,",
            "        lat=fields['latitude'],",
            "        lon=fields['longitude'],",
            "        color=fields.get('value'),",
            "        size=fields.get('size'),",
            "        hover_name=fields.get('label'),",
            "    )",
        ]
    if renderer == "echarts":
        return [
            "    import plotly.graph_objects as go",
            "    figure = go.Figure()",
            "    figure.add_annotation(",
            "        text='ECharts option is preserved in PAYLOAD. Use the ADVP share page for exact rendering.',",
            "        showarrow=False,",
            "    )",
            "    return figure",
        ]
    if renderer == "vtk":
        return [
            "    import matplotlib.pyplot as plt",
            "    import numpy as np",
            "    imaging = PAYLOAD['figure'].get('imaging', {})",
            "    axis = int(imaging.get('axis', 0))",
            "    index = int(imaging.get('index', 0))",
            "    volume = int(imaging.get('volume', 0))",
            "    array = np.asarray(data)",
            "    if array.ndim == 4:",
            "        array = array[volume]",
            "        axis = max(0, axis - 1)",
            "    if array.ndim == 3:",
            "        array = np.take(array, index, axis=axis if 0 <= axis < 3 else 0)",
            "    window = imaging.get('window') or {}",
            "    vmin = window.get('min')",
            "    vmax = window.get('max')",
            "    plt.imshow(array, cmap='gray', vmin=vmin, vmax=vmax)",
            "    plt.colorbar()",
            "    class _Figure:",
            "        def write_html(self, path):",
            "            plt.savefig(str(path).replace('.html', '.png'), dpi=200, bbox_inches='tight')",
            "    return _Figure()",
        ]
    return [
        "    raise ValueError(f\"unsupported renderer: {PAYLOAD['renderer']}\")",
    ]


def build_scene_python_script(dataset: Dataset, scene_json: dict[str, Any]) -> str:
    """Generate a reproducible Mayavi/VTK-style script from Scene JSON."""
    payload = {
        "scene": scene_json,
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "kind": dataset.kind,
            "format": dataset.format,
            "source_path": dataset.source_path,
            "options": dataset.options,
            "schema": dataset.schema_json,
        },
    }
    lines = [
        '"""ADVP reproducible 3D scene export.',
        "",
        f"Dataset: {dataset.name} ({dataset.format})",
        '"""',
        "",
        "# Requirements: numpy pandas mayavi vtk",
        "# Install: pip install numpy pandas mayavi vtk",
        "",
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "",
        "PAYLOAD = json.loads(r'''"
        + json.dumps(payload, ensure_ascii=False).replace("'''", "\\'\\'\\'")
        + "''')",
        "",
        "SOURCE = Path(PAYLOAD['dataset']['source_path'])",
        "",
        "def load_data():",
    ]
    lines.extend(_data_loader(dataset))
    lines.extend(
        [
            "",
            "def build_scene():",
            "    import numpy as np",
            "    from mayavi import mlab",
            "",
            "    data = load_data()",
            "    scene = PAYLOAD['scene']",
            "    geometry = scene.get('geometry', {})",
            "    mode = geometry.get('type', 'points')",
            "    mlab.options.offscreen = True",
            "    figure = mlab.figure(size=(1280, 720), bgcolor=(0.04, 0.08, 0.15))",
            "",
            "    if mode in ('points', 'surface'):",
            "        coords = scene.get('data', {}).get('coordinates', {})",
            "        x_name = coords.get('x')",
            "        y_name = coords.get('y')",
            "        z_name = coords.get('z')",
            "        fields = scene.get('data', {}).get('fields') or []",
            "        value_name = fields[0] if fields else None",
            "        values = data[value_name].to_numpy() if value_name else None",
            "        mlab.points3d(data[x_name], data[y_name], data[z_name] if z_name else np.zeros(len(data)), values, colormap=scene.get('colormap', {}).get('name', 'viridis'))",
            "    else:",
            "        array = np.asarray(data)",
            "        if array.ndim > 3:",
            "            array = array[0]",
            "        if mode == 'slice' and array.ndim == 3:",
            "            mlab.imshow(array[0], colormap=scene.get('colormap', {}).get('name', 'viridis'))",
            "        else:",
            "            source = mlab.pipeline.scalar_field(array)",
            "            mlab.pipeline.volume(source)",
            "",
            "    mlab.view(azimuth=45, elevation=60, distance='auto', focalpoint=(0, 0, 0))",
            "    mlab.savefig('scene.png', figure=figure)",
            "    return figure",
            "",
            "if __name__ == '__main__':",
            "    build_scene()",
            "    print('wrote scene.png')",
            "",
        ]
    )
    return "\n".join(lines)

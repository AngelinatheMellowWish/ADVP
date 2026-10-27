"""Read metadata and individual slices from stored scientific arrays."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import h5py  # type: ignore[import-untyped]
import nibabel as nib
import numpy as np
import pydicom
import xarray as xr
from astropy.io import fits  # type: ignore[import-untyped]
from pydicom.errors import InvalidDicomError

from advp.models import Dataset


class ImagingError(Exception):
    """Imaging metadata or slice request cannot be satisfied."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def imaging_meta(dataset: Dataset) -> dict[str, Any]:
    """Return shape, axes, window, and slice limits for one array dataset."""
    if dataset.kind != "array":
        raise ImagingError("unsupported_kind", "imaging requires an array dataset")
    schema = dataset.schema_json or {}
    shape = [int(size) for size in schema.get("shape", [])]
    dims = [str(dim) for dim in schema.get("dims", [])]
    if len(shape) < 2:
        raise ImagingError("not_imaging", "imaging requires at least a 2D array")
    if len(shape) > 4:
        raise ImagingError("array_dim_unsupported", "imaging supports 2D, 3D, and 4D arrays")
    if len(dims) != len(shape):
        dims = [f"dim_{index}" for index in range(len(shape))]
    stats = (dataset.profile_json.get("array") or {}).get("stats") or {}
    slice_axes, volume_axis, volume_count = _slice_axes(shape, dims)
    return {
        "dataset_id": dataset.id,
        "format": dataset.format,
        "shape": shape,
        "dims": dims,
        "dtype": schema.get("dtype"),
        "units": schema.get("units"),
        "slice_axes": slice_axes,
        "volume_axis": volume_axis,
        "volume_count": volume_count,
        "default_axis": slice_axes[0]["axis"] if slice_axes else None,
        "default_index": 0,
        "window": {"min": stats.get("min"), "max": stats.get("max")},
    }


def read_slice(
    dataset: Dataset,
    *,
    axis: int,
    index: int,
    volume: int = 0,
) -> dict[str, Any]:
    """Read one 2D slice from a stored 2D/3D/4D array."""
    meta = imaging_meta(dataset)
    shape = meta["shape"]
    dims = meta["dims"]
    ndim = len(shape)
    volume_axis = meta["volume_axis"]
    volume_count = meta["volume_count"]
    if volume_axis is not None and not (0 <= volume < int(volume_count)):
        raise ImagingError(
            "invalid_volume",
            f"volume {volume} is outside 0..{int(volume_count) - 1}",
        )
    if ndim == 2:
        if axis not in (0,) or index not in (0,):
            raise ImagingError("invalid_axis", "2D images have a single slice at axis=0,index=0")
    else:
        allowed = {int(item["axis"]) for item in meta["slice_axes"]}
        if axis not in allowed:
            raise ImagingError("invalid_axis", f"axis {axis} is not sliceable")
        size = shape[axis]
        if not (0 <= index < size):
            raise ImagingError("invalid_index", f"index {index} is outside 0..{size - 1}")

    array = _read_array(dataset, ndim=ndim, axis=axis, index=index, volume=volume)
    if array.ndim > 2:
        array = np.squeeze(array)
    if array.ndim != 2:
        raise ImagingError(
            "slice_dimension_unsupported",
            f"slice produced {array.ndim} dimensions instead of 2",
        )
    finite = array[np.isfinite(array)] if np.issubdtype(array.dtype, np.number) else array
    vmin = _json_number(np.min(finite)) if finite.size else None
    vmax = _json_number(np.max(finite)) if finite.size else None
    return {
        "dataset_id": dataset.id,
        "axis": axis,
        "index": index,
        "axis_name": dims[axis] if axis < len(dims) else f"axis_{axis}",
        "volume": volume,
        "rows": int(array.shape[0]),
        "cols": int(array.shape[1]),
        "values": [[_json_value(value) for value in row] for row in array.tolist()],
        "vmin": vmin,
        "vmax": vmax,
        "shape": shape,
    }


VOLUME_SAMPLE_LIMIT = 2_000_000


def read_sampled_volume(
    dataset: Dataset,
    *,
    max_elements: int = VOLUME_SAMPLE_LIMIT,
    volume: int = 0,
) -> dict[str, Any]:
    """Read a strided 2D/3D sample from a stored volume.

    The full source is never materialized for NIfTI/HDF5/NetCDF/FITS/RAW;
    only the requested stride is read. This keeps large volumes usable by the
    browser renderer without requiring a server-side render.
    """
    if dataset.kind != "array":
        raise ImagingError("unsupported_kind", "volume sampling requires an array dataset")
    schema = dataset.schema_json or {}
    shape = [int(size) for size in schema.get("shape", [])]
    dims = [str(dim) for dim in schema.get("dims", [])]
    if len(shape) not in (2, 3, 4):
        raise ImagingError(
            "array_dim_unsupported",
            "volume sampling supports 2D, 3D, and 4D arrays",
        )
    if any(size <= 0 for size in shape):
        raise ImagingError("empty_array", "volume has no elements")
    if len(dims) != len(shape):
        dims = [f"dim_{index}" for index in range(len(shape))]
    volume_count = shape[0] if len(shape) == 4 else 1
    if not 0 <= volume < volume_count:
        raise ImagingError(
            "invalid_volume",
            f"volume {volume} is outside 0..{volume_count - 1}",
        )
    working_shape = shape[1:] if len(shape) == 4 else shape
    working_dims = dims[1:] if len(shape) == 4 else dims
    total = math.prod(working_shape)
    limit = max(1, int(max_elements))
    stride = max(1, math.ceil((total / limit) ** (1 / len(working_shape))))
    base_indexer = tuple(slice(None, None, stride) for _ in working_shape)
    indexer = (volume, *base_indexer) if len(shape) == 4 else base_indexer
    array = _read_volume(dataset, indexer=indexer, volume=volume, ndim=len(shape))
    if array.ndim != len(working_shape):
        array = np.squeeze(array)
    if array.ndim != len(working_shape):
        raise ImagingError(
            "volume_dimension_unsupported",
            f"volume sample produced {array.ndim} dimensions instead of {len(working_shape)}",
        )
    finite = array[np.isfinite(array)] if np.issubdtype(array.dtype, np.number) else array
    vmin = _json_number(np.min(finite)) if finite.size else None
    vmax = _json_number(np.max(finite)) if finite.size else None
    values = [_json_value(value) for value in array.reshape(-1).tolist()]
    return {
        "dataset_id": dataset.id,
        "variable": str(schema.get("variable", dataset.name)),
        "shape": working_shape,
        "source_shape": shape,
        "dims": working_dims,
        "dtype": schema.get("dtype") or str(array.dtype),
        "units": schema.get("units"),
        "spacing": _volume_spacing(dataset, len(working_shape)),
        "origin": [0.0, 0.0, 0.0],
        "range": [vmin, vmax],
        "display_shape": [int(size) for size in array.shape],
        "sampled": bool(dataset.sampled or stride > 1 or len(shape) == 4),
        "lod": stride,
        "volume": volume,
        "volume_count": volume_count,
        "values": values,
    }


def _read_volume(
    dataset: Dataset,
    *,
    indexer: tuple[Any, ...],
    volume: int,
    ndim: int,
) -> np.ndarray:
    schema = dataset.schema_json or {}
    variable = str(schema.get("variable", dataset.name))
    path = Path(dataset.source_path)
    if dataset.format == "hdf5":
        with h5py.File(path, "r") as handle:
            return np.asarray(handle[variable][indexer])
    if dataset.format == "netcdf":
        with xr.open_dataset(path, decode_times=False) as data:
            dim_names = list(data[variable].dims)
            selection = {
                dim_names[position]: (
                    slice(value.start, value.stop, value.step)
                    if isinstance(value, slice)
                    else value
                )
                for position, value in enumerate(indexer)
            }
            return np.asanyarray(data[variable].isel(selection).values)
    if dataset.format == "fits":
        with fits.open(path, memmap=True) as hdul:
            for hdu in hdul:
                if getattr(hdu, "name", "") == variable:
                    if hdu.data is None:
                        raise ImagingError("empty_array", "FITS HDU has no data")
                    return np.asarray(hdu.data[indexer])
        raise ImagingError("invalid_source", f"FITS HDU {variable!r} was not found")
    if dataset.format == "nifti":
        image: Any = nib.load(str(path))
        return np.asanyarray(image.dataobj[indexer])
    if dataset.format == "raw":
        return _read_raw(dataset, indexer)
    if dataset.format == "dicom":
        array = _read_dicom_volume(path, ndim=ndim, volume=volume)
        sample_indexer = indexer[1:] if ndim == 4 else indexer
        return np.asarray(array[sample_indexer])
    raise ImagingError("unsupported_kind", f"format {dataset.format!r} has no volume reader")


def _read_dicom_volume(path: Path, *, ndim: int, volume: int) -> np.ndarray:
    entries = _dicom_entries(path)
    if ndim == 4:
        if volume >= len(entries):
            raise ImagingError("invalid_volume", f"volume {volume} is outside the series")
        array = _dicom_array(pydicom.dcmread(entries[volume][0], force=True))
        if array.ndim == 2:
            return array[np.newaxis, :, :]
        if array.ndim != 3:
            raise ImagingError(
                "volume_dimension_unsupported",
                "4D DICOM volume requires 2D slices or multi-frame entries",
            )
        return array
    first = _dicom_array(pydicom.dcmread(entries[0][0], force=True))
    if len(entries) == 1 and first.ndim == 3:
        return first
    arrays = [_dicom_array(pydicom.dcmread(item[0], force=True)) for item in entries]
    if arrays[0].ndim == 2:
        return np.stack(arrays)
    return np.concatenate(arrays, axis=0)


def _volume_spacing(dataset: Dataset, ndim: int) -> list[float]:
    if dataset.format == "nifti":
        try:
            image: Any = nib.load(dataset.source_path)
            zooms = [float(value) for value in image.header.get_zooms()]
            return (zooms + [1.0] * 3)[:ndim]
        except (OSError, ValueError):
            pass
    return [1.0] * ndim


def _slice_axes(
    shape: list[int],
    dims: list[str],
) -> tuple[list[dict[str, Any]], int | None, int]:
    if len(shape) == 2:
        return [], None, 1
    if len(shape) == 3:
        return (
            [{"axis": index, "name": dims[index], "size": shape[index]} for index in range(3)],
            None,
            1,
        )
    return (
        [{"axis": index, "name": dims[index], "size": shape[index]} for index in range(1, 4)],
        0,
        shape[0],
    )


def _read_array(
    dataset: Dataset,
    *,
    ndim: int,
    axis: int,
    index: int,
    volume: int,
) -> np.ndarray:
    schema = dataset.schema_json or {}
    variable = str(schema.get("variable", dataset.name))
    indexer = _index_tuple(ndim=ndim, axis=axis, index=index, volume=volume)
    path = Path(dataset.source_path)
    try:
        if dataset.format == "hdf5":
            with h5py.File(path, "r") as handle:
                return np.asarray(handle[variable][indexer])
        if dataset.format == "netcdf":
            with xr.open_dataset(path, decode_times=False) as data:
                dim_names = list(data[variable].dims)
                selection = {
                    dim_names[position]: value
                    for position, value in enumerate(indexer)
                    if value != slice(None)
                }
                return np.asanyarray(data[variable].isel(selection).values)
        if dataset.format == "fits":
            with fits.open(path, memmap=True) as hdul:
                for hdu in hdul:
                    if getattr(hdu, "name", "") == variable:
                        if hdu.data is None:
                            raise ImagingError("empty_array", "FITS HDU has no data")
                        return np.asarray(hdu.data[indexer])
            raise ImagingError("invalid_source", f"FITS HDU {variable!r} was not found")
        if dataset.format == "nifti":
            image: Any = nib.load(str(path))
            return np.asanyarray(image.dataobj[indexer])
        if dataset.format == "raw":
            return _read_raw(dataset, indexer)
        if dataset.format == "dicom":
            return _read_dicom(
                path,
                ndim=ndim,
                axis=axis,
                index=index,
                volume=volume,
            )
    except ImagingError:
        raise
    except (OSError, ValueError, KeyError, InvalidDicomError) as exc:
        raise ImagingError("imaging_read_failed", f"cannot read imaging slice: {exc}") from exc
    raise ImagingError("unsupported_kind", f"format {dataset.format!r} has no slice reader")


def _index_tuple(
    *,
    ndim: int,
    axis: int,
    index: int,
    volume: int,
) -> tuple[Any, ...]:
    if ndim == 2:
        return (slice(None), slice(None))
    if ndim == 3:
        return tuple(index if position == axis else slice(None) for position in range(3))
    return tuple(
        volume if position == 0 else index if position == axis else slice(None)
        for position in range(4)
    )


def _read_raw(dataset: Dataset, indexer: tuple[Any, ...]) -> np.ndarray:
    options = dataset.options or {}
    shape = [int(size) for size in options.get("shape", [])]
    dtype_text = options.get("dtype")
    if not shape or not dtype_text:
        raise ImagingError("invalid_source", "RAW slice requires shape and dtype options")
    dtype = np.dtype(str(dtype_text))
    if options.get("byte_order") == "little":
        dtype = dtype.newbyteorder("<")
    elif options.get("byte_order") == "big":
        dtype = dtype.newbyteorder(">")
    memory_map = np.memmap(
        dataset.source_path,
        dtype=dtype,
        mode="r",
        offset=int(options.get("raw_offset", 0) or 0),
        shape=tuple(shape),
    )
    try:
        return np.asarray(memory_map[indexer]).copy()
    finally:
        del memory_map


def _read_dicom(
    path: Path,
    *,
    ndim: int,
    axis: int,
    index: int,
    volume: int = 0,
) -> np.ndarray:
    entries = _dicom_entries(path)
    if ndim == 4:
        if volume >= len(entries):
            raise ImagingError("invalid_volume", f"volume {volume} is outside the series")
        dataset = pydicom.dcmread(entries[volume][0], force=True)
        array = _dicom_array(dataset)
        if array.ndim != 3:
            raise ImagingError(
                "slice_dimension_unsupported",
                "4D DICOM series requires multi-frame entries",
            )
        if axis == 1:
            return np.asarray(array[index])
        if axis == 2:
            return np.asarray(array[:, index, :])
        if axis == 3:
            return np.asarray(array[:, :, index])
        raise ImagingError("invalid_axis", f"axis {axis} is not sliceable for 4D DICOM")
    if ndim == 3:
        first = _dicom_array(pydicom.dcmread(entries[0][0], force=True))
        if len(entries) == 1 and first.ndim == 3:
            if axis == 0:
                return np.asarray(first[index])
            if axis == 1:
                return np.asarray(first[:, index, :])
            return np.asarray(first[:, :, index])
        if axis == 0:
            dataset = pydicom.dcmread(entries[index][0], force=True)
            return _dicom_array(dataset)
        arrays = [_dicom_array(pydicom.dcmread(item[0], force=True)) for item in entries]
        stacked: np.ndarray = np.stack(arrays)
        if axis == 1:
            return np.asarray(stacked[:, index, :])
        return np.asarray(stacked[:, :, index])
    arrays = [_dicom_array(pydicom.dcmread(item[0], force=True)) for item in entries]
    return np.asarray(arrays[0] if len(arrays) == 1 else np.stack(arrays))


def _dicom_entries(path: Path) -> list[tuple[Path, Any]]:
    candidates = (
        sorted(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else [path]
    )
    entries: list[tuple[Path, Any]] = []
    for candidate in candidates:
        try:
            dataset = pydicom.dcmread(candidate, stop_before_pixels=True, force=True)
        except (InvalidDicomError, OSError, ValueError):
            continue
        if not hasattr(dataset, "Rows") or not hasattr(dataset, "Columns"):
            continue
        entries.append((candidate, dataset))
    if not entries:
        raise ImagingError("invalid_source", "no DICOM images were found")
    entries.sort(
        key=lambda item: (
            float(getattr(item[1], "InstanceNumber", 0) or 0),
            item[0].name,
        )
    )
    return entries


def _dicom_array(dataset: Any) -> np.ndarray:
    array = np.asarray(dataset.pixel_array)
    slope = float(getattr(dataset, "RescaleSlope", 1) or 1)
    intercept = float(getattr(dataset, "RescaleIntercept", 0) or 0)
    if slope != 1 or intercept != 0:
        array = array.astype(np.float32) * slope + intercept
    return array


def _json_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_value(value: Any) -> float | None:
    if isinstance(value, (np.generic,)):
        value = value.item()
    return _json_number(value)

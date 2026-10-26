"""Browse and profile HDF5, NetCDF, and FITS arrays."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py  # type: ignore[import-untyped]
import nibabel as nib
import numpy as np
import pydicom
import xarray as xr
from astropy.io import fits  # type: ignore[import-untyped]
from pydicom.errors import InvalidDicomError

from advp.ingest.files import (
    FileTooLargeError,
    ImportOptions,
    InvalidSourceError,
    SourceNotFoundError,
    UnsupportedFormatError,
)

SCIENTIFIC_SUFFIXES = {
    ".h5": "hdf5",
    ".hdf5": "hdf5",
    ".he5": "hdf5",
    ".nc": "netcdf",
    ".nc4": "netcdf",
    ".cdf": "netcdf",
    ".fits": "fits",
    ".fit": "fits",
    ".fts": "fits",
    ".nii": "nifti",
    ".dcm": "dicom",
    ".dicom": "dicom",
    ".raw": "raw",
    ".bin": "raw",
}

IMAGING_FORMATS = {"dicom", "nifti", "raw"}


@dataclass(slots=True)
class ScientificInspection:
    path: Path
    format: str
    size_bytes: int
    mtime: float
    variables: list[dict[str, Any]]
    variable: str | None
    schema: dict[str, Any]
    profile: dict[str, Any]
    preview: list[dict[str, Any]]
    row_count: int
    column_count: int
    sampled: bool
    options: dict[str, Any]
    detected: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)


def _looks_like_dicom_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    for index, candidate in enumerate(sorted(item for item in path.iterdir() if item.is_file())):
        if index >= 5:
            break
        try:
            pydicom.dcmread(candidate, stop_before_pixels=True, force=True)
            return True
        except (InvalidDicomError, OSError, ValueError):
            pass
    return False


def is_scientific_source(path: str | Path) -> bool:
    value = Path(path)
    if value.is_dir():
        return _looks_like_dicom_dir(value)
    name = value.name.lower()
    if name.endswith(".nii.gz"):
        return True
    return value.suffix.lower() in SCIENTIFIC_SUFFIXES


def resolve_source(path_value: str, max_file_bytes: int) -> tuple[Path, str, int, float]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise SourceNotFoundError(
            f"source file was not found: {path.name}",
            hint="check the path or relocate the dataset",
        )
    if path.is_dir():
        files = [item for item in path.rglob("*") if item.is_file()]
        if not files:
            raise InvalidSourceError(f"source directory is empty: {path.name}")
        size = sum(item.stat().st_size for item in files)
        mtime = max(item.stat().st_mtime for item in files)
        if size > max_file_bytes:
            limit_gb = max_file_bytes / (1024**3)
            raise FileTooLargeError(
                f"directory is {size / (1024**3):.2f} GiB, above the {limit_gb:.2f} GiB limit",
                hint="split the series or raise the configured limit",
            )
        return path, "dicom", size, mtime
    if not path.is_file():
        raise InvalidSourceError(f"source path is not a file: {path.name}")
    name = path.name.lower()
    file_format = (
        "nifti" if name.endswith(".nii.gz") else SCIENTIFIC_SUFFIXES.get(path.suffix.lower())
    )
    if file_format is None:
        supported = ", ".join(sorted(SCIENTIFIC_SUFFIXES))
        raise UnsupportedFormatError(
            f"unsupported scientific format: {path.suffix or '<none>'}",
            hint=f"supported formats: {supported}, .nii.gz, DICOM directories",
        )
    size = path.stat().st_size
    if size > max_file_bytes:
        limit_gb = max_file_bytes / (1024**3)
        raise FileTooLargeError(
            f"file is {size / (1024**3):.2f} GiB, above the {limit_gb:.2f} GiB limit",
            hint="split the file or raise the configured limit",
        )
    return path, file_format, size, path.stat().st_mtime


def _decode_attr(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        return _decode_attr(value.reshape(-1)[0])
    return str(value)


def _hdf5_dims(dataset: h5py.Dataset) -> list[str]:
    if dataset.ndim == 0:
        return []
    dims: list[str] = []
    for index in range(dataset.ndim):
        try:
            label = dataset.dims[index].label
        except (AttributeError, IndexError, ValueError):
            label = ""
        dims.append(label or f"dim_{index}")
    return dims


def _hdf5_variables(path: Path) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []

    def visit(name: str, obj: h5py.Dataset | h5py.Group) -> None:
        if not isinstance(obj, h5py.Dataset):
            return
        variables.append(
            {
                "name": name,
                "path": name,
                "shape": list(obj.shape),
                "dtype": str(obj.dtype),
                "dims": _hdf5_dims(obj),
                "units": _decode_attr(obj.attrs.get("units")),
            }
        )

    try:
        with h5py.File(path, "r") as handle:
            handle.visititems(visit)
    except OSError as exc:
        raise InvalidSourceError(f"cannot open HDF5 file: {exc}") from exc
    return variables


def _netcdf_variables(path: Path) -> list[dict[str, Any]]:
    try:
        with xr.open_dataset(path, decode_times=False) as dataset:
            names = list(dataset.data_vars) or list(dataset.variables)
            variables = []
            for name in names:
                variable = dataset[name]
                variables.append(
                    {
                        "name": name,
                        "path": name,
                        "shape": list(variable.shape),
                        "dtype": str(variable.dtype),
                        "dims": list(variable.dims),
                        "units": _decode_attr(variable.attrs.get("units")),
                    }
                )
            return variables
    except (OSError, ValueError) as exc:
        raise InvalidSourceError(f"cannot open NetCDF file: {exc}") from exc


def _fits_variables(path: Path) -> list[dict[str, Any]]:
    try:
        with fits.open(path, memmap=True) as hdul:
            variables = []
            for index, hdu in enumerate(hdul):
                data = getattr(hdu, "data", None)
                if data is None:
                    continue
                if not getattr(hdu, "is_image", False):
                    continue
                name = hdu.name or f"HDU{index}"
                ndim = getattr(data, "ndim", 0)
                shape = [int(size) for size in getattr(data, "shape", ())]
                variables.append(
                    {
                        "name": name,
                        "path": name,
                        "shape": shape,
                        "dtype": str(getattr(data, "dtype", "")),
                        "dims": [f"NAXIS{axis + 1}" for axis in range(ndim)],
                        "units": _decode_attr(hdu.header.get("BUNIT")),
                    }
                )
            return variables
    except OSError as exc:
        raise InvalidSourceError(f"cannot open FITS file: {exc}") from exc


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
        raise InvalidSourceError(
            "no DICOM images were found in the source",
            hint="select a DICOM series directory or a .dcm file",
        )
    entries.sort(
        key=lambda item: (
            float(getattr(item[1], "InstanceNumber", 0) or 0),
            item[0].name,
        )
    )
    return entries


def _dicom_variables(path: Path) -> list[dict[str, Any]]:
    entries = _dicom_entries(path)
    dataset = entries[0][1]
    rows = int(getattr(dataset, "Rows", 0))
    columns = int(getattr(dataset, "Columns", 0))
    frames = int(getattr(dataset, "NumberOfFrames", 1) or 1)
    if len(entries) > 1 and frames > 1:
        shape = [len(entries), frames, rows, columns]
        dims = ["slice", "frame", "row", "col"]
    elif len(entries) > 1:
        shape = [len(entries), rows, columns]
        dims = ["slice", "row", "col"]
    elif frames > 1:
        shape = [frames, rows, columns]
        dims = ["frame", "row", "col"]
    else:
        shape = [rows, columns]
        dims = ["row", "col"]
    bits = int(getattr(dataset, "BitsAllocated", 16) or 16)
    signed = int(getattr(dataset, "PixelRepresentation", 0) or 0)
    dtype = f"{'int' if signed else 'uint'}{bits}"
    return [
        {
            "name": "series",
            "path": "series",
            "shape": shape,
            "dtype": dtype,
            "dims": dims,
            "units": None,
        }
    ]


def _nifti_variables(path: Path) -> list[dict[str, Any]]:
    try:
        image: Any = nib.load(str(path))
    except Exception as exc:
        raise InvalidSourceError(f"cannot open NIfTI file: {exc}") from exc
    shape = [int(size) for size in image.shape]
    return [
        {
            "name": "volume",
            "path": "volume",
            "shape": shape,
            "dtype": str(image.get_data_dtype()),
            "dims": _axis_names(shape),
            "units": None,
        }
    ]


def _raw_variables(path: Path, options: ImportOptions | None) -> list[dict[str, Any]]:
    if options is None or not options.shape or not options.dtype:
        raise InvalidSourceError(
            "RAW import requires shape and dtype options",
            hint="provide options.shape, options.dtype, and optional byte_order/raw_offset",
        )
    shape = [int(size) for size in options.shape]
    if any(size <= 0 for size in shape):
        raise InvalidSourceError("RAW shape values must be positive")
    return [
        {
            "name": "raw",
            "path": "raw",
            "shape": shape,
            "dtype": options.dtype,
            "dims": [f"dim_{index}" for index in range(len(shape))],
            "units": None,
        }
    ]


def _axis_names(shape: list[int]) -> list[str]:
    names = ["x", "y", "z", "t"]
    return names[: len(shape)] + [f"dim_{index}" for index in range(len(names), len(shape))]


def list_variables(
    path: Path,
    file_format: str,
    options: ImportOptions | None = None,
) -> list[dict[str, Any]]:
    if file_format == "hdf5":
        return _hdf5_variables(path)
    if file_format == "netcdf":
        return _netcdf_variables(path)
    if file_format == "fits":
        return _fits_variables(path)
    if file_format == "dicom":
        return _dicom_variables(path)
    if file_format == "nifti":
        return _nifti_variables(path)
    if file_format == "raw":
        return _raw_variables(path, options)
    raise UnsupportedFormatError(f"unsupported scientific format: {file_format}")


def _sample_slices(shape: list[int], max_elements: int) -> tuple[slice, ...]:
    if not shape:
        return ()
    total = math.prod(shape)
    if total <= max_elements:
        return tuple(slice(0, size) for size in shape)
    per_dim = max(1, int(max_elements ** (1 / len(shape))))
    return tuple(slice(0, min(size, per_dim)) for size in shape)


def _sample_shape(shape: list[int], slices: tuple[slice, ...]) -> list[int]:
    return [max(0, (item.stop or 0) - (item.start or 0)) for item in slices]


def _read_hdf5(
    path: Path, variable: str, max_elements: int
) -> tuple[np.ndarray, list[int], list[str], str, str | None, int]:
    try:
        with h5py.File(path, "r") as handle:
            if variable not in handle:
                raise InvalidSourceError(f"HDF5 variable not found: {variable}")
            dataset = handle[variable]
            shape = list(dataset.shape)
            slices = _sample_slices(shape, max_elements)
            sample = dataset[()] if not shape else dataset[slices]
            values = np.asarray(sample).reshape(-1)
            return (
                values,
                shape,
                _hdf5_dims(dataset),
                str(dataset.dtype),
                _decode_attr(dataset.attrs.get("units")),
                math.prod(shape) if shape else 1,
            )
    except OSError as exc:
        raise InvalidSourceError(f"cannot read HDF5 variable: {exc}") from exc


def _read_netcdf(
    path: Path, variable: str, max_elements: int
) -> tuple[np.ndarray, list[int], list[str], str, str | None, int]:
    try:
        with xr.open_dataset(path, decode_times=False) as dataset:
            if variable not in dataset.variables:
                raise InvalidSourceError(f"NetCDF variable not found: {variable}")
            data = dataset[variable]
            shape = [int(size) for size in data.shape]
            slices = _sample_slices(shape, max_elements)
            indexers = {
                dim: slice(item.start, item.stop)
                for dim, item in zip(data.dims, slices, strict=False)
            }
            sampled = data.isel(indexers) if indexers else data
            raw = np.asarray(sampled.values)
            if np.ma.isMaskedArray(sampled.values):
                raw = np.ma.filled(sampled.values, np.nan)
            values = np.asarray(raw).reshape(-1)
            return (
                values,
                shape,
                [str(dim) for dim in data.dims],
                str(data.dtype),
                _decode_attr(data.attrs.get("units")),
                math.prod(shape) if shape else 1,
            )
    except (OSError, ValueError, KeyError) as exc:
        raise InvalidSourceError(f"cannot read NetCDF variable: {exc}") from exc


def _read_fits(
    path: Path, variable: str, max_elements: int
) -> tuple[np.ndarray, list[int], list[str], str, str | None, int]:
    try:
        with fits.open(path, memmap=True) as hdul:
            hdu = None
            for candidate in hdul:
                if getattr(candidate, "name", "") == variable:
                    hdu = candidate
                    break
            if hdu is None:
                raise InvalidSourceError(f"FITS HDU not found: {variable}")
            data = hdu.data
            if data is None:
                raise InvalidSourceError(f"FITS HDU has no image data: {variable}")
            shape = [int(size) for size in data.shape]
            slices = _sample_slices(shape, max_elements)
            sample = data[()] if not shape else data[slices]
            values = np.asarray(sample).reshape(-1)
            dims = [f"NAXIS{axis + 1}" for axis in range(len(shape))]
            return (
                values,
                shape,
                dims,
                str(data.dtype),
                _decode_attr(hdu.header.get("BUNIT")),
                math.prod(shape) if shape else 1,
            )
    except OSError as exc:
        raise InvalidSourceError(f"cannot read FITS HDU: {exc}") from exc


def _dicom_array(dataset: Any) -> np.ndarray:
    array = np.asarray(dataset.pixel_array)
    slope = float(getattr(dataset, "RescaleSlope", 1) or 1)
    intercept = float(getattr(dataset, "RescaleIntercept", 0) or 0)
    if slope != 1 or intercept != 0:
        array = array.astype(np.float32) * slope + intercept
    return array


def _read_dicom(
    path: Path, variable: str, max_elements: int
) -> tuple[np.ndarray, list[int], list[str], str, str | None, int]:
    try:
        entries = _dicom_entries(path)
        if len(entries) > 1:
            first = pydicom.dcmread(entries[0][0], force=True)
            first_array = _dicom_array(first)
            frame_shape = [int(size) for size in first_array.shape]
            per_item = math.prod(frame_shape) if frame_shape else 1
            count = max(1, max_elements // max(per_item, 1))
            selected = entries[: min(len(entries), count)]
            arrays = [_dicom_array(pydicom.dcmread(item[0], force=True)) for item in selected]
            stacked = np.stack(arrays)
            values = stacked.reshape(-1)
            shape = [len(entries), *frame_shape]
            if len(frame_shape) == 2:
                dims = ["slice", "row", "col"]
            elif len(frame_shape) == 3:
                dims = ["slice", "frame", "row", "col"]
            else:
                dims = ["slice"] + [f"dim_{index}" for index in range(len(frame_shape))]
            return (
                values,
                shape,
                dims,
                str(stacked.dtype),
                None,
                len(entries) * per_item,
            )
        dataset = pydicom.dcmread(entries[0][0], force=True)
        array = _dicom_array(dataset)
        shape = [int(size) for size in array.shape]
        slices = _sample_slices(shape, max_elements)
        values = np.asarray(array[slices]).reshape(-1)
        if len(shape) == 2:
            dims = ["row", "col"]
        elif len(shape) == 3:
            dims = ["frame", "row", "col"]
        else:
            dims = [f"dim_{index}" for index in range(len(shape))]
        return values, shape, dims, str(array.dtype), None, math.prod(shape)
    except (InvalidDicomError, OSError, ValueError, AttributeError) as exc:
        raise InvalidSourceError(f"cannot read DICOM series: {exc}") from exc


def _read_nifti(
    path: Path, variable: str, max_elements: int
) -> tuple[np.ndarray, list[int], list[str], str, str | None, int]:
    try:
        image: Any = nib.load(str(path))
        shape = [int(size) for size in image.shape]
        slices = _sample_slices(shape, max_elements)
        sample = image.dataobj[slices]
        values = np.asanyarray(sample).reshape(-1)
        return (
            values,
            shape,
            _axis_names(shape),
            str(image.get_data_dtype()),
            None,
            math.prod(shape),
        )
    except Exception as exc:
        raise InvalidSourceError(f"cannot read NIfTI volume: {exc}") from exc


def _read_raw(
    path: Path,
    variable: str,
    max_elements: int,
    options: ImportOptions,
) -> tuple[np.ndarray, list[int], list[str], str, str | None, int]:
    if not options.shape or not options.dtype:
        raise InvalidSourceError(
            "RAW import requires shape and dtype options",
            hint="provide options.shape, options.dtype, and optional byte_order/raw_offset",
        )
    shape = [int(size) for size in options.shape]
    if any(size <= 0 for size in shape):
        raise InvalidSourceError("RAW shape values must be positive")
    try:
        dtype = np.dtype(options.dtype)
    except TypeError as exc:
        raise InvalidSourceError(f"unsupported RAW dtype: {options.dtype}") from exc
    if options.byte_order == "little":
        dtype = dtype.newbyteorder("<")
    elif options.byte_order == "big":
        dtype = dtype.newbyteorder(">")
    elif options.byte_order not in (None, "native"):
        raise InvalidSourceError("RAW byte_order must be 'little', 'big', or omitted")
    total = math.prod(shape)
    required = options.raw_offset + total * dtype.itemsize
    if path.stat().st_size < required:
        raise InvalidSourceError(
            "RAW file is smaller than shape × dtype",
            hint="check options.shape, options.dtype, byte_order, and raw_offset",
        )
    memory_map = np.memmap(
        path,
        dtype=dtype,
        mode="r",
        offset=options.raw_offset,
        shape=tuple(shape),
    )
    slices = _sample_slices(shape, max_elements)
    values = np.asarray(memory_map[slices]).reshape(-1).copy()
    del memory_map
    return (
        values,
        shape,
        [f"dim_{index}" for index in range(len(shape))],
        str(dtype),
        None,
        total,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (np.datetime64,)):
        return str(value)
    return value


def _array_profile(
    values: np.ndarray,
    *,
    shape: list[int],
    dims: list[str],
    dtype: str,
    units: str | None,
    variable: str,
    sampled: bool,
    total_elements: int,
    preview_rows: int,
    max_elements: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    flat = np.asarray(values).reshape(-1)
    numeric = np.issubdtype(flat.dtype, np.number) and not np.issubdtype(
        flat.dtype, np.complexfloating
    )
    issues: list[dict[str, Any]] = []
    finite = np.isfinite(flat) if numeric else np.ones(flat.shape, dtype=bool)
    missing = int(flat.size - np.count_nonzero(finite))
    finite_values = flat[finite] if numeric else flat[:0]
    stats: dict[str, Any] = {
        "finite_count": int(finite_values.size),
        "missing_count": missing,
    }
    if numeric and finite_values.size:
        stats.update(
            {
                "min": _json_value(np.min(finite_values)),
                "max": _json_value(np.max(finite_values)),
                "mean": _json_value(np.mean(finite_values)),
                "std": _json_value(np.std(finite_values)),
                "median": _json_value(np.median(finite_values)),
            }
        )
    if total_elements == 0:
        issues.append(
            {
                "code": "empty_array",
                "severity": "blocking",
                "message": f"variable {variable!r} has no elements",
                "suggestion": "choose another variable or check the file dimensions",
            }
        )
    if missing:
        issues.append(
            {
                "code": "missing_values",
                "severity": "warning",
                "message": f"variable {variable!r} has {missing} missing values",
                "suggestion": "mask or impute missing values before analysis",
            }
        )
    if numeric and finite_values.size and np.unique(finite_values).size <= 1:
        issues.append(
            {
                "code": "constant_array",
                "severity": "info",
                "message": f"variable {variable!r} is constant",
                "suggestion": "consider another variable for visualization",
            }
        )
    if not numeric:
        issues.append(
            {
                "code": "non_numeric_array",
                "severity": "info",
                "message": f"variable {variable!r} is not numeric",
                "suggestion": "string and structured arrays are preview-only in this milestone",
            }
        )
    if sampled:
        issues.append(
            {
                "code": "sampled_profile",
                "severity": "info",
                "message": f"profile uses {flat.size} sampled elements",
                "suggestion": "use a larger sample if distributions look unstable",
            }
        )
    counts = {"blocking": 0, "warning": 0, "info": 0}
    for issue in issues:
        counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1
    score = 0 if counts["blocking"] else max(0, 100 - counts["warning"] * 8 - counts["info"])
    preview = [
        {"index": index, "value": _json_value(value)}
        for index, value in enumerate(flat[:preview_rows])
    ]
    slice_shape = _sample_shape(shape, _sample_slices(shape, max_elements))
    schema = {
        "version": 1,
        "kind": "array",
        "variable": variable,
        "shape": shape,
        "dims": dims,
        "dtype": dtype,
        "units": units,
        "index_order": "C",
        "slice": {"sample_shape": slice_shape, "sampled": sampled},
        "columns": [],
    }
    profile = {
        "kind": "array",
        "quality_score": score,
        "sampled": sampled,
        "sample_rows": int(flat.size),
        "total_rows": total_elements,
        "row_count_estimated": False,
        "duplicate_rows": 0,
        "columns": [],
        "issues": issues,
        "summary": {
            "missing_cells": missing,
            "sensitive_columns": [],
            "issue_counts": counts,
        },
        "array": {
            "shape": shape,
            "dims": dims,
            "dtype": dtype,
            "units": units,
            "stats": stats,
        },
    }
    return schema, profile, preview, issues


def inspect_scientific(
    path_value: str,
    options: ImportOptions | None,
    *,
    max_file_bytes: int,
    default_sample_rows: int,
) -> ScientificInspection:
    effective = (options or ImportOptions()).normalized(default_sample_rows=default_sample_rows)
    path, file_format, size, mtime = resolve_source(path_value, max_file_bytes)
    variables = list_variables(path, file_format, effective)
    variable = effective.variable
    if variable is None and file_format in IMAGING_FORMATS:
        variable = str(variables[0]["name"])
        effective.variable = variable
    if variable is None:
        empty_profile: dict[str, Any] = {
            "kind": "array",
            "quality_score": 100,
            "sampled": False,
            "sample_rows": 0,
            "total_rows": 0,
            "row_count_estimated": False,
            "duplicate_rows": 0,
            "columns": [],
            "issues": [],
            "summary": {
                "missing_cells": 0,
                "sensitive_columns": [],
                "issue_counts": {"blocking": 0, "warning": 0, "info": 0},
            },
            "array": None,
        }
        return ScientificInspection(
            path=path,
            format=file_format,
            size_bytes=size,
            mtime=mtime,
            variables=variables,
            variable=None,
            schema={"version": 1, "kind": "array", "columns": []},
            profile=empty_profile,
            preview=[],
            row_count=0,
            column_count=0,
            sampled=False,
            options=effective.as_dict(),
            detected={"variables": len(variables)},
            issues=[],
        )
    if file_format == "hdf5":
        values, shape, dims, dtype, units, total = _read_hdf5(path, variable, effective.sample_rows)
    elif file_format == "netcdf":
        values, shape, dims, dtype, units, total = _read_netcdf(
            path, variable, effective.sample_rows
        )
    elif file_format == "fits":
        values, shape, dims, dtype, units, total = _read_fits(path, variable, effective.sample_rows)
    elif file_format == "dicom":
        values, shape, dims, dtype, units, total = _read_dicom(
            path, variable, effective.sample_rows
        )
    elif file_format == "nifti":
        values, shape, dims, dtype, units, total = _read_nifti(
            path, variable, effective.sample_rows
        )
    else:
        values, shape, dims, dtype, units, total = _read_raw(
            path, variable, effective.sample_rows, effective
        )
    sampled = int(values.size) < total
    schema, profile, preview, issues = _array_profile(
        values,
        shape=shape,
        dims=dims,
        dtype=dtype,
        units=units,
        variable=variable,
        sampled=sampled,
        total_elements=total,
        preview_rows=effective.preview_rows,
        max_elements=effective.sample_rows,
    )
    return ScientificInspection(
        path=path,
        format=file_format,
        size_bytes=size,
        mtime=mtime,
        variables=variables,
        variable=variable,
        schema=schema,
        profile=profile,
        preview=preview,
        row_count=total,
        column_count=max(len(shape), 1),
        sampled=sampled,
        options=effective.as_dict(),
        detected={"variable": variable},
        issues=issues,
    )

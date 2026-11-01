"""Generate a deterministic sample project with table, array, and text data."""

from __future__ import annotations

import csv
import random
from pathlib import Path

import h5py  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from advp.config import get_settings
from advp.ingest.files import ImportOptions
from advp.models import Project
from advp.services import projects as project_service


def sample_directory(project: Project) -> Path:
    """Return the private sample data directory for a project."""
    directory = get_settings().workspace_dir / "sample" / project.id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_sample_project(session: Session, name: str = "Sample project") -> Project:
    """Create a project with synthetic table, 3D array, and text-statistics data."""
    project = project_service.create_project(session, name)
    directory = sample_directory(project)
    _write_table(directory / "sample_table.csv")
    _write_volume(directory / "sample_volume.h5")
    _write_document(directory / "sample_report.docx")
    _write_text_facts(directory / "sample_facts.csv")

    project_service.import_dataset(
        session,
        project,
        path=str(directory / "sample_table.csv"),
        name="Sample observations",
        options=ImportOptions(sample_rows=10_000, preview_rows=20),
    )
    project_service.import_dataset(
        session,
        project,
        path=str(directory / "sample_volume.h5"),
        name="Sample volume",
        options=ImportOptions(
            variable="volume",
            sample_rows=10_000,
            preview_rows=20,
        ),
    )
    text_dataset = project_service.import_dataset(
        session,
        project,
        path=str(directory / "sample_facts.csv"),
        name="Sample text statistics",
        options=ImportOptions(sample_rows=10_000, preview_rows=20),
    )
    text_dataset.options = {
        **(text_dataset.options or {}),
        "source_kind": "text_stats",
        "text_stats": {
            "shape": "long",
            "ai_used": False,
            "source_path": str(directory / "sample_report.docx"),
        },
        "sample": True,
    }
    session.commit()
    session.refresh(project)
    return project


def _write_table(path: Path) -> None:
    generator = random.Random(42)
    categories = ["alpha", "beta", "gamma"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "category", "value", "latitude", "longitude", "missing"])
        for index in range(120):
            writer.writerow(
                [
                    f"2026-01-{index % 28 + 1:02d}",
                    categories[index % len(categories)],
                    round(generator.uniform(10, 100), 3),
                    round(30 + generator.uniform(-5, 5), 4),
                    round(120 + generator.uniform(-5, 5), 4),
                    "" if index % 17 == 0 else round(generator.uniform(0, 1), 3),
                ]
            )


def _write_volume(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        volume = handle.create_dataset("volume", shape=(16, 16, 16), dtype="float32")
        for x in range(16):
            for y in range(16):
                for z in range(16):
                    volume[x, y, z] = (x - 8) ** 2 + (y - 8) ** 2 + (z - 8) ** 2


def _write_document(path: Path) -> None:
    from docx import Document

    document = Document()
    document.add_heading("Sample scientific report", level=1)
    document.add_paragraph("Temperature increased by 12.5 percent in 2025.")
    document.add_paragraph("Pressure decreased to 98.2 kPa at the station.")
    document.add_paragraph("Sample size was 240 observations.")
    document.save(str(path))


def _write_text_facts(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["主体", "指标", "数值", "单位", "备注"])
        writer.writerow(["Temperature", "change", 12.5, "percent", "2025"])
        writer.writerow(["Pressure", "value", 98.2, "kPa", "station"])
        writer.writerow(["Sample", "size", 240, "observations", ""])

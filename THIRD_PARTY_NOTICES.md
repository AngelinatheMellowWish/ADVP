# Third-Party Notices

ADVP is licensed under Apache-2.0. This file lists the principal third-party
components and their licenses. It is an initial inventory for the requirements
phase; the release build must regenerate and audit it from the actual lockfiles.

> 发布前必须用锁文件与安装包重新生成并审计；本表不是最终法律意见。

## Runtime and backend

| Component | License | Purpose |
|---|---|---|
| Python | PSF-2.0 | Runtime |
| FastAPI | MIT | HTTP API |
| Uvicorn | BSD-3-Clause | ASGI server |
| Pydantic | MIT | Validation |
| SQLAlchemy | MIT | Database toolkit |
| psycopg | LGPL-3.0 | PostgreSQL driver |
| PyMySQL | MIT | MySQL driver |
| boto3 | Apache-2.0 | S3 client |
| httpx | BSD-3-Clause | HTTP client |
| lxml | BSD-3-Clause | HTML/XML parsing |
| pandas | BSD-3-Clause | HTML table parsing |
| fastexcel | MIT | Excel reader |
| charset-normalizer | MIT | Encoding detection |
| openpyxl | MIT | Excel test fixtures (dev) |
| pdfplumber | MIT | PDF table extraction |
| reportlab | BSD-3-Clause | PDF test fixtures (dev) |
| Alembic | MIT | Migrations |
| Huey | MIT | Task queue |
| Polars | MIT | DataFrames |
| DuckDB | MIT | Analytical SQL |
| Apache Arrow | Apache-2.0 | Columnar exchange |
| NumPy | BSD-3-Clause | Arrays |
| xarray | Apache-2.0 | N-dimensional data |
| h5py | BSD-3-Clause | HDF5 |
| netCDF4 | MIT | NetCDF |
| Astropy | BSD-3-Clause | FITS |
| pydicom | MIT | DICOM |
| nibabel | MIT | NIfTI |
| pdfplumber | MIT | PDF tables |
| python-docx | MIT | Word tables |
| Trafilatura | Apache-2.0 | Web extraction |
| Playwright | Apache-2.0 | Dynamic web pages |
| websockets | BSD-3-Clause | WebSocket |
| confluent-kafka | Apache-2.0 | Kafka client (librdkafka) |
| keyring | MIT | Windows Credential Manager |
| structlog | Apache-2.0 | Structured logging |

## Visualization and scientific rendering

| Component | License | Purpose |
|---|---|---|
| Plotly (Python) | MIT | Figure JSON generation |
| Plotly.js | MIT | 2D charts |
| Apache ECharts | Apache-2.0 | Dashboards / charts |
| VTK | BSD-3-Clause | Scientific rendering |
| VTK.js | BSD-3-Clause | Browser 3D |
| Mayavi | BSD-3-Clause | Scientific 3D |
| trame | Apache-2.0 | Remote VTK UI |
| deck.gl | MIT | Maps / large point data |
| world-atlas | ISC | Offline country boundaries |
| topojson-client | BSD-3-Clause | TopoJSON conversion |
| Natural Earth (admin-1) | Public domain | Global admin-1 boundaries |
| i18n-iso-countries | MIT | Country code/name matching |
| Cytoscape.js | MIT | Network graphs |
| PySide6 (Qt) | LGPL-3.0 (dynamic linking) | Mayavi/Qt UI runtime |
| FFmpeg | LGPL-2.1+ (use LGPL build) | MP4/GIF encoding |

## Frontend and tooling

| Component | License | Purpose |
|---|---|---|
| React | MIT | UI |
| TypeScript | Apache-2.0 | Language/tooling |
| Vite | MIT | Build |
| Tailwind CSS | MIT | Styling |
| Radix UI | MIT | Accessible primitives |
| Zustand | MIT | State |
| TanStack Query | MIT | Server state |
| i18next | MIT | Internationalization |
| Monaco Editor | MIT | Code viewer |
| Vitest | MIT | Tests |
| Playwright | Apache-2.0 | End-to-end tests |
| ESLint | MIT | Linting |
| ruff | MIT | Python lint/format |
| mypy | MIT | Python typing |
| pytest | MIT | Python tests |

## License review actions

- **Qt/PySide6**: dynamic linking only; do not statically link or modify Qt.
  Include LGPL notices and provide relinking information if required.
- **FFmpeg**: use an LGPL build; exclude GPL-only components (e.g., x264) unless
  the whole distribution complies with GPL.
- **librdkafka**: include its BSD-2-Clause notice and any bundled notices.
- **Map tiles / fonts / sample data**: verify separate licenses before bundling.
- **Generated reports**: user data and third-party content remain the user's
  responsibility; do not redistribute restricted data.

## Regeneration

Before each release:

```powershell
# Python
pip-audit -r backend/requirements.txt
# Node
npm audit --audit-level=high
# Secret scan
gitleaks detect --source . --redact
```

Then update this file from the actual dependency tree and attach it to the
release artifacts.

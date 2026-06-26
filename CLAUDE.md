# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Sentinel-2 NDVI mapping & timeseries pipeline for a German county (default: Märkisch-Oderland,
Brandenburg), built on the [openEO](https://openeo.org) API against the Copernicus Data Space
Ecosystem (CDSE). It produces a monthly cloud-masked NDVI netCDF cube plus a county mean-NDVI
CSV/PNG timeseries.

## Commands

```bash
# Install dependencies (uses uv, requires Python >=3.14)
uv sync

# Run the pipeline with defaults (Märkisch-Oderland, 2025-05-01..2026-05-01, monthly, 20m)
uv run python main.py

# Common option overrides
uv run python main.py --start 2024-04-01 --end 2024-11-01   # date range (end exclusive)
uv run python main.py --resolution 10                        # finer grid (larger files)
uv run python main.py --aoi-name "Barnim" --aoi-key-prefix 12060   # different county
uv run python main.py --vg250-path path/to/VG250_KRS.shp     # use a local boundary file
```

On the first run, the openEO client performs an interactive OIDC device-code auth: it prints a
URL + code, you confirm in a browser against a CDSE login. The refresh token is then cached in
`.openeo-auth/` so subsequent runs are non-interactive.

```bash
# Run the test suite (no network access, no real CDSE account needed)
uv run pytest

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# A single test
uv run pytest tests/test_aoi.py::test_load_aoi_selects_by_key_prefix_and_dissolves
```

CI (`.github/workflows/ci.yml`) runs `uv sync --locked` + `uv run pytest` on every push to `main`
and on pull requests.

The test suite never hits the real CDSE backend or downloads the real BKG boundary file: openEO
calls go through `openeo.rest._testing.DummyBackend` (an in-process fake backend wired up via
`requests_mock`, shared as the `dummy_backend` fixture in `tests/conftest.py`), and `aoi.py`'s
`gpd.read_file`/`_download_vg250` are monkeypatched with synthetic GeoDataFrames. Tests assert
against the actual openEO process graph JSON (node `process_id`s and arguments) rather than
mocking `DataCube` methods directly, so they catch real regressions in graph construction (e.g.
wrong SCL mask classes, wrong `resample_spatial` resolution/projection).

## Architecture

Execution flow, `main.py` -> `src/pipeline.py::run`:

1. **`src/config.py`** — `Config` dataclass holds every run parameter (date range, AOI
   name/key, resolution, EPSG, output/data dirs) plus derived output paths (`netcdf_path`,
   `timeseries_csv`, `timeseries_png`). `parse_args()` builds a `Config` from CLI flags;
   `Config()` defaults are the single source of truth for default values shown in `--help`.
   Also holds the openEO backend URL, the S2 collection id, and the SCL class codes treated as
   cloud/invalid pixels.
2. **`src/aoi.py::load_aoi`** — resolves the target county to a single dissolved WGS84
   polygon + bbox. Downloads BKG's VG250 (*Verwaltungsgebiete 1:250 000*) Kreise shapefile via a
   stable "aktuell" alias (cached under `data/`, skipped if already extracted), prefers the
   `GF==4` "land area" feature variant when present, selects by AGS/ARS/RS key prefix first and
   falls back to a name match, then dissolves multi-row selections into one geometry. Can be
   bypassed with `--vg250-path` to use a local boundary file instead of downloading.
3. **`src/ndvi_cube.py`** — `connect()` authenticates to CDSE; `build_monthly_ndvi()` builds the
   openEO process graph: load S2 L2A bands B04/B08/SCL over the AOI bbox and date range, mask
   pixels whose SCL class is in `SCL_MASK_CLASSES`, compute NDVI, reduce to monthly median,
   resample to the target resolution/projection, then linearly interpolate gaps from
   fully-clouded months (keeps regular time steps). Resampling before interpolating keeps the
   interpolation step's pixel grid small — doing it at native (10m) resolution over a whole
   county can exceed the backend's synchronous/executor memory limits. This builds a lazy graph
   — nothing executes until a downstream `.execute()`/`.execute_batch()` call in `outputs.py`.
4. **`src/outputs.py`** — `write_timeseries()` runs `aggregate_spatial` (mean NDVI per month)
   synchronously and writes CSV + a matplotlib PNG chart; `write_netcdf_cube()` clips the cube to
   the county polygon and submits an openEO **batch job** (can take several minutes) to produce
   the netCDF cube.

`pipeline.run()` deliberately calls `write_timeseries` before `write_netcdf_cube`: the
lightweight synchronous timeseries call is a fast signal that auth and the process graph are
valid before kicking off the slow batch job.

**`src/landsat.py`** is a separate, standalone path (not part of `pipeline.run()`). CDSE hosts
only Copernicus/Sentinel data, so 30 m Landsat C2 L2 imagery for the field blocks is sourced
from the **Microsoft Planetary Computer** STAC (`landsat-c2-l2`) instead of the openEO backend.
It searches scenes over the blocks' footprint, then writes one surface-reflectance GeoTIFF + one
`qa_pixel` GeoTIFF per scene to `outputs/landsat/`, clipped to the blocks. Run it with
`uv run python -m src.landsat`. Its test (`tests/test_landsat.py`) mocks `pystac_client.Client`
and `odc.stac.load` — no network.

Outputs land in `outputs/` (gitignored), boundary downloads/cache in `data/` (gitignored).

Note: on this Windows checkout the venv resolves via an extended-length UNC path
(`\\?\UNC\...`), which makes the `uv run pytest` console-script shim fail to load numpy's
C-extension ("DLL load failed ... The parameter is incorrect"). Use `uv run python -m pytest`
locally instead. CI runs on Linux and is unaffected, so the documented `uv run pytest` works there.

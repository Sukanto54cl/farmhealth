# farmhealth

> Monthly cloud-masked Sentinel-2 NDVI composites and a county mean-NDVI timeseries, built on openEO / Copernicus.

Sentinel-2 **NDVI mapping & timeseries** over the **Märkisch-Oderland** county
(Brandenburg, Germany) using the [openEO](https://openeo.org) API against the
**Copernicus Data Space Ecosystem (CDSE)**.

The pipeline builds **monthly, cloud-masked median NDVI** composites and produces:

- `outputs/ndvi_monthly_maerkisch-oderland.nc` — per-pixel monthly NDVI datacube (netCDF),
  clipped to the county, 20 m, EPSG:32633.
- `outputs/ndvi_timeseries.csv` — county **mean NDVI** per month.
- `outputs/ndvi_timeseries.png` — chart of the mean-NDVI seasonal curve.

## Prerequisites

1. A **free CDSE account** — register at <https://dataspace.copernicus.eu>.
2. Python 3.14 environment with dependencies installed (this repo uses [`uv`](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

## Run

```bash
# Defaults: Märkisch-Oderland, 2025-05-01 .. 2026-05-01, monthly, 20 m
uv run python main.py
```

On the **first run**, the openEO client prints a URL and a code: open the URL in a
browser, sign in to CDSE, and confirm the code. The refresh token is cached locally
(`.openeo-auth/`) so later runs are non-interactive.

### Options

```bash
python main.py --start 2024-04-01 --end 2024-11-01     # custom date range (end is exclusive)
python main.py --resolution 10                          # finer grid (larger files)
python main.py --aoi-name "Barnim" --aoi-key-prefix 12060   # a different Brandenburg county
python main.py --vg250-path path/to/VG250_KRS.shp      # use a local BKG boundary file
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--start` / `--end` | `2025-05-01` / `2026-05-01` | Date range (end exclusive). |
| `--aoi-name` | `Märkisch-Oderland` | County (Kreis) name. |
| `--aoi-key-prefix` | `12064` | Official ARS/AGS key used to select the county. |
| `--resolution` | `20` | Output resolution in metres. |
| `--epsg` | `32633` | Output projection (UTM 33N). |
| `--out-dir` | `outputs` | Where deliverables are written. |
| `--vg250-path` | _(auto-download)_ | Local BKG VG250 vector file override. |

## Data sources

- **Imagery:** Sentinel-2 L2A via CDSE openEO (`SENTINEL2_L2A`). Cloud masking uses the
  Scene Classification Layer (SCL).
- **Boundary:** BKG **VG250** *Verwaltungsgebiete 1:250 000* (Datenlizenz Deutschland –
  Namensnennung 2.0). Auto-downloaded from the BKG `aktuell` open-data alias.

## Project layout

```
farmhealth/
  config.py      # CLI flags + run configuration
  aoi.py         # BKG VG250 -> dissolved county polygon + bbox
  ndvi_cube.py   # openEO: S2 -> SCL mask -> NDVI -> monthly median -> resample
  outputs.py     # netCDF cube + mean-NDVI CSV/PNG
  pipeline.py    # orchestration
main.py          # CLI entry point
```

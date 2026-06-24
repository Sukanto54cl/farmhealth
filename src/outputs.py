"""Produce the deliverables: NDVI netCDF cube + mean-NDVI timeseries (CSV & PNG)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openeo
import pandas as pd

from .aoi import AOI
from .config import Config


def write_netcdf_cube(monthly: openeo.DataCube, aoi: AOI, config: Config) -> Path:
    """Clip the monthly NDVI cube to the county and download it as netCDF."""
    config.out_dir.mkdir(parents=True, exist_ok=True)
    clipped = monthly.mask_polygon(aoi.geometry_4326)
    out = config.netcdf_path
    print(f"Submitting batch job for NDVI cube -> {out} (this can take several minutes) ...")
    clipped.execute_batch(
        outputfile=str(out),
        out_format="netCDF",
        title=f"Monthly NDVI {config.aoi_name} {config.start}..{config.end}",
    )
    print(f"Wrote {out}")
    return out


def _parse_timeseries(result: dict) -> pd.DataFrame:
    """Flatten an aggregate_spatial JSON result to a (date, ndvi) DataFrame."""
    rows = []
    for date, geometries in result.items():
        # geometries: [[band0, band1, ...], ...] -> first geometry, first band.
        value = None
        if geometries and geometries[0]:
            value = geometries[0][0]
        rows.append({"date": pd.to_datetime(date), "ndvi": value})
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return df


def write_timeseries(monthly: openeo.DataCube, aoi: AOI, config: Config) -> Path:
    """Compute county mean NDVI per month, save CSV, and render a chart."""
    config.out_dir.mkdir(parents=True, exist_ok=True)
    print("Computing county mean-NDVI timeseries ...")
    result = monthly.aggregate_spatial(geometries=aoi.geometry_4326, reducer="mean").execute()
    df = _parse_timeseries(result)

    df.to_csv(config.timeseries_csv, index=False)
    print(f"Wrote {config.timeseries_csv} ({len(df)} rows)")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["date"], df["ndvi"], marker="o", color="#2e8b57")
    ax.set_title(f"Mean NDVI — {config.aoi_name} ({config.start} to {config.end})")
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean NDVI")
    ax.set_ylim(-0.1, 1.0)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(config.timeseries_png, dpi=120)
    plt.close(fig)
    print(f"Wrote {config.timeseries_png}")
    return config.timeseries_csv


def _parse_block_timeseries(result: dict, block_ids: list[str]) -> pd.DataFrame:
    """Flatten an aggregate_spatial JSON result (one geometry per block) to (block_id, date, ndvi)."""
    rows = []
    for date, geometries in result.items():
        for block_id, geometry in zip(block_ids, geometries):
            value = geometry[0] if geometry else None
            rows.append({"block_id": block_id, "date": pd.to_datetime(date), "ndvi": value})
    df = pd.DataFrame(rows).sort_values(["block_id", "date"]).reset_index(drop=True)
    return df


def write_block_timeseries(monthly: openeo.DataCube, blocks: gpd.GeoDataFrame, config: Config) -> Path:
    """Compute mean NDVI per month for each block, and save as CSV (block_id, date, ndvi)."""
    config.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Computing mean-NDVI timeseries for {len(blocks)} block(s) ...")
    # aggregate_spatial needs a GeoJSON-style dict, not a GeoDataFrame directly.
    result = monthly.aggregate_spatial(geometries=blocks.__geo_interface__, reducer="mean").execute()
    df = _parse_block_timeseries(result, list(blocks["FB_ID"]))

    out = config.blocks_timeseries_csv
    df.to_csv(out, index=False)
    print(f"Wrote {out} ({len(df)} rows)")
    return out

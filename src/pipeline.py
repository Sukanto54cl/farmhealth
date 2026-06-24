"""End-to-end orchestration of the NDVI pipeline."""

from __future__ import annotations

from .aoi import load_aoi
from .blocks import load_blocks
from .config import Config
from .ndvi_cube import build_monthly_ndvi, connect
from .outputs import write_block_timeseries, write_netcdf_cube, write_timeseries


def run(config: Config) -> None:
    """Resolve AOI, build the cube on CDSE, and write all deliverables."""
    aoi = load_aoi(config)
    blocks = load_blocks()

    connection = connect()
    monthly = build_monthly_ndvi(connection, aoi, config)

    # Lightweight, fast result first — good early signal that auth + graph are valid.
    write_timeseries(monthly, aoi, config)
    write_block_timeseries(monthly, blocks, config)

    # Heavy spatial cube via a batch job.
    write_netcdf_cube(monthly, aoi, config)

    print("Done.")

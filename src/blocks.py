"""Load specific field blocks (Feldblöcke) for block-level mean-NDVI timeseries.

Source: the DFBK (Digitales Feldblockkataster) field-block shapefile for
Märkisch-Oderland, cached locally under ``data/``.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

BLOCKS_PATH = Path("data/dfbk_fb_mol.shp")
BLOCK_IDS = ("DEBBLI0264002685", "DEBBLI2064399462")


def load_blocks(path: Path = BLOCKS_PATH, block_ids: tuple[str, ...] = BLOCK_IDS) -> gpd.GeoDataFrame:
    """Return the selected field blocks as a WGS84 GeoDataFrame, ordered by ``block_ids``."""
    gdf = gpd.read_file(path)
    selected = gdf[gdf["FB_ID"].isin(block_ids)]
    missing = set(block_ids) - set(selected["FB_ID"])
    if missing:
        raise ValueError(f"Block ID(s) not found in {path}: {sorted(missing)}")
    selected = selected.set_index("FB_ID").loc[list(block_ids)].reset_index()
    return selected.to_crs(4326)[["FB_ID", "geometry"]]

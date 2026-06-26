"""Download Landsat Collection-2 Level-2 (30 m surface reflectance) scenes for the field blocks.

CDSE (the openEO backend used for Sentinel-2) does not host Landsat, so this module
sources 30 m imagery from the Microsoft Planetary Computer STAC instead. It searches the
``landsat-c2-l2`` collection over the field blocks' footprint, then writes one GeoTIFF per
scene (clipped to the blocks, with a context buffer): a multi-band surface-reflectance file
plus a companion single-band ``qa_pixel`` file for cloud/shadow masking.

Run standalone::

    uv run python -m src.landsat --start 2024-04-01 --end 2024-11-01 --max-cloud 30
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import planetary_computer
import pystac_client
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from odc import stac as odc_stac
from shapely.geometry import box

from .blocks import load_blocks
from .config import (
    LANDSAT_COLLECTION,
    LANDSAT_QA_BAND,
    LANDSAT_SR_BANDS,
    LANDSAT_SR_OFFSET,
    LANDSAT_SR_SCALE,
    PC_STAC_URL,
    Config,
)


def search_scenes(
    blocks: gpd.GeoDataFrame,
    start: str,
    end: str,
    *,
    max_cloud: float = 100.0,
    collection: str = LANDSAT_COLLECTION,
    stac_url: str = PC_STAC_URL,
) -> list:
    """Return Landsat C2 L2 STAC items intersecting the blocks, sorted by acquisition time.

    ``start``/``end`` are ISO dates (``end`` exclusive, matching the pipeline convention);
    ``max_cloud`` filters on scene-level ``eo:cloud_cover`` percent.
    """
    minx, miny, maxx, maxy = blocks.to_crs(4326).total_bounds
    client = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)
    search = client.search(
        collections=[collection],
        bbox=(minx, miny, maxx, maxy),
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    items = list(search.items())
    items.sort(key=lambda it: it.datetime)
    return items


def _scene_stem(item) -> str:
    """A filesystem-safe, date-sortable stem like ``2024-06-12_LC08..._..._SR``."""
    date = item.datetime.strftime("%Y-%m-%d")
    return f"{date}_{item.id}"


def _clip_bbox_4326(blocks: gpd.GeoDataFrame, epsg: int, buffer_m: float) -> tuple[float, float, float, float]:
    """Blocks' combined footprint, buffered by ``buffer_m`` metres, as a lon/lat bbox."""
    buffered = blocks.to_crs(epsg).buffer(buffer_m)
    bounds_box = box(*buffered.total_bounds)
    return tuple(gpd.GeoSeries([bounds_box], crs=epsg).to_crs(4326).total_bounds)


def download_scene(
    item,
    blocks: gpd.GeoDataFrame,
    out_dir: Path,
    *,
    epsg: int,
    resolution: int = 30,
    buffer_m: float = 150.0,
    scale: bool = True,
    sr_bands: tuple[str, ...] = LANDSAT_SR_BANDS,
    qa_band: str = LANDSAT_QA_BAND,
) -> tuple[Path, Path]:
    """Load one scene clipped to the blocks and write a surface-reflectance + a QA GeoTIFF.

    Returns the (surface-reflectance, qa) output paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    bbox = _clip_bbox_4326(blocks, epsg, buffer_m)

    ds = odc_stac.load(
        [item],
        bands=(*sr_bands, qa_band),
        crs=f"EPSG:{epsg}",
        resolution=resolution,
        bbox=bbox,
        chunks={},
    ).isel(time=0)

    qa = ds[qa_band].astype("uint16")
    sr = ds[list(sr_bands)]
    # DN 0 is the C2 L2 fill value; drop it before scaling to reflectance.
    sr = sr.where(sr != 0)
    if scale:
        sr = sr * LANDSAT_SR_SCALE + LANDSAT_SR_OFFSET
    sr = sr.astype("float32")

    stem = _scene_stem(item)
    sr_path = out_dir / f"{stem}_sr.tif"
    qa_path = out_dir / f"{stem}_qa.tif"

    sr_da = sr.to_dataarray(dim="band")  # (band, y, x), band coord = reflectance band names
    sr_da.rio.to_raster(sr_path, compress="deflate")
    qa.rio.to_raster(qa_path, compress="deflate")
    return sr_path, qa_path


def _confirm_download(n: int) -> bool:
    """Ask the user to confirm before downloading. Only an explicit 'y'/'yes' proceeds."""
    reply = input(f"Download these {n} scene(s)? [y/N]: ").strip().lower()
    return reply in ("y", "yes")


def download_blocks_landsat(
    config: Config,
    *,
    max_cloud: float = 50.0,
    buffer_m: float = 150.0,
    scale: bool = True,
    assume_yes: bool = False,
) -> list[Path]:
    """Search matching Landsat scenes, print them, then download after a 'y' confirmation.

    Pass ``assume_yes=True`` (CLI ``--yes``) to skip the prompt for non-interactive runs.
    """
    blocks = load_blocks()
    items = search_scenes(blocks, config.start, config.end, max_cloud=max_cloud)
    print(
        f"Found {len(items)} Landsat scene(s) for {len(blocks)} block(s), "
        f"{config.start}..{config.end}, cloud < {max_cloud:.0f}%:"
    )
    for i, item in enumerate(items, 1):
        cloud = item.properties.get("eo:cloud_cover")
        print(f"  {i:>2}. {item.datetime:%Y-%m-%d}  {item.id}  {cloud:.0f}% cloud")

    if not items:
        return []
    if not assume_yes and not _confirm_download(len(items)):
        print("Aborted; nothing downloaded.")
        return []

    written: list[Path] = []
    for i, item in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] downloading {item.id} ...")
        sr_path, _ = download_scene(
            item, blocks, config.landsat_dir, epsg=config.epsg, buffer_m=buffer_m, scale=scale
        )
        written.append(sr_path)
    print(f"Wrote {len(written)} scene(s) to {config.landsat_dir}")
    return written


def parse_args(argv: list[str] | None = None) -> tuple[Config, float, float, bool, bool]:
    p = argparse.ArgumentParser(
        description="Download Landsat C2 L2 (30 m) scenes for the field blocks via Planetary Computer.",
    )
    defaults = Config()
    p.add_argument("--start", default=defaults.start, help="Start date (inclusive, YYYY-MM-DD).")
    p.add_argument("--end", default=defaults.end, help="End date (exclusive, YYYY-MM-DD).")
    p.add_argument("--epsg", type=int, default=defaults.epsg, help="Output projection EPSG code.")
    p.add_argument("--out-dir", type=Path, default=defaults.out_dir, help="Output directory.")
    p.add_argument("--data-dir", type=Path, default=defaults.data_dir, help="Cache dir for boundaries/blocks.")
    p.add_argument("--max-cloud", type=float, default=50.0, help="Max scene cloud cover percent.")
    p.add_argument("--buffer", type=float, default=150.0, help="Context buffer around blocks (m).")
    p.add_argument("--no-scale", action="store_true", help="Keep raw DN instead of scaling to reflectance.")
    p.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt and download.")
    a = p.parse_args(argv)
    config = Config(start=a.start, end=a.end, epsg=a.epsg, out_dir=a.out_dir, data_dir=a.data_dir)
    return config, a.max_cloud, a.buffer, not a.no_scale, a.yes


def main(argv: list[str] | None = None) -> None:
    config, max_cloud, buffer_m, scale, assume_yes = parse_args(argv)
    download_blocks_landsat(
        config, max_cloud=max_cloud, buffer_m=buffer_m, scale=scale, assume_yes=assume_yes
    )


if __name__ == "__main__":
    main()

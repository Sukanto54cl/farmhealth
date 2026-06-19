"""Area-of-interest loading from the official BKG VG250 administrative boundaries.

The German Federal Agency for Cartography and Geodesy (BKG) publishes the
*Verwaltungsgebiete 1:250 000* (VG250) as open data (Datenlizenz Deutschland –
Namensnennung 2.0). BKG keeps a stable ``aktuell`` alias pointing at the current
edition, which we use so the pipeline keeps working across yearly releases.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import MultiPolygon, Polygon

from .config import Config

# Stable "aktuell" (current edition) download — UTM32 shapefile, all layers.
VG250_URL = (
    "https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_0101/aktuell/"
    "vg250_01-01.utm32s.shape.ebenen.zip"
)


@dataclass
class AOI:
    """A resolved area of interest."""

    name: str
    geometry_4326: Polygon | MultiPolygon  # for mask_polygon / aggregate_spatial
    bbox_4326: dict                         # {"west","south","east","north"} for load_collection

    @property
    def spatial_extent(self) -> dict:
        return self.bbox_4326


def _download_vg250(data_dir: Path) -> Path:
    """Download and extract the VG250 archive; return the extraction directory."""
    data_dir.mkdir(parents=True, exist_ok=True)
    zip_path = data_dir / "vg250.zip"
    extract_dir = data_dir / "vg250"

    if not extract_dir.exists():
        if not zip_path.exists():
            print(f"Downloading BKG VG250 boundaries from {VG250_URL} ...")
            tmp_path = zip_path.with_suffix(".zip.part")
            try:
                with requests.get(VG250_URL, stream=True, timeout=300) as r:
                    r.raise_for_status()
                    with open(tmp_path, "wb") as fh:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            fh.write(chunk)
                tmp_path.rename(zip_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        print(f"Extracting {zip_path} ...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    return extract_dir


def _find_kreise_layer(root: Path) -> Path:
    """Locate the Kreise (district) shapefile within the extracted VG250 tree."""
    candidates = list(root.rglob("*_KRS.shp")) + list(root.rglob("VG250_KRS.shp"))
    if not candidates:
        # Fall back to any vector file that looks like a Kreise layer.
        candidates = [p for p in root.rglob("*KRS*") if p.suffix.lower() in {".shp", ".gpkg"}]
    if not candidates:
        raise FileNotFoundError(
            f"Could not find a VG250 Kreise (*_KRS.shp) layer under {root}. "
            "Pass --vg250-path to point at the file explicitly."
        )
    return candidates[0]


def load_aoi(config: Config) -> AOI:
    """Resolve the configured county to a dissolved WGS84 polygon + bbox."""
    if config.vg250_path is not None:
        source = config.vg250_path
    else:
        source = _find_kreise_layer(_download_vg250(config.data_dir))

    gdf = gpd.read_file(source)

    # Prefer the land-area geometry variant when the GF (Geofaktor) attribute exists:
    # GF==4 is "mit Struktur Land" (the real administrative land polygon).
    if "GF" in gdf.columns and (gdf["GF"] == 4).any():
        gdf = gdf[gdf["GF"] == 4]

    # Select the county by official key (AGS/ARS prefix), with a name fallback.
    key_col = next((c for c in ("AGS", "ARS", "RS") if c in gdf.columns), None)
    selection = None
    if key_col is not None:
        selection = gdf[gdf[key_col].astype(str).str.startswith(config.aoi_key_prefix)]
    if selection is None or selection.empty:
        name_col = next((c for c in ("GEN", "NAME", "BEZ") if c in gdf.columns), None)
        if name_col is None:
            raise KeyError(f"No usable name/key column in {list(gdf.columns)}")
        selection = gdf[gdf[name_col] == config.aoi_name]
    if selection.empty:
        raise ValueError(
            f"County '{config.aoi_name}' (key prefix {config.aoi_key_prefix}) "
            f"not found in {source}."
        )

    # Dissolve any multi-row selection into a single (multi)polygon in WGS84.
    geom_4326 = selection.to_crs(4326).union_all()
    minx, miny, maxx, maxy = geom_4326.bounds

    print(
        f"AOI '{config.aoi_name}': {len(selection)} feature(s), "
        f"bbox=({minx:.4f},{miny:.4f},{maxx:.4f},{maxy:.4f})"
    )
    return AOI(
        name=config.aoi_name,
        geometry_4326=geom_4326,
        bbox_4326={"west": minx, "south": miny, "east": maxx, "north": maxy},
    )

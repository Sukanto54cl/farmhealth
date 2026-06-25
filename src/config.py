"""Runtime configuration for the NDVI pipeline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

# openEO backend (Copernicus Data Space Ecosystem).
OPENEO_BACKEND = "openeo.dataspace.copernicus.eu"

# Sentinel-2 L2A collection on CDSE.
S2_COLLECTION = "SENTINEL2_L2A"

# Sentinel-2 Scene Classification (SCL) class codes treated as invalid (masked out):
#   0 no-data, 1 saturated/defective, 3 cloud shadow,
#   8 cloud medium prob, 9 cloud high prob, 10 thin cirrus, 11 snow/ice.
SCL_MASK_CLASSES = (0, 1, 3, 8, 9, 10, 11)


@dataclass
class Config:
    """All knobs for a single pipeline run."""

    start: str = "2025-05-01"          # inclusive ISO date
    end: str = "2026-05-01"            # exclusive ISO date (covers through 2026-04-30)
    aoi_name: str = "Märkisch-Oderland"
    aoi_key_prefix: str = "12064"      # ARS/AGS prefix for the Kreis (cross-check)
    resolution: int = 20               # metres
    epsg: int = 32633                  # UTM 33N, native for Brandenburg
    out_dir: Path = Path("outputs")
    data_dir: Path = Path("data")
    vg250_path: Path | None = None     # optional override for the BKG boundary file

    @property
    def aoi_slug(self) -> str:
        return (
            self.aoi_name.lower()
            .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
            .replace(" ", "-")
        )

    @property
    def netcdf_path(self) -> Path:
        return self.out_dir / f"ndvi_monthly_{self.aoi_slug}.nc"

    @property
    def timeseries_csv(self) -> Path:
        return self.out_dir / "ndvi_timeseries.csv"

    @property
    def timeseries_png(self) -> Path:
        return self.out_dir / "ndvi_timeseries.png"
    
    @property
    def blocks_timeseries_png(self) -> Path:
        return self.out_dir / "ndvi_blocks_timeseries.png"

    @property
    def blocks_timeseries_csv(self) -> Path:
        return self.out_dir / "ndvi_blocks_timeseries.csv"


def parse_args(argv: list[str] | None = None) -> Config:
    p = argparse.ArgumentParser(
        description="Sentinel-2 NDVI mapping & timeseries over a German county via openEO/CDSE.",
    )
    defaults = Config()
    p.add_argument("--start", default=defaults.start, help="Start date (inclusive, YYYY-MM-DD).")
    p.add_argument("--end", default=defaults.end, help="End date (exclusive, YYYY-MM-DD).")
    p.add_argument("--aoi-name", default=defaults.aoi_name, help="County (Kreis) name.")
    p.add_argument("--aoi-key-prefix", default=defaults.aoi_key_prefix,
                   help="ARS/AGS key prefix used to cross-check the selected county.")
    p.add_argument("--resolution", type=int, default=defaults.resolution, help="Output resolution (m).")
    p.add_argument("--epsg", type=int, default=defaults.epsg, help="Output projection EPSG code.")
    p.add_argument("--out-dir", type=Path, default=defaults.out_dir, help="Output directory.")
    p.add_argument("--data-dir", type=Path, default=defaults.data_dir, help="Cache dir for boundaries.")
    p.add_argument("--vg250-path", type=Path, default=None,
                   help="Path to a local BKG VG250 vector file (skips download).")
    a = p.parse_args(argv)
    return Config(
        start=a.start,
        end=a.end,
        aoi_name=a.aoi_name,
        aoi_key_prefix=a.aoi_key_prefix,
        resolution=a.resolution,
        epsg=a.epsg,
        out_dir=a.out_dir,
        data_dir=a.data_dir,
        vg250_path=a.vg250_path,
    )

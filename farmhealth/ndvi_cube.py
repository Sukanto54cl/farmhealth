"""Build the monthly, cloud-masked NDVI datacube on the CDSE openEO backend."""

from __future__ import annotations

import openeo

from .aoi import AOI
from .config import (
    OPENEO_BACKEND,
    S2_COLLECTION,
    SCL_MASK_CLASSES,
    Config,
)


def connect() -> openeo.Connection:
    """Connect to CDSE and authenticate via the interactive OIDC device flow.

    On first run this prints a URL + code to confirm in a browser; the refresh
    token is then cached locally by the openeo client for subsequent runs.
    """
    connection = openeo.connect(OPENEO_BACKEND)
    connection.authenticate_oidc()
    return connection


def build_monthly_ndvi(connection: openeo.Connection, aoi: AOI, config: Config) -> openeo.DataCube:
    """Return a monthly-median NDVI datacube, cloud-masked via SCL and resampled."""
    s2 = connection.load_collection(
        S2_COLLECTION,
        spatial_extent=aoi.spatial_extent,
        temporal_extent=[config.start, config.end],
        bands=["B04", "B08", "SCL"],
    )

    # Invalid-pixel mask from the Scene Classification Layer (True == drop).
    scl = s2.band("SCL")
    invalid = None
    for cls in SCL_MASK_CLASSES:
        cond = scl == cls
        invalid = cond if invalid is None else (invalid | cond)

    red = s2.band("B04")
    nir = s2.band("B08")
    ndvi = (nir - red) / (nir + red)
    ndvi = ndvi.mask(invalid)

    monthly = ndvi.aggregate_temporal_period(period="month", reducer="median")

    # Fill gaps left by fully-clouded months so the cube has regular time steps.
    monthly = monthly.apply_dimension(dimension="t", process="array_interpolate_linear")

    monthly = monthly.resample_spatial(
        resolution=config.resolution,
        projection=config.epsg,
    )
    return monthly

"""Shared fixtures for the farmhealth test suite."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from openeo.rest._testing import DummyBackend, OPENEO_BACKEND
from shapely.geometry import Polygon

from src.aoi import AOI
from src.config import Config


@pytest.fixture
def dummy_backend(requests_mock) -> DummyBackend:
    """An in-process fake openEO backend; no real network calls are made."""
    backend = DummyBackend.at_url(OPENEO_BACKEND, requests_mock=requests_mock)
    backend.setup_collection("SENTINEL2_L2A", bands=["B04", "B08", "SCL"])
    backend.setup_credentials_oidc()
    backend.setup_file_format("netCDF")
    return backend


@pytest.fixture
def sample_aoi() -> AOI:
    geometry = Polygon([(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)])
    return AOI(
        name="Test County",
        geometry_4326=geometry,
        bbox_4326={"west": 0.0, "south": 0.0, "east": 1.0, "north": 1.0},
    )


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(out_dir=tmp_path / "outputs", data_dir=tmp_path / "data")


@pytest.fixture
def sample_blocks() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "FB_ID": ["DEBBLI0264002685", "DEBBLI2064399462"],
            "geometry": [
                Polygon([(0.1, 0.1), (0.1, 0.2), (0.2, 0.2), (0.2, 0.1)]),
                Polygon([(0.3, 0.3), (0.3, 0.4), (0.4, 0.4), (0.4, 0.3)]),
            ],
        },
        crs="EPSG:4326",
    )

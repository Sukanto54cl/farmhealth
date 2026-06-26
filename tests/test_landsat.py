"""Tests for the Landsat downloader. No network: the STAC client and odc-stac loader are mocked."""

from __future__ import annotations

import datetime as dt

import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from shapely.geometry import box

from src import landsat
from src.config import Config


class _FakeItem:
    def __init__(self, item_id, when, cloud):
        self.id = item_id
        self.datetime = when
        self.properties = {"eo:cloud_cover": cloud}


class _FakeSearch:
    def __init__(self, items):
        self._items = items

    def items(self):
        return list(self._items)


class _FakeClient:
    last_open_kwargs: dict = {}
    last_search_kwargs: dict = {}

    def __init__(self, items):
        self._items = items

    @classmethod
    def open(cls, url, **kwargs):
        cls.last_open_kwargs = {"url": url, **kwargs}
        return cls(_FakeClient._pending_items)

    def search(self, **kwargs):
        _FakeClient.last_search_kwargs = kwargs
        return _FakeSearch(self._items)


def test_search_scenes_sorts_by_datetime_and_filters_cloud(monkeypatch, sample_blocks):
    later = _FakeItem("L_later", dt.datetime(2024, 8, 1), 10)
    earlier = _FakeItem("L_earlier", dt.datetime(2024, 5, 1), 5)
    _FakeClient._pending_items = [later, earlier]
    monkeypatch.setattr(landsat.pystac_client, "Client", _FakeClient)

    items = landsat.search_scenes(sample_blocks, "2024-04-01", "2024-11-01", max_cloud=30)

    assert [it.id for it in items] == ["L_earlier", "L_later"]
    assert _FakeClient.last_search_kwargs["datetime"] == "2024-04-01/2024-11-01"
    assert _FakeClient.last_search_kwargs["query"] == {"eo:cloud_cover": {"lt": 30}}
    # bbox derived from the blocks' WGS84 footprint.
    assert len(_FakeClient.last_search_kwargs["bbox"]) == 4


def test_clip_bbox_buffers_the_footprint(sample_blocks):
    epsg = 32633
    tight = landsat._clip_bbox_4326(sample_blocks, epsg, buffer_m=0.0)
    buffered = landsat._clip_bbox_4326(sample_blocks, epsg, buffer_m=500.0)

    assert buffered[0] < tight[0] and buffered[1] < tight[1]  # west/south expand outward
    assert buffered[2] > tight[2] and buffered[3] > tight[3]  # east/north expand outward


def _fake_pixel_da(epsg=32633):
    """A 6x6, 30 m grid in EPSG:32633 with round coordinates for hand-computable pixel boxes.

    rio.bounds() == (100000.0, 100020.0, 100180.0, 100200.0), resolution() == (30.0, -30.0).
    """
    x = np.arange(6) * 30.0 + 100_015.0  # centers: 100015, 100045, ..., 100165
    y = 100_185.0 - np.arange(6) * 30.0  # centers: 100185, 100155, ..., 100035 (descending)
    da = xr.DataArray(np.zeros((6, 6), dtype="float32"), coords={"y": y, "x": x}, dims=("y", "x"))
    return da.rio.write_crs(f"EPSG:{epsg}")


def _block(block_id, geom, crs=32633):
    return gpd.GeoDataFrame({"FB_ID": [block_id], "geometry": [geom]}, crs=crs)


def test_pixel_grid_pure_pixel_classified_correctly():
    da = _fake_pixel_da()
    # exact bounds of the top-left pixel box (center 100015, 100185).
    blocks = _block("pure_block", box(100_000.0, 100_170.0, 100_030.0, 100_200.0))

    grid = landsat.pixel_grid(da, blocks, epsg=32633, buffer_px=0)

    assert len(grid) == 1
    assert grid.iloc[0]["frac_in_block"] == pytest.approx(1.0)
    assert grid.iloc[0]["geometry"].bounds == pytest.approx((100_000.0, 100_170.0, 100_030.0, 100_200.0))


def test_pixel_grid_mixed_pixel_classified_correctly():
    da = _fake_pixel_da()
    # left half of the same top-left pixel box.
    blocks = _block("mixed_block", box(100_000.0, 100_170.0, 100_015.0, 100_200.0))

    grid = landsat.pixel_grid(da, blocks, epsg=32633, buffer_px=0)

    assert len(grid) == 1
    assert grid.iloc[0]["frac_in_block"] == pytest.approx(0.5)


def test_pixel_grid_buffer_px_expands_selection():
    da = _fake_pixel_da()
    # a middle pixel (center 100075, 100125) so a 1-pixel ring isn't clipped by the raster edge.
    blocks = _block("mid_block", box(100_060.0, 100_110.0, 100_090.0, 100_140.0))

    tight = landsat.pixel_grid(da, blocks, epsg=32633, buffer_px=0)
    ringed = landsat.pixel_grid(da, blocks, epsg=32633, buffer_px=1)

    assert len(tight) == 1
    assert len(ringed) == 9  # the pixel plus its full ring of 8 neighbors
    ring_only = ringed[ringed["frac_in_block"] == 0.0]
    assert len(ring_only) == 8


def test_pixel_grid_returns_per_block_rows_for_multiple_blocks():
    da = _fake_pixel_da()
    block_a = box(100_000.0, 100_170.0, 100_030.0, 100_200.0)  # top-left pixel
    block_b = box(100_150.0, 100_020.0, 100_180.0, 100_050.0)  # bottom-right pixel
    blocks = gpd.GeoDataFrame(
        {"FB_ID": ["block_a", "block_b"], "geometry": [block_a, block_b]}, crs=32633
    )

    grid = landsat.pixel_grid(da, blocks, epsg=32633, buffer_px=0)

    assert len(grid) == 2
    assert set(grid["block_id"]) == {"block_a", "block_b"}


def test_pixel_grid_columns_and_crs():
    da = _fake_pixel_da()
    blocks = _block("b", box(100_000.0, 100_170.0, 100_030.0, 100_200.0))

    grid = landsat.pixel_grid(da, blocks, epsg=32633, buffer_px=1)

    assert list(grid.columns) == ["block_id", "x", "y", "frac_in_block", "geometry"]
    assert grid.crs.to_epsg() == 32633


def test_pixel_grid_accepts_blocks_in_different_crs():
    da = _fake_pixel_da()
    geom_32633 = box(100_000.0, 100_170.0, 100_030.0, 100_200.0)
    blocks_4326 = _block("b", geom_32633).to_crs(4326)

    grid = landsat.pixel_grid(da, blocks_4326, epsg=32633, buffer_px=0)

    assert len(grid) == 1
    assert grid.iloc[0]["frac_in_block"] == pytest.approx(1.0)


def _fake_scene_dataset(epsg=32633):
    y = np.array([5_800_030.0, 5_800_000.0])
    x = np.array([400_000.0, 400_030.0])
    red = np.array([[[20000, 0], [20000, 20000]]], dtype="uint16")  # DN; one fill (0) pixel
    nir = np.array([[[30000, 30000], [30000, 30000]]], dtype="uint16")
    qa = np.array([[[21824, 21888], [21824, 55052]]], dtype="uint16")
    ds = xr.Dataset(
        {
            "red": (("time", "y", "x"), red),
            "nir08": (("time", "y", "x"), nir),
            "qa_pixel": (("time", "y", "x"), qa),
        },
        coords={"time": [np.datetime64("2024-06-12")], "y": y, "x": x},
    )
    return ds.rio.write_crs(f"EPSG:{epsg}")


def test_download_scene_writes_scaled_sr_and_qa(monkeypatch, tmp_path):
    monkeypatch.setattr(landsat.odc_stac, "load", lambda *a, **k: _fake_scene_dataset())
    item = _FakeItem("LC08_L2SP_test", dt.datetime(2024, 6, 12), 12)
    # sample blocks not used by the mocked loader, but _clip_bbox needs a real geometry.
    blocks = gpd.GeoDataFrame(
        {"FB_ID": ["x"], "geometry": [box(400_000, 5_800_000, 400_060, 5_800_060)]},
        crs="EPSG:32633",
    ).to_crs(4326)

    sr_path, qa_path = landsat.download_scene(
        item, blocks, tmp_path, epsg=32633, sr_bands=("red", "nir08"), qa_band="qa_pixel"
    )

    assert sr_path.name == "2024-06-12_LC08_L2SP_test_sr.tif"
    assert qa_path.name == "2024-06-12_LC08_L2SP_test_qa.tif"

    sr = rioxarray.open_rasterio(sr_path)
    assert sr.rio.crs.to_epsg() == 32633
    # DN 20000 -> 20000 * 0.0000275 - 0.2 = 0.35 reflectance.
    red = sr.sel(band=1).values
    assert np.isclose(np.nanmax(red), 0.35, atol=1e-4)
    # The DN-0 fill pixel becomes NaN, not -0.2.
    assert np.isnan(red).sum() == 1

    qa = rioxarray.open_rasterio(qa_path)
    assert qa.dtype == np.uint16


def test_parse_args_builds_config_and_options():
    config, max_cloud, buffer_m, scale, assume_yes = landsat.parse_args(
        ["--start", "2024-04-01", "--end", "2024-11-01", "--max-cloud", "20", "--no-scale"]
    )
    assert isinstance(config, Config)
    assert config.start == "2024-04-01" and config.end == "2024-11-01"
    assert max_cloud == 20
    assert scale is False
    assert assume_yes is False


def test_parse_args_yes_flag():
    *_, assume_yes = landsat.parse_args(["--yes"])
    assert assume_yes is True


def test_download_blocks_aborts_without_yes(monkeypatch, config):
    item = _FakeItem("LC09_test", dt.datetime(2025, 3, 20), 0)
    monkeypatch.setattr(landsat, "load_blocks", lambda: "blocks")
    monkeypatch.setattr(landsat, "search_scenes", lambda *a, **k: [item])
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    called = []
    monkeypatch.setattr(landsat, "download_scene", lambda *a, **k: called.append(1) or ("sr", "qa"))

    written = landsat.download_blocks_landsat(config, assume_yes=False)

    assert written == []
    assert called == []  # 'n' at the prompt means no scene is downloaded


def test_download_blocks_proceeds_on_yes(monkeypatch, config):
    item = _FakeItem("LC09_test", dt.datetime(2025, 3, 20), 0)
    monkeypatch.setattr(landsat, "load_blocks", lambda: "blocks")
    monkeypatch.setattr(landsat, "search_scenes", lambda *a, **k: [item])
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(landsat, "download_scene", lambda *a, **k: (config.landsat_dir / "x_sr.tif", "qa"))

    written = landsat.download_blocks_landsat(config, assume_yes=False)

    assert len(written) == 1

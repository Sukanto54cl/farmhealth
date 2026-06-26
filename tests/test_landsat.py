"""Tests for the Landsat downloader. No network: the STAC client and odc-stac loader are mocked."""

from __future__ import annotations

import datetime as dt

import numpy as np
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr

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
    from shapely.geometry import box
    import geopandas as gpd

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

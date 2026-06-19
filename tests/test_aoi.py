import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from src.aoi import _download_vg250, _find_kreise_layer, load_aoi
from src.config import Config


def _gdf(rows):
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def test_find_kreise_layer_matches_nested_shapefile(tmp_path):
    nested = tmp_path / "vg250" / "vg250_ebenen" / "DE"
    nested.mkdir(parents=True)
    target = nested / "vg250_01-01.utm32s.shape.ebenen_KRS.shp"
    target.write_text("")

    assert _find_kreise_layer(tmp_path) == target


def test_find_kreise_layer_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        _find_kreise_layer(tmp_path)


def test_load_aoi_selects_by_key_prefix_and_dissolves(tmp_path, monkeypatch):
    gdf = _gdf(
        [
            {"AGS": "120640001", "GEN": "Mte", "GF": 4, "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
            {"AGS": "120640002", "GEN": "Mte", "GF": 4, "geometry": Polygon([(1, 0), (1, 1), (2, 1), (2, 0)])},
            {"AGS": "120999999", "GEN": "Other", "GF": 4, "geometry": Polygon([(5, 5), (5, 6), (6, 6), (6, 5)])},
        ]
    )
    monkeypatch.setattr("src.aoi.gpd.read_file", lambda path: gdf)

    config = Config(aoi_name="Märkisch-Oderland", aoi_key_prefix="12064", vg250_path=tmp_path / "fake.shp")
    aoi = load_aoi(config)

    assert aoi.bbox_4326 == {"west": 0.0, "south": 0.0, "east": 2.0, "north": 1.0}
    assert aoi.geometry_4326.area == pytest.approx(2.0)


def test_load_aoi_prefers_land_area_geofaktor(tmp_path, monkeypatch):
    gdf = _gdf(
        [
            {"AGS": "120640001", "GEN": "Mte", "GF": 4, "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
            {"AGS": "120640001", "GEN": "Mte", "GF": 9, "geometry": Polygon([(10, 10), (10, 20), (20, 20), (20, 10)])},
        ]
    )
    monkeypatch.setattr("src.aoi.gpd.read_file", lambda path: gdf)

    config = Config(aoi_name="Märkisch-Oderland", aoi_key_prefix="12064", vg250_path=tmp_path / "fake.shp")
    aoi = load_aoi(config)

    assert aoi.bbox_4326 == {"west": 0.0, "south": 0.0, "east": 1.0, "north": 1.0}


def test_load_aoi_falls_back_to_name_when_prefix_unmatched(tmp_path, monkeypatch):
    gdf = _gdf(
        [
            {"AGS": "999999999", "GEN": "Barnim", "GF": 4, "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
            {"AGS": "888888888", "GEN": "OtherCounty", "GF": 4, "geometry": Polygon([(50, 50), (50, 51), (51, 51), (51, 50)])},
        ]
    )
    monkeypatch.setattr("src.aoi.gpd.read_file", lambda path: gdf)

    config = Config(aoi_name="Barnim", aoi_key_prefix="12064", vg250_path=tmp_path / "fake.shp")
    aoi = load_aoi(config)

    assert aoi.bbox_4326 == {"west": 0.0, "south": 0.0, "east": 1.0, "north": 1.0}


def test_load_aoi_raises_when_not_found(tmp_path, monkeypatch):
    gdf = _gdf(
        [
            {"AGS": "999999999", "GEN": "Other", "GF": 4, "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
        ]
    )
    monkeypatch.setattr("src.aoi.gpd.read_file", lambda path: gdf)

    config = Config(aoi_name="Nowhere", aoi_key_prefix="00000", vg250_path=tmp_path / "fake.shp")
    with pytest.raises(ValueError):
        load_aoi(config)


def test_download_vg250_skips_network_when_already_extracted(tmp_path, monkeypatch):
    extract_dir = tmp_path / "vg250"
    extract_dir.mkdir()

    def boom(*args, **kwargs):
        raise AssertionError("should not hit the network when already extracted")

    monkeypatch.setattr("src.aoi.requests.get", boom)

    assert _download_vg250(tmp_path) == extract_dir


def test_load_aoi_downloads_when_no_local_path_given(tmp_path, monkeypatch):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    krs_file = extracted / "VG250_KRS.shp"
    krs_file.write_text("")
    monkeypatch.setattr("src.aoi._download_vg250", lambda data_dir: extracted)

    gdf = _gdf(
        [
            {"AGS": "120640001", "GEN": "Mte", "GF": 4, "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
        ]
    )
    captured = {}

    def fake_read_file(path):
        captured["path"] = path
        return gdf

    monkeypatch.setattr("src.aoi.gpd.read_file", fake_read_file)

    config = Config(aoi_name="Märkisch-Oderland", aoi_key_prefix="12064", vg250_path=None, data_dir=tmp_path)
    load_aoi(config)

    assert captured["path"] == krs_file


def test_load_aoi_raises_keyerror_without_usable_columns(tmp_path, monkeypatch):
    gdf = _gdf([{"geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])}])
    monkeypatch.setattr("src.aoi.gpd.read_file", lambda path: gdf)

    config = Config(vg250_path=tmp_path / "fake.shp")
    with pytest.raises(KeyError):
        load_aoi(config)


def test_load_aoi_skips_download_when_local_path_given(tmp_path, monkeypatch):
    gdf = _gdf(
        [
            {"AGS": "120640001", "GEN": "Mte", "GF": 4, "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
        ]
    )
    monkeypatch.setattr("src.aoi.gpd.read_file", lambda path: gdf)

    def boom(_data_dir):
        raise AssertionError("should not download when vg250_path is set")

    monkeypatch.setattr("src.aoi._download_vg250", boom)

    config = Config(aoi_name="Märkisch-Oderland", aoi_key_prefix="12064", vg250_path=tmp_path / "fake.shp")
    load_aoi(config)  # must not raise

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from src.blocks import load_blocks


def _gdf(rows):
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:25833")


def test_load_blocks_selects_and_orders_by_block_ids(tmp_path, monkeypatch):
    gdf = _gdf(
        [
            {"FB_ID": "B", "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])},
            {"FB_ID": "A", "geometry": Polygon([(10, 10), (10, 11), (11, 11), (11, 10)])},
            {"FB_ID": "C", "geometry": Polygon([(20, 20), (20, 21), (21, 21), (21, 20)])},
        ]
    )
    monkeypatch.setattr("src.blocks.gpd.read_file", lambda path: gdf)

    blocks = load_blocks(path=tmp_path / "fake.shp", block_ids=("A", "B"))

    assert list(blocks["FB_ID"]) == ["A", "B"]
    assert blocks.crs.to_epsg() == 4326


def test_load_blocks_raises_when_id_missing(tmp_path, monkeypatch):
    gdf = _gdf([{"FB_ID": "A", "geometry": Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])}])
    monkeypatch.setattr("src.blocks.gpd.read_file", lambda path: gdf)

    with pytest.raises(ValueError, match="MISSING"):
        load_blocks(path=tmp_path / "fake.shp", block_ids=("A", "MISSING"))

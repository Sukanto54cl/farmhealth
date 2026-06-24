import pandas as pd
import pytest

from src.ndvi_cube import build_monthly_ndvi
from src.outputs import (
    _parse_block_timeseries,
    _parse_timeseries,
    write_block_timeseries,
    write_netcdf_cube,
    write_timeseries,
)


def test_parse_timeseries_sorts_and_extracts_first_band():
    result = {
        "2025-06-01T00:00:00Z": [[0.55]],
        "2025-05-01T00:00:00Z": [[0.42]],
    }
    df = _parse_timeseries(result)
    assert list(df["date"]) == [pd.Timestamp("2025-05-01", tz="UTC"), pd.Timestamp("2025-06-01", tz="UTC")]
    assert list(df["ndvi"]) == [0.42, 0.55]


def test_parse_timeseries_missing_values_become_none():
    result = {
        "2025-05-01T00:00:00Z": [[]],  # geometry present but no band value (fully masked)
        "2025-06-01T00:00:00Z": [],  # no geometry result at all
    }
    df = _parse_timeseries(result)
    assert df["ndvi"].isna().all()


def test_write_timeseries_writes_csv_png_and_uses_mean_reducer(dummy_backend, sample_aoi, config):
    cube = build_monthly_ndvi(dummy_backend.connection, sample_aoi, config)
    dummy_backend.next_result = {"2025-05-01T00:00:00Z": [[0.42]]}

    write_timeseries(cube, sample_aoi, config)

    assert config.timeseries_csv.exists()
    assert config.timeseries_png.exists()
    df = pd.read_csv(config.timeseries_csv)
    assert df["ndvi"].iloc[0] == pytest.approx(0.42)

    pg = dummy_backend.get_sync_pg()
    agg = next(n for n in pg.values() if n["process_id"] == "aggregate_spatial")
    reducer_pg = agg["arguments"]["reducer"]["process_graph"]
    assert {n["process_id"] for n in reducer_pg.values()} == {"mean"}


def test_parse_block_timeseries_maps_geometry_order_to_block_id():
    result = {
        "2025-05-01T00:00:00Z": [[0.1], [0.2]],
        "2025-06-01T00:00:00Z": [[], [0.3]],  # block A fully masked in June
    }
    df = _parse_block_timeseries(result, ["A", "B"])

    a = df[df["block_id"] == "A"].reset_index(drop=True)
    b = df[df["block_id"] == "B"].reset_index(drop=True)
    assert list(a["ndvi"]) == [0.1, None]
    assert list(b["ndvi"]) == [0.2, 0.3]


def test_write_block_timeseries_writes_csv_with_one_row_per_block_per_date(
    dummy_backend, sample_aoi, sample_blocks, config
):
    cube = build_monthly_ndvi(dummy_backend.connection, sample_aoi, config)
    dummy_backend.next_result = {"2025-05-01T00:00:00Z": [[0.1], [0.2]]}

    out_path = write_block_timeseries(cube, sample_blocks, config)

    assert out_path == config.blocks_timeseries_csv
    df = pd.read_csv(out_path)
    assert set(df["block_id"]) == {"DEBBLI0264002685", "DEBBLI2064399462"}
    assert df.loc[df["block_id"] == "DEBBLI0264002685", "ndvi"].iloc[0] == pytest.approx(0.1)
    assert df.loc[df["block_id"] == "DEBBLI2064399462", "ndvi"].iloc[0] == pytest.approx(0.2)

    pg = dummy_backend.get_sync_pg()
    agg = next(n for n in pg.values() if n["process_id"] == "aggregate_spatial")
    assert len(agg["arguments"]["geometries"]["features"]) == 2


def test_write_netcdf_cube_clips_to_aoi_and_writes_netcdf(dummy_backend, sample_aoi, config):
    cube = build_monthly_ndvi(dummy_backend.connection, sample_aoi, config)

    out_path = write_netcdf_cube(cube, sample_aoi, config)

    assert out_path == config.netcdf_path
    assert out_path.exists()

    pg = dummy_backend.get_batch_pg()
    assert any(n["process_id"] == "mask_polygon" for n in pg.values())
    save_result = next(n for n in pg.values() if n["process_id"] == "save_result")
    assert save_result["arguments"]["format"] == "netCDF"

    post_data = dummy_backend.get_batch_post_data()
    assert post_data["title"] == f"Monthly NDVI {config.aoi_name} {config.start}..{config.end}"

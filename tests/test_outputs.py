import pandas as pd
import pytest

from src.ndvi_cube import build_monthly_ndvi
from src.outputs import _parse_timeseries, write_netcdf_cube, write_timeseries


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

from pathlib import Path

from src.config import Config, parse_args


def test_defaults():
    config = Config()
    assert config.start == "2025-05-01"
    assert config.end == "2026-05-01"
    assert config.aoi_name == "Märkisch-Oderland"
    assert config.aoi_key_prefix == "12064"
    assert config.resolution == 20
    assert config.epsg == 32633
    assert config.out_dir == Path("outputs")
    assert config.data_dir == Path("data")
    assert config.vg250_path is None


def test_aoi_slug_transliterates_german_characters():
    assert Config(aoi_name="Märkisch-Oderland").aoi_slug == "maerkisch-oderland"
    assert Config(aoi_name="Würzburg").aoi_slug == "wuerzburg"
    assert Config(aoi_name="Groß-Gerau").aoi_slug == "gross-gerau"
    assert Config(aoi_name="Barnim").aoi_slug == "barnim"


def test_derived_output_paths():
    config = Config(aoi_name="Barnim", out_dir=Path("out"))
    assert config.netcdf_path == Path("out/ndvi_monthly_barnim.nc")
    assert config.timeseries_csv == Path("out/ndvi_timeseries.csv")
    assert config.timeseries_png == Path("out/ndvi_timeseries.png")


def test_parse_args_defaults_match_config_defaults():
    assert parse_args([]) == Config()


def test_parse_args_overrides():
    config = parse_args(
        [
            "--start", "2024-01-01",
            "--end", "2024-02-01",
            "--aoi-name", "Barnim",
            "--aoi-key-prefix", "12060",
            "--resolution", "10",
            "--epsg", "25832",
            "--out-dir", "custom-out",
            "--data-dir", "custom-data",
            "--vg250-path", "boundaries/VG250_KRS.shp",
        ]
    )
    assert config == Config(
        start="2024-01-01",
        end="2024-02-01",
        aoi_name="Barnim",
        aoi_key_prefix="12060",
        resolution=10,
        epsg=25832,
        out_dir=Path("custom-out"),
        data_dir=Path("custom-data"),
        vg250_path=Path("boundaries/VG250_KRS.shp"),
    )

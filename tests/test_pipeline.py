import json

from src.pipeline import run


def test_run_orchestrates_aoi_connect_and_outputs(monkeypatch, dummy_backend, sample_aoi, config):
    monkeypatch.setattr("src.pipeline.load_aoi", lambda cfg: sample_aoi)
    monkeypatch.setattr("src.pipeline.connect", lambda: dummy_backend.connection)
    # Pre-encoded as bytes (rather than a dict) so the same `next_result` satisfies both the
    # JSON sync /result response (timeseries) and the binary batch-job asset download (netCDF).
    dummy_backend.next_result = json.dumps({"2025-05-01T00:00:00Z": [[0.42]]}).encode("utf-8")

    run(config)

    assert config.timeseries_csv.exists()
    assert config.timeseries_png.exists()
    assert config.netcdf_path.exists()
    assert len(dummy_backend.sync_requests) == 1
    assert len(dummy_backend.batch_jobs) == 1

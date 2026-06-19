from src.config import SCL_MASK_CLASSES, Config
from src.ndvi_cube import build_monthly_ndvi, connect


class _FakeConnection:
    def __init__(self):
        self.authenticated = False

    def authenticate_oidc(self):
        self.authenticated = True


def test_connect_authenticates_via_oidc(monkeypatch):
    fake_connection = _FakeConnection()
    captured = {}

    def fake_connect(url):
        captured["url"] = url
        return fake_connection

    monkeypatch.setattr("src.ndvi_cube.openeo.connect", fake_connect)

    result = connect()

    assert captured["url"] == "openeo.dataspace.copernicus.eu"
    assert result is fake_connection
    assert fake_connection.authenticated is True


def _scl_eq_values(pg: dict) -> list[int]:
    """Comparison values of the `eq` nodes inside the SCL-mask reduce_dimension subgraph."""
    scl_reduce = next(
        node
        for node in pg.values()
        if node["process_id"] == "reduce_dimension"
        and any(n["process_id"] == "eq" for n in node["arguments"]["reducer"]["process_graph"].values())
    )
    reducer_pg = scl_reduce["arguments"]["reducer"]["process_graph"]
    return sorted(n["arguments"]["y"] for n in reducer_pg.values() if n["process_id"] == "eq")


def test_build_monthly_ndvi_graph_shape(dummy_backend, sample_aoi):
    config = Config(resolution=20, epsg=32633)
    cube = build_monthly_ndvi(dummy_backend.connection, sample_aoi, config)
    pg = dummy_backend.execute(cube)

    load = pg["loadcollection1"]
    assert load["arguments"]["id"] == "SENTINEL2_L2A"
    assert load["arguments"]["bands"] == ["B04", "B08", "SCL"]
    assert load["arguments"]["spatial_extent"] == sample_aoi.bbox_4326
    assert load["arguments"]["temporal_extent"] == [config.start, config.end]

    assert pg["mask1"]["process_id"] == "mask"

    agg = pg["aggregatetemporalperiod1"]
    assert agg["arguments"]["period"] == "month"
    reducer_pg = agg["arguments"]["reducer"]["process_graph"]
    assert {n["process_id"] for n in reducer_pg.values()} == {"median"}

    interp = pg["applydimension1"]
    assert interp["arguments"]["dimension"] == "t"
    interp_pg = interp["arguments"]["process"]["process_graph"]
    assert {n["process_id"] for n in interp_pg.values()} == {"array_interpolate_linear"}

    resample = pg["resamplespatial1"]
    assert resample["arguments"]["resolution"] == 20
    assert resample["arguments"]["projection"] == 32633


def test_build_monthly_ndvi_masks_configured_scl_classes(dummy_backend, sample_aoi):
    config = Config()
    cube = build_monthly_ndvi(dummy_backend.connection, sample_aoi, config)
    pg = dummy_backend.execute(cube)

    assert _scl_eq_values(pg) == sorted(SCL_MASK_CLASSES)


def test_build_monthly_ndvi_uses_custom_resolution_and_epsg(dummy_backend, sample_aoi):
    config = Config(resolution=10, epsg=25832)
    cube = build_monthly_ndvi(dummy_backend.connection, sample_aoi, config)
    pg = dummy_backend.execute(cube)

    resample = next(n for n in pg.values() if n["process_id"] == "resample_spatial")
    assert resample["arguments"]["resolution"] == 10
    assert resample["arguments"]["projection"] == 25832

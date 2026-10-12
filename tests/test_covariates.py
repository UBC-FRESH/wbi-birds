from __future__ import annotations

import pytest

from wbi_birds.covariates import CovariateError, build_covariate_rows, sample_rasters


def _samples(**overrides):
    base = {
        "A": [10.0, 20.0, 5.0],
        "B": [5.0, 0.0, 1.0],
        "C": [2.0, 4.0, 8.0],
        "mvol": [100.0, 50.0, 10.0],
        "knn_age": [100.0, 50.0, 2.0],
    }
    base.update(overrides)
    return base


def test_build_covariate_rows_scales_and_projects() -> None:
    rows = build_covariate_rows(
        _samples(),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=(2005, 2011, 2015),
    )
    # third row: age 2 - (2011-2015) = 6 -> retained here; first row: 100-6=94
    assert len(rows) == 3
    assert rows[0]["softwood"] == pytest.approx(0.01 * 100.0 * 15.0)
    assert rows[0]["hardwood"] == pytest.approx(0.01 * 100.0 * 2.0)
    assert rows[0]["age"] == pytest.approx(94.0)
    assert rows[1]["age"] == pytest.approx(50.0)
    assert rows[2]["age"] == pytest.approx(6.0)


def test_build_covariate_rows_drops_negative_projection() -> None:
    rows = build_covariate_rows(
        _samples(),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=(2000, 2011, 2015),  # row 2: 50 - 11 = 39 kept
    )
    assert len(rows) == 3
    # make the projection negative for all: base year far in the future
    rows = build_covariate_rows(
        _samples(),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=(2011, 2011, 2011),
        base_year=2200,
    )
    assert rows == []


def test_fri_age_takes_precedence() -> None:
    rows = build_covariate_rows(
        _samples(fri_age=[80.0, None, 30.0]),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        fri_age="fri_age",
        observation_year=(2011, 2011, 2011),
    )
    assert [row["age"] for row in rows] == [80.0, 50.0, 30.0]


def test_build_covariate_rows_validates_layers() -> None:
    with pytest.raises(CovariateError, match="fri_age layer"):
        build_covariate_rows(
            _samples(),
            softwood_species=("A",),
            hardwood_species=("C",),
            merchantable_volume="mvol",
            knn_age="knn_age",
            fri_age="missing",
            observation_year=(2011, 2011, 2011),
        )
    with pytest.raises(CovariateError, match="observation_year"):
        build_covariate_rows(
            _samples(),
            softwood_species=("A",),
            hardwood_species=("C",),
            merchantable_volume="mvol",
            knn_age="knn_age",
            observation_year=(2011,),
        )


def test_sample_rasters_requires_optional_dependency() -> None:
    try:
        import rasterio  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("rasterio is installed")
    with pytest.raises(CovariateError, match="rasterio"):
        sample_rasters({"a": "does-not-exist.tif"}, [(0.0, 0.0)])


def test_sample_rasters_reads_geotiff(tmp_path) -> None:
    rasterio = pytest.importorskip("rasterio")
    np = pytest.importorskip("numpy")
    from rasterio.transform import from_origin

    path = tmp_path / "a.tif"
    data = np.array([[1.0, 2.0], [3.0, -9999.0]], dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0.0, 2.0, 1.0, 1.0),
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)
    samples = sample_rasters({"a": path}, [(0.5, 1.5), (1.5, 1.5), (1.5, 0.5)], nodata=None)
    assert samples["a"][0] == 1.0
    assert samples["a"][1] == 2.0
    assert samples["a"][2] is None  # raster-declared nodata

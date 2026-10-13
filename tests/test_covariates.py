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
        definition="legacy_biomass_scaled",
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


def _contract_samples(**overrides):
    base = {
        "A": [10.0, 20.0, 5.0, 0.0],
        "B": [5.0, 0.0, 1.0, 0.0],
        "C": [2.0, 4.0, 8.0, 0.0],
        "mvol": [100.0, 50.0, 10.0, 80.0],
        "knn_age": [100.0, 50.0, 60.0, 70.0],
    }
    base.update(overrides)
    return base


def test_allocation_sums_to_merchantable_volume() -> None:
    rows = build_covariate_rows(
        _contract_samples(),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=(2011, 2011, 2011, 2011),
    )
    assert len(rows) == 3  # the all-zero-biomass row has no defined share
    for row, mvol in zip(rows, (100.0, 50.0, 10.0), strict=True):
        assert row["softwood"] + row["hardwood"] == pytest.approx(mvol)
    assert rows[0]["softwood"] == pytest.approx(100.0 * 15.0 / 17.0)
    assert rows[0]["hardwood"] == pytest.approx(100.0 * 2.0 / 17.0)


def test_zero_biomass_rows_are_dropped() -> None:
    samples = _contract_samples(
        A=[0.0, 0.0, 0.0, 0.0], B=[0.0, 0.0, 0.0, 0.0], C=[0.0, 0.0, 0.0, 0.0]
    )
    assert (
        build_covariate_rows(
            samples,
            softwood_species=("A", "B"),
            hardwood_species=("C",),
            merchantable_volume="mvol",
            knn_age="knn_age",
            observation_year=2011,
        )
        == []
    )


def test_missing_classified_species_drops_the_row() -> None:
    """R NA propagation: a partial denominator would bias the share, so the row goes."""
    samples = _contract_samples(B=[5.0, float("nan"), 1.0, 0.0])
    rows = build_covariate_rows(
        samples,
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=2011,
    )
    # row 1 (missing B) and row 3 (zero biomass) are dropped; rows 0 and 2 remain
    assert [row["softwood"] + row["hardwood"] for row in rows] == pytest.approx([100.0, 10.0])


def test_unsampled_classified_species_is_a_configuration_error() -> None:
    with pytest.raises(CovariateError, match="not sampled"):
        build_covariate_rows(
            _contract_samples(),
            softwood_species=("A", "Z"),
            hardwood_species=("C",),
            merchantable_volume="mvol",
            knn_age="knn_age",
            observation_year=2011,
        )


def test_unknown_definition_is_rejected() -> None:
    with pytest.raises(CovariateError, match="unknown wood-type definition"):
        build_covariate_rows(
            _contract_samples(),
            softwood_species=("A", "B"),
            hardwood_species=("C",),
            merchantable_volume="mvol",
            knn_age="knn_age",
            observation_year=2011,
            definition="biomass_mystery",
        )


def test_response_is_aligned_to_retained_rows() -> None:
    rows = build_covariate_rows(
        _contract_samples(B=[5.0, float("nan"), 1.0, 0.0]),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=2011,
        response=[3.0, 7.0, 1.0, 9.0],
    )
    # row 1 is dropped for its missing species; row 3 has zero classified biomass (no share).
    # The surviving counts must stay aligned to their own rows.
    assert [row["observation_count"] for row in rows] == [3.0, 1.0]


def test_legacy_definition_still_matches_the_2019_scaling() -> None:
    rows = build_covariate_rows(
        _contract_samples(),
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=2011,
        definition="legacy_biomass_scaled",
    )
    assert rows[0]["softwood"] == pytest.approx(0.01 * 100.0 * 15.0)
    assert rows[0]["hardwood"] == pytest.approx(0.01 * 100.0 * 2.0)
    assert rows[0]["softwood"] + rows[0]["hardwood"] != pytest.approx(100.0)


def test_accepts_numpy_arrays_for_years_counts_and_layers() -> None:
    """The refit passes numpy arrays; they must behave like the list inputs."""
    import numpy as np

    samples = {
        name: np.asarray(values, dtype=float) for name, values in _contract_samples().items()
    }
    rows = build_covariate_rows(
        samples,
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=np.array([2011, 2011, 2011, 2011]),
        response=np.array([3.0, 7.0, 1.0, 9.0]),
    )
    # row 3 has zero classified biomass (no share) and is dropped; rows 0-2 keep their counts
    assert [row["observation_count"] for row in rows] == [3.0, 7.0, 1.0]
    assert [row["age"] for row in rows] == pytest.approx([100.0, 50.0, 60.0])
    scalar_year = build_covariate_rows(
        samples,
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=np.int64(2011),
    )
    assert len(scalar_year) == 3


def test_zero_volume_rows_are_kept_with_zero_wood_volume() -> None:
    """Zero merchantable volume is a real state (harvested/non-forest): keep it, at zero."""
    samples = _contract_samples(
        A=[10.0, 20.0, 5.0, 0.0],
        B=[5.0, 0.0, 1.0, 0.0],
        C=[2.0, 4.0, 8.0, 0.0],
        mvol=[100.0, 50.0, 10.0, 0.0],
    )
    rows = build_covariate_rows(
        samples,
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume="mvol",
        knn_age="knn_age",
        observation_year=2011,
    )
    zero_volume = rows[-1]
    assert zero_volume["softwood"] == 0.0 and zero_volume["hardwood"] == 0.0
    assert len(rows) == 4

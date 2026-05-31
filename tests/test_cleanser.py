"""Tests for src/cleanser.py."""
import pandas as pd
import pytest

from src.cleanser import (
    coerce_orders_types,
    coerce_zip_codes,
    dedupe_geolocation,
    dedupe_reviews,
    fill_category_name,
    filter_invalid_prices,
    filter_invalid_payments,
    filter_invalid_product_dimensions,
)


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def test_coerce_orders_types_converts_dates():
    df = pd.DataFrame(
        {
            "order_id": ["a", "b"],
            "order_purchase_timestamp": ["2017-01-15 10:00:00", "2017-02-20 14:30:00"],
            "order_approved_at": ["2017-01-15 12:00:00", "2017-02-20 16:00:00"],
        }
    )
    result = coerce_orders_types(df)
    assert pd.api.types.is_datetime64_any_dtype(result["order_purchase_timestamp"])
    assert pd.api.types.is_datetime64_any_dtype(result["order_approved_at"])


def test_coerce_orders_types_does_not_mutate_input():
    df = pd.DataFrame({"order_purchase_timestamp": ["2017-01-15 10:00:00"]})
    original_dtype = df["order_purchase_timestamp"].dtype
    coerce_orders_types(df)
    assert df["order_purchase_timestamp"].dtype == original_dtype


def test_coerce_zip_codes_preserves_leading_zeros():
    df = pd.DataFrame({"zip": [1234, 567, 89012]})
    result = coerce_zip_codes(df, "zip")
    assert list(result["zip"]) == ["01234", "00567", "89012"]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_dedupe_geolocation_removes_full_duplicates():
    df = pd.DataFrame(
        {
            "zip": [1000, 1000, 2000, 2000, 3000],
            "lat": [-23.5, -23.5, -22.9, -22.9, -25.0],
            "lng": [-46.6, -46.6, -47.0, -47.0, -49.3],
        }
    )
    result, stats = dedupe_geolocation(df)
    assert len(result) == 3
    assert stats.rows_removed == 2
    assert stats.removed_pct == 40.0


def test_dedupe_reviews_keeps_first():
    df = pd.DataFrame(
        {
            "review_id": ["a", "b", "a", "c"],
            "review_creation_date": [
                "2017-01-01 10:00:00",
                "2017-02-01 10:00:00",
                "2017-03-01 10:00:00",
                "2017-04-01 10:00:00",
            ],
            "review_score": [5, 4, 3, 2],
        }
    )
    result, stats = dedupe_reviews(df, strategy="keep_first")
    assert len(result) == 3
    assert result[result["review_id"] == "a"]["review_score"].iloc[0] == 5


def test_dedupe_reviews_keeps_latest():
    df = pd.DataFrame(
        {
            "review_id": ["a", "b", "a"],
            "review_creation_date": [
                "2017-01-01 10:00:00",
                "2017-02-01 10:00:00",
                "2017-03-01 10:00:00",
            ],
            "review_score": [5, 4, 1],
        }
    )
    result, _ = dedupe_reviews(df, strategy="keep_latest")
    # keep_latest должен оставить запись с score=1 (самая свежая)
    assert result[result["review_id"] == "a"]["review_score"].iloc[0] == 1


def test_dedupe_reviews_invalid_strategy_raises():
    df = pd.DataFrame({"review_id": ["a"], "review_creation_date": ["2017-01-01 10:00:00"]})
    with pytest.raises(ValueError):
        dedupe_reviews(df, strategy="nonsense")


# ---------------------------------------------------------------------------
# Null handling
# ---------------------------------------------------------------------------


def test_fill_category_name_fills_nulls():
    df = pd.DataFrame({"product_category_name": ["electronics", None, "books", None]})
    result = fill_category_name(df)
    assert result["product_category_name"].isnull().sum() == 0
    assert (result["product_category_name"] == "unknown").sum() == 2


# ---------------------------------------------------------------------------
# Invalid record filtering
# ---------------------------------------------------------------------------


def test_filter_invalid_prices_removes_zero_and_negative():
    df = pd.DataFrame({"price": [10.0, 0.0, -5.0, 100.0, 0.85]})
    result, stats = filter_invalid_prices(df)
    assert len(result) == 3
    assert (result["price"] > 0).all()
    assert stats.rows_removed == 2


def test_filter_invalid_payments_removes_not_defined_and_zero():
    df = pd.DataFrame(
        {
            "payment_type": ["credit_card", "not_defined", "boleto", "credit_card"],
            "payment_value": [100.0, 50.0, 0.0, 200.0],
        }
    )
    result, _ = filter_invalid_payments(df)
    assert len(result) == 2
    assert "not_defined" not in result["payment_type"].values
    assert (result["payment_value"] > 0).all()


def test_filter_invalid_product_dimensions_keeps_nan_rows():
    df = pd.DataFrame(
        {
            "product_weight_g": [500, 0, 300, None],
            "product_length_cm": [10, 10, 5, None],
            "product_height_cm": [5, 5, 0, 10],
            "product_width_cm": [8, 8, 8, 8],
        }
    )
    result, _ = filter_invalid_product_dimensions(df)
    # Row 0: всё положительное (оставляем)
    # Row 1: вес = 0 (фильтруем)
    # Row 2: высота = 0 (фильтруем)
    # Row 3: есть NaN (оставляем — частичные данные)
    assert len(result) == 2

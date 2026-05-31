"""Cleansing pipeline for Olist e-commerce data.

Each function takes a raw DataFrame and returns a cleansed copy.
Strategies are explicit per issue type (drop / fill / coerce / filter).
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class CleansingStats:
    """Tracks rows affected by a single cleansing operation."""

    operation: str
    rows_before: int
    rows_after: int

    @property
    def rows_removed(self) -> int:
        return self.rows_before - self.rows_after

    @property
    def removed_pct(self) -> float:
        if self.rows_before == 0:
            return 0.0
        return round(self.rows_removed / self.rows_before * 100, 2)

    def __repr__(self) -> str:
        return (
            f"  {self.operation}: {self.rows_before:,} -> {self.rows_after:,} "
            f"(-{self.rows_removed:,}, {self.removed_pct}%)"
        )


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


ORDERS_DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def coerce_orders_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert order date columns from object to datetime64."""
    df = df.copy()
    for col in ORDERS_DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def coerce_zip_codes(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """ZIP codes must be strings to preserve leading zeros."""
    df = df.copy()
    df[col] = df[col].astype(str).str.zfill(5)
    return df


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def dedupe_geolocation(df: pd.DataFrame) -> tuple[pd.DataFrame, CleansingStats]:
    """Drop full-row duplicates in geolocation (26% of the table)."""
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    stats = CleansingStats("geolocation_dedup", before, len(df))
    logger.info(stats)
    return df, stats


def dedupe_reviews(
    df: pd.DataFrame, strategy: str = "keep_first"
) -> tuple[pd.DataFrame, CleansingStats]:
    """Resolve duplicate review_id rows.

    Strategies:
      - keep_first: stable, keeps original row order
      - keep_latest: keeps the row with the most recent review_creation_date
    """
    before = len(df)
    if strategy == "keep_first":
        df = df.drop_duplicates(subset="review_id", keep="first").reset_index(drop=True)
    elif strategy == "keep_latest":
        df = df.copy()
        df["review_creation_date"] = pd.to_datetime(df["review_creation_date"])
        df = (
            df.sort_values("review_creation_date", ascending=False)
            .drop_duplicates(subset="review_id", keep="first")
            .reset_index(drop=True)
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}")
    stats = CleansingStats(f"reviews_dedup_{strategy}", before, len(df))
    logger.info(stats)
    return df, stats


# ---------------------------------------------------------------------------
# Null handling
# ---------------------------------------------------------------------------


def fill_category_name(df: pd.DataFrame) -> pd.DataFrame:
    """Fill null product_category_name with 'unknown'.

    Strategy choice: fill, not drop, because the row still has valid pricing
    and dimension data that downstream analytics needs.
    """
    df = df.copy()
    df["product_category_name"] = df["product_category_name"].fillna("unknown")
    return df


# ---------------------------------------------------------------------------
# Invalid record filtering
# ---------------------------------------------------------------------------


def filter_invalid_prices(df: pd.DataFrame) -> tuple[pd.DataFrame, CleansingStats]:
    """Drop order_items rows with non-positive price."""
    before = len(df)
    df = df[df["price"] > 0].reset_index(drop=True)
    stats = CleansingStats("order_items_price_filter", before, len(df))
    logger.info(stats)
    return df, stats


def filter_invalid_payments(df: pd.DataFrame) -> tuple[pd.DataFrame, CleansingStats]:
    """Drop payment rows that are unusable for financial reporting:

    - payment_type == 'not_defined' (3 records)
    - payment_value == 0 (9 records, potential fraud signal)
    """
    before = len(df)
    df = df[
        (df["payment_type"] != "not_defined") & (df["payment_value"] > 0)
    ].reset_index(drop=True)
    stats = CleansingStats("payments_filter", before, len(df))
    logger.info(stats)
    return df, stats


PRODUCT_DIM_COLS = [
    "product_weight_g",
    "product_length_cm",
    "product_height_cm",
    "product_width_cm",
]


def filter_invalid_product_dimensions(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, CleansingStats]:
    """Drop products with zero or negative dimensions.

    Rows with NaN in dimensions are kept — partial info is still useful and
    the downstream consumer can decide imputation.
    """
    before = len(df)
    all_positive = (df[PRODUCT_DIM_COLS] > 0).all(axis=1)
    any_nan = df[PRODUCT_DIM_COLS].isna().any(axis=1)
    df = df[all_positive | any_nan].reset_index(drop=True)
    stats = CleansingStats("products_dim_filter", before, len(df))
    logger.info(stats)
    return df, stats


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], list[CleansingStats]]:
    """Apply the full cleansing pipeline.

    Args:
        raw: dict mapping table name -> raw DataFrame.

    Returns:
        (clean, stats):
            clean: dict mapping table name -> cleansed DataFrame.
            stats: list of CleansingStats for operations that filter rows.
    """
    clean: dict[str, pd.DataFrame] = {}
    stats: list[CleansingStats] = []

    # Type coercion (no row filtering)
    clean["orders"] = coerce_orders_types(raw["orders"])
    clean["customers"] = coerce_zip_codes(raw["customers"], "customer_zip_code_prefix")
    clean["sellers"] = coerce_zip_codes(raw["sellers"], "seller_zip_code_prefix")

    # Deduplication
    clean["geolocation"], s = dedupe_geolocation(raw["geolocation"])
    stats.append(s)
    clean["order_reviews"], s = dedupe_reviews(raw["order_reviews"], strategy="keep_first")
    stats.append(s)

    # Null handling + filtering
    products = fill_category_name(raw["products"])
    clean["products"], s = filter_invalid_product_dimensions(products)
    stats.append(s)

    clean["order_items"], s = filter_invalid_prices(raw["order_items"])
    stats.append(s)

    clean["order_payments"], s = filter_invalid_payments(raw["order_payments"])
    stats.append(s)

    return clean, stats

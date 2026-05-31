"""Tests for src/custom_checks.py."""
import pandas as pd

from src.custom_checks import (
    CheckResult,
    check_conditional_not_null,
    check_date_order,
    check_fk_integrity,
    check_orders_have_items,
)


def test_check_result_success_rate():
    r = CheckResult(name="x", total_checked=100, violations=5, success=False)
    assert r.success_rate == 0.95


def test_check_result_zero_total():
    r = CheckResult(name="x", total_checked=0, violations=0, success=True)
    assert r.success_rate == 1.0


# ---------------------------------------------------------------------------
# Conditional null
# ---------------------------------------------------------------------------


def test_conditional_not_null_finds_violations():
    df = pd.DataFrame(
        {
            "status": ["delivered", "delivered", "shipped", "delivered"],
            "delivery_date": ["2017-01-01", None, None, "2017-01-03"],
        }
    )
    result = check_conditional_not_null(df, "status", "delivered", "delivery_date")
    assert result.violations == 1  # одна 'delivered' без даты
    assert result.total_checked == 3  # три записи со status='delivered'
    assert not result.success


def test_conditional_not_null_clean_data():
    df = pd.DataFrame(
        {
            "status": ["delivered", "shipped", "delivered"],
            "delivery_date": ["2017-01-01", None, "2017-01-03"],
        }
    )
    result = check_conditional_not_null(df, "status", "delivered", "delivery_date")
    assert result.violations == 0
    assert result.success


# ---------------------------------------------------------------------------
# Date order
# ---------------------------------------------------------------------------


def test_date_order_detects_violations():
    df = pd.DataFrame(
        {
            "purchase": ["2017-01-01", "2017-02-01", "2017-03-01"],
            "approved": ["2017-01-02", "2017-01-15", "2017-03-02"],
            # row 1: approved (Jan 15) < purchase (Feb 1) — violation
        }
    )
    result = check_date_order(df, "purchase", "approved")
    assert result.violations == 1
    assert not result.success


def test_date_order_ignores_nans():
    df = pd.DataFrame(
        {
            "purchase": ["2017-01-01", None, "2017-03-01"],
            "approved": ["2017-01-02", "2017-02-15", None],
        }
    )
    result = check_date_order(df, "purchase", "approved")
    # Только первая строка имеет обе даты
    assert result.total_checked == 1
    assert result.violations == 0


# ---------------------------------------------------------------------------
# FK integrity
# ---------------------------------------------------------------------------


def test_fk_integrity_passes_when_all_parents_exist():
    parent = pd.DataFrame({"id": ["a", "b", "c"]})
    child = pd.DataFrame({"parent_id": ["a", "a", "b"]})
    result = check_fk_integrity(child, "parent_id", parent, "id")
    assert result.violations == 0
    assert result.success


def test_fk_integrity_finds_orphans():
    parent = pd.DataFrame({"id": ["a", "b"]})
    child = pd.DataFrame({"parent_id": ["a", "x", "y", "b"]})
    result = check_fk_integrity(child, "parent_id", parent, "id")
    assert result.violations == 2
    assert "x" in result.sample_violations
    assert "y" in result.sample_violations


# ---------------------------------------------------------------------------
# Orders have items
# ---------------------------------------------------------------------------


def test_orders_have_items_detects_empty_orders():
    orders = pd.DataFrame({"order_id": ["o1", "o2", "o3", "o4"]})
    items = pd.DataFrame({"order_id": ["o1", "o2", "o2"], "product_id": ["p1", "p2", "p3"]})
    result = check_orders_have_items(orders, items)
    # o3 и o4 — без товаров
    assert result.violations == 2
    assert "o3" in result.sample_violations
    assert "o4" in result.sample_violations

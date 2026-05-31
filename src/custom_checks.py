"""Custom data quality checks that go beyond standard Great Expectations.

Covers:
  - conditional checks (column X required when column Y == value)
  - chronological order between date columns
  - cross-table foreign key integrity
  - referential completeness (every parent has at least one child)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class CheckResult:
    """Standardized output for a single data quality check."""

    name: str
    total_checked: int
    violations: int
    success: bool
    sample_violations: list[Any] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_checked == 0:
            return 1.0
        return 1 - self.violations / self.total_checked

    def __repr__(self) -> str:
        status = "PASS" if self.success else "FAIL"
        return (
            f"[{status}] {self.name}: {self.violations:,} of {self.total_checked:,} "
            f"({self.success_rate * 100:.2f}% pass rate)"
        )


def check_conditional_not_null(
    df: pd.DataFrame,
    condition_col: str,
    condition_value: Any,
    target_col: str,
    name: str | None = None,
) -> CheckResult:
    """When condition_col == condition_value, target_col must not be null."""
    name = name or f"{target_col} not null when {condition_col}={condition_value}"
    subset = df[df[condition_col] == condition_value]
    null_mask = subset[target_col].isnull()
    violations = int(null_mask.sum())
    sample = subset[null_mask].head(3).to_dict("records") if violations > 0 else []
    return CheckResult(
        name=name,
        total_checked=len(subset),
        violations=violations,
        success=violations == 0,
        sample_violations=sample,
    )


def check_date_order(
    df: pd.DataFrame,
    earlier_col: str,
    later_col: str,
    name: str | None = None,
) -> CheckResult:
    """earlier_col must be <= later_col. Rows with NaN in either are ignored."""
    name = name or f"{earlier_col} <= {later_col}"
    earlier = pd.to_datetime(df[earlier_col], errors="coerce")
    later = pd.to_datetime(df[later_col], errors="coerce")
    both_present = earlier.notna() & later.notna()
    violations_mask = both_present & (earlier > later)
    violations = int(violations_mask.sum())
    sample = df[violations_mask][[earlier_col, later_col]].head(3).to_dict("records")
    return CheckResult(
        name=name,
        total_checked=int(both_present.sum()),
        violations=violations,
        success=violations == 0,
        sample_violations=sample,
    )


def check_fk_integrity(
    child_df: pd.DataFrame,
    child_col: str,
    parent_df: pd.DataFrame,
    parent_col: str,
    name: str | None = None,
) -> CheckResult:
    """Every value of child_col must exist in parent_df[parent_col]."""
    name = name or f"FK {child_col} -> {parent_col}"
    parent_set = set(parent_df[parent_col].dropna().unique())
    child_values = child_df[child_col].dropna()
    orphan_mask = ~child_values.isin(parent_set)
    violations = int(orphan_mask.sum())
    sample = child_values[orphan_mask].head(3).tolist()
    return CheckResult(
        name=name,
        total_checked=len(child_values),
        violations=violations,
        success=violations == 0,
        sample_violations=sample,
    )


def check_orders_have_items(
    orders_df: pd.DataFrame, order_items_df: pd.DataFrame
) -> CheckResult:
    """Every order must have at least one row in order_items.

    Orders without items can't contribute to GMV calculations.
    """
    orders_with_items = set(order_items_df["order_id"].unique())
    all_orders = orders_df["order_id"]
    no_items_mask = ~all_orders.isin(orders_with_items)
    violations = int(no_items_mask.sum())
    sample = all_orders[no_items_mask].head(3).tolist()
    return CheckResult(
        name="orders have at least one item",
        total_checked=len(all_orders),
        violations=violations,
        success=violations == 0,
        sample_violations=sample,
    )


def run_all_checks(tables: dict[str, pd.DataFrame]) -> list[CheckResult]:
    """Run all custom checks against a dict of raw tables."""
    results: list[CheckResult] = []

    # Conditional checks
    results.append(
        check_conditional_not_null(
            tables["orders"], "order_status", "delivered", "order_delivered_customer_date"
        )
    )
    results.append(
        check_conditional_not_null(
            tables["orders"], "order_status", "delivered", "order_delivered_carrier_date"
        )
    )

    # Date order checks
    orders = tables["orders"]
    results.append(check_date_order(orders, "order_purchase_timestamp", "order_approved_at"))
    results.append(
        check_date_order(orders, "order_approved_at", "order_delivered_carrier_date")
    )
    results.append(
        check_date_order(
            orders, "order_delivered_carrier_date", "order_delivered_customer_date"
        )
    )

    # FK integrity
    results.append(
        check_fk_integrity(tables["orders"], "customer_id", tables["customers"], "customer_id")
    )
    results.append(
        check_fk_integrity(tables["order_items"], "order_id", tables["orders"], "order_id")
    )
    results.append(
        check_fk_integrity(
            tables["order_items"], "product_id", tables["products"], "product_id"
        )
    )
    results.append(
        check_fk_integrity(
            tables["order_items"], "seller_id", tables["sellers"], "seller_id"
        )
    )

    # Completeness
    results.append(check_orders_have_items(tables["orders"], tables["order_items"]))

    return results


def summarize_results(results: list[CheckResult]) -> pd.DataFrame:
    """Convert a list of CheckResult to a summary DataFrame for reporting."""
    return pd.DataFrame(
        [
            {
                "check": r.name,
                "total": r.total_checked,
                "violations": r.violations,
                "pass_rate_%": round(r.success_rate * 100, 2),
                "status": "PASS" if r.success else "FAIL",
            }
            for r in results
        ]
    )

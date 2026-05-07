"""
spis/models/inventory_kpi.py
------------------------------
Inventory turnover ratio KPI.

Turnover = units sold in period / average on-hand inventory.
Average inventory is approximated by the current stock level in
atc_inventory (the only stock snapshot this system maintains).

Classification thresholds:
    Slow      < 4    -- excess stock; capital tied up
    Low       4-6    -- below optimal; review order frequency
    Healthy   6-12   -- normal pharmacy range
    High      12-24  -- fast mover; watch for stockouts
    Excessive > 24   -- extremely fast; increase safety stock
"""

import sqlite3
from pathlib import Path


def compute_turnover(
    db_path: str | Path, period_days: int = 365
) -> dict[str, dict]:
    """
    Compute inventory turnover ratio for every ATC code in atc_inventory.

    Formula:  turnover = units_sold_in_period / avg_inventory
    avg_inventory is the current_stock value from atc_inventory.

    Args:
        db_path    : Path to the SQLite database.
        period_days: Look-back window in days (default 365).

    Returns:
        Dict keyed by atc_code. Each value is a dict with:
            units_sold     (float) -- total units sold in the window
            avg_inventory  (float) -- current stock used as proxy
            turnover       (float) -- ratio; 0.0 when inventory is zero
            classification (str)  -- Slow | Low | Healthy | High | Excessive
    """
    db_path = Path(db_path)
    cutoff = f"-{period_days} days"

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        sales_rows = conn.execute(
            """
            SELECT atc_code, COALESCE(SUM(quantity), 0.0) AS units_sold
            FROM   sales
            WHERE  granularity = 'daily'
              AND  date(sale_date) >= date('now', ?)
            GROUP  BY atc_code
            """,
            (cutoff,),
        ).fetchall()

        inv_rows = conn.execute(
            "SELECT atc_code, current_stock FROM atc_inventory"
        ).fetchall()

    sales_map = {row["atc_code"]: float(row["units_sold"]) for row in sales_rows}
    result = {}

    for row in inv_rows:
        code = row["atc_code"]
        avg_inv = float(row["current_stock"])
        sold = sales_map.get(code, 0.0)

        turnover = round(sold / avg_inv, 2) if avg_inv > 0 else 0.0

        result[code] = {
            "units_sold": sold,
            "avg_inventory": avg_inv,
            "turnover": turnover,
            "classification": _classify(turnover),
        }

    return result


def _classify(turnover: float) -> str:
    """Return the turnover classification label for a given ratio."""
    if turnover < 4:
        return "Slow"
    if turnover < 6:
        return "Low"
    if turnover <= 12:
        return "Healthy"
    if turnover <= 24:
        return "High"
    return "Excessive"

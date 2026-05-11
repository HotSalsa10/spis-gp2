"""Inventory turnover = units_sold / current_stock."""

import sqlite3
from pathlib import Path


def compute_turnover(
    db_path: str | Path, period_days: int = 365
) -> dict[str, dict]:
    """Per-ATC turnover ratio + Slow/Low/Healthy/High/Excessive label."""
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
    if turnover < 4:
        return "Slow"
    if turnover < 6:
        return "Low"
    if turnover <= 12:
        return "Healthy"
    if turnover <= 24:
        return "High"
    return "Excessive"

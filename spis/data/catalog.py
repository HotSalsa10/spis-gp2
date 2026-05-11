"""Drug/ATC catalog helpers. Used by CLI + Page 7."""

import sqlite3
from pathlib import Path


def _infer_levels(code: str) -> tuple[str, str]:
    """Pull level 1 (1 char) and level 2 (3 chars) from an ATC code."""
    code = code.strip().upper()
    level1 = code[0] if len(code) >= 1 else ""
    level2 = code[:3] if len(code) >= 3 else code
    return level1, level2


def add_atc_code(
    db_path: str | Path,
    code: str,
    name: str,
    system: str = "",
    level1: str = "",
    level2: str = "",
    initial_stock: float = 0.0,
) -> bool:
    """Returns False if already registered."""
    if not code or not code.strip():
        raise ValueError("ATC code cannot be empty.")
    if not name or not name.strip():
        raise ValueError("ATC name cannot be empty.")

    atc_code = code.strip().upper()
    inferred1, inferred2 = _infer_levels(atc_code)
    l1 = level1.strip().upper() if level1 else inferred1
    l2 = level2.strip().upper() if level2 else inferred2
    sys_name = system.strip() if system else f"Unknown system ({l1})"

    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        existing = conn.execute(
            "SELECT atc_name FROM atc_categories WHERE atc_code = ?",
            (atc_code,),
        ).fetchone()
        if existing:
            return False

        conn.execute(
            "INSERT INTO atc_categories "
            "(atc_code, atc_name, system_name, level1_code, level2_code) "
            "VALUES (?, ?, ?, ?, ?)",
            (atc_code, name.strip(), sys_name, l1, l2),
        )
        conn.execute(
            "INSERT OR IGNORE INTO atc_inventory "
            "(atc_code, current_stock, notes) VALUES (?, ?, ?)",
            (atc_code, initial_stock, "Registered via catalog.py"),
        )
        conn.commit()

    return True


def add_drug(
    db_path: str | Path,
    drug_name: str,
    atc_code: str,
    unit: str = "tablets",
    is_critical: int = 0,
) -> None:
    if not drug_name or not drug_name.strip():
        raise ValueError("Drug name cannot be empty.")

    drug_name = drug_name.strip()
    atc_code  = atc_code.strip().upper()
    is_critical = 1 if is_critical else 0

    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        atc_row = conn.execute(
            "SELECT atc_code FROM atc_categories WHERE atc_code = ?",
            (atc_code,),
        ).fetchone()
        if atc_row is None:
            raise ValueError(f"ATC code not registered: {atc_code}")

        dup = conn.execute(
            "SELECT drug_id FROM drugs WHERE drug_name = ?",
            (drug_name,),
        ).fetchone()
        if dup is not None:
            raise ValueError(f"Drug already exists: {drug_name}")

        conn.execute(
            "INSERT INTO drugs (drug_name, atc_code, unit, is_critical) VALUES (?, ?, ?, ?)",
            (drug_name, atc_code, unit, is_critical),
        )
        conn.commit()


def list_atc_codes(db_path: str | Path) -> list[dict]:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT c.atc_code,
                      c.atc_name,
                      c.system_name,
                      COUNT(d.drug_id)            AS drug_count,
                      COALESCE(i.current_stock, 0) AS current_stock
               FROM atc_categories c
               LEFT JOIN drugs d       ON c.atc_code = d.atc_code
               LEFT JOIN atc_inventory i ON c.atc_code = i.atc_code
               GROUP BY c.atc_code
               ORDER BY c.atc_code"""
        ).fetchall()
    return [dict(r) for r in rows]


def list_drugs(db_path: str | Path) -> list[dict]:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT d.drug_id, d.drug_name, d.atc_code,
                      c.atc_name, d.unit, d.is_critical
               FROM drugs d
               JOIN atc_categories c ON d.atc_code = c.atc_code
               ORDER BY d.atc_code, d.drug_name"""
        ).fetchall()
    return [dict(r) for r in rows]

"""
scripts/register_atc.py
-----------------------
Register a new ATC drug category into the SPIS database.

Run this before ingesting sales data that contains an ATC code not already
in the database (e.g. when onboarding a new pharmacy with different drugs).

What it does:
  1. Inserts a row into atc_categories (name, body system, level codes).
  2. Inserts a row into atc_inventory with the given initial stock level.

Safe to re-run — uses INSERT OR IGNORE so existing codes are never overwritten.

Usage
-----
  # Register a new code with full metadata:
  python scripts/register_atc.py \\
      --code A10BA \\
      --name "Biguanides" \\
      --system "Alimentary tract and metabolism" \\
      --level1 A \\
      --level2 A10 \\
      --stock 200.0

  # Minimal — only code and name required; levels inferred from the code:
  python scripts/register_atc.py --code A10BA --name "Biguanides" --stock 150.0

  # List all currently registered ATC codes:
  python scripts/register_atc.py --list
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the project root importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from spis.data.database import init_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_codes(db_path: Path) -> None:
    """Print a table of all registered ATC codes."""
    if not db_path.exists():
        print(f"[register] Database not found: {db_path}")
        print("[register] Run python scripts/ingest_data.py or ingest_kaggle.py first.")
        sys.exit(1)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT c.atc_code, c.atc_name, c.system_name, "
            "       COALESCE(i.current_stock, 0.0) "
            "FROM atc_categories c "
            "LEFT JOIN atc_inventory i ON c.atc_code = i.atc_code "
            "ORDER BY c.atc_code"
        ).fetchall()

    if not rows:
        print("[register] No ATC codes registered yet.")
        return

    print(f"\n{'CODE':<10} {'NAME':<40} {'SYSTEM':<35} {'STOCK':>8}")
    print("-" * 97)
    for code, name, system, stock in rows:
        print(f"{code:<10} {name:<40} {system:<35} {stock:>8.1f}")
    print(f"\n{len(rows)} code(s) registered.")


def _infer_levels(code: str) -> tuple[str, str]:
    """
    Infer WHO ATC level-1 and level-2 codes from the full ATC code.

    ATC codes follow a structured pattern:
        A          -> level 1 (anatomical main group, 1 letter)
        A10        -> level 2 (therapeutic main group, 3 chars)
        A10B       -> level 3
        A10BA      -> level 4 (chemical subgroup)
        A10BA02    -> level 5 (substance)

    We only need levels 1 and 2 for the atc_categories table.
    """
    code = code.strip().upper()
    level1 = code[0] if len(code) >= 1 else ""
    level2 = code[:3] if len(code) >= 3 else code
    return level1, level2


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SPIS — Register a new ATC drug category"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all registered ATC codes and exit.",
    )
    parser.add_argument(
        "--code",
        help="ATC code to register (e.g. A10BA).",
    )
    parser.add_argument(
        "--name",
        help="Short descriptive name (e.g. 'Biguanides').",
    )
    parser.add_argument(
        "--system", default="",
        help="Body system / anatomical group (e.g. 'Alimentary tract and metabolism').",
    )
    parser.add_argument(
        "--level1",
        help="Level-1 ATC code (single letter). Inferred from --code if not given.",
    )
    parser.add_argument(
        "--level2",
        help="Level-2 ATC code (3 chars). Inferred from --code if not given.",
    )
    parser.add_argument(
        "--stock", type=float, default=0.0,
        help="Initial stock level (default: 0.0).",
    )
    parser.add_argument(
        "--db", default="data/inventory.db",
        help="Path to the SQLite database (default: data/inventory.db).",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.list:
        _list_codes(db_path)
        return

    # Validate required args
    if not args.code:
        parser.error("--code is required unless --list is used.")
    if not args.name:
        parser.error("--name is required unless --list is used.")

    atc_code = args.code.strip().upper()

    # Infer level codes if not supplied
    inferred1, inferred2 = _infer_levels(atc_code)
    level1 = args.level1.strip().upper() if args.level1 else inferred1
    level2 = args.level2.strip().upper() if args.level2 else inferred2

    system = args.system or f"Unknown system ({level1})"

    print("=" * 60)
    print("SPIS ATC Code Registration")
    print("=" * 60)
    print(f"  Code    : {atc_code}")
    print(f"  Name    : {args.name}")
    print(f"  System  : {system}")
    print(f"  Level 1 : {level1}")
    print(f"  Level 2 : {level2}")
    print(f"  Stock   : {args.stock:.1f}")
    print(f"  DB      : {db_path}")
    print()

    # Ensure DB schema exists before we try to insert
    init_db(db_path)
    print()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # Check if already registered
        existing = conn.execute(
            "SELECT atc_name FROM atc_categories WHERE atc_code = ?", (atc_code,)
        ).fetchone()

        if existing:
            print(
                f"[register] '{atc_code}' is already registered as '{existing[0]}'.\n"
                "[register] No changes made.  Use a direct SQL UPDATE to rename it."
            )
            return

        # Insert into atc_categories
        conn.execute(
            "INSERT INTO atc_categories "
            "(atc_code, atc_name, system_name, level1_code, level2_code) "
            "VALUES (?, ?, ?, ?, ?)",
            (atc_code, args.name, system, level1, level2),
        )

        # Insert into atc_inventory
        conn.execute(
            "INSERT OR IGNORE INTO atc_inventory "
            "(atc_code, current_stock, notes) VALUES (?, ?, ?)",
            (atc_code, args.stock, "Registered via register_atc.py"),
        )

        conn.commit()

    print(f"[register] '{atc_code}' registered successfully.")
    print(
        "\nNext steps:\n"
        f"  1. Ingest historical sales data:\n"
        f"         python scripts/ingest_data.py --csv path/to/sales.csv\n"
        f"  2. Rebuild the feature pipeline:\n"
        f"         python scripts/run_pipeline.py\n"
        f"  3. Retrain the XGBoost model (required when new ATC codes are added):\n"
        f"         python scripts/train_model.py\n"
    )


if __name__ == "__main__":
    main()

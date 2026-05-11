"""
scripts/register_atc.py
-----------------------
Register a new ATC drug category into the SPIS database.

Run this before ingesting sales data that contains an ATC code not already
in the database (e.g. when onboarding a new pharmacy with different drugs).

What it does:
  1. Inserts a row into atc_categories (name, body system, level codes).
  2. Inserts a row into atc_inventory with the given initial stock level.

Safe to re-run -- idempotent if the code is already registered.

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

  # Minimal -- only code and name required; levels inferred from the code:
  python scripts/register_atc.py --code A10BA --name "Biguanides" --stock 150.0

  # List all currently registered ATC codes:
  python scripts/register_atc.py --list
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from spis.data.catalog import add_atc_code  # noqa: E402
from spis.data.database import init_db       # noqa: E402


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SPIS -- Register a new ATC drug category"
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

    print("=" * 60)
    print("SPIS ATC Code Registration")
    print("=" * 60)
    print(f"  Code    : {atc_code}")
    print(f"  Name    : {args.name}")
    print(f"  System  : {args.system or '(will be inferred)'}")
    print(f"  Level 1 : {args.level1 or '(will be inferred)'}")
    print(f"  Level 2 : {args.level2 or '(will be inferred)'}")
    print(f"  Stock   : {args.stock:.1f}")
    print(f"  DB      : {db_path}")
    print()

    init_db(db_path)
    print()

    inserted = add_atc_code(
        db_path=db_path,
        code=atc_code,
        name=args.name,
        system=args.system,
        level1=args.level1 or "",
        level2=args.level2 or "",
        initial_stock=args.stock,
    )

    if not inserted:
        print(
            f"[register] '{atc_code}' is already registered.\n"
            "[register] No changes made. Use a direct SQL UPDATE to rename it."
        )
        return

    print(f"[register] '{atc_code}' registered successfully.")
    print(
        "\nNext steps:\n"
        "  1. Ingest historical sales data:\n"
        "         python scripts/ingest_data.py --csv path/to/sales.csv\n"
        "  2. Rebuild the feature pipeline:\n"
        "         python scripts/run_pipeline.py\n"
        "  3. Retrain the XGBoost model (required when new ATC codes are added):\n"
        "         python scripts/train_model.py\n"
    )


if __name__ == "__main__":
    main()

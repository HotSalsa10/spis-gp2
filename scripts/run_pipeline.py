"""
scripts/run_pipeline.py
-----------------------
Run the SPIS Phase 2 data pipeline: extract daily sales from the database,
engineer time-series features, split train/test, and write CSVs to data/processed/.

Prerequisites
-------------
  1. Run scripts/ingest_kaggle.py first to populate data/inventory.db.
  2. Activate the virtual environment.

Usage
-----
  python scripts/run_pipeline.py
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the project root importable so we can use spis.*
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from spis.data.pipeline import run_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DB_PATH    = PROJECT_ROOT / "data" / "inventory.db"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run 'python scripts/ingest_kaggle.py' first to create it.")
        sys.exit(1)

    run_pipeline(DB_PATH, OUTPUT_DIR)

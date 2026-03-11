"""
scripts/train_model.py
----------------------
CLI entry point for Phase 3: trains the XGBoost demand forecaster,
compares against baselines, and saves artifacts to models/.

Prerequisites
-------------
  1. Run scripts/run_pipeline.py first to generate train/test CSVs.
  2. Activate the virtual environment.

Usage:
    python scripts/train_model.py
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the project root importable so we can use spis.*
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from spis.models.forecaster import train_and_evaluate  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TRAIN_PATH = PROJECT_ROOT / "data" / "processed" / "train.csv"
TEST_PATH  = PROJECT_ROOT / "data" / "processed" / "test.csv"
OUTPUT_DIR = PROJECT_ROOT / "models"


if __name__ == "__main__":
    if not TRAIN_PATH.exists() or not TEST_PATH.exists():
        print("ERROR: train.csv / test.csv not found in data/processed/")
        print("Run 'python scripts/run_pipeline.py' first.")
        sys.exit(1)

    train_and_evaluate(TRAIN_PATH, TEST_PATH, OUTPUT_DIR)

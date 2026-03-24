"""
scripts/assess_risk.py
-----------------------
Phase 4 CLI: run risk classification and order-quantity recommendations.

Loads the trained XGBoost model + encoder (Phase 3 artifacts), reads the
feature-engineered CSV (Phase 2 output), and current stock levels from the
SQLite database (atc_inventory table), then prints a risk tier report and
writes results to data/processed/risk_assessment.csv.

Usage:
    python scripts/assess_risk.py
    python scripts/assess_risk.py --db data/inventory.db
                                  --features data/processed/features_daily.csv
                                  --models models
                                  --output data/processed/risk_assessment.csv
                                  --safety-days 3
"""

import argparse
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from spis.models.forecaster import load_model
from spis.models.risk_classifier import assess_from_features, load_atc_inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SPIS Phase 4 -- Risk Classification & Order Recommendations"
    )
    parser.add_argument(
        "--db",
        default="data/inventory.db",
        help="Path to the SQLite inventory database (default: data/inventory.db)",
    )
    parser.add_argument(
        "--features",
        default="data/processed/features_daily.csv",
        help="Path to the feature-engineered daily CSV (default: data/processed/features_daily.csv)",
    )
    parser.add_argument(
        "--models",
        default="models",
        help="Directory containing xgboost_forecaster.joblib and label_encoder.joblib (default: models)",
    )
    parser.add_argument(
        "--output",
        default="data/processed/risk_assessment.csv",
        help="Output CSV path for risk assessment results (default: data/processed/risk_assessment.csv)",
    )
    parser.add_argument(
        "--safety-days",
        type=float,
        default=3.0,
        help="Safety buffer in days for order qty calculation (default: 3.0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    db_path       = Path(args.db)
    features_path = Path(args.features)
    models_dir    = Path(args.models)
    output_path   = Path(args.output)

    print("=" * 60)
    print("SPIS Risk Classifier -- Phase 4")
    print("=" * 60)

    # Validate input paths
    for path, label in [(db_path, "database"), (features_path, "features CSV")]:
        if not path.exists():
            print(f"[ERROR] {label} not found: {path}")
            print("  Run scripts/ingest_kaggle.py and scripts/run_pipeline.py first.")
            sys.exit(1)

    for filename in ("xgboost_forecaster.joblib", "label_encoder.joblib"):
        if not (models_dir / filename).exists():
            print(f"[ERROR] Model artifact not found: {models_dir / filename}")
            print("  Run scripts/train_model.py first.")
            sys.exit(1)

    # Load artifacts
    print("\n[1/3] Loading model artifacts ...")
    model, encoder = load_model(models_dir)
    print(f"  Model   : {models_dir / 'xgboost_forecaster.joblib'}")
    print(f"  Encoder : {models_dir / 'label_encoder.joblib'}")
    print(f"  Classes : {list(encoder.classes_)}")

    # Load current stock levels
    print("\n[2/3] Loading inventory stock levels ...")
    inventory = load_atc_inventory(db_path)
    for atc_code, stock in sorted(inventory.items()):
        print(f"  {atc_code:<8}  {stock:>8.1f} units")

    # Run assessment
    print("\n[3/3] Assessing risk and forecasting orders ...")
    print()
    results = assess_from_features(
        features_csv=features_path,
        inventory=inventory,
        model=model,
        encoder=encoder,
        safety_days=args.safety_days,
        output_csv=output_path,
    )

    print(f"Done. {len(results)} ATC codes assessed.")


if __name__ == "__main__":
    main()

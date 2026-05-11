
import argparse
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spis.api.app import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SPIS Phase 5 -- Flask REST API Server"
    )
    parser.add_argument("--host",  default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port",  default=5000, type=int, help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    parser.add_argument("--db",      default="data/inventory.db",
                        help="SQLite inventory database path")
    parser.add_argument("--features", default="data/processed/features_daily.csv",
                        help="Feature CSV path")
    parser.add_argument("--models",   default="models",
                        help="Directory with xgboost_forecaster.joblib + label_encoder.joblib")
    parser.add_argument("--safety-days", type=float, default=3.0,
                        help="Safety buffer days for order qty (default: 3.0)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("SPIS REST API -- Phase 5")
    print("=" * 60)
    print(f"  DB            : {args.db}")
    print(f"  Features CSV  : {args.features}")
    print(f"  Models dir    : {args.models}")
    print(f"  Safety days   : {args.safety_days}")
    print(f"  Server        : http://{args.host}:{args.port}")
    print()

    app = create_app({
        "DB_PATH":       args.db,
        "FEATURES_PATH": args.features,
        "MODELS_DIR":    args.models,
        "SAFETY_DAYS":   args.safety_days,
    })

    if app.config.get("_MODEL") is None:
        print("[WARN] Model artifacts not found -- /api/v1/risk and /api/v1/forecast will return 503.")
        print("       Run scripts/train_model.py first.")
        print()

    print("[INFO] Endpoints:")
    print("       GET /health")
    print("       GET /api/v1/risk")
    print("       GET /api/v1/forecast/<atc_code>")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

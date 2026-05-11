
import argparse
import subprocess
import sys
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "spis" / "dashboard" / "app.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the SPIS Streamlit dashboard.")
    parser.add_argument("--port", type=int, default=8501, help="Port (default: 8501)")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(APP_PATH),
        "--server.port", str(args.port),
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()

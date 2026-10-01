"""Run the project CLI from the existing .venv without installing the project."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from k2_261b.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

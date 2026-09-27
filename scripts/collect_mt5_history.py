"""Read-only MT5 candle download; see xaupy_engine.history_collect."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from xaupy_engine.history_collect import main

if __name__ == "__main__":
    main()

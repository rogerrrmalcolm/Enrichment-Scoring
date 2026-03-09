from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import AppSettings
from src.api import create_app
from src.utils.logging import configure_logging


def main() -> int:
    settings = AppSettings.from_root(ROOT)
    configure_logging(settings.log_dir)
    try:
        import uvicorn
    except ImportError:
        print("FastAPI server dependencies are missing. Install 'fastapi' and 'uvicorn' first.")
        return 1

    app = create_app(settings)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

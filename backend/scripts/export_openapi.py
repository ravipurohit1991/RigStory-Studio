from __future__ import annotations

import json
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "frontend" / "src" / "api" / "generated" / "openapi.json"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    OUTPUT_PATH.write_text(
        f"{json.dumps(schema, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

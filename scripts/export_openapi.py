#!/usr/bin/env python3
"""Export the OpenAPI spec from the FastAPI app without triggering lifespan.

Usage:
    python scripts/export_openapi.py          # writes to openapi.json
    python scripts/export_openapi.py --check  # exits 1 if spec differs from openapi.json
"""

import json
import sys
from pathlib import Path

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.projects import router as projects_router

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "openapi.json"


def build_spec_app() -> FastAPI:
    """Create a minimal FastAPI app (no lifespan) just for OpenAPI generation."""
    app = FastAPI(
        title="tgram-analytics",
        description=(
            "Self-hosted, privacy-first analytics platform "
            "controlled entirely through a Telegram bot."
        ),
        version="0.1.0",
    )
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(ingestion_router)
    return app


def main() -> None:
    check_mode = "--check" in sys.argv

    app = build_spec_app()
    spec = app.openapi()
    spec_json = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if check_mode:
        if not SPEC_PATH.exists():
            print(f"ERROR: {SPEC_PATH} does not exist. Run without --check first.")
            sys.exit(1)
        existing = SPEC_PATH.read_text()
        if existing != spec_json:
            print("ERROR: openapi.json is out of date. Regenerate with:")
            print("  python scripts/export_openapi.py")
            sys.exit(1)
        print("openapi.json is up to date.")
    else:
        SPEC_PATH.write_text(spec_json)
        print(f"Wrote {SPEC_PATH}")


if __name__ == "__main__":
    main()

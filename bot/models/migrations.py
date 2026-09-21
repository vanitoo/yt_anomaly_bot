"""Synchronous Alembic runner shared by Telegram and standalone web modes."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def run_migrations(database_url: str) -> None:
    project_root = Path(__file__).resolve().parents[2]
    ini_path = project_root / "alembic.ini"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    logger.info("Applying Alembic migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ini_path), "upgrade", "head"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        logger.error("Alembic migration failed: %s", result.stderr)
        raise RuntimeError(f"Alembic migration failed: {result.stderr}")
    logger.info("Alembic migrations applied successfully.")

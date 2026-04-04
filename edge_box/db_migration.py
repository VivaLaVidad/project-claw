from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger("claw.edge.migration")


def run_migrations() -> None:
    """启动时执行 Alembic 迁移。"""
    edge_dir = Path(__file__).resolve().parent
    alembic_ini = edge_dir / "alembic.ini"

    if not alembic_ini.exists():
        logger.warning("[Migration] alembic.ini 不存在，跳过迁移")
        return

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(edge_dir / "migrations"))
    db_path = os.getenv("EDGE_DB_PATH", str(edge_dir / "edge_data.db"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{Path(db_path).resolve()}")

    logger.info("[Migration] upgrading head db=%s", db_path)
    command.upgrade(cfg, "head")
    logger.info("[Migration] done")

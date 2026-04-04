from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable

import requests

logger = logging.getLogger("claw.edge.health")


class HealthMonitor:
    def __init__(
        self,
        *,
        tracked_paths: list[str],
        state_db_path: str = "./edge_box/edge_data.db",
        cloud_version_url: str = "",
        check_interval_sec: int = 24 * 3600,
        incremental_sync_callback: Callable[[str, str], None] | None = None,
    ):
        self.tracked_paths = tracked_paths
        self.state_db_path = Path(state_db_path)
        self.cloud_version_url = cloud_version_url
        self.check_interval_sec = check_interval_sec
        self.incremental_sync_callback = incremental_sync_callback
        self._init_state_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.state_db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init_state_db(self) -> None:
        self.state_db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS data_sync_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    local_md5 TEXT NOT NULL,
                    cloud_version TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            c.commit()

    def _compute_local_md5(self) -> str:
        md5 = hashlib.md5()
        for p in self.tracked_paths:
            path = Path(p)
            if not path.exists():
                continue
            md5.update(path.name.encode("utf-8"))
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    md5.update(chunk)
        return md5.hexdigest()

    def _fetch_cloud_version(self) -> tuple[str, str]:
        if not self.cloud_version_url:
            return "", ""
        resp = requests.get(self.cloud_version_url, timeout=8)
        resp.raise_for_status()
        data = resp.json() or {}
        return str(data.get("version", "")), str(data.get("md5", ""))

    def _load_state(self) -> tuple[str, str]:
        with self._conn() as c:
            row = c.execute("SELECT local_md5, cloud_version FROM data_sync_state WHERE id=1").fetchone()
            if not row:
                return "", ""
            return str(row[0]), str(row[1])

    def _save_state(self, local_md5: str, cloud_version: str) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO data_sync_state(id, local_md5, cloud_version, updated_at)
                VALUES(1,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    local_md5=excluded.local_md5,
                    cloud_version=excluded.cloud_version,
                    updated_at=excluded.updated_at
                """,
                (local_md5, cloud_version, time.time()),
            )
            c.commit()

    def check_once(self) -> None:
        local_md5 = self._compute_local_md5()
        cloud_version, cloud_md5 = self._fetch_cloud_version()

        prev_local_md5, prev_cloud_version = self._load_state()
        mismatch = bool(cloud_md5 and local_md5 != cloud_md5)
        version_changed = bool(cloud_version and cloud_version != prev_cloud_version)

        if mismatch or version_changed:
            logger.warning(
                "[HealthMonitor] data mismatch detected local=%s cloud=%s version=%s",
                local_md5,
                cloud_md5,
                cloud_version,
            )
            if self.incremental_sync_callback:
                self.incremental_sync_callback(cloud_version, cloud_md5)

        self._save_state(local_md5=local_md5, cloud_version=cloud_version or prev_cloud_version)

    def run_forever(self) -> None:
        while True:
            try:
                self.check_once()
            except Exception as e:
                logger.error("[HealthMonitor] check failed: %s", e)
            time.sleep(self.check_interval_sec)

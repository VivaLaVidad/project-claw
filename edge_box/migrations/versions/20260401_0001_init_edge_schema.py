from __future__ import annotations

from alembic import op

revision = "20260401_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS verifiable_reasoning_logs (
            log_id TEXT PRIMARY KEY,
            trade_id TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            signature_b64 TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            record_hash TEXT NOT NULL,
            verify_code TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_vrl_trade_id ON verifiable_reasoning_logs(trade_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            local_md5 TEXT NOT NULL,
            cloud_version TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_sync_state")
    op.execute("DROP TABLE IF EXISTS verifiable_reasoning_logs")

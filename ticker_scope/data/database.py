from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "ticker_scope.sqlite3"
CURRENT_SCHEMA_VERSION = 5


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS symbols (
      ticker TEXT PRIMARY KEY,
      name TEXT,
      exchange TEXT,
      currency TEXT,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_prices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticker TEXT NOT NULL,
      price_date TEXT NOT NULL,
      interval TEXT NOT NULL DEFAULT '1d',
      open REAL,
      high REAL,
      low REAL,
      close REAL NOT NULL,
      volume INTEGER,
      adjusted INTEGER NOT NULL DEFAULT 1,
      source TEXT NOT NULL DEFAULT 'yfinance',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE (ticker, price_date, interval, adjusted),
      FOREIGN KEY (ticker) REFERENCES symbols(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      event_date TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT 'manual',
      ticker TEXT,
      lower_window INTEGER NOT NULL DEFAULT 0,
      upper_window INTEGER NOT NULL DEFAULT 0,
      source TEXT NOT NULL DEFAULT 'manual',
      notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (ticker) REFERENCES symbols(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT NOT NULL,
      ticker TEXT,
      period TEXT,
      interval TEXT,
      status TEXT NOT NULL,
      row_count INTEGER NOT NULL DEFAULT 0,
      message TEXT,
      started_at TEXT NOT NULL,
      finished_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticker TEXT NOT NULL,
      strategy TEXT NOT NULL,
      period TEXT,
      interval TEXT NOT NULL DEFAULT '1d',
      adjusted INTEGER NOT NULL DEFAULT 1,
      train_ratio REAL,
      horizons TEXT,
      rolling_windows INTEGER,
      min_train_rows INTEGER,
      interval_width REAL NOT NULL,
      use_events INTEGER NOT NULL DEFAULT 0,
      event_count INTEGER NOT NULL DEFAULT 0,
      row_count INTEGER NOT NULL DEFAULT 0,
      data_start_date TEXT,
      data_end_date TEXT,
      status TEXT NOT NULL,
      message TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY (ticker) REFERENCES symbols(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_metrics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL,
      horizon_days INTEGER,
      cutoff_date TEXT,
      train_start_date TEXT,
      train_end_date TEXT,
      test_start_date TEXT,
      test_end_date TEXT,
      test_rows INTEGER NOT NULL DEFAULT 0,
      mae REAL,
      rmse REAL,
      mape REAL,
      coverage REAL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fear_greed_index (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT NOT NULL,
      index_date TEXT NOT NULL,
      value REAL NOT NULL,
      classification TEXT,
      raw_timestamp INTEGER,
      notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE (source, index_date)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_date
    ON daily_prices (ticker, price_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_ticker_date
    ON events (ticker, event_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fear_greed_index_date
    ON fear_greed_index (index_date)
    """,
]


MIGRATIONS = [
    Migration(version=1, name="baseline_schema", statements=()),
    Migration(
        version=2,
        name="storage_stability_indexes",
        statements=(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_prices_lookup
            ON daily_prices (ticker, interval, adjusted, price_date)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sync_runs_ticker_started
            ON sync_runs (ticker, started_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sync_runs_status_started
            ON sync_runs (status, started_at)
            """,
        ),
    ),
    Migration(
        version=3,
        name="backtest_result_storage",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticker TEXT NOT NULL,
              strategy TEXT NOT NULL,
              period TEXT,
              interval TEXT NOT NULL DEFAULT '1d',
              adjusted INTEGER NOT NULL DEFAULT 1,
              train_ratio REAL,
              horizons TEXT,
              rolling_windows INTEGER,
              min_train_rows INTEGER,
              interval_width REAL NOT NULL,
              use_events INTEGER NOT NULL DEFAULT 0,
              event_count INTEGER NOT NULL DEFAULT 0,
              row_count INTEGER NOT NULL DEFAULT 0,
              data_start_date TEXT,
              data_end_date TEXT,
              status TEXT NOT NULL,
              message TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (ticker) REFERENCES symbols(ticker)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS backtest_metrics (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              horizon_days INTEGER,
              cutoff_date TEXT,
              train_start_date TEXT,
              train_end_date TEXT,
              test_start_date TEXT,
              test_end_date TEXT,
              test_rows INTEGER NOT NULL DEFAULT 0,
              mae REAL,
              rmse REAL,
              mape REAL,
              coverage REAL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_backtest_runs_ticker_created
            ON backtest_runs (ticker, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_backtest_metrics_run_horizon
            ON backtest_metrics (run_id, horizon_days)
            """,
        ),
    ),
    Migration(
        version=4,
        name="backtest_date_policy",
        statements=(
            """
            ALTER TABLE backtest_runs
            ADD COLUMN date_policy TEXT NOT NULL DEFAULT 'us_stock_market'
            """,
        ),
    ),
    Migration(
        version=5,
        name="fear_greed_index_storage",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS fear_greed_index (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              index_date TEXT NOT NULL,
              value REAL NOT NULL,
              classification TEXT,
              raw_timestamp INTEGER,
              notes TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE (source, index_date)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_fear_greed_index_date
            ON fear_greed_index (index_date)
            """,
        ),
    ),
]


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path).expanduser()

    configured = os.getenv("TICKER_SCOPE_DB_PATH")
    if configured:
        return Path(configured).expanduser()

    return DB_PATH


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    resolved_path = resolve_db_path(db_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved_path, factory=ManagedConnection)
    connection.row_factory = sqlite3.Row
    _configure_connection(connection)
    return connection


def init_database(db_path: Path | str | None = None) -> Path:
    resolved_path = resolve_db_path(db_path)
    with get_connection(resolved_path) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        _apply_migrations(connection)
        connection.commit()
    return resolved_path


def get_schema_version(db_path: Path | str | None = None) -> int:
    with get_connection(db_path) as connection:
        row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")


def _apply_migrations(connection: sqlite3.Connection) -> None:
    applied_versions = {
        int(row["version"])
        for row in connection.execute("SELECT version FROM schema_migrations")
    }

    for migration in MIGRATIONS:
        if migration.version in applied_versions:
            continue

        for statement in migration.statements:
            connection.execute(statement)

        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (migration.version, migration.name, _utc_now()),
        )

    connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

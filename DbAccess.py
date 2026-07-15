import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("ember.db")
SCHEMA_PATH = Path("db_sql/sql.sql")

def connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        logger.info("[Server - connect] Successfully connected to database")
        logger.info("[Server - connect] using db at %s", Path(DB_PATH).resolve())
    except sqlite3.OperationalError as e:
        logger.error(f"[Server - connect] Failed to connect to the database: {e}")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def get_db():
    """FastAPI dependency: one connection per request, closed afterward."""
    conn = connect()
    try:
        # pauses the function, allowing the conn object to stay live until it's done with
        yield conn
    except sqlite3.OperationalError as e:
        logger.error(f"[Server - get_db] Connecting to database failed {json.dumps(e)}")
        raise
    finally:
        conn.close()

def init_db() -> None:
    """Create tables if they don't exist. Safe to run on every startup."""
    sql = SCHEMA_PATH.read_text()

    conn = connect()
    try:
        conn.executescript(sql)
        conn.commit()
        logger.info("[Server - init_db] Schema applied to %s", DB_PATH)
    finally:
        conn.close()
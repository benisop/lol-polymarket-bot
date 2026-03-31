"""
database.py — Modelos SQLite y helpers para el Bot D.

Tablas:
    signals   → señales detectadas (timestamp, market, edge, side, size)
    trades    → órdenes ejecutadas (order_id, resultado, P&L)
    games     → caché de gameId por slug (evita llamadas repetidas)
    positions → posiciones abiertas actuales

Motor: sqlite3 estándar de Python (sin ORM externo).
"""

import sqlite3
import logging
from datetime import datetime
from backend.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Retorna conexión SQLite con row_factory para acceso por nombre."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crea todas las tablas si no existen."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            market_slug TEXT    NOT NULL,
            team1       TEXT,
            team2       TEXT,
            edge        REAL    NOT NULL,
            side        TEXT    NOT NULL,
            size_usd    REAL    NOT NULL,
            p_model     REAL,
            p_market    REAL,
            dry_run     INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id   INTEGER REFERENCES signals(id),
            order_id    TEXT,
            timestamp   TEXT    NOT NULL,
            market_slug TEXT    NOT NULL,
            side        TEXT    NOT NULL,
            size_usd    REAL    NOT NULL,
            fill_price  REAL,
            outcome     TEXT,   -- 'win' | 'loss' | 'open'
            pnl_usd     REAL,
            dry_run     INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS games (
            slug        TEXT PRIMARY KEY,
            game_id     TEXT NOT NULL,
            league      TEXT,
            team1       TEXT,
            team2       TEXT,
            game_date   TEXT,
            cached_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id    INTEGER REFERENCES trades(id),
            market_slug TEXT    NOT NULL UNIQUE,
            side        TEXT    NOT NULL,
            size_usd    REAL    NOT NULL,
            opened_at   TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'open'  -- 'open' | 'closed'
        );
    """)

    conn.commit()
    conn.close()
    logger.info("Base de datos inicializada en %s", DB_PATH)


# ── Helpers signals ───────────────────────────────────────────────────────────

def save_signal(
    market_slug: str, edge: float, side: str, size_usd: float,
    p_model: float, p_market: float, team1: str = "", team2: str = "",
    dry_run: bool = True,
) -> int:
    """Guarda una señal detectada. Retorna el id insertado."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO signals
            (timestamp, market_slug, team1, team2, edge, side, size_usd,
             p_model, p_market, dry_run)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(), market_slug, team1, team2,
        edge, side, size_usd, p_model, p_market, int(dry_run),
    ))
    conn.commit()
    signal_id = cur.lastrowid
    conn.close()
    return signal_id


# ── Helpers games cache ───────────────────────────────────────────────────────

def get_cached_game_id(slug: str) -> str | None:
    """Retorna gameId cacheado o None si no existe."""
    conn = get_connection()
    row = conn.execute(
        "SELECT game_id FROM games WHERE slug = ?", (slug,)
    ).fetchone()
    conn.close()
    return row["game_id"] if row else None


def cache_game_id(slug: str, game_id: str, league: str = "",
                  team1: str = "", team2: str = "", game_date: str = "") -> None:
    """Guarda o actualiza el gameId para un slug dado."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO games (slug, game_id, league, team1, team2, game_date, cached_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            game_id=excluded.game_id, cached_at=excluded.cached_at
    """, (slug, game_id, league, team1, team2, game_date,
          datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


# ── Helpers trades / P&L ─────────────────────────────────────────────────────

def get_todays_pnl() -> float:
    """Retorna el P&L neto de trades cerrados hoy."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(pnl_usd), 0) as total
        FROM trades
        WHERE timestamp LIKE ? AND outcome IN ('win','loss')
    """, (f"{today}%",)).fetchone()
    conn.close()
    return float(row["total"])


def count_open_positions() -> int:
    """Cuenta posiciones actualmente abiertas."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM positions WHERE status='open'"
    ).fetchone()
    conn.close()
    return row["cnt"]

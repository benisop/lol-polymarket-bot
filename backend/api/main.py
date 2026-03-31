"""
api/main.py — FastAPI del Bot D.

Endpoints:
    GET /health          → status del bot
    GET /api/stats       → bankroll, trades hoy, win rate, P&L
    GET /api/trades      → últimos 50 trades con resultado
    GET /api/signals     → últimas 50 señales detectadas
    GET /api/positions   → posiciones abiertas actuales

Ejecución:
    uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
"""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import (
    DRY_RUN, BANKROLL, MIN_EDGE_THRESHOLD,
    MAX_POSITION_SIZE_USD, MIN_MARKET_LIQUIDITY,
)
from backend.database import get_connection, init_db

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bot D — LoL Polymarket Trading Bot",
    description=(
        "Bot de trading automatizado para mercados de League of Legends "
        "en Polymarket. Usa modelo de Regresión Logística con datos del min 15."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Bot D API arrancada | DRY_RUN=%s", DRY_RUN)


# ── /health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Status básico del bot."""
    from pathlib import Path
    from backend.config import MODEL_PATH

    model_ready = Path(MODEL_PATH).exists()
    return {
        "status":      "ok",
        "dry_run":     DRY_RUN,
        "model_ready": model_ready,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }


# ── /api/stats ────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """
    Retorna métricas actuales del bot:
        - bankroll inicial y P&L del día
        - número de trades hoy
        - win rate histórico
        - posiciones abiertas
        - configuración de riesgo
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn  = get_connection()

    # Trades de hoy
    trades_today = conn.execute("""
        SELECT COUNT(*) as cnt, COALESCE(SUM(pnl_usd), 0) as pnl
        FROM trades
        WHERE timestamp LIKE ? AND dry_run = ?
    """, (f"{today}%", int(DRY_RUN))).fetchone()

    # Win rate histórico
    wr = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins
        FROM trades
        WHERE outcome IN ('win','loss') AND dry_run = ?
    """, (int(DRY_RUN),)).fetchone()

    # P&L total
    pnl_total = conn.execute("""
        SELECT COALESCE(SUM(pnl_usd), 0) as total
        FROM trades WHERE outcome IN ('win','loss') AND dry_run = ?
    """, (int(DRY_RUN),)).fetchone()

    # Señales de hoy
    signals_today = conn.execute("""
        SELECT COUNT(*) as cnt FROM signals WHERE timestamp LIKE ?
    """, (f"{today}%",)).fetchone()

    # Posiciones abiertas
    open_pos = conn.execute(
        "SELECT COUNT(*) as cnt FROM positions WHERE status='open'"
    ).fetchone()

    conn.close()

    total_trades = wr["total"] or 0
    wins         = wr["wins"]  or 0
    win_rate     = wins / total_trades if total_trades > 0 else None

    return {
        "mode":         "DRY_RUN" if DRY_RUN else "LIVE",
        "bankroll":     BANKROLL,
        "pnl_today":    round(trades_today["pnl"], 2),
        "pnl_total":    round(float(pnl_total["total"]), 2),
        "trades_today": trades_today["cnt"],
        "signals_today": signals_today["cnt"],
        "win_rate":     round(win_rate, 3) if win_rate else None,
        "total_trades": total_trades,
        "open_positions": open_pos["cnt"],
        "config": {
            "min_edge_threshold":   MIN_EDGE_THRESHOLD,
            "max_position_usd":     MAX_POSITION_SIZE_USD,
            "min_market_liquidity": MIN_MARKET_LIQUIDITY,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── /api/trades ───────────────────────────────────────────────────────────────

@app.get("/api/trades")
def get_trades(limit: int = 50, offset: int = 0):
    """Últimos N trades con resultado y P&L."""
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit máximo: 200")

    conn = get_connection()
    rows = conn.execute("""
        SELECT
            t.id, t.timestamp, t.market_slug, t.side,
            t.size_usd, t.fill_price, t.outcome, t.pnl_usd,
            t.order_id, t.dry_run,
            s.edge, s.p_model, s.p_market, s.team1, s.team2
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        ORDER BY t.timestamp DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()

    return {
        "trades": [dict(r) for r in rows],
        "count":  len(rows),
        "limit":  limit,
        "offset": offset,
    }


# ── /api/signals ──────────────────────────────────────────────────────────────

@app.get("/api/signals")
def get_signals(limit: int = 50, offset: int = 0):
    """Últimas N señales detectadas (con y sin trade ejecutado)."""
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit máximo: 200")

    conn = get_connection()
    rows = conn.execute("""
        SELECT id, timestamp, market_slug, team1, team2,
               edge, side, size_usd, p_model, p_market, dry_run
        FROM signals
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()

    return {
        "signals": [dict(r) for r in rows],
        "count":   len(rows),
    }


# ── /api/positions ────────────────────────────────────────────────────────────

@app.get("/api/positions")
def get_positions():
    """Posiciones abiertas actuales."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.market_slug, p.side, p.size_usd, p.opened_at,
               t.order_id, t.fill_price
        FROM positions p
        LEFT JOIN trades t ON p.trade_id = t.id
        WHERE p.status = 'open'
        ORDER BY p.opened_at DESC
    """).fetchall()
    conn.close()

    return {
        "positions": [dict(r) for r in rows],
        "count":     len(rows),
    }


# ── /api/markets (live) ───────────────────────────────────────────────────────

@app.get("/api/markets")
def get_active_markets():
    """Mercados LoL LCK/LEC activos en Polymarket en este momento."""
    try:
        from backend.polymarket.markets import get_lol_markets
        markets = get_lol_markets()
        return {
            "markets": markets,
            "count":   len(markets),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("Error obteniendo mercados: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

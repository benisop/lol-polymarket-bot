"""
scheduler.py — Loop principal del Bot D. Orquesta todos los módulos.

Ciclo cada 5 minutos:
    1. Mercados LEC/LCK activos de Polymarket
    2. slug → gameId → stats min15 → P(win) → edge → trade
    3. Revisar posiciones abiertas
    4. Stop-loss diario

Ejecución:
    python -m backend.scheduler
"""

import logging
import time
import sqlite3
from datetime import datetime, timezone

from backend.config import (
    DRY_RUN, BANKROLL, MIN_EDGE_THRESHOLD,
    MAX_POSITION_SIZE_USD, STOP_LOSS_PCT,
    MAX_OPEN_POSITIONS, SCHEDULER_INTERVAL_SECONDS, DB_PATH,
)
from backend.database import (
    init_db, save_signal, count_open_positions,
    get_todays_pnl, get_connection,
)
from backend.telegram_bot import (
    notify_signal, notify_trade, notify_stop_loss, notify_error,
)

logger = logging.getLogger(__name__)

# ── Estado global de sesión ────────────────────────────────────────────────────
_stop_loss_triggered = False
_processed_markets: set[str] = set()   # slugs ya operados en la sesión


# ── Helpers ────────────────────────────────────────────────────────────────────

def _already_positioned(slug: str) -> bool:
    """True si ya tenemos posición abierta en este mercado."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM positions WHERE market_slug=? AND status='open'",
        (slug,),
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def _save_trade(signal_id: int, order_id: str, market_slug: str,
                side: str, size_usd: float, dry_run: bool) -> int:
    """Persiste un trade ejecutado y abre la posición."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trades
            (signal_id, order_id, timestamp, market_slug, side, size_usd, outcome, dry_run)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
    """, (signal_id, order_id, datetime.utcnow().isoformat(),
          market_slug, side, size_usd, int(dry_run)))
    trade_id = cur.lastrowid

    cur.execute("""
        INSERT OR IGNORE INTO positions
            (trade_id, market_slug, side, size_usd, opened_at, status)
        VALUES (?, ?, ?, ?, ?, 'open')
    """, (trade_id, market_slug, side, size_usd,
          datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return trade_id


def _settle_finished_games() -> None:
    """
    Revisa posiciones abiertas y registra resultado si el partido terminó.
    Actualiza outcome y P&L en la tabla trades.
    """
    from backend.data.lolesports_api import get_live_stats
    from backend.database import get_cached_game_id

    conn = get_connection()
    positions = conn.execute(
        "SELECT * FROM positions WHERE status='open'"
    ).fetchall()
    conn.close()

    for pos in positions:
        slug = pos["market_slug"]
        game_id = get_cached_game_id(slug)
        if not game_id:
            continue

        stats = get_live_stats(game_id)
        if not stats:
            continue

        if stats["game_state"] != "finished":
            continue

        # Partido terminado → determinar ganador y P&L
        # (La lógica exacta depende de los datos del mercado al cerrar)
        logger.info("Partido terminado para %s — cerrando posición.", slug)
        conn = get_connection()
        conn.execute("""
            UPDATE positions SET status='closed' WHERE market_slug=?
        """, (slug,))
        conn.execute("""
            UPDATE trades SET outcome='closed' WHERE market_slug=? AND outcome='open'
        """, (slug,))
        conn.commit()
        conn.close()


# ── Ciclo principal ────────────────────────────────────────────────────────────

def _run_cycle() -> dict:
    """
    Ejecuta un ciclo completo del bot.
    Retorna stats del ciclo para logging.
    """
    from backend.polymarket.markets import get_lol_markets
    from backend.data.game_mapper import get_game_id
    from backend.data.lolesports_api import extract_minute15_stats
    from backend.model.predict import predict_win_probability, ModelNotFoundError
    from backend.polymarket.trader import execute_signal

    cycle_stats = {
        "markets_checked": 0,
        "games_mapped":    0,
        "stats_available": 0,
        "signals":         0,
        "trades":          0,
        "errors":          0,
    }

    # ── 0. Refrescar cache de partidos en vivo (1 sola llamada HTTP por ciclo)
    from backend.data.game_mapper import refresh_live_cache
    refresh_live_cache()

    # ── 1. Mercados activos ────────────────────────────────────────────────────
    markets = get_lol_markets()
    cycle_stats["markets_checked"] = len(markets)

    if not markets:
        logger.info("Sin mercados LoL LCK/LEC activos en Polymarket.")
        return cycle_stats

    logger.info("Ciclo: %d mercados activos.", len(markets))

    # ── 2. Procesar cada mercado ───────────────────────────────────────────────
    for market in markets:
        slug = market["slug"]

        try:
            # No abrir posición duplicada en el mismo mercado
            if _already_positioned(slug):
                logger.debug("Ya posicionados en %s — skip.", slug)
                continue

            # Límite de posiciones simultáneas
            if count_open_positions() >= MAX_OPEN_POSITIONS:
                logger.info("Máximo de posiciones abiertas (%d). Esperando.",
                            MAX_OPEN_POSITIONS)
                break

            # ── a. slug → gameId ───────────────────────────────────────────
            game_id = get_game_id(slug)
            if not game_id:
                logger.debug("No se encontró gameId para: %s", slug)
                continue
            cycle_stats["games_mapped"] += 1

            # ── b. Stats del minuto 15 ─────────────────────────────────────
            features = extract_minute15_stats(game_id)
            if not features:
                logger.debug("Stats min15 no disponibles para gameId %s", game_id)
                continue
            cycle_stats["stats_available"] += 1

            # ── c. Predicción del modelo ───────────────────────────────────
            try:
                p_model = predict_win_probability(features)
            except ModelNotFoundError:
                logger.error("model.pkl no encontrado — ejecutar train_model.py")
                notify_error("predict", "model.pkl no encontrado")
                return cycle_stats

            p_market = market["prices"][0] if market.get("prices") else None
            if p_market is None:
                continue

            edge = abs(p_model - p_market)

            logger.info(
                "%s | P_modelo=%.2f P_mercado=%.2f edge=%.2f%%",
                slug, p_model, p_market, edge * 100,
            )

            # ── d. Evaluar edge ────────────────────────────────────────────
            if edge < MIN_EDGE_THRESHOLD:
                continue
            cycle_stats["signals"] += 1

            # Determinar equipos desde el slug para notificación
            from backend.data.game_mapper import parse_slug
            parsed   = parse_slug(slug) or {}
            team1    = parsed.get("team1", "Equipo A")
            team2    = parsed.get("team2", "Equipo B")
            league   = parsed.get("league", "LCK/LEC")
            side_str = "YES" if p_model > p_market else "NO"

            from backend.polymarket.trader import kelly_size, determine_side
            side, p_adj, pm_adj = determine_side(p_model, p_market)
            size_usd = kelly_size(p_adj, pm_adj)

            # Guardar señal en DB
            signal_id = save_signal(
                market_slug=slug, edge=edge, side=side,
                size_usd=size_usd, p_model=p_model, p_market=p_market,
                team1=team1, team2=team2, dry_run=DRY_RUN,
            )

            # Notificar Telegram
            notify_signal(
                team1=team1, team2=team2, league=league,
                edge=edge, side=side, size_usd=size_usd,
                p_model=p_model, p_market=p_market, dry_run=DRY_RUN,
            )

            # ── e. Ejecutar trade ──────────────────────────────────────────
            result = execute_signal(market, p_model=p_model, dry_run=DRY_RUN)
            if result and result.get("order_id"):
                trade_id = _save_trade(
                    signal_id=signal_id,
                    order_id=result["order_id"],
                    market_slug=slug,
                    side=side,
                    size_usd=size_usd,
                    dry_run=DRY_RUN,
                )
                notify_trade(
                    order_id=result["order_id"],
                    market_slug=slug,
                    side=side,
                    size_usd=size_usd,
                    dry_run=DRY_RUN,
                )
                cycle_stats["trades"] += 1
                logger.info(
                    "[TRADE] %s | %s | $%.2f | edge=%.2f%% | dry=%s",
                    slug, side, size_usd, edge * 100, DRY_RUN,
                )

        except Exception as exc:
            cycle_stats["errors"] += 1
            logger.error("Error procesando mercado %s: %s", slug, exc, exc_info=True)
            notify_error("scheduler", f"{slug}: {str(exc)[:200]}")

    # ── 3. Revisar posiciones abiertas ─────────────────────────────────────────
    try:
        _settle_finished_games()
    except Exception as exc:
        logger.error("Error en settle_finished_games: %s", exc)

    return cycle_stats


def _check_stop_loss() -> bool:
    """
    Verifica stop-loss diario.
    Retorna True si se debe pausar el bot.
    """
    global _stop_loss_triggered
    if _stop_loss_triggered:
        return True

    daily_pnl = get_todays_pnl()
    stop_loss_limit = -BANKROLL * STOP_LOSS_PCT

    if daily_pnl < stop_loss_limit:
        logger.critical(
            "STOP-LOSS: P&L del día $%.2f < límite $%.2f",
            daily_pnl, stop_loss_limit,
        )
        notify_stop_loss(abs(daily_pnl), BANKROLL)
        _stop_loss_triggered = True
        return True

    return False


# ── Entry point ────────────────────────────────────────────────────────────────

def run(max_cycles: int | None = None) -> None:
    """
    Loop principal del bot.

    Args:
        max_cycles: Número máximo de ciclos (None = infinito).
                    Útil para tests: run(max_cycles=1).
    """
    global _stop_loss_triggered
    _stop_loss_triggered = False

    logger.info("=" * 60)
    logger.info("Bot D arrancando | DRY_RUN=%s | bankroll=$%.0f",
                DRY_RUN, BANKROLL)
    logger.info("Edge mínimo: %.0f%% | Max posición: $%.0f",
                MIN_EDGE_THRESHOLD * 100, MAX_POSITION_SIZE_USD)
    logger.info("Intervalo: %ds | Stop-loss: %.0f%%",
                SCHEDULER_INTERVAL_SECONDS, STOP_LOSS_PCT * 100)
    logger.info("=" * 60)

    # Inicializar DB
    init_db()

    cycle = 0
    while True:
        cycle += 1
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        logger.info("=== Ciclo #%d (%s) ===", cycle, now)

        # Stop-loss check
        if _check_stop_loss():
            logger.critical("Stop-loss activo. Bot pausado.")
            break

        # Ejecutar ciclo
        try:
            stats = _run_cycle()
            logger.info(
                "Ciclo #%d completado | mercados=%d mapeados=%d "
                "stats=%d señales=%d trades=%d errores=%d",
                cycle,
                stats["markets_checked"], stats["games_mapped"],
                stats["stats_available"], stats["signals"],
                stats["trades"], stats["errors"],
            )
        except Exception as exc:
            logger.error("Error fatal en ciclo #%d: %s", cycle, exc, exc_info=True)
            notify_error("scheduler_loop", str(exc)[:300])

        # Condición de salida para tests
        if max_cycles and cycle >= max_cycles:
            logger.info("max_cycles=%d alcanzado. Saliendo.", max_cycles)
            break

        # Esperar hasta el próximo ciclo
        logger.info("Proximo ciclo en %ds...", SCHEDULER_INTERVAL_SECONDS)
        time.sleep(SCHEDULER_INTERVAL_SECONDS)


if __name__ == "__main__":
    import sys
    # Forzar UTF-8 en la consola Windows (cp1252 no soporta caracteres especiales)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            stream_handler,
            logging.FileHandler("bot_d.log", encoding="utf-8"),
        ],
    )
    run()

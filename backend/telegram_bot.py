"""
telegram_bot.py — Notificaciones vía Telegram para el Bot D.

Mensajes enviados:
    - Señal detectada: equipos, edge, lado, tamaño, modo DRY_RUN.
    - Trade ejecutado: confirmación con order_id.
    - Stop-loss activado: alerta crítica.
    - Error crítico de módulo.

Uso:
    from backend.telegram_bot import notify, notify_signal, notify_error
"""

import logging
import requests
from backend.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def notify(message: str) -> bool:
    """Envía mensaje de texto plano a Telegram. Retorna True si OK."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram no configurado, mensaje omitido: %s", message)
        return False
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Error enviando Telegram: %s", exc)
        return False


def notify_signal(
    team1: str, team2: str, league: str,
    edge: float, side: str, size_usd: float,
    p_model: float, p_market: float,
    dry_run: bool = True,
) -> None:
    """Notifica una señal de trading detectada."""
    mode = "🟡 DRY RUN" if dry_run else "🟢 LIVE"
    msg = (
        f"{mode} | <b>SEÑAL BOT D</b>\n"
        f"⚔️  {team1} vs {team2} ({league})\n"
        f"📊  Modelo: {p_model:.1%} | Mercado: {p_market:.1%}\n"
        f"📈  Edge: <b>{edge:.1%}</b> → {side}\n"
        f"💵  Tamaño: ${size_usd:.2f} USDC"
    )
    notify(msg)


def notify_trade(order_id: str, market_slug: str, side: str,
                 size_usd: float, dry_run: bool = True) -> None:
    """Notifica trade ejecutado."""
    mode = "DRY RUN" if dry_run else "EJECUTADO"
    msg = (
        f"✅ <b>TRADE {mode}</b>\n"
        f"Mercado: {market_slug}\n"
        f"Lado: {side} | ${size_usd:.2f}\n"
        f"Order ID: {order_id or 'N/A'}"
    )
    notify(msg)


def notify_stop_loss(daily_loss: float, bankroll: float) -> None:
    """Alerta crítica de stop-loss."""
    msg = (
        f"🔴 <b>STOP-LOSS ACTIVADO</b>\n"
        f"Pérdida del día: ${daily_loss:.2f} ({daily_loss/bankroll:.1%} del bankroll)\n"
        f"Bot pausado. Revisión manual necesaria."
    )
    notify(msg)


def notify_error(module: str, error: str) -> None:
    """Notifica error crítico de un módulo."""
    msg = f"❌ <b>ERROR en {module}</b>\n<code>{error[:500]}</code>"
    notify(msg)

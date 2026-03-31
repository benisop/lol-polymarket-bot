"""
trader.py — Ejecuta órdenes en Polymarket usando py-clob-client SDK oficial.

NO implementa EIP-712 manual. Usa ClobClient del SDK.
En DRY_RUN=true: loguea la orden sin ejecutar nada.
"""

import logging
from functools import lru_cache

from backend.config import (
    DRY_RUN,
    POLYMARKET_PRIVATE_KEY,
    POLYMARKET_PROXY_ADDRESS,
    BANKROLL,
    MAX_POSITION_SIZE_USD,
    KELLY_FRACTION,
    MIN_EDGE_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Polygon chain ID (Polymarket opera en Polygon mainnet)
POLYGON_CHAIN_ID = 137


# ── Cliente CLOB ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client():
    """
    Inicializa y cachea el ClobClient del SDK oficial.
    Lanza ImportError si py-clob-client no está instalado.
    Lanza ValueError si las credenciales no están configuradas.
    """
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.constants import POLYGON
    except ImportError as e:
        raise ImportError(
            "py-clob-client no instalado. Ejecuta: pip install py-clob-client"
        ) from e

    if not POLYMARKET_PRIVATE_KEY:
        raise ValueError(
            "POLYMARKET_PRIVATE_KEY no configurada. "
            "Revisa tu .env. (DRY_RUN=true no requiere clave real)"
        )

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=POLYMARKET_PRIVATE_KEY,
        chain_id=POLYGON_CHAIN_ID,
        signature_type=2,           # EIP-712 (proxy wallet)
        funder=POLYMARKET_PROXY_ADDRESS or None,
    )
    logger.info("ClobClient inicializado (proxy=%s)", POLYMARKET_PROXY_ADDRESS)
    return client


# ── Kelly fraccionado ──────────────────────────────────────────────────────────

def kelly_size(
    p_model: float,
    p_market: float,
    bankroll: float = BANKROLL,
    kelly_fraction: float = KELLY_FRACTION,
    max_size: float = MAX_POSITION_SIZE_USD,
) -> float:
    """
    Calcula el tamaño óptimo de posición con Kelly fraccionado.

    Fórmula Kelly para mercados binarios:
        b = (1 / p_market) - 1   ← odds netas
        f = (b * p_model - (1 - p_model)) / b
        size = f * kelly_fraction * bankroll

    Args:
        p_model:       Probabilidad del modelo P(win).
        p_market:      Precio actual en Polymarket (≈ probabilidad implícita).
        bankroll:      Capital total disponible.
        kelly_fraction: Fracción de Kelly (0.25 = 25%).
        max_size:      Tamaño máximo en USD.

    Returns:
        Tamaño en USD, capped en max_size. 0 si Kelly es negativo.
    """
    if p_market <= 0 or p_market >= 1:
        return 0.0

    b = (1.0 / p_market) - 1.0          # odds netas
    f = (b * p_model - (1.0 - p_model)) / b   # fracción Kelly

    if f <= 0:
        logger.debug("Kelly negativo (f=%.4f) — no operar.", f)
        return 0.0

    raw_size = f * kelly_fraction * bankroll
    size = min(raw_size, max_size)
    logger.debug(
        "Kelly: p_model=%.3f p_market=%.3f b=%.3f f=%.4f "
        "raw=$%.2f → size=$%.2f",
        p_model, p_market, b, f, raw_size, size,
    )
    return round(size, 2)


def determine_side(p_model: float, p_market: float) -> tuple[str, float, float]:
    """
    Determina qué lado comprar según el modelo.

    Si p_model > p_market → modelo cree que el YES está subvalorado → BUY YES
    Si p_model < p_market → modelo cree que el NO está subvalorado  → BUY NO

    Returns:
        (side, p_model_adj, p_market_adj)
        side: "YES" o "NO"
        p_model_adj:  probabilidad del modelo para el lado elegido
        p_market_adj: precio de mercado para el lado elegido
    """
    if p_model >= p_market:
        return "YES", p_model, p_market
    else:
        # Comprar NO → P(NO) = 1 - P(YES)
        return "NO", 1.0 - p_model, 1.0 - p_market


# ── Órdenes ────────────────────────────────────────────────────────────────────

def place_market_order(
    token_id: str,
    side: str,
    amount_usdc: float,
    dry_run: bool | None = None,
) -> str | None:
    """
    Coloca una orden de mercado en Polymarket.

    Args:
        token_id:    Token ID del outcome (de get_token_id() en markets.py).
        side:        "BUY" o "SELL".
        amount_usdc: Monto en USDC.
        dry_run:     Override del DRY_RUN global. None usa config.

    Returns:
        order_id como string si se ejecutó, "DRY_RUN_ORDER" en modo dry,
        o None si falló.
    """
    effective_dry_run = DRY_RUN if dry_run is None else dry_run

    if effective_dry_run:
        logger.info(
            "[DRY RUN] Orden simulada: %s $%.2f USDC | token_id=%s",
            side, amount_usdc, token_id,
        )
        return "DRY_RUN_ORDER"

    try:
        from py_clob_client.clob_types import OrderArgs, OrderType, BUY, SELL

        client = _get_client()
        order_side = BUY if side.upper() == "BUY" else SELL

        order_args = OrderArgs(
            token_id=token_id,
            price=None,          # market order
            size=amount_usdc,
            side=order_side,
        )

        resp = client.create_and_post_order(order_args)
        order_id = resp.get("orderID") or resp.get("order_id")
        logger.info(
            "✅ Orden ejecutada: %s $%.2f | token_id=%s | order_id=%s",
            side, amount_usdc, token_id, order_id,
        )
        return str(order_id) if order_id else None

    except Exception as exc:
        error_msg = str(exc)

        if "insufficient" in error_msg.lower():
            logger.error("❌ Fondos insuficientes para orden $%.2f: %s",
                         amount_usdc, exc)
        elif "closed" in error_msg.lower():
            logger.error("❌ Mercado cerrado para token %s: %s", token_id, exc)
        elif "slippage" in error_msg.lower():
            logger.error("❌ Slippage excesivo en orden $%.2f: %s",
                         amount_usdc, exc)
        else:
            logger.error("❌ Error colocando orden: %s", exc)

        return None


def get_position(market_condition_id: str) -> dict:
    """
    Retorna la posición actual en un mercado.

    Args:
        market_condition_id: conditionId del mercado.

    Returns:
        dict con: condition_id, size, avg_price, pnl_usd
        o dict vacío si no hay posición o DRY_RUN.
    """
    if DRY_RUN:
        logger.debug("[DRY RUN] get_position llamado para %s", market_condition_id)
        return {}

    try:
        client = _get_client()
        positions = client.get_positions()
        for pos in (positions or []):
            if pos.get("conditionId") == market_condition_id:
                return {
                    "condition_id": market_condition_id,
                    "size":         float(pos.get("size", 0)),
                    "avg_price":    float(pos.get("avgPrice", 0)),
                    "pnl_usd":      float(pos.get("pnl", 0)),
                }
    except Exception as exc:
        logger.error("Error consultando posición %s: %s", market_condition_id, exc)

    return {}


def execute_signal(
    market: dict,
    p_model: float,
    outcome_index: int = 0,
    dry_run: bool | None = None,
) -> dict | None:
    """
    Función de alto nivel: evalúa edge y ejecuta trade si procede.

    Orquesta: determine_side → kelly_size → place_market_order.

    Args:
        market:        Dict normalizado de markets.get_lol_markets().
        p_model:       P(win) del modelo para el equipo del outcome 0.
        outcome_index: 0 = YES (equipo 1 gana), 1 = NO.
        dry_run:       Override DRY_RUN global.

    Returns:
        dict con {side, size_usd, edge, order_id, p_model, p_market}
        o None si no hay edge suficiente.
    """
    from backend.polymarket.markets import get_market_price, get_token_id

    p_market = get_market_price(market, outcome_index=0)
    if p_market is None:
        logger.warning("Sin precio para mercado: %s", market.get("slug"))
        return None

    side, p_adj, pm_adj = determine_side(p_model, p_market)
    edge = abs(p_adj - pm_adj)

    if edge < MIN_EDGE_THRESHOLD:
        logger.info(
            "Edge %.2f%% < threshold %.2f%% — sin señal para %s",
            edge * 100, MIN_EDGE_THRESHOLD * 100, market.get("slug"),
        )
        return None

    # Token ID según el lado: YES=índice 0, NO=índice 1
    token_idx = 0 if side == "YES" else 1
    token_id  = get_token_id(market, outcome_index=token_idx)
    if not token_id:
        logger.warning("Sin token_id para %s (lado %s)", market.get("slug"), side)
        return None

    size_usd = kelly_size(p_adj, pm_adj)
    if size_usd <= 0:
        return None

    order_id = place_market_order(
        token_id=token_id,
        side="BUY",
        amount_usdc=size_usd,
        dry_run=dry_run,
    )

    return {
        "side":      side,
        "size_usd":  size_usd,
        "edge":      edge,
        "order_id":  order_id,
        "p_model":   p_model,
        "p_market":  p_market,
        "token_id":  token_id,
        "slug":      market.get("slug", ""),
    }


# ── Ejecución directa ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    print("\n─── TEST trader.py ───────────────────────────────────────────")
    print(f"DRY_RUN global: {DRY_RUN}")

    # Test Kelly sizing
    print("\nKelly sizing (p_model=0.72, p_market=0.60, bankroll=$1000):")
    size = kelly_size(p_model=0.72, p_market=0.60, bankroll=1000)
    print(f"  Tamaño calculado: ${size:.2f}")

    # Test determine_side
    side, pa, pm = determine_side(p_model=0.72, p_market=0.60)
    print(f"\nSide: {side} (edge={abs(pa-pm):.2%})")

    # Test DRY_RUN order
    print("\nSimulando orden (DRY_RUN=True):")
    order_id = place_market_order(
        token_id="MOCK_TOKEN_123",
        side="BUY",
        amount_usdc=25.50,
        dry_run=True,
    )
    print(f"  order_id: {order_id}")

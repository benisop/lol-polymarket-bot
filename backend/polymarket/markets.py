"""
markets.py — Consulta Gamma API de Polymarket y filtra mercados LoL LCK/LEC.

Endpoint:
    GET https://gamma-api.polymarket.com/markets
        ?tag_slug=esports&active=true&limit=100
"""

import logging
from datetime import datetime, timezone, timedelta

import requests

from backend.config import MIN_MARKET_LIQUIDITY

logger = logging.getLogger(__name__)

GAMMA_API_URL  = "https://gamma-api.polymarket.com/markets"
CLOB_API_URL   = "https://clob.polymarket.com"
LOL_SLUG_KEYS  = ("lol-lck", "lol-lec")
MIN_CLOSE_MINS = 10   # no operar si cierra en menos de 10 minutos


def _is_lol_market(market: dict) -> bool:
    """True si el slug contiene lol-lck o lol-lec."""
    slug = (market.get("slug") or "").lower()
    return any(key in slug for key in LOL_SLUG_KEYS)


def _minutes_to_close(market: dict) -> float | None:
    """Minutos hasta que cierra el mercado. None si no hay fecha."""
    end_str = market.get("endDate") or market.get("end_date_iso")
    if not end_str:
        return None
    try:
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (end - now).total_seconds() / 60
    except Exception:
        return None


def _parse_market(raw: dict) -> dict:
    """
    Normaliza un market de Gamma API al formato estándar del bot.

    Retorna:
        {
            slug, question, outcomes, prices,
            volume, liquidity, close_time,
            token_ids, condition_id,
            minutes_to_close,
        }
    """
    outcomes = raw.get("outcomes", "[]")
    if isinstance(outcomes, str):
        import json
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []

    prices_raw = raw.get("outcomePrices", "[]")
    if isinstance(prices_raw, str):
        import json
        try:
            prices_raw = json.loads(prices_raw)
        except Exception:
            prices_raw = []

    prices = [float(p) for p in prices_raw] if prices_raw else []

    # token_ids para CLOB (necesario para trader.py)
    clob_token_ids = raw.get("clobTokenIds", "[]")
    if isinstance(clob_token_ids, str):
        import json
        try:
            clob_token_ids = json.loads(clob_token_ids)
        except Exception:
            clob_token_ids = []

    mins = _minutes_to_close(raw)

    return {
        "slug":             raw.get("slug", ""),
        "question":         raw.get("question", ""),
        "condition_id":     raw.get("conditionId", ""),
        "outcomes":         outcomes,
        "prices":           prices,
        "volume":           float(raw.get("volume", 0) or 0),
        "liquidity":        float(raw.get("liquidity", 0) or 0),
        "close_time":       raw.get("endDate") or raw.get("end_date_iso", ""),
        "minutes_to_close": mins,
        "token_ids":        clob_token_ids,
        "active":           bool(raw.get("active", True)),
        "closed":           bool(raw.get("closed", False)),
    }


def _fetch_page(offset: int = 0, limit: int = 100) -> list[dict]:
    """Descarga una página de mercados de Gamma API."""
    try:
        resp = requests.get(
            GAMMA_API_URL,
            params={
                "tag_slug": "esports",
                "active":   "true",
                "limit":    limit,
                "offset":   offset,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # Gamma API puede retornar lista directa o dict con 'markets'
        if isinstance(data, list):
            return data
        return data.get("markets", data.get("results", []))
    except Exception as exc:
        logger.error("Error consultando Gamma API (offset=%d): %s", offset, exc)
        return []


def get_lol_markets(
    min_liquidity: float | None = None,
    min_close_minutes: float = MIN_CLOSE_MINS,
) -> list[dict]:
    """
    Retorna mercados LoL LCK/LEC activos de Polymarket con liquidez suficiente.

    Args:
        min_liquidity:     Liquidez mínima en USD. Default: MIN_MARKET_LIQUIDITY.
        min_close_minutes: Minutos mínimos hasta el cierre. Default: 10.

    Returns:
        Lista de dicts con slug, question, outcomes, prices, volume,
        liquidity, close_time, token_ids, minutes_to_close.
    """
    if min_liquidity is None:
        min_liquidity = MIN_MARKET_LIQUIDITY

    all_markets: list[dict] = []
    offset = 0
    limit  = 100

    # Paginado: máx 500 mercados por seguridad
    while offset < 500:
        page = _fetch_page(offset=offset, limit=limit)
        if not page:
            break
        all_markets.extend(page)
        if len(page) < limit:
            break
        offset += limit

    logger.info("Gamma API: %d mercados totales descargados.", len(all_markets))

    # Filtrar LoL LCK/LEC
    lol_raw = [m for m in all_markets if _is_lol_market(m)]
    logger.info("Mercados LoL LCK/LEC encontrados: %d", len(lol_raw))

    # Parsear y aplicar filtros de riesgo
    result: list[dict] = []
    for raw in lol_raw:
        market = _parse_market(raw)

        if market["closed"]:
            continue
        if market["liquidity"] < min_liquidity:
            logger.debug("Descartado (liquidez $%.0f < $%.0f): %s",
                         market["liquidity"], min_liquidity, market["slug"])
            continue

        mins = market["minutes_to_close"]
        if mins is not None and mins < min_close_minutes:
            logger.debug("Descartado (cierra en %.1f min): %s",
                         mins, market["slug"])
            continue

        result.append(market)

    logger.info(
        "Mercados válidos para operar: %d "
        "(liquidez ≥ $%.0f, cierre ≥ %d min)",
        len(result), min_liquidity, min_close_minutes,
    )
    return result


def get_market_price(market: dict, outcome_index: int = 0) -> float | None:
    """
    Retorna el precio actual de un outcome (0 = YES / equipo 1).

    Args:
        market:        Dict normalizado de get_lol_markets().
        outcome_index: 0 para el primer outcome (YES/team1), 1 para el segundo.

    Returns:
        Float en [0, 1] o None si no hay precio.
    """
    prices = market.get("prices", [])
    if len(prices) > outcome_index:
        return prices[outcome_index]
    return None


def get_token_id(market: dict, outcome_index: int = 0) -> str | None:
    """Retorna el token_id de CLOB para un outcome dado."""
    token_ids = market.get("token_ids", [])
    if len(token_ids) > outcome_index:
        return str(token_ids[outcome_index])
    return None


# ── Ejecución directa ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    markets = get_lol_markets()
    print(f"\n─── MERCADOS LoL LCK/LEC ACTIVOS ({len(markets)}) ────────────")
    if not markets:
        print("No se encontraron mercados activos en este momento.")
        print("(Puede que no haya partidos en curso o Gamma API no responde)")
    else:
        for m in markets:
            mins = m["minutes_to_close"]
            mins_str = f"{mins:.0f}min" if mins else "?"
            prices_str = " / ".join(f"{p:.2f}" for p in m["prices"])
            print(
                f"  [{m['slug'][:50]:<50}] "
                f"liq=${m['liquidity']:>7,.0f} | "
                f"prices={prices_str} | "
                f"cierra en {mins_str}"
            )

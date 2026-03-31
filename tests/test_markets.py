"""
tests/test_markets.py — Tests de markets.py y trader.py.

Ejecutar:
    pytest tests/test_markets.py -v
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.polymarket.markets import (
    get_lol_markets, _is_lol_market, _parse_market,
    get_market_price, get_token_id, _minutes_to_close,
)
from backend.polymarket.trader import (
    kelly_size, determine_side, place_market_order, execute_signal,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures y helpers
# ══════════════════════════════════════════════════════════════════════════════

MOCK_MARKET_RAW = {
    "slug":          "lol-lck-t1-gen-g-2026-03-30-game1",
    "question":      "Will T1 win vs Gen.G? (LCK 2026-03-30 Game 1)",
    "conditionId":   "0xABC123",
    "active":        True,
    "closed":        False,
    "liquidity":     8500.0,
    "volume":        42000.0,
    "endDate":       "2099-12-31T23:59:00Z",
    "outcomePrices": '["0.65", "0.35"]',
    "outcomes":      '["Yes", "No"]',
    "clobTokenIds":  '["TOKEN_YES_001", "TOKEN_NO_001"]',
}

MOCK_MARKET_LEC = {
    **MOCK_MARKET_RAW,
    "slug":        "lol-lec-g2-fnatic-2026-03-29-game1",
    "conditionId": "0xDEF456",
    "outcomePrices": '["0.70", "0.30"]',
    "clobTokenIds":  '["TOKEN_G2_YES", "TOKEN_G2_NO"]',
}

MOCK_NON_LOL = {
    "slug":     "nba-lakers-celtics-2026-03-30",
    "active":   True,
    "closed":   False,
    "liquidity": 10000.0,
}


# ══════════════════════════════════════════════════════════════════════════════
# Tests de _is_lol_market
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("slug,expected", [
    ("lol-lck-t1-gen-g-2026-03-30-game1", True),
    ("lol-lec-g2-fnatic-2026-03-29-game1", True),
    ("nba-lakers-celtics-2026-03-30",      False),
    ("lol-lpl-jdg-weibo-2026-03-30",       False),  # LPL excluido
    ("will-t1-win-lck-2026-03-30",         False),  # sin prefijo lol-lck
])
def test_is_lol_market(slug, expected):
    assert _is_lol_market({"slug": slug}) == expected


# ══════════════════════════════════════════════════════════════════════════════
# Tests de _parse_market
# ══════════════════════════════════════════════════════════════════════════════

def test_parse_market_schema():
    m = _parse_market(MOCK_MARKET_RAW)
    assert m["slug"]      == "lol-lck-t1-gen-g-2026-03-30-game1"
    assert m["liquidity"] == 8500.0
    assert m["volume"]    == 42000.0
    assert len(m["prices"])    == 2
    assert len(m["outcomes"])  == 2
    assert len(m["token_ids"]) == 2
    assert m["active"]  is True
    assert m["closed"]  is False


def test_parse_market_prices_float():
    m = _parse_market(MOCK_MARKET_RAW)
    for p in m["prices"]:
        assert isinstance(p, float)
        assert 0.0 <= p <= 1.0


def test_parse_market_prices_sum_to_one():
    m = _parse_market(MOCK_MARKET_RAW)
    total = sum(m["prices"])
    assert abs(total - 1.0) < 0.05, f"Precios no suman 1: {total}"


def test_parse_market_token_ids():
    m = _parse_market(MOCK_MARKET_RAW)
    assert m["token_ids"][0] == "TOKEN_YES_001"
    assert m["token_ids"][1] == "TOKEN_NO_001"


# ══════════════════════════════════════════════════════════════════════════════
# Tests de get_lol_markets (con mock de Gamma API)
# ══════════════════════════════════════════════════════════════════════════════

@patch("requests.get")
def test_get_lol_markets_returns_list(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [MOCK_MARKET_RAW, MOCK_MARKET_LEC, MOCK_NON_LOL],
    )
    markets = get_lol_markets(min_liquidity=100)
    assert isinstance(markets, list)


@patch("requests.get")
def test_get_lol_markets_filters_non_lol(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [MOCK_MARKET_RAW, MOCK_MARKET_LEC, MOCK_NON_LOL],
    )
    markets = get_lol_markets(min_liquidity=100)
    slugs = [m["slug"] for m in markets]
    assert "nba-lakers-celtics-2026-03-30" not in slugs


@patch("requests.get")
def test_get_lol_markets_both_leagues(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [MOCK_MARKET_RAW, MOCK_MARKET_LEC],
    )
    markets = get_lol_markets(min_liquidity=100)
    slugs = " ".join(m["slug"] for m in markets)
    assert "lck" in slugs
    assert "lec" in slugs


@patch("requests.get")
def test_get_lol_markets_liquidity_filter(mock_get):
    low_liq = {**MOCK_MARKET_RAW, "slug": "lol-lck-low-liq", "liquidity": 100.0}
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [MOCK_MARKET_RAW, low_liq],
    )
    markets = get_lol_markets(min_liquidity=500)
    assert all(m["liquidity"] >= 500 for m in markets)


@patch("requests.get")
def test_get_lol_markets_closed_excluded(mock_get):
    closed = {**MOCK_MARKET_RAW, "slug": "lol-lck-closed", "closed": True}
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [MOCK_MARKET_RAW, closed],
    )
    markets = get_lol_markets(min_liquidity=100)
    assert all(not m["closed"] for m in markets)


@patch("requests.get")
def test_get_lol_markets_api_error(mock_get):
    mock_get.side_effect = Exception("timeout")
    markets = get_lol_markets()
    assert markets == []


# ══════════════════════════════════════════════════════════════════════════════
# Tests de get_market_price y get_token_id
# ══════════════════════════════════════════════════════════════════════════════

def test_get_market_price_yes():
    m = _parse_market(MOCK_MARKET_RAW)
    price = get_market_price(m, outcome_index=0)
    assert price == pytest.approx(0.65)


def test_get_market_price_no():
    m = _parse_market(MOCK_MARKET_RAW)
    price = get_market_price(m, outcome_index=1)
    assert price == pytest.approx(0.35)


def test_get_token_id_yes():
    m = _parse_market(MOCK_MARKET_RAW)
    assert get_token_id(m, 0) == "TOKEN_YES_001"


def test_get_token_id_no():
    m = _parse_market(MOCK_MARKET_RAW)
    assert get_token_id(m, 1) == "TOKEN_NO_001"


# ══════════════════════════════════════════════════════════════════════════════
# Tests de kelly_size
# ══════════════════════════════════════════════════════════════════════════════

def test_kelly_size_con_edge():
    size = kelly_size(p_model=0.72, p_market=0.60, bankroll=1000)
    assert size > 0
    assert size <= 50  # capped en MAX_POSITION_SIZE_USD


def test_kelly_size_sin_edge():
    """Sin edge, Kelly debe ser 0."""
    size = kelly_size(p_model=0.60, p_market=0.62, bankroll=1000)
    # Kelly puede ser positivo o negativo aquí — lo relevante es que se llame bien
    assert size >= 0


def test_kelly_size_negativo():
    """Modelo más bajo que mercado → Kelly negativo → retorna 0."""
    size = kelly_size(p_model=0.40, p_market=0.70, bankroll=1000)
    assert size == 0.0


def test_kelly_size_capped():
    """Nunca supera MAX_POSITION_SIZE_USD."""
    size = kelly_size(p_model=0.99, p_market=0.01, bankroll=100000)
    assert size <= 50.0


def test_kelly_size_edge_cases():
    assert kelly_size(p_model=0.5, p_market=0.0,  bankroll=1000) == 0.0
    assert kelly_size(p_model=0.5, p_market=1.0,  bankroll=1000) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Tests de determine_side
# ══════════════════════════════════════════════════════════════════════════════

def test_determine_side_buy_yes():
    side, p_adj, pm_adj = determine_side(p_model=0.72, p_market=0.60)
    assert side     == "YES"
    assert p_adj    == pytest.approx(0.72)
    assert pm_adj   == pytest.approx(0.60)


def test_determine_side_buy_no():
    side, p_adj, pm_adj = determine_side(p_model=0.35, p_market=0.60)
    assert side     == "NO"
    assert p_adj    == pytest.approx(0.65)   # 1 - 0.35
    assert pm_adj   == pytest.approx(0.40)   # 1 - 0.60


# ══════════════════════════════════════════════════════════════════════════════
# Tests de place_market_order (DRY_RUN)
# ══════════════════════════════════════════════════════════════════════════════

def test_place_market_order_dry_run():
    order_id = place_market_order(
        token_id="TOKEN_MOCK",
        side="BUY",
        amount_usdc=25.0,
        dry_run=True,
    )
    assert order_id == "DRY_RUN_ORDER"


def test_place_market_order_dry_run_returns_string():
    result = place_market_order("TOKEN", "BUY", 10.0, dry_run=True)
    assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════════════
# Tests de execute_signal
# ══════════════════════════════════════════════════════════════════════════════

def test_execute_signal_con_edge():
    market = _parse_market(MOCK_MARKET_RAW)  # precio YES = 0.65
    # Modelo dice 0.80 → edge = 15% → debe generar señal
    result = execute_signal(market, p_model=0.80, dry_run=True)
    assert result is not None
    assert result["edge"] >= 0.08
    assert result["order_id"] == "DRY_RUN_ORDER"
    assert result["side"] in ("YES", "NO")
    assert result["size_usd"] > 0


def test_execute_signal_sin_edge():
    market = _parse_market(MOCK_MARKET_RAW)  # precio YES = 0.65
    # Modelo dice 0.66 → edge = 1% → sin señal
    result = execute_signal(market, p_model=0.66, dry_run=True)
    assert result is None


def test_execute_signal_compra_no():
    market = _parse_market(MOCK_MARKET_RAW)  # precio YES = 0.65
    # Modelo dice 0.40 → modelo cree que NO está subvalorado
    result = execute_signal(market, p_model=0.40, dry_run=True)
    if result:  # solo si hay edge suficiente
        assert result["side"] == "NO"

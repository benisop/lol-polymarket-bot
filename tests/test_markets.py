"""
tests/test_markets.py — Valida que Gamma API devuelve mercados LoL LCK/LEC.

Tests:
    test_returns_list           → get_lol_markets() retorna lista
    test_at_least_one_market    → hay ≥ 1 mercado LCK o LEC activo
    test_market_schema          → cada item tiene slug, prices, liquidity
    test_liquidity_filter       → todos superan MIN_MARKET_LIQUIDITY
"""

"""
markets.py — Consulta Gamma API de Polymarket y filtra mercados LoL LCK/LEC.

Endpoint:
    GET https://gamma-api.polymarket.com/markets
        ?tag_slug=esports&active=true&limit=100

Filtros:
    - slug contiene "lol-lck" o "lol-lec"
    - liquidity >= MIN_MARKET_LIQUIDITY ($500)
    - cierra en > 10 minutos

Retorna lista de dicts:
    {slug, question, outcomes, prices, volume, liquidity, close_time}

Maneja paginación si hay > 100 mercados.
"""

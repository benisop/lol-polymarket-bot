"""
scheduler.py — Loop principal del Bot D. Orquesta todos los módulos.

Ciclo cada 5 minutos:
    1. Obtener mercados LEC/LCK activos de Polymarket (markets.py).
    2. Para cada mercado:
       a. Mapear slug → gameId (game_mapper.py).
       b. Obtener stats minuto 15 (lolesports_api.py).
       c. Predecir P(win) (predict.py).
       d. Calcular edge = |P_modelo - P_polymarket|.
       e. Si edge >= MIN_EDGE_THRESHOLD → sizing Kelly 25% → trade.
    3. Revisar posiciones abiertas → registrar resultado si partido terminó.
    4. Chequear stop-loss diario (15% bankroll) → pausar si se supera.

Ejecución:
    python -m backend.scheduler
"""

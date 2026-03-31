"""
api/main.py — FastAPI del Bot D.

Endpoints:
    GET /api/stats   → bankroll actual, trades hoy, win rate, P&L
    GET /api/trades  → últimos 50 trades con resultado
    GET /health      → status del bot

Ejecución:
    uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
"""

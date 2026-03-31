"""
tests/test_lolesports_api.py — Valida respuesta de la LoL Esports API.

Tests:
    test_api_health             → endpoint responde sin error 5xx
    test_game_state_field       → respuesta contiene campo gameState
    test_minute15_none_early    → retorna None si partido no llegó al min 15
    test_minute15_keys          → dict tiene las 7 variables del modelo
"""

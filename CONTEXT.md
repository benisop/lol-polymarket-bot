# Bot D — LoL Polymarket Trading Bot

## Qué es
Bot de trading automatizado para Polymarket que opera en mercados de
League of Legends (LEC y LCK) usando un modelo de Regresión Logística
entrenado con datos del **minuto 15** de cada partido.

## Estrategia
1. Espera al min 15 para tener datos reales (gold diff, XP, CS, dragones).
2. Compara P(win) del modelo contra el precio actual en Polymarket.
3. Si edge ≥ 8% → trade (Kelly 25%, máx $50 USDC, DRY_RUN=true por defecto).
4. Inspirado en @xsaghav que opera manualmente LEC/LCK con 430 shares fijos.

## Base Académica
**Uppsala University 2026** — predicción del ganador de partidos profesionales
de LoL con datos del minuto 15: **73-78% de accuracy**.
- LCK: ~78% | LEC: ~73%
- Modelo óptimo: **LogisticRegression** (supera RF, SVM, XGBoost)

### Variables del modelo (por importancia)
| Variable | Fórmula | Tipo |
|---|---|---|
| goldrelat15 | golddiffat15 / goldat15 | continua |
| xprelat15 | xpdiffat15 / xpat15 | continua |
| firstdragon | 0 o 1 | binaria |
| csrelat15 | csdiffat15 / csat15 | continua |
| killsrelat15 | kills / (kills + kills_opp) | continua |
| firstblood | 0 o 1 | binaria |
| firstherald | 0 o 1 | binaria |

## Stack Técnico
- Python 3.11 + FastAPI + SQLite
- scikit-learn LogisticRegression → `backend/model/model.pkl`
- py-clob-client SDK (Polymarket)
- Oracle's Elixir CSV (datos históricos 2021-2025)
- feed.lolesports.com (stats en vivo, unofficial API)
- gamma-api.polymarket.com (lectura de mercados)
- Railway (deploy), Telegram (notificaciones)

## Estructura
```
lol-polymarket-bot/
├── backend/
│   ├── model/
│   │   ├── train.py          # entrena + serializa model.pkl
│   │   ├── predict.py        # carga model.pkl → P(win)
│   │   └── model.pkl         # generado por train_model.py
│   ├── data/
│   │   ├── oracle_elixir.py  # datos históricos
│   │   ├── lolesports_api.py # stats en vivo + fallbacks
│   │   └── game_mapper.py    # slug → gameId de Riot
│   ├── polymarket/
│   │   ├── markets.py        # mercados LCK/LEC activos
│   │   └── trader.py         # ejecuta órdenes CLOB
│   ├── api/
│   │   └── main.py           # FastAPI endpoints
│   ├── scheduler.py          # loop principal (cada 5 min)
│   ├── telegram_bot.py       # notificaciones
│   ├── config.py             # variables de entorno
│   └── database.py           # SQLite helpers
├── scripts/
│   └── train_model.py        # ejecutar 1 vez
├── tests/
│   ├── test_model.py
│   ├── test_lolesports_api.py
│   └── test_markets.py
├── CONTEXT.md
├── requirements.txt
├── Procfile
├── railway.json
└── .env.example
```

## IDs de Ligas Riot
- LCK: `98767991310872058`
- LEC: `98767991302996019`

## Horarios (hora Chile)
- LCK: 04:00–10:00
- LEC: 11:00–17:00

## Gestión de Riesgo
| Parámetro | Valor |
|---|---|
| DRY_RUN | `true` siempre hasta validar |
| MIN_EDGE_THRESHOLD | 8% |
| MAX_POSITION_SIZE_USD | $50 |
| MIN_MARKET_LIQUIDITY | $500 |
| KELLY_FRACTION | 25% |
| STOP_LOSS_PCT | 15% del bankroll diario |
| MAX_OPEN_POSITIONS | 3 |
| MAX_GAME_MINUTE | 25 (no operar después) |

## Criterios para pasar a LIVE (todos deben cumplirse)
1. `train.py` logra ≥ 70% accuracy
2. `game_mapper.py` mapea correctamente ≥ 5 slugs de ejemplo
3. `lolesports_api.py` obtiene stats de un partido real activo
4. `markets.py` encuentra ≥ 1 mercado LCK/LEC activo en Polymarket
5. `scheduler.py` corre 30 min en DRY_RUN sin errores
6. ≥ 3 señales detectadas en DRY_RUN

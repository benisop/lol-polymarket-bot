# Bot D — LoL Polymarket Trading Bot
## Estado: COMPLETO — listo para DRY_RUN ✅

---

## Qué es
Bot de trading automatizado para Polymarket que opera mercados de League
of Legends (LEC y LCK) con un modelo de Regresión Logística entrenado
con datos del **minuto 15** de cada partido en vivo.

## Estrategia
1. Detecta mercados LCK/LEC activos en Polymarket (Gamma API).
2. Mapea cada slug al gameId real de Riot (game_mapper.py).
3. Espera al min 15: extrae gold diff, XP, CS, dragones, kills.
4. Predice P(win) con LogisticRegression (73-78% accuracy).
5. Si edge ≥ 8% → Kelly 25% → trade (máx $50 USDC).
6. DRY_RUN=true siempre hasta validar 6 criterios de éxito.

## Base Académica
**Uppsala University 2026** — accuracy 73-78% con datos del min 15.
Modelo: **LogisticRegression** > RF, SVM, XGBoost.

### Variables del modelo (orden de importancia)
| Variable | Fórmula |
|---|---|
| goldrelat15 | golddiffat15 / goldat15 |
| xprelat15 | xpdiffat15 / xpat15 |
| firstdragon | binaria 0/1 |
| csrelat15 | csdiffat15 / csat15 |
| killsrelat15 | kills / (kills + kills_opp) |
| firstblood | binaria 0/1 |
| firstherald | binaria 0/1 |

---

## Stack
- Python 3.11 + FastAPI + SQLite
- scikit-learn LogisticRegression → `backend/model/model.pkl`
- py-clob-client SDK (Polymarket CLOB)
- Oracle's Elixir CSV (históricos 2021-2025, descarga automática S3)
- feed.lolesports.com (stats en vivo, unofficial API)
- gamma-api.polymarket.com (lectura de mercados)
- Railway (deploy web + worker)
- Telegram (notificaciones)

---

## Estructura de archivos

```
lol-polymarket-bot/
├── backend/
│   ├── model/
│   │   ├── train.py          ✅ LR + StandardScaler, split sin leakage
│   │   ├── predict.py        ✅ lru_cache, retorna float [0,1]
│   │   └── model.pkl         ⚙️  generar con: python scripts/train_model.py
│   ├── data/
│   │   ├── oracle_elixir.py  ✅ descarga S3, caché local, 7 variables
│   │   ├── lolesports_api.py ✅ rate limit, retry, ventana [15-25] min
│   │   └── game_mapper.py    ✅ 30+ aliases, Riot API, fallback Leaguepedia
│   ├── polymarket/
│   │   ├── markets.py        ✅ Gamma API paginada, filtros liquidez/cierre
│   │   └── trader.py         ✅ Kelly 25%, SDK, DRY_RUN, execute_signal()
│   ├── api/
│   │   └── main.py           ✅ /health /api/stats /trades /signals /positions
│   ├── scheduler.py          ✅ loop 5min, stop-loss, settle posiciones
│   ├── telegram_bot.py       ✅ señales, trades, stop-loss, errores
│   ├── config.py             ✅ todas las variables de entorno
│   └── database.py           ✅ SQLite: signals, trades, games, positions
├── scripts/
│   └── train_model.py        ✅ CLI con --force
├── tests/
│   ├── test_model.py         ✅ 14 tests accuracy + predict
│   ├── test_lolesports_api.py✅ 16 tests game_mapper + API
│   └── test_markets.py       ✅ 30 tests markets + trader
├── CONTEXT.md                ✅ este archivo
├── DEPLOY.md                 ✅ instrucciones Railway paso a paso
├── requirements.txt          ✅
├── Procfile                  ✅ web + worker
├── railway.json              ✅ healthcheck configurado
├── runtime.txt               ✅ python-3.11.9
└── .env.example              ✅
```

---

## Módulos clave — resumen rápido

### game_mapper.py — el más crítico
```python
from backend.data.game_mapper import get_game_id
game_id = get_game_id("lol-t1-gen-g-2026-03-30-game1")
# → "110853020732646396"
```
Flujo: caché → parse slug → Riot Schedule API → match por equipos+fecha → fallback Leaguepedia → cachear.

### lolesports_api.py
```python
from backend.data.lolesports_api import extract_minute15_stats
features = extract_minute15_stats(game_id)
# → {"goldrelat15": 0.05, "firstdragon": 1, ...} o None
```
Solo retorna datos si el partido está entre el min 15 y 25.

### predict.py
```python
from backend.model.predict import predict_win_probability
p = predict_win_probability(features)  # float [0,1]
```

### trader.py
```python
from backend.polymarket.trader import execute_signal
result = execute_signal(market, p_model=0.75, dry_run=True)
# → {"side": "YES", "size_usd": 32.50, "edge": 0.15, "order_id": "DRY_RUN_ORDER"}
```

---

## Gestión de riesgo
| Parámetro | Valor | Variable |
|---|---|---|
| DRY_RUN | `true` hasta validar | `DRY_RUN` |
| Edge mínimo | 8% | `MIN_EDGE_THRESHOLD` |
| Tamaño máximo | $50 USDC | `MAX_POSITION_SIZE_USD` |
| Liquidez mínima | $500 | `MIN_MARKET_LIQUIDITY` |
| Kelly fraccionado | 25% | `KELLY_FRACTION` |
| Stop-loss diario | 15% del bankroll | `STOP_LOSS_PCT` |
| Max posiciones | 3 simultáneas | `MAX_OPEN_POSITIONS` |
| Ventana operacional | min 15–25 | `MAX_GAME_MINUTE` |

---

## Criterios para pasar a LIVE
- [ ] `train.py` ≥ 70% accuracy global
- [ ] `game_mapper.py` mapea ≥ 5 slugs correctamente
- [ ] `lolesports_api.py` obtiene stats de un partido real activo
- [ ] `markets.py` encuentra ≥ 1 mercado LCK/LEC activo
- [ ] `scheduler.py` corre 30 min en DRY_RUN sin errores
- [ ] ≥ 3 señales detectadas → verificar en `/api/signals`

**→ Solo entonces: `DRY_RUN=false` en Railway.**

---

## Primeros pasos al retomar este proyecto
```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Copiar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 3. Entrenar modelo
python scripts/train_model.py

# 4. Ejecutar tests
pytest tests/ -v

# 5. Probar módulos individuales
python -m backend.data.oracle_elixir
python -m backend.polymarket.markets
python -m backend.data.game_mapper

# 6. Arrancar en DRY_RUN
python -m backend.scheduler

# 7. API en paralelo (otra terminal)
uvicorn backend.api.main:app --reload --port 8000
# → http://localhost:8000/api/stats
# → http://localhost:8000/api/markets
```

---

## IDs de ligas Riot
- LCK: `98767991310872058`
- LEC: `98767991302996019`

## Horarios (Chile)
- LCK: 04:00–10:00
- LEC: 11:00–17:00

## Referencias
- Oracle's Elixir: oracleselixir.com/tools/downloads
- LoL Esports API docs: vickz84259.github.io/lolesports-api-docs
- Polymarket CLOB: py-clob-client docs
- Paper Uppsala: FULLTEXT01.pdf (en Downloads)

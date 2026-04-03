# Bot D — LoL Polymarket Trading Bot

Bot de trading automatizado para Polymarket que opera mercados de **League of Legends LCK/LEC** usando un modelo de Regresión Logística entrenado con datos del minuto 15 de cada partido en vivo.

---

## Cómo arrancarlo (Windows)

```powershell
cd C:\Users\hp\Downloads\lol-polymarket-bot

# Opción 1 — Ver logs en consola (recomendado)
python -m backend.scheduler

# Opción 2 — Background con auto-restart (dejar corriendo toda la noche)
.\start_bot.bat
```

> Si ya hay un proceso corriendo y da error de archivo en uso, mátalo primero:
> ```powershell
> Stop-Process -Id <PID> -Force
> ```
> Ver PID con: `Get-Process python`

Para ver logs en tiempo real desde otra terminal:
```powershell
Get-Content bot_d.log -Encoding UTF8 -Wait -Tail 20
```

---

## Estado actual (2 abril 2026)

| Item | Estado |
|------|--------|
| Modelo entrenado | ✅ 55.6% WR backtest, LCK 57.9% |
| Mercados LCK/LEC encontrados | ✅ ~33 por ciclo (solo winner markets) |
| getLive detectando partidos | ✅ DK vs NS detectado hoy a las 05:03 |
| Minuto 15 funcionando | ✅ Fix RFC 822 aplicado (bug crítico resuelto) |
| Señales generadas en vivo | ⏳ Pendiente verificar con próximo partido |
| Telegram notificaciones | ✅ Configurado y funcionando |
| DRY_RUN | ✅ Activo (no opera dinero real aún) |

---

## Estrategia

```
Cada 5 minutos:
  1. Polymarket Gamma API → mercados LCK/LEC activos
  2. getLive (Riot API) → gameId de partidos en curso
  3. feed.lolesports.com → stats del minuto 15
  4. LogisticRegression → P(win) equipo azul
  5. Si edge = |P_modelo - P_mercado| ≥ 8% → señal
  6. Kelly 25% → tamaño de apuesta (máx $50 USDC)
  7. Notificación Telegram
```

---

## Estructura del proyecto

```
lol-polymarket-bot/
├── backend/
│   ├── config.py                # Variables de entorno y constantes
│   ├── scheduler.py             # Loop principal cada 5 min
│   ├── telegram_bot.py          # Notificaciones
│   ├── database.py              # SQLite: signals, trades, positions
│   ├── model/
│   │   ├── train.py             # Entrena LogisticRegression + StandardScaler
│   │   ├── predict.py           # predict_win_probability(features) → float
│   │   └── model.pkl            # Modelo entrenado (generado con train_model.py)
│   ├── data/
│   │   ├── oracle_elixir.py     # Datos históricos LCK/LEC (Oracle's Elixir S3)
│   │   ├── lolesports_api.py    # Feed API Riot: stats minuto 15 en vivo
│   │   └── game_mapper.py       # Slug Polymarket → gameId Riot (getLive cache)
│   ├── polymarket/
│   │   ├── markets.py           # Gamma API: filtrado LCK/LEC winner markets
│   │   └── trader.py            # Kelly sizing + execute_signal() + DRY_RUN
│   └── api/
│       └── main.py              # FastAPI: /health /api/stats /trades /signals
├── scripts/
│   ├── backtest.py              # Backtest histórico Oracle's Elixir
│   ├── check_live.py            # Diagnóstico getLive API
│   ├── diagnose_markets.py      # Ver todos los mercados y por qué se filtran
│   ├── verify_pipeline.py       # Test end-to-end del pipeline
│   └── train_model.py           # CLI para entrenar modelo
├── tests/
│   ├── test_model.py
│   ├── test_lolesports_api.py
│   └── test_markets.py
├── start_bot.bat                # Auto-restart en Windows
├── CONTEXT.md                   # Documentación técnica detallada (legacy)
├── DEPLOY.md                    # Instrucciones Railway
├── CHANGELOG.md                 # Historial de cambios
└── requirements.txt
```

---

## Variables de entorno (.env)

```env
# Polymarket (solo para LIVE - dejar vacío en DRY_RUN)
POLYMARKET_PRIVATE_KEY=0x...
POLYMARKET_PROXY_ADDRESS=0x...

# Telegram (recomendado)
TELEGRAM_BOT_TOKEN=123:AAxx...
TELEGRAM_CHAT_ID=-100...

# Bot config
BANKROLL=1000
MIN_EDGE_THRESHOLD=0.08
MAX_POSITION_SIZE_USD=50
MIN_MARKET_LIQUIDITY=50
DRY_RUN=true
KELLY_FRACTION=0.25
```

---

## Modelo

- **Algoritmo:** LogisticRegression + StandardScaler
- **Datos:** Oracle's Elixir 2021–2025 (LCK + LEC)
- **Variables (minuto 15):**

| Variable | Descripción |
|----------|-------------|
| `goldrelat15` | (gold_blue - gold_red) / gold_blue |
| `xprelat15` | (xp_blue - xp_red) / xp_blue |
| `csrelat15` | (cs_blue - cs_red) / cs_blue |
| `killsrelat15` | kills_blue / (kills_blue + kills_red) |
| `firstdragon` | 1 si blue tomó primer dragón |
| `firstblood` | 1 si blue hizo first blood |
| `firstherald` | 1 si blue tomó primer heraldo |

- **Backtest:** 2,816 partidos → 55.6% WR global, LCK 57.9%, LEC 51.8%

---

## Horarios de partidos (hora Chile, UTC-3)

| Liga | Días | Hora Chile |
|------|------|-----------|
| LCK | Mié–Dom | 05:00 y 08:00 |
| LEC | Sáb–Dom | 11:00–17:00 |

---

## Criterios para activar LIVE (DRY_RUN=false)

- [ ] `lolesports_api.py` llega al minuto 15 en un partido real
- [ ] Al menos 3 señales generadas en DRY_RUN y verificadas
- [ ] Señales coinciden con resultado real del partido
- [ ] Tests `pytest tests/ -v` pasando

---

## Comandos útiles

```powershell
# Ver log en tiempo real
Get-Content bot_d.log -Encoding UTF8 -Wait -Tail 20

# Verificar qué mercados encuentra ahora
python scripts/diagnose_markets.py

# Test getLive API
python scripts/check_live.py

# Re-entrenar modelo
python scripts/train_model.py

# Backtest histórico
python scripts/backtest.py

# Tests
pytest tests/ -v
```

---

## Referencias

- [Oracle's Elixir](https://oracleselixir.com/tools/downloads) — datos históricos
- [LoL Esports API docs](https://vickz84259.github.io/lolesports-api-docs) — feed API unofficial
- [Polymarket CLOB](https://github.com/Polymarket/py-clob-client) — SDK trading
- Paper Uppsala 2026 — LogisticRegression min-15 LCK/LEC (FULLTEXT01.pdf)

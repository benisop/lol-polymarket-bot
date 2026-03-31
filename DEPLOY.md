# Deploy en Railway — Bot D

## Pre-requisitos
1. Cuenta en Railway (railway.app)
2. Repo `benisop/lol-polymarket-bot` conectado
3. `model.pkl` generado localmente (ver paso 1 abajo)

---

## Paso 1 — Generar model.pkl localmente

```bash
# Instalar dependencias
pip install -r requirements.txt

# Entrenar modelo (descarga ~200MB de CSVs de Oracle's Elixir)
python scripts/train_model.py

# Verificar que pasó los 6 criterios mínimos
# Expected output:
#   ✅ ENTRENAMIENTO EXITOSO
#   Global accuracy : 0.7XX
#   LCK accuracy    : 0.7XX
#   LEC accuracy    : 0.7XX
```

> **Nota**: `model.pkl` está en `.gitignore`. Debes subirlo manualmente
> a Railway como variable de entorno o usar Railway Volumes.

---

## Paso 2 — Variables de entorno en Railway

En el dashboard de Railway → tu proyecto → Variables:

| Variable | Valor | Requerida |
|---|---|---|
| `POLYMARKET_PRIVATE_KEY` | `0x...` | Solo en LIVE |
| `POLYMARKET_PROXY_ADDRESS` | `0x...` | Solo en LIVE |
| `TELEGRAM_BOT_TOKEN` | `123:AAxx...` | Recomendada |
| `TELEGRAM_CHAT_ID` | `-100...` | Recomendada |
| `BANKROLL` | `1000` | Sí |
| `MIN_EDGE_THRESHOLD` | `0.08` | Sí |
| `MAX_POSITION_SIZE_USD` | `50` | Sí |
| `MIN_MARKET_LIQUIDITY` | `500` | Sí |
| `DRY_RUN` | `true` | **Siempre true al inicio** |
| `DB_PATH` | `/data/lol_bot.db` | Sí (Railway Volume) |
| `MODEL_PATH` | `/data/model.pkl` | Sí (Railway Volume) |

---

## Paso 3 — Railway Volume (persistencia)

El bot usa SQLite y model.pkl. Sin volumen se pierden los datos en cada deploy.

```
Railway Dashboard → tu proyecto → Add Volume
  Mount path: /data
```

Luego sube `model.pkl` con:
```bash
railway run cp backend/model/model.pkl /data/model.pkl
```

---

## Paso 4 — Servicios en Railway

El proyecto necesita **2 servicios**:

### Servicio 1: API (web)
```
Start command: uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
```
- Expone los endpoints `/health`, `/api/stats`, `/api/trades`

### Servicio 2: Scheduler (worker)
```
Start command: python -m backend.scheduler
```
- Loop cada 5 min que detecta señales y ejecuta trades

En `railway.json` ya está configurado el servicio web.
Para el worker, crear un segundo servicio en el dashboard.

---

## Paso 5 — Deploy

```bash
# Desde el repo local
git push origin master:main

# Railway hace auto-deploy en cada push a main
```

---

## Paso 6 — Verificar deploy

```bash
# Healthcheck
curl https://tu-app.railway.app/health

# Stats del bot
curl https://tu-app.railway.app/api/stats

# Mercados activos ahora
curl https://tu-app.railway.app/api/markets
```

---

## Paso 7 — Validar criterios antes de LIVE

Correr en DRY_RUN mínimo 30 minutos y verificar:

- [ ] `train.py` logra >= 70% accuracy
- [ ] `game_mapper.py` mapea >= 5 slugs de ejemplo
- [ ] `lolesports_api.py` obtiene stats de un partido activo
- [ ] `markets.py` encuentra >= 1 mercado LCK/LEC activo
- [ ] `scheduler.py` corre 30 min sin errores en logs
- [ ] >= 3 señales detectadas en DRY_RUN (ver `/api/signals`)

**Solo cuando los 6 pasen → cambiar `DRY_RUN=false` en Railway.**

---

## Monitoreo

```bash
# Logs en tiempo real
railway logs --tail

# Últimos trades
curl .../api/trades

# Señales detectadas hoy
curl .../api/signals
```

## Telegram

Cada señal y trade genera una notificación automática.
Configura `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` para recibirlas.

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `model.pkl no encontrado` | No se subió al Volume | `railway run cp model.pkl /data/` |
| `Sin mercados activos` | No hay partidos LCK/LEC | Normal fuera de horario |
| `gameId no encontrado` | Slug formato no reconocido | Revisar aliases en `game_mapper.py` |
| `HTTP 429 en CLOB` | Rate limit de Polymarket | Reducir frecuencia o esperar |
| Stop-loss activado | Pérdidas > 15% del día | Revisión manual, cambiar `DRY_RUN=true` |

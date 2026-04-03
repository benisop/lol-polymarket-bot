# CLAUDE.md — Contexto Completo del Bot D (LoL Polymarket)

> Este archivo es el punto de entrada para nuevas sesiones de Claude.
> Contiene el estado completo del proyecto, decisiones tomadas, bugs resueltos y tareas pendientes.
> Leer SIEMPRE al inicio de una nueva sesión antes de tocar cualquier codigo.

---

## MODO DE TRABAJO OBLIGATORIO (leer antes que todo)

**Activar siempre al inicio de cada sesion:**

```
CLAUDE_CODE_COORDINATOR_MODE=1
```

### Token Efficiency Mode
- Se extremadamente conciso en respuestas
- Resume progresos en vez de repetir contexto completo
- Usa scratchpad para estados persistentes
- Compacta contexto cuando se acerque al limite
- NO repitas el contexto completo innecesariamente

### Rol principal
Eres el ingeniero principal y Team Lead del Bot D.

### Equipo de agentes especializados
Cuando sea necesario crear o delegar trabajo, usa este equipo:

| Agente          | Responsabilidad                                              |
|-----------------|--------------------------------------------------------------|
| Architect       | Diseno general, estructura, decisiones de arquitectura       |
| Data-Engineer   | oracle_elixir.py, train.py, predict.py, modelo ML            |
| API-Specialist  | lolesports_api.py, game_mapper.py, markets.py, trader.py     |
| Tester          | tests/, validaciones, pytest, verify_pipeline.py             |
| Deployer        | scheduler.py, main.py (FastAPI), Railway, start_bot.bat      |

### Reglas del equipo
- Asignar tareas en paralelo donde sea posible
- Los agentes comparten conocimiento en la carpeta `scratchpad/`
- Usar TaskCreateTool para convertir pasos en tareas independientes
- Usar TaskUpdateTool al terminar cada tarea (marcar done)
- Avisar al usuario despues de terminar cada fase grande
- Antes de trabajo complejo: usar UltraPlan (blueprint detallado primero)

---

## Prompt para nueva sesion

```
Activa modo coordinator multi-agent completo (CLAUDE_CODE_COORDINATOR_MODE=1).
Token efficiency mode: se extremadamente conciso, resume progresos, usa scratchpad
para estados persistentes y compacta contexto cuando se acerque al limite.
No repitas el contexto completo innecesariamente.

Eres mi ingeniero principal y Team Lead del Bot D de LoL Polymarket.

Lee primero CLAUDE.md en:
  C:\Users\hp\Downloads\lol-polymarket-bot\CLAUDE.md

Luego lee las ultimas 50 lineas del log:
  tail -50 C:/Users/hp/Downloads/lol-polymarket-bot/bot_d.log

Con ese contexto, dame un resumen breve del estado actual y dime que necesita
atencion inmediata. No hagas nada mas hasta que yo confirme.
```

---

## Descripcion del proyecto

Bot de trading automatizado para Polymarket que opera mercados de League of Legends
(LCK y LEC) usando un modelo de Regresion Logistica entrenado con datos del minuto 15.

**Flujo principal (cada 5 minutos):**
1. Polymarket Gamma API → mercados LCK/LEC activos con liquidez >= $50
2. getLive (Riot API) → gameId de partidos en curso
3. feed.lolesports.com → stats del minuto 15
4. LogisticRegression → P(win) equipo azul
5. Si edge = |P_modelo - P_mercado| >= 8% → senal
6. Kelly 25% → tamano de apuesta (max $50 USDC)
7. Notificacion Telegram + registro SQLite

---

## Carpeta del proyecto

```
C:\Users\hp\Downloads\lol-polymarket-bot\
```

---

## Comandos esenciales (PowerShell)

```powershell
# Arrancar el bot (VISIBLE en consola - recomendado)
cd C:\Users\hp\Downloads\lol-polymarket-bot
python -m backend.scheduler

# Ver log en tiempo real (otra terminal)
Get-Content bot_d.log -Encoding UTF8 -Wait -Tail 30

# Ver si el bot esta corriendo
Get-Process python

# Matar el bot
Stop-Process -Id <PID> -Force

# Diagnostico de mercados activos ahora
python scripts/diagnose_markets.py

# Test de getLive API
python scripts/check_live.py

# Test end-to-end del pipeline
python scripts/verify_pipeline.py
```

---

## Estructura del codigo

```
lol-polymarket-bot/
├── CLAUDE.md                        <- ESTE ARCHIVO (contexto sesiones)
├── README.md                        <- Documentacion publica
├── CHANGELOG.md                     <- Historial de cambios por version
├── start_bot.bat                    <- Loop auto-restart Windows (background)
├── bot_d.log                        <- Log principal del bot
├── bot_d_error.log                  <- Errores del bat (background)
├── lol_bot.db                       <- SQLite: signals, trades, positions
├── .env                             <- Variables de entorno (NO en git)
├── backend/
│   ├── config.py                    <- Variables de entorno y constantes
│   ├── scheduler.py                 <- Loop principal cada 5 min
│   ├── telegram_bot.py              <- Notificaciones Telegram
│   ├── database.py                  <- SQLite: signals, trades, positions
│   ├── model/
│   │   ├── train.py                 <- Entrena LogisticRegression + StandardScaler
│   │   ├── predict.py               <- predict_win_probability(features) -> float
│   │   └── model.pkl                <- Modelo entrenado
│   ├── data/
│   │   ├── oracle_elixir.py         <- Datos historicos LCK/LEC (Google Drive)
│   │   ├── lolesports_api.py        <- Feed API Riot: stats minuto 15 EN VIVO
│   │   └── game_mapper.py           <- Slug Polymarket -> gameId Riot
│   ├── polymarket/
│   │   ├── markets.py               <- Gamma API: filtrado LCK/LEC winner markets
│   │   └── trader.py                <- Kelly sizing + execute_signal() + DRY_RUN
│   └── api/
│       └── main.py                  <- FastAPI: /health /api/stats /trades /signals
├── scripts/
│   ├── backtest.py                  <- Backtest historico Oracle's Elixir
│   ├── check_live.py                <- Diagnostico getLive API
│   ├── diagnose_markets.py          <- Ver mercados y por que se filtran
│   ├── verify_pipeline.py           <- Test end-to-end del pipeline
│   └── train_model.py               <- CLI para entrenar modelo
└── tests/
    ├── test_model.py
    ├── test_lolesports_api.py
    └── test_markets.py
```

---

## Archivos mas importantes (leer en este orden)

1. `backend/data/lolesports_api.py`  — logica de timestamps y minuto 15
2. `backend/data/game_mapper.py`     — como se mapea slug -> gameId
3. `backend/polymarket/markets.py`   — filtrado de mercados Polymarket
4. `backend/scheduler.py`            — loop principal
5. `backend/config.py`               — constantes y .env

---

## Configuracion actual (.env)

```env
DRY_RUN=true                    <- NO opera dinero real todavia
BANKROLL=1000
MIN_EDGE_THRESHOLD=0.08         <- 8% de ventaja minima para operar
MAX_POSITION_SIZE_USD=50        <- Max $50 USDC por apuesta
MIN_MARKET_LIQUIDITY=50         <- Min $50 liquidez en el mercado
KELLY_FRACTION=0.25             <- Kelly al 25%
TELEGRAM_BOT_TOKEN=...          <- Configurado y funcionando
TELEGRAM_CHAT_ID=...            <- Configurado y funcionando
POLYMARKET_PRIVATE_KEY=         <- Vacio hasta activar LIVE
POLYMARKET_PROXY_ADDRESS=       <- Vacio hasta activar LIVE
```

---

## Modelo de ML

- **Algoritmo:** LogisticRegression + StandardScaler
- **Datos:** Oracle's Elixir 2021-2025 (LCK + LEC), 2816 partidos
- **Variables (minuto 15, perspectiva equipo AZUL):**

| Variable       | Formula                                          |
|---------------|--------------------------------------------------|
| goldrelat15   | (gold_blue - gold_red) / gold_blue               |
| xprelat15     | (xp_blue - xp_red) / xp_blue                    |
| csrelat15     | (cs_blue - cs_red) / cs_blue                    |
| killsrelat15  | kills_blue / (kills_blue + kills_red)           |
| firstdragon   | 1 si blue tomo primer dragon                     |
| firstblood    | 1 si blue hizo first blood                       |
| firstherald   | 1 si blue tomo primer heraldo                    |

- **Backtest:** 55.6% WR global | LCK: 57.9% | LEC: 51.8%
- **Ventana de operacion:** minuto 15 a 25 del partido

---

## APIs utilizadas

### Polymarket Gamma API
- Endpoint markets: `https://gamma-api.polymarket.com/markets`
- Endpoint events:  `https://gamma-api.polymarket.com/events`
- Tag usado: `league-of-legends` y `esports`
- Filtro: solo mercados con fecha YYYY-MM-DD en el slug, sin props

### Riot LoL Esports API
- getLive:  `https://esports-api.lolesports.com/persisted/gw/getLive?hl=en-US`
  - Header: `x-api-key: 0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z`
  - Unica fuente confiable de gameIds en tiempo real
- Feed window: `https://feed.lolesports.com/livestats/v1/window/{gameId}`
  - Requiere `startingTime` (divisible por 10s) para datos actuales
  - Sin startingTime: devuelve frames desde inicio del juego
- Feed details: `https://feed.lolesports.com/livestats/v1/details/{gameId}`

---

## Bugs resueltos (HISTORIAL CRITICO)

### Bug #1 — Tag incorrecto Gamma API [0.3.0]
- **Problema:** `tag_slug=esports` devuelvia 0 mercados
- **Fix:** Cambiar a `tag_slug=league-of-legends`

### Bug #2 — Leaguepedia fallback [0.3.0]
- **Problema:** Retornaba wiki IDs no numericos → 404 en feed API
- **Fix:** Eliminado completamente. getLive es la unica fuente de gameIds.

### Bug #3 — False positives "lec" [0.3.0]
- **Problema:** La palabra "election" hacia match con el regex LEC
- **Fix:** `\blec\b` con word boundary

### Bug #4 — RFC 822 timestamp [0.4.0]
- **Problema:** `datetime.fromisoformat()` no parsea formato RFC 822
  `"Thu, 02 Apr 2026 08:10:00 GMT"` → ValueError silencioso → game_time_s = 0
- **Fix:** `_parse_ts()` con `email.utils.parsedate_to_datetime` como fallback

### Bug #5 — rfc460Timestamp (ULTIMO FIX - 03 Abr 2026) [0.4.1]
- **Problema RAIZ REAL:** La API NO usa `rfc822Timestamp`. Usa `rfc460Timestamp`
  (formato ISO-8601). El codigo buscaba el campo incorrecto → None → 0.0 min siempre.
  Ademas, sin el parametro `startingTime`, la API devuelve frames del INICIO del
  juego (gold=0, todos los stats en 0) — no el estado actual del partido.
  Finalmente, `gameStartTime` no aparece en la metadata del window endpoint.
- **Fix completo en `lolesports_api.py`:**
  1. Nueva funcion `_ts_from_frame(frame)` → lee `rfc460Timestamp` o `rfc822Timestamp`
  2. Nueva funcion `_current_window_params()` → genera `startingTime=ahora-3min`
     (redondeado a multiplo de 10 segundos como requiere la API)
  3. Cache `_game_start_times: dict[str, datetime]` → primera query sin startingTime
     para inferir el inicio del juego desde el primer frame; queries siguientes
     usan startingTime para obtener frames actuales
  4. `_find_minute15_frame()` actualizado para usar `rfc460Timestamp` y el cache
- **Verificado:** gameId 115548128962906276 (Gen.G vs KT, 03-Abr)
  Antes: 0.0 min | Despues: 25min 58s / finished / Blue gold=53,524

---

## Estado actual del proyecto (03 Abril 2026)

| Item                          | Estado                                      |
|-------------------------------|---------------------------------------------|
| Modelo entrenado              | OK — 55.6% WR backtest, LCK 57.9%         |
| Mercados LCK/LEC encontrados  | OK — ~32 por ciclo (solo winner markets)   |
| getLive detectando partidos   | OK — Gen.G vs KT detectado hoy             |
| Timestamps correctos          | OK — rfc460Timestamp fix aplicado hoy      |
| Stats en vivo correctas       | OK — startingTime fix aplicado hoy         |
| Senales generadas en VIVO     | PENDIENTE — proxima sesion de LCK/LEC      |
| Telegram notificaciones       | OK — configurado y funcionando             |
| DRY_RUN                       | ACTIVO — no opera dinero real              |

---

## Git / GitHub

- **Repositorio:** https://github.com/benisop/lol-polymarket-bot
- **Branch activo:** `fix/rfc822-timestamp-game-time`
- **Ultimo commit:** `94a2f80` — fix rfc460Timestamp + startingTime

```powershell
# Ver estado git
git status
git log --oneline -5

# Push (si hiciste cambios)
git push origin fix/rfc822-timestamp-game-time
```

---

## Horarios de partidos

| Liga | Dias      | Hora Chile (UTC-3) | Hora UTC |
|------|-----------|-------------------|----------|
| LCK  | Mie-Dom   | 05:00 AM          | 08:00    |
| LCK  | Mie-Dom   | 08:00 AM          | 11:00    |
| LEC  | Sab-Dom   | 11:00 - 17:00     | 14-20    |

**IMPORTANTE:** El bot debe estar corriendo ANTES del inicio del partido.
El minuto 15 es la ventana critica. Si el bot no esta activo en ese momento, no habra senal.

---

## Tareas pendientes (prioridad)

### ALTA PRIORIDAD
- [ ] **Verificar primera senal real** — Proxima sesion LCK (05:00 AM Chile)
      El fix de timestamps esta aplicado. Debe generar senal si hay edge >= 8%.
      Confirmar que llega a "min 15.x" en los logs.

- [ ] **Agregar aliases de equipos LEC faltantes** en `game_mapper.py` → `TEAM_ALIASES`:
      ```python
      "gx":    "GiantX",
      "giantx": "GiantX",
      "th":    "Team Heretics",
      "heretics": "Team Heretics",
      "navi":  "Natus Vincere",
      "shft":  "Shopify Rebellion",  # puede aparecer como "shft"
      "mkoi":  "MAD Lions KOI",
      "mad":   "MAD Lions KOI",
      ```
      El log muestra "Gx vs Th" y "SK Gaming vs Shft" → no los resuelve.

- [ ] **Merge PR** en GitHub:
      https://github.com/benisop/lol-polymarket-bot/pull/new/fix/rfc822-timestamp-game-time

### MEDIA PRIORIDAD
- [ ] **Verificar que `extract_minute15_stats` encuentra frames del minuto 15**
      Con el fix de startingTime la query trae los ultimos 3 minutos.
      Para encontrar el frame del MIN 15 exacto necesitamos TODOS los frames.
      Puede requerir una segunda query con startingTime=game_start+12min.

- [ ] **Criterios para activar LIVE (DRY_RUN=false):**
      - Al menos 3 senales DRY_RUN generadas y verificadas manualmente
      - Las senales coinciden con el resultado real del partido
      - `pytest tests/ -v` pasando 100%

- [ ] **Tests pytest** — Verificar que pasan con los cambios de timestamps:
      ```powershell
      pytest tests/ -v
      ```

### BAJA PRIORIDAD
- [ ] Implementar fallback gol.gg con BeautifulSoup (actualmente es un stub)
- [ ] Agregar endpoint `/api/positions` al FastAPI
- [ ] Deploy en Railway (ver DEPLOY.md)

---

## Problema conocido: extract_minute15_stats con startingTime

**ATENCION:** Existe un posible problema de logica en `extract_minute15_stats`:

El fix de Bug #5 hace que `get_live_stats()` use `startingTime=ahora-3min` para
obtener frames actuales. Pero `extract_minute15_stats()` llama a `get_live_stats()`
para obtener `all_frames` y busca el frame del minuto 15 entre ellos.

Si el partido ya paso el minuto 15 (estamos en min 18, por ejemplo), los frames
retornados por la query `ahora-3min` seran del rango [min15, min18] → correcto.
Pero si la query solo retorna frames de los ultimos 3 minutos y el partido empezo
hace mucho, podria no incluir el frame exacto del min 15.

**Solucion sugerida (no implementada aun):**
En `extract_minute15_stats`, hacer una segunda query especifica para el minuto 15:
```
startingTime = game_start + 12 minutos (redondeado a 10s)
```
Esto garantiza frames alrededor del min 15 independientemente de cuando se ejecute.

---

## Como reiniciar el bot despues de viajar

1. Abrir PowerShell
2. Verificar que no haya procesos viejos:
   ```powershell
   Get-Process python
   # Si hay alguno: Stop-Process -Id <PID> -Force
   ```
3. Arrancar el bot:
   ```powershell
   cd C:\Users\hp\Downloads\lol-polymarket-bot
   python -m backend.scheduler
   ```
4. Verificar en los logs que el ciclo corre sin errores:
   - Debe ver: `Ciclo #XXX completado | mercados=XX mapeados=X`
   - Si hay partido en vivo: debe ver `gameId XXXXX: X.X min | estado=in_game`
   - Si el tiempo es >= 15min: debe intentar calcular features

---

## Variables del modelo — donde se calculan

En `lolesports_api.py` → funcion `_compute_features(frame, metadata)`:
- `blue = frame.get("blueTeam", {})` — tiene: totalGold, kills, totalCS, totalXP, dragons, towerKills
- `red  = frame.get("redTeam",  {})` — idem
- firstblood/firstdragon/firstherald se infieren de la metadata o heuristicas del frame

---

## Notas de la API de Riot (CRITICAS)

```
feed.lolesports.com/livestats/v1/window/{gameId}

Sin parametros:
  → Devuelve ~10 frames desde el INICIO del juego (gold=0)
  → util para inferir game start time

Con startingTime=YYYY-MM-DDTHH:MM:SSZ (multiplo de 10s):
  → Devuelve frames a partir de ese momento
  → Para stats actuales: startingTime = ahora - 3 minutos
  → Para min 15: startingTime = game_start + 12 minutos

Campos de timestamp en frames:
  → rfc460Timestamp: "2026-04-03T08:10:26.755Z"  (ISO-8601, el que existe)
  → rfc822Timestamp: NO EXISTE en partidos actuales (campo viejo)

gameMetadata:
  → gameStartTime: NO siempre presente (puede estar vacio)
  → blueTeamMetadata.participantMetadata: jugadores y champions
```

---

## Notas del equipo azul vs rojo en Polymarket

Polymarket lista equipos como `outcomes: ["TeamA", "TeamB"]`.
El equipo en `outcomes[0]` corresponde al equipo AZUL (blue side) en la mayoria de
los casos, pero esto NO esta garantizado. El modelo predice P(win) para blue side.

Si los resultados son incorrectos en LIVE, revisar el mapeo de outcomes → sides.

---

*Documento generado: 03 Abril 2026*
*Ultima actualizacion: fix Bug #5 (rfc460Timestamp + startingTime)*

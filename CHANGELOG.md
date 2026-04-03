# Changelog — Bot D LoL Polymarket

## [0.4.0] — 2026-04-02 (sesión actual)

### Bug crítico resuelto
- **RFC 822 timestamp parsing**: La Riot feed API devuelve `rfc822Timestamp` en formato
  RFC 822 (`"Thu, 02 Apr 2026 08:10:00 GMT"`). El código usaba `datetime.fromisoformat()`
  que no soporta este formato → fallaba silenciosamente → `game_time_s = 0` siempre →
  el juego nunca llegaba al minuto 15 → **cero señales generadas jamás**.
  Fix: `_parse_ts()` con `email.utils.parsedate_to_datetime` como fallback.

### Performance
- **getLive cache por ciclo**: `refresh_live_cache()` llama a getLive **una sola vez**
  por ciclo y guarda el resultado. Antes se llamaba una vez por mercado (~56 llamadas
  HTTP por ciclo → ahora 1).
- **Stats cache 60s**: `extract_minute15_stats()` cachea el resultado 60 segundos.
  Evita llamadas repetidas al feed API cuando múltiples mercados apuntan al mismo gameId.
- **Rate limit 30s → 10s**: Con el cache, el rate limit puede ser más agresivo.

### Filtros de mercados
- Prop markets completamente excluidos: `total-games`, `handicap`, `kill-over`,
  `kill-under`, `any-player`, `destroy-inhib`.
- Regex `-\d+pt\d+` elimina cualquier mercado con línea numérica (ej: `29pt5`, `2pt5`).
- Mercados por ciclo reducidos de ~56 a ~33 (solo winner markets).

### Archivos nuevos
- `start_bot.bat` — loop infinito con auto-restart en Windows
- `scripts/backtest.py` — backtest histórico con Oracle's Elixir
- `scripts/check_live.py` — diagnóstico getLive API
- `scripts/diagnose_markets.py` — ver todos los mercados y por qué se filtran
- `scripts/verify_pipeline.py` — test end-to-end del pipeline
- `README.md` — documentación completa del proyecto

### Confirmado funcionando
- A las 05:03 Chile (08:03 UTC) el bot detectó DK vs NS con `gameId=115548128962906292`
  estado `inProgress`. El pipeline llegó hasta el feed API. El bug del timestamp
  impedía avanzar al minuto 15. Con el fix aplicado, el próximo partido debería
  generar señales.

---

## [0.3.0] — 2026-04-01 (sesión anterior - noche)

### Polymarket Gamma API — corrección crítica
- **Tag incorrecto**: Se usaba `tag_slug=esports` → 0 mercados. Fix: `tag_slug=league-of-legends`.
- **Endpoint incorrecto**: Los mercados per-match solo aparecen en `/events`, no en `/markets`.
  Añadido `_fetch_events_markets()` que consulta `/events` y propaga `_event_title`.
- **False positives "lec"**: La palabra "election" hacía match. Fix: `\blec\b` con word boundary.
- **Leaguepedia fallback eliminado**: Retornaba wiki IDs (`LCK/2026 Season/...`) no numéricos
  que causaban 404 en feed API. Eliminado completamente de `get_game_id()`.

### Game mapper
- getLive como única fuente de gameIds en tiempo real.
- `LCK_SLUG_TOKENS` y `LEC_SLUG_TOKENS` para detección de liga desde tokens del slug.
- TEAM_ALIASES expandido: `drx`, `dnf`, `fearx`, `brion`, `t1`, `gen`, `kt`, `ns`, `hle`.
- `parse_slug()` detecta liga desde equipos cuando no está explícito en el slug.

### Bot persistencia Windows
- `start_bot.bat` con loop infinito y auto-restart.
- Fix: no redirigir stdout en bat (conflicto con Python FileHandler → PermissionError).
- `-WindowStyle Hidden` para correr sin ventana visible.

### Configuración
- `MIN_MARKET_LIQUIDITY` bajado de $500 a $50.

---

## [0.2.0] — 2026-03-31

### Fixes Windows
- UTF-8 forzado en logging (`encoding='utf-8'`).
- Caracteres Unicode incompatibles con cp1252 reemplazados.
- `sys.path` fix en `train_model.py`.

### Oracle's Elixir
- S3 deprecado → migrado a Google Drive para descarga de CSVs históricos.

---

## [0.1.0] — 2026-03-30 (commit inicial)

### Arquitectura completa
- LogisticRegression + StandardScaler entrenado con Oracle's Elixir 2021-2025.
- Pipeline: Gamma API → game_mapper → lolesports feed → predict → Kelly → trade.
- FastAPI con endpoints `/health`, `/api/stats`, `/api/trades`, `/api/signals`.
- Scheduler loop 5 minutos con stop-loss diario 15%.
- Telegram notificaciones para señales, trades y errores.
- SQLite para persistencia de signals, trades, games, positions.
- DRY_RUN=true como default hasta validar 3+ señales reales.
- Tests: 60+ tests cubriendo model, markets, lolesports_api.
- Deploy en Railway con Procfile (web + worker).

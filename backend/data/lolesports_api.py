"""
lolesports_api.py — Cliente para la Unofficial LoL Esports Live Stats API.

Docs: vickz84259.github.io/lolesports-api-docs

Endpoints:
    GET feed.lolesports.com/livestats/v1/window/{gameId}
    GET feed.lolesports.com/livestats/v1/details/{gameId}
"""

import logging
import time
from datetime import datetime, timezone
from functools import lru_cache

import requests

from backend.config import LOLESPORTS_BASE_URL

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────────────────────────
MAX_RETRIES      = 3
RATE_LIMIT_SECS  = 30       # mínimo entre requests al mismo gameId
MIN_GAME_MINUTE  = 15       # minuto objetivo para el modelo
MAX_GAME_MINUTE  = 25       # pasado este minuto, modelo no es fiable

# Caché simple de timestamps para rate limiting por gameId
_last_request: dict[str, float] = {}


def _rate_limit(game_id: str) -> None:
    """Espera si se llamó a este gameId hace menos de RATE_LIMIT_SECS."""
    now = time.monotonic()
    last = _last_request.get(game_id, 0)
    wait = RATE_LIMIT_SECS - (now - last)
    if wait > 0:
        logger.debug("Rate limit: esperando %.1fs para gameId %s", wait, game_id)
        time.sleep(wait)
    _last_request[game_id] = time.monotonic()


def _get_with_retry(url: str, params: dict | None = None) -> dict | None:
    """GET con retry exponencial. Retorna JSON dict o None."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                logger.warning("404 para %s — game no encontrado o no empezó.", url)
                return None
            elif resp.status_code == 429:
                wait = 10 * (attempt + 1)
                logger.warning("429 Rate limit, esperando %ds …", wait)
                time.sleep(wait)
            else:
                logger.warning("HTTP %d para %s", resp.status_code, url)
        except requests.Timeout:
            logger.warning("Timeout en intento %d para %s", attempt + 1, url)
        except Exception as exc:
            logger.error("Error request %s: %s", url, exc)

        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)

    return None


# ── Funciones principales ──────────────────────────────────────────────────────

def get_live_stats(game_id: str) -> dict | None:
    """
    Obtiene el frame más reciente de stats en vivo para un gameId.

    Retorna dict con estructura:
        {
            "game_id":      str,
            "game_state":   str,   # "in_game" | "finished" | "paused"
            "game_time_s":  int,   # segundos transcurridos
            "patch":        str,
            "blue": {
                "total_gold": int, "kills": int,
                "dragons": int,    "towers": int,
            },
            "red": {
                "total_gold": int, "kills": int,
                "dragons": int,    "towers": int,
            },
            "raw_frame": dict,     # frame completo para extract_minute15_stats
        }
    o None si no hay datos disponibles.
    """
    _rate_limit(game_id)
    url = f"{LOLESPORTS_BASE_URL}/window/{game_id}"
    data = _get_with_retry(url)

    if not data:
        return _fallback_golgg(game_id)

    try:
        metadata = data.get("gameMetadata", {})
        frames   = data.get("frames", [])

        if not frames:
            logger.info("gameId %s: sin frames aún.", game_id)
            return None

        frame = frames[-1]
        game_state = frame.get("gameState", "unknown")

        # Tiempo de juego en segundos
        game_time_s = 0
        start_str = metadata.get("gameStartTime", "")
        frame_ts_str = frame.get("rfc822Timestamp", "")
        if start_str and frame_ts_str:
            try:
                start  = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                frame_ts = datetime.fromisoformat(frame_ts_str.replace("Z", "+00:00"))
                game_time_s = int((frame_ts - start).total_seconds())
            except Exception:
                pass

        teams = frame.get("blueTeam", {}), frame.get("redTeam", {})
        # Algunos endpoints usan teams[] array
        if not teams[0] and "teams" in frame:
            team_list = frame["teams"]
            teams = (
                team_list[0] if len(team_list) > 0 else {},
                team_list[1] if len(team_list) > 1 else {},
            )

        def _team_stats(t: dict) -> dict:
            return {
                "total_gold": t.get("totalGold", 0),
                "kills":      t.get("kills", 0),
                "dragons":    len(t.get("dragons", [])) if isinstance(
                    t.get("dragons"), list) else t.get("dragonKills", 0),
                "towers":     t.get("towerKills", 0),
            }

        return {
            "game_id":    game_id,
            "game_state": game_state,
            "game_time_s": game_time_s,
            "patch":      metadata.get("patchVersion", ""),
            "blue":       _team_stats(teams[0]),
            "red":        _team_stats(teams[1]),
            "raw_frame":  frame,
            "all_frames": frames,    # necesario para extract_minute15_stats
            "metadata":   metadata,
        }

    except Exception as exc:
        logger.error("Error parseando respuesta de gameId %s: %s", game_id, exc)
        return None


def extract_minute15_stats(game_id: str) -> dict | None:
    """
    Extrae las 7 variables del modelo para el minuto 15 de un partido.

    Retorna dict listo para predict_win_probability() o None si:
        - El partido no llegó al min 15 aún.
        - El partido ya pasó el min 25 (demasiado tarde).
        - No hay datos disponibles.

    Variables retornadas (perspectiva del equipo AZUL):
        goldrelat15, xprelat15, firstdragon, csrelat15,
        killsrelat15, firstblood, firstherald
    """
    stats = get_live_stats(game_id)
    if not stats:
        return None

    game_time_s  = stats["game_time_s"]
    game_time_m  = game_time_s / 60

    logger.info("gameId %s: %.1f min | estado=%s",
                game_id, game_time_m, stats["game_state"])

    # Ventana de operación: [15, 25] minutos
    if game_time_m < MIN_GAME_MINUTE:
        logger.info("Partido en min %.1f — aún no llegó al min 15.", game_time_m)
        return None
    if game_time_m > MAX_GAME_MINUTE:
        logger.info("Partido en min %.1f — ya pasó el min 25, modelo no fiable.", game_time_m)
        return None

    # Buscar el frame más cercano al minuto 15
    frames   = stats.get("all_frames", [])
    metadata = stats.get("metadata", {})
    frame_15 = _find_minute15_frame(frames, metadata)

    if frame_15 is None:
        logger.warning("No se encontró frame del min 15 para gameId %s", game_id)
        return None

    return _compute_features(frame_15, metadata)


def _find_minute15_frame(frames: list, metadata: dict) -> dict | None:
    """Retorna el frame más cercano al minuto 15 desde el inicio del juego."""
    start_str = metadata.get("gameStartTime", "")
    if not start_str:
        # Sin gameStartTime, usar el frame a índice ~(15/0.5) ≈ 30 desde el inicio
        idx = min(30, len(frames) - 1)
        return frames[idx] if frames else None

    try:
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except Exception:
        return frames[min(30, len(frames) - 1)] if frames else None

    target_s = MIN_GAME_MINUTE * 60  # 900 segundos
    best_frame = None
    best_diff  = float("inf")

    for frame in frames:
        ts_str = frame.get("rfc822Timestamp", "")
        if not ts_str:
            continue
        try:
            ts   = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            diff = abs((ts - start).total_seconds() - target_s)
            if diff < best_diff:
                best_diff  = diff
                best_frame = frame
        except Exception:
            continue

    # Tolerancia: el frame más cercano debe estar a ≤ 5 minutos del min 15
    if best_frame and best_diff <= 300:
        return best_frame
    return None


def _compute_features(frame: dict, metadata: dict) -> dict | None:
    """
    Calcula las 7 variables relativas del modelo a partir de un frame.

    Variables (perspectiva equipo azul = blue side):
        goldrelat15  = (gold_blue - gold_red) / gold_blue
        xprelat15    = (xp_blue - xp_red)    / xp_blue
        csrelat15    = (cs_blue  - cs_red)    / cs_blue
        killsrelat15 = kills_blue / (kills_blue + kills_red)
        firstdragon  = 1 si blue tomó el primer dragón
        firstblood   = 1 si blue hizo el first blood
        firstherald  = 1 si blue tomó el primer heraldo
    """
    eps = 1e-6

    # Extraer datos de ambos equipos
    blue = frame.get("blueTeam", {})
    red  = frame.get("redTeam",  {})

    # Soporte para formato alternativo teams[]
    if not blue and "teams" in frame:
        teams = frame["teams"]
        blue  = teams[0] if len(teams) > 0 else {}
        red   = teams[1] if len(teams) > 1 else {}

    if not blue or not red:
        logger.warning("Frame sin datos de equipos: %s", list(frame.keys()))
        return None

    def _gold(t):  return float(t.get("totalGold", 0))
    def _kills(t): return float(t.get("kills", 0))
    def _cs(t):    return float(t.get("totalCS", t.get("creepScore", 0)))
    def _xp(t):    return float(t.get("totalXP", t.get("xp", 0)))

    g_blue, g_red = _gold(blue), _gold(red)
    k_blue, k_red = _kills(blue), _kills(red)
    cs_blue, cs_red = _cs(blue), _cs(red)
    xp_blue, xp_red = _xp(blue), _xp(red)

    # Inferir firstdragon / firstblood / firstherald desde metadata si está disponible
    first_dragon  = int(bool(metadata.get("blueFirstDragon", False) or
                             _dragons_blue_first(blue, red)))
    first_blood   = int(bool(metadata.get("blueFirstBlood", False)))
    first_herald  = int(bool(metadata.get("blueFirstHerald", False) or
                             _herald_blue(blue)))

    features = {
        "goldrelat15":  (g_blue  - g_red)  / (g_blue  + eps),
        "xprelat15":    (xp_blue - xp_red) / (xp_blue + eps),
        "csrelat15":    (cs_blue - cs_red) / (cs_blue  + eps),
        "killsrelat15": k_blue / (k_blue + k_red + eps),
        "firstdragon":  first_dragon,
        "firstblood":   first_blood,
        "firstherald":  first_herald,
    }

    logger.info("Features min15 calculadas: %s",
                {k: round(v, 4) for k, v in features.items()})
    return features


def _dragons_blue_first(blue: dict, red: dict) -> bool:
    """Heurística: si blue tiene más dragones que red, asume que tomó el primero."""
    blue_d = len(blue.get("dragons", [])) if isinstance(
        blue.get("dragons"), list) else blue.get("dragonKills", 0)
    red_d  = len(red.get("dragons",  [])) if isinstance(
        red.get("dragons"),  list) else red.get("dragonKills", 0)
    return blue_d > red_d


def _herald_blue(blue: dict) -> bool:
    """Heurística: blue tomó el heraldo si tiene riftHerald > 0."""
    return int(blue.get("riftHeraldKills", blue.get("heralds", 0))) > 0


# ── Fallback: gol.gg ──────────────────────────────────────────────────────────

def _fallback_golgg(game_id: str) -> dict | None:
    """
    Fallback: scraping básico de gol.gg.
    Retorna estructura compatible con get_live_stats o None.
    """
    try:
        url = f"https://gol.gg/game/stats/{game_id}/page-game/"
        resp = requests.get(url, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            logger.info("gol.gg respondió para gameId %s", game_id)
            # Parsing básico — gol.gg no tiene API JSON pública
            # Se deja como stub para implementar con BeautifulSoup si es necesario
            return None
    except Exception as exc:
        logger.debug("gol.gg fallback falló: %s", exc)
    return None


# ── Ejecución directa ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Usar gameId de argumento o uno de ejemplo
    game_id = sys.argv[1] if len(sys.argv) > 1 else "110853020732646396"

    print(f"\n─── TEST lolesports_api.py (gameId: {game_id}) ───────────────")
    stats = get_live_stats(game_id)
    if stats:
        print(f"Estado       : {stats['game_state']}")
        print(f"Tiempo       : {stats['game_time_s'] // 60}min {stats['game_time_s'] % 60}s")
        print(f"Blue gold    : {stats['blue']['total_gold']:,}")
        print(f"Red  gold    : {stats['red']['total_gold']:,}")
        print(f"Blue kills   : {stats['blue']['kills']}")
        print(f"Red  kills   : {stats['red']['kills']}")

        print("\n─── Intentando extract_minute15_stats … ──────────────────")
        features = extract_minute15_stats(game_id)
        if features:
            print("Variables minuto 15:")
            for k, v in features.items():
                print(f"  {k:20s}: {v:.4f}")
        else:
            print("No disponibles (partido fuera de ventana 15-25 min).")
    else:
        print("No se obtuvieron stats. El partido puede no estar en curso.")

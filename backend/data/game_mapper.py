"""
game_mapper.py — Mapea un market slug de Polymarket a un gameId real de Riot.

Ejemplo:
    slug    = "lol-t1-gen-g-2026-03-30-game1"
    game_id = get_game_id(slug)  # "110853020732646396"
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from backend.config import LOLESPORTS_SCHEDULE_URL, LEAGUE_IDS
from backend.database import get_cached_game_id, cache_game_id

logger = logging.getLogger(__name__)

# ── Aliases de equipos ─────────────────────────────────────────────────────────
# Normaliza el nombre en el slug al nombre oficial de Riot/Leaguepedia
TEAM_ALIASES: dict[str, str] = {
    # LCK
    "t1":            "T1",
    "geng":          "Gen.G",
    "gen-g":         "Gen.G",
    "gen":           "Gen.G",
    "kdf":           "Kwangdong Freecs",
    "kwangdong":     "Kwangdong Freecs",
    "drx":           "DRX",
    "kt":            "KT Rolster",
    "kt-rolster":    "KT Rolster",
    "ns":            "Nongshim RedForce",
    "nongshim":      "Nongshim RedForce",
    "dk":            "Dplus KIA",
    "dplus":         "Dplus KIA",
    "dplus-kia":     "Dplus KIA",
    "ok":            "OKSavingsBank BRION",
    "brion":         "OKSavingsBank BRION",
    "hle":           "Hanwha Life Esports",
    "hanwha":        "Hanwha Life Esports",
    "lsb":           "Liiv SANDBOX",
    "sandbox":       "Liiv SANDBOX",
    # LEC
    "g2":            "G2 Esports",
    "fnc":           "Fnatic",
    "fnatic":        "Fnatic",
    "vitality":      "Team Vitality",
    "vit":           "Team Vitality",
    "mad":           "MAD Lions KOI",
    "mad-lions":     "MAD Lions KOI",
    "sk":            "SK Gaming",
    "sk-gaming":     "SK Gaming",
    "rge":           "Rogue",
    "rogue":         "Rogue",
    "xl":            "Excel Esports",
    "excel":         "Excel Esports",
    "astralis":      "Astralis",
    "ast":           "Astralis",
    "bds":           "Team BDS",
    "team-bds":      "Team BDS",
    "karmine":       "Karmine Corp",
    "kc":            "Karmine Corp",
}

# Headers necesarios para la API de Riot Esports
SCHEDULE_HEADERS = {
    "x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z",  # clave pública conocida
}


# ── Parser de slug ─────────────────────────────────────────────────────────────

def _normalize_team(raw: str) -> str:
    """Convierte el fragmento de slug a nombre oficial."""
    key = raw.lower().strip()
    return TEAM_ALIASES.get(key, raw.title())


def parse_slug(slug: str) -> dict | None:
    """
    Parsea un slug de Polymarket y extrae los campos relevantes.

    Ejemplos de slugs válidos:
        lol-t1-gen-g-2026-03-30-game1
        lol-lck-t1-geng-game-1-2026-03-30
        will-t1-win-vs-gen-g-lck-2026-03-30

    Retorna dict con: team1, team2, date (YYYY-MM-DD), game_num, league
    o None si no se puede parsear.
    """
    slug = slug.lower()

    # Detectar liga
    league = None
    if "lck" in slug:
        league = "LCK"
    elif "lec" in slug:
        league = "LEC"

    # Extraer fecha YYYY-MM-DD
    date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", slug)
    if not date_match:
        logger.warning("No se encontró fecha en slug: %s", slug)
        return None
    date_str = date_match.group(0)

    # Extraer número de game (game1, game2, game-1, game-2, etc.)
    game_match = re.search(r"game[-_]?(\d)", slug)
    game_num = int(game_match.group(1)) if game_match else 1

    # Extraer equipos: parte del slug sin "lol-", sin fecha, sin "game-N"
    core = slug
    core = re.sub(r"lol-?", "", core)
    core = re.sub(r"lck-?|lec-?", "", core)
    core = re.sub(r"\d{4}-\d{2}-\d{2}", "", core)
    core = re.sub(r"game[-_]?\d", "", core)
    core = re.sub(r"will-|-win|-vs|-match", "", core)
    core = core.strip("-").strip()

    # Los equipos están separados por "-vs-" o simplemente "-"
    if "-vs-" in core:
        parts = core.split("-vs-")
    else:
        # Heurística: dividir a la mitad
        tokens = [t for t in core.split("-") if t]
        mid = len(tokens) // 2
        parts = ["-".join(tokens[:mid]), "-".join(tokens[mid:])]

    if len(parts) < 2:
        logger.warning("No se pudieron extraer dos equipos de: %s", slug)
        return None

    team1 = _normalize_team(parts[0].strip("-"))
    team2 = _normalize_team(parts[1].strip("-"))

    return {
        "team1":    team1,
        "team2":    team2,
        "date":     date_str,
        "game_num": game_num,
        "league":   league,
    }


# ── Consulta al schedule de LoL Esports API ────────────────────────────────────

def _fetch_schedule(league_id: str, pages: int = 3) -> list[dict]:
    """
    Descarga el schedule de una liga de Riot Esports API.
    Sigue el paginado hasta 'pages' páginas hacia atrás/adelante.
    """
    events: list[dict] = []
    page_token: str | None = None

    for _ in range(pages):
        params: dict = {"hl": "en-US", "leagueId": league_id}
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = requests.get(
                LOLESPORTS_SCHEDULE_URL,
                headers=SCHEDULE_HEADERS,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            schedule = data.get("data", {}).get("schedule", {})
            events.extend(schedule.get("events", []))
            page_token = schedule.get("pages", {}).get("newer")
            if not page_token:
                break
        except Exception as exc:
            logger.error("Error fetch schedule league %s: %s", league_id, exc)
            break

        time.sleep(0.5)

    return events


def _match_event(
    events: list[dict], team1: str, team2: str, date_str: str, game_num: int
) -> str | None:
    """
    Busca en los eventos el gameId que corresponde a los equipos y fecha.
    Tolerancia de ±1 día para cubrir diferencias de zona horaria.
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Normalizar nombres para comparación flexible
    def _norm(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    t1_norm = _norm(team1)
    t2_norm = _norm(team2)

    for event in events:
        if event.get("type") != "match":
            continue

        match = event.get("match", {})
        teams = match.get("teams", [])
        if len(teams) < 2:
            continue

        e_t1 = _norm(teams[0].get("name", ""))
        e_t2 = _norm(teams[1].get("name", ""))

        # Comprobar que los equipos coinciden (en cualquier orden)
        teams_match = (
            (t1_norm in e_t1 or e_t1 in t1_norm) and
            (t2_norm in e_t2 or e_t2 in t2_norm)
        ) or (
            (t1_norm in e_t2 or e_t2 in t1_norm) and
            (t2_norm in e_t1 or e_t1 in t2_norm)
        )
        if not teams_match:
            continue

        # Comprobar fecha (tolerancia ±1 día por zonas horarias)
        start_time_str = event.get("startTime", "")
        if start_time_str:
            try:
                event_date = datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                ).date()
                if abs((event_date - target_date).days) > 1:
                    continue
            except Exception:
                pass

        # Obtener el gameId del game N dentro del match
        games = match.get("games", [])
        # game_num es 1-indexed
        idx = min(game_num - 1, len(games) - 1)
        if games:
            game_id = games[idx].get("id")
            if game_id:
                logger.info(
                    "Match encontrado: %s vs %s (%s) → gameId=%s",
                    team1, team2, date_str, game_id,
                )
                return str(game_id)

    return None


# ── Fallback: Leaguepedia API ──────────────────────────────────────────────────

def _leaguepedia_fallback(team1: str, team2: str, date_str: str) -> str | None:
    """
    Consulta Leaguepedia (lol.fandom.com) como fallback para obtener gameId.
    Usa la Cargo API pública.
    """
    try:
        url = "https://lol.fandom.com/api.php"
        params = {
            "action":  "cargoquery",
            "tables":  "MatchSchedule=MS,MatchScheduleGame=MSG",
            "join_on": "MS.MatchId=MSG.MatchId",
            "fields":  "MSG.GameId,MS.Team1,MS.Team2,MS.DateTime_UTC",
            "where":   (
                f"(MS.Team1 LIKE '%{team1}%' OR MS.Team2 LIKE '%{team1}%') "
                f"AND (MS.Team1 LIKE '%{team2}%' OR MS.Team2 LIKE '%{team2}%') "
                f"AND MS.DateTime_UTC LIKE '{date_str}%'"
            ),
            "limit":   "5",
            "format":  "json",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("cargoquery", [])
        if results:
            game_id = results[0].get("title", {}).get("GameId")
            if game_id:
                logger.info("Leaguepedia fallback → gameId=%s", game_id)
                return game_id
    except Exception as exc:
        logger.error("Leaguepedia fallback falló: %s", exc)
    return None


# ── API pública ────────────────────────────────────────────────────────────────

def get_game_id(slug: str) -> str | None:
    """
    Mapea un market slug de Polymarket al gameId real de Riot.

    Flujo:
        1. Revisar caché SQLite.
        2. Parsear slug → equipos, fecha, game_num, liga.
        3. Consultar schedule de Riot Esports API.
        4. Buscar match por equipos + fecha.
        5. Fallback: Leaguepedia si Riot API no encuentra.
        6. Cachear resultado en SQLite.

    Args:
        slug: Market slug de Polymarket
              (ej: "lol-t1-gen-g-2026-03-30-game1")

    Returns:
        gameId como string, o None si no se encuentra.
    """
    # 1. Caché
    cached = get_cached_game_id(slug)
    if cached:
        logger.debug("Cache hit para slug %s → %s", slug, cached)
        return cached

    # 2. Parsear slug
    parsed = parse_slug(slug)
    if not parsed:
        logger.warning("No se pudo parsear slug: %s", slug)
        return None

    team1    = parsed["team1"]
    team2    = parsed["team2"]
    date_str = parsed["date"]
    game_num = parsed["game_num"]
    league   = parsed["league"]

    logger.info(
        "Buscando gameId: %s vs %s | %s | game %d | %s",
        team1, team2, date_str, game_num, league,
    )

    # 3-4. Consultar Riot API para cada liga relevante
    game_id = None
    league_ids_to_check = (
        [LEAGUE_IDS[league]] if league and league in LEAGUE_IDS
        else list(LEAGUE_IDS.values())
    )

    for league_id in league_ids_to_check:
        events = _fetch_schedule(league_id)
        game_id = _match_event(events, team1, team2, date_str, game_num)
        if game_id:
            break

    # 5. Fallback Leaguepedia
    if not game_id:
        logger.info("Riot API no encontró match, probando Leaguepedia …")
        game_id = _leaguepedia_fallback(team1, team2, date_str)

    # 6. Cachear si encontramos
    if game_id:
        cache_game_id(
            slug=slug,
            game_id=game_id,
            league=league or "",
            team1=team1,
            team2=team2,
            game_date=date_str,
        )
    else:
        logger.warning("No se encontró gameId para slug: %s", slug)

    return game_id


# ── Ejecución directa (tests básicos) ─────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    from backend.database import init_db
    init_db()

    TEST_SLUGS = [
        "lol-t1-gen-g-2026-03-30-game1",
        "lol-lck-kt-rolster-drx-2026-03-29-game2",
        "lol-lec-g2-fnatic-2026-03-29-game1",
        "lol-hle-dplus-kia-2026-03-28-game1",
        "lol-lec-vitality-mad-lions-2026-03-28-game1",
    ]

    print("\n─── TEST SLUGS ──────────────────────────────────────────────")
    ok = 0
    for slug in TEST_SLUGS:
        parsed = parse_slug(slug)
        game_id = get_game_id(slug)
        status = "✅" if game_id else "⚠️ "
        if game_id:
            ok += 1
        print(f"{status} {slug}")
        print(f"   Parsed : {parsed}")
        print(f"   GameId : {game_id or 'NO ENCONTRADO'}")
        print()

    print(f"Resultado: {ok}/{len(TEST_SLUGS)} slugs mapeados correctamente")

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
TEAM_ALIASES: dict[str, str] = {
    # LCK
    "t1":            "T1",
    "geng":          "Gen.G",
    "gen-g":         "Gen.G",
    "gen":           "Gen.G",
    "kdf":           "Kwangdong Freecs",
    "freecs":        "Kwangdong Freecs",
    "kwangdong":     "Kwangdong Freecs",
    "drx":           "Kiwoom DRX",
    "kt":            "KT Rolster",
    "kt-rolster":    "KT Rolster",
    "ns":            "Nongshim RedForce",
    "nongshim":      "Nongshim RedForce",
    "dk":            "Dplus KIA",
    "dplus":         "Dplus KIA",
    "dplus-kia":     "Dplus KIA",
    "dnf":           "DN SOOPers",
    "dn":            "DN SOOPers",
    "ok":            "OKSavingsBank BRION",
    "brion":         "BRION",
    "hle":           "Hanwha Life Esports",
    "hanwha":        "Hanwha Life Esports",
    "lsb":           "Liiv SANDBOX",
    "sandbox":       "Liiv SANDBOX",
    "fearx":         "FEARX",
    "fox":           "FEARX",
    # LCK — variantes con sufijo numérico (Polymarket añade 1/2 en slugs de serie)
    "hle1":          "Hanwha Life Esports",
    "hle2":          "Hanwha Life Esports",
    "fox1":          "FEARX",
    "fox2":          "FEARX",
    "foxy":          "FEARX",
    "bro1":          "OKSavingsBank BRION",
    "bro2":          "OKSavingsBank BRION",
    # LCK Challengers League 2026
    # getLive usa nombres como "HLE Challengers", "KRX Challengers", "T1 Academy", etc.
    # Los aliases deben ser substrings de esos nombres (normeados)
    "t1a":           "T1",          # getLive: "T1 Academy"       → norm "t1academy"
    "dkc":           "Dplus",       # getLive: "DK Challengers"   → norm "dkchallengers"
    "ktc":           "KT",          # getLive: "KT Challengers"   → norm "ktchallengers"
    "nsea":          "Nongshim",    # getLive: "Nongshim Esports Academy" → norm contiene "nongshim"
    "drxc":          "KRX",         # getLive: "KRX Challengers"  → norm "krxchallengers"
    "dnsc":          "DN",          # getLive: "DN Challengers"   → norm contiene "dn"
    "genga":         "Gen.G",       # getLive: "Gen.G Global Academy" → norm contiene "geng"
    "foxy":          "BNK",         # getLive: "BNK FearX Youth"  → norm "bnkfearxyouth"
    # LEC 2026
    "g2":            "G2 Esports",
    "fnc":           "Fnatic",
    "fnatic":        "Fnatic",
    "vit":           "Team Vitality",
    "vitality":      "Team Vitality",
    "mkoi":          "MAD Lions KOI",
    "mad":           "MAD Lions KOI",
    "mad-lions":     "MAD Lions KOI",
    "sk":            "SK Gaming",
    "rge":           "Rogue",
    "xl":            "Excel Esports",
    "ast":           "Astralis",
    "bds":           "Team BDS",
    "kc":            "Karmine Corp",
    "karmine":       "Karmine Corp",
    "gx":            "GiantX",
    "giantx":        "GiantX",
    "th":            "Team Heretics",
    "her":           "Team Heretics",
    "heretics":      "Team Heretics",
    "navi":          "Natus Vincere",
    "shft":          "Shopify Rebellion",
    # EMEA Masters 2026 — getLive usa nombres como "FF1", "BIG", "USE1", "ME1"
    "ff1":           "FF1",
    "big":           "BIG",
    "big1":          "BIG",
    "use1":          "USE1",
    "me1":           "ME1",
    "koi":           "KOI",
    "heretics":      "Team Heretics",
    "gam":           "GAM Esports",
    "fut":           "FUT Esports",
    "gam1":          "GAM Esports",
    "fut1":          "FUT Esports",
}

# Slugs de equipos LCK conocidos para detección de liga
LCK_SLUG_TOKENS = {
    "t1","geng","gen","kdf","freecs","drx","kt","ns","dk","dplus",
    "dnf","dn","brion","hle","hanwha","lsb","fearx","fox",
    # variantes con sufijo / LCK CL
    "hle1","hle2","fox1","fox2","foxy","bro1","bro2",
    "dkc","ktc","nsea","drxc","dnsc",
}
# Slugs de equipos LEC conocidos
LEC_SLUG_TOKENS = {
    "g2","fnc","fnatic","vit","vitality","mkoi","mad","sk","rge",
    "xl","ast","bds","kc","karmine","her","heretics",
    "gx","giantx","th","navi","shft",
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

    Formatos observados en Polymarket (Abril 2026):
        lol-t1-gen-g-2026-03-30-game1          (formato original esperado)
        lol-lck-t1-geng-game-1-2026-03-30
        lec-g2-esports-vs-giantx               (LEC sin fecha)
        lec-movistar-vs-fnatic                 (LEC sin fecha)
        lol-blg-vs-tes                         (LoL sin fecha ni liga)
        lol-dnfc-vs-bfxy-2025-09-23            (LoL con fecha)

    Retorna dict con: team1, team2, date (YYYY-MM-DD o None), game_num, league
    o None si no se puede parsear.
    """
    slug = slug.lower()

    # Detectar liga por prefijo explícito o por tokens de equipos conocidos
    league = None
    if "lck" in slug:
        league = "LCK"
    elif "lec" in slug:
        league = "LEC"
    else:
        tokens = set(re.split(r"[-_]", slug))
        if tokens & LCK_SLUG_TOKENS:
            league = "LCK"
        elif tokens & LEC_SLUG_TOKENS:
            league = "LEC"

    # Extraer fecha YYYY-MM-DD (opcional en los nuevos formatos)
    date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", slug)
    date_str = date_match.group(0) if date_match else datetime.now().strftime("%Y-%m-%d")
    if not date_match:
        logger.info("Slug sin fecha explícita '%s', usando fecha de hoy: %s",
                    slug, date_str)

    # Extraer número de game (game1, game2, game-1, game-2, etc.)
    game_match = re.search(r"game[-_]?(\d)", slug)
    game_num = int(game_match.group(1)) if game_match else 1

    # Extraer equipos: limpiar prefijos, fechas y ruido
    core = slug
    core = re.sub(r"^lol-", "", core)           # quitar "lol-" al inicio
    core = re.sub(r"^lec-", "", core)           # quitar "lec-" al inicio
    core = re.sub(r"^lck-", "", core)           # quitar "lck-" al inicio
    core = re.sub(r"lck-?|lec-?", "", core)     # quitar lck/lec internos
    core = re.sub(r"\d{4}-\d{2}-\d{2}", "", core)
    core = re.sub(r"game[-_]?\d", "", core)
    core = re.sub(r"will-|-win|-match", "", core)
    core = core.strip("-").strip()

    # Los equipos están separados por "-vs-" o simplemente "-"
    if "-vs-" in core:
        parts = core.split("-vs-")
    else:
        # Heurística: dividir a la mitad
        tokens = [t for t in core.split("-") if t]
        mid = max(1, len(tokens) // 2)
        parts = ["-".join(tokens[:mid]), "-".join(tokens[mid:])]

    if len(parts) < 2:
        logger.warning("No se pudieron extraer dos equipos de: %s", slug)
        return None

    raw1  = parts[0].strip("-").lower()
    raw2  = parts[1].strip("-").lower()
    team1 = _normalize_team(raw1)
    team2 = _normalize_team(raw2)

    return {
        "team1":    team1,
        "team2":    team2,
        "raw1":     raw1,
        "raw2":     raw2,
        "date":     date_str,
        "game_num": game_num,
        "league":   league,
    }


# ── getLive: única fuente fiable de gameIds ────────────────────────────────────

# Cache de getLive por ciclo — se llama UNA VEZ y se reutiliza para todos los mercados
_live_cache: list[dict] = []
_live_cache_ts: float = 0.0
LIVE_CACHE_TTL: float = 240.0   # válido por 4 minutos (un ciclo completo)


def refresh_live_cache() -> None:
    """Llama a getLive UNA vez y guarda el resultado. Llamar al inicio de cada ciclo."""
    global _live_cache, _live_cache_ts
    try:
        resp = requests.get(
            "https://esports-api.lolesports.com/persisted/gw/getLive",
            headers=SCHEDULE_HEADERS,
            params={"hl": "en-US"},
            timeout=15,
        )
        resp.raise_for_status()
        _live_cache = resp.json().get("data", {}).get("schedule", {}).get("events", [])
        _live_cache_ts = time.time()
        logger.info("getLive cache: %d partidos en vivo.", len(_live_cache))
    except Exception as exc:
        logger.error("Error refreshing live cache: %s", exc)
        _live_cache = []


def _get_live_game_id(team1: str, team2: str, league: str | None, raw1: str = "", raw2: str = "") -> str | None:
    """
    Consulta getLive para encontrar el gameId de un partido en curso.
    Es la UNICA fuente que retorna gameIds reales (getSchedule siempre devuelve []).

    Retorna el gameId del game en estado 'inProgress' o 'paused', o None.
    """
    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    t1 = _norm(team1)
    t2 = _norm(team2)
    r1 = _norm(raw1)
    r2 = _norm(raw2)

    try:
        # Usar cache del ciclo — NO hacer HTTP request por cada mercado
        if time.time() - _live_cache_ts > LIVE_CACHE_TTL:
            refresh_live_cache()
        events = _live_cache

        if not events:
            logger.info("getLive: sin partidos en vivo ahora.")
            return None

        live_teams = []
        for event in events:
            match = event.get("match", {})
            teams = match.get("teams", [])
            if len(teams) >= 2:
                live_teams.append(
                    f"{teams[0].get('name','?')} vs {teams[1].get('name','?')} "
                    f"[{event.get('league',{}).get('slug','?')}]"
                )

            # Filtrar por liga si conocemos cuál es
            if league:
                event_league = event.get("league", {}).get("slug", "").upper()
                if league not in event_league and event_league not in league:
                    continue

            if len(teams) < 2:
                continue

            e_t1 = _norm(teams[0].get("name", ""))
            e_t2 = _norm(teams[1].get("name", ""))
            def _m(cand: str, raw: str, et: str) -> bool:
                return cand in et or et in cand or (bool(raw) and raw in et)

            teams_match = (
                _m(t1, r1, e_t1) and _m(t2, r2, e_t2)
            ) or (
                _m(t1, r1, e_t2) and _m(t2, r2, e_t1)
            )
            if not teams_match:
                continue

            # Buscar el game activo (inProgress o paused)
            for game in match.get("games", []):
                state = game.get("state", "")
                gid = game.get("id")
                if gid and state in ("inProgress", "paused"):
                    logger.info(
                        "getLive: %s vs %s → gameId=%s (state=%s)",
                        team1, team2, gid, state,
                    )
                    return str(gid)

            # Partido encontrado pero no activo aún
            logger.info(
                "getLive: %s vs %s encontrado pero sin game activo (scheduled/completed).",
                team1, team2,
            )
            return None

        # No se encontró el partido en getLive — loguear qué hay en vivo
        logger.info(
            "getLive: %s vs %s NO encontrado. Partidos en vivo ahora: %s",
            team1, team2,
            live_teams if live_teams else "ninguno",
        )

    except Exception as exc:
        logger.error("Error getLive: %s", exc)

    return None


# ── Fallback: Leaguepedia API ──────────────────────────────────────────────────

def _leaguepedia_fallback(team1: str, team2: str, date_str: str) -> str | None:
    """
    Consulta Leaguepedia (lol.fandom.com) como fallback para obtener el
    RiotGameId numérico (no el GameId de página wiki).
    """
    try:
        url = "https://lol.fandom.com/api.php"
        # Intentar con fecha exacta primero, luego sin fecha (pre-partido)
        for date_filter in [f"AND MS.DateTime_UTC LIKE '{date_str}%'", ""]:
            params = {
                "action":  "cargoquery",
                "tables":  "MatchSchedule=MS,MatchScheduleGame=MSG",
                "join_on": "MS.MatchId=MSG.MatchId",
                "fields":  "MSG.RiotGameId,MSG.GameId,MS.Team1,MS.Team2,MS.DateTime_UTC",
                "where":   (
                    f"(MS.Team1 LIKE '%{team1}%' OR MS.Team2 LIKE '%{team1}%') "
                    f"AND (MS.Team1 LIKE '%{team2}%' OR MS.Team2 LIKE '%{team2}%') "
                    + date_filter
                ),
                "order_by": "MS.DateTime_UTC DESC",
                "limit":    "5",
                "format":   "json",
            }
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("cargoquery", [])
            for row in results:
                title = row.get("title", {})
                # RiotGameId es el numérico real para feed.lolesports.com
                riot_id = title.get("RiotGameId", "").strip()
                if riot_id and riot_id.isdigit():
                    logger.info("Leaguepedia fallback → RiotGameId=%s", riot_id)
                    return riot_id
                # Fallback al GameId de wiki si no hay RiotGameId todavía
                wiki_id = title.get("GameId", "").strip()
                if wiki_id:
                    logger.warning(
                        "Leaguepedia: solo GameId wiki disponible (partido no empezó?): %s",
                        wiki_id,
                    )
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

    # 3. getLive — única fuente fiable de gameIds en tiempo real
    # Si el partido no está live, retorna None inmediatamente (sin más API calls)
    game_id = _get_live_game_id(team1, team2, league,
                                raw1=parsed.get("raw1", ""),
                                raw2=parsed.get("raw2", ""))

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

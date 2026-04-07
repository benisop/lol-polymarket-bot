"""
verify_pipeline.py — Prueba end-to-end con partidos LCK reales ya jugados.

1. Obtiene un RiotGameId numérico de Leaguepedia (partido completado)
2. Llama al feed API con ese gameId
3. Extrae stats del minuto 15
4. Corre el modelo de predicción
5. Compara con resultado real

Demuestra que TODA la cadena funciona.
"""
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(message)s")

import requests
from backend.model.predict import predict_win_probability
from backend.data.lolesports_api import extract_minute15_stats

HEADERS = {"x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"}

def get_recent_lck_game_ids(n: int = 10) -> list[dict]:
    """
    Obtiene RiotGameIds numéricos de partidos LCK recientes.
    Usa ScoreboardGames que tiene RiotGameId poblado para partidos jugados.
    """
    url = "https://lol.fandom.com/api.php"
    games = []

    # Intentar con ScoreboardGames (más confiable para RiotGameId)
    for tournament in ["%LCK%2026%", "%LCK%2025%"]:
        params = {
            "action":   "cargoquery",
            "tables":   "ScoreboardGames=SG",
            "fields":   "SG.RiotGameId,SG.Team1,SG.Team2,SG.Winner,SG.DateTime_UTC,SG.Tournament",
            "where":    f"SG.Tournament LIKE '{tournament}' AND SG.RiotGameId IS NOT NULL AND SG.RiotGameId != ''",
            "order_by": "SG.DateTime_UTC DESC",
            "limit":    str(n),
            "format":   "json",
        }
        resp = requests.get(url, params=params, timeout=15)
        results = resp.json().get("cargoquery", [])
        for r in results:
            t = r.get("title", {})
            riot_id = t.get("RiotGameId", "").strip()
            if riot_id and riot_id.isdigit():
                games.append({
                    "gameId":     riot_id,
                    "team1":      t.get("Team1", "?"),
                    "team2":      t.get("Team2", "?"),
                    "winner":     t.get("Winner", "?"),
                    "win_team":   "",
                    "date":       (t.get("DateTime UTC") or "")[:10],
                    "tournament": t.get("Tournament", ""),
                })
        if games:
            print(f"  Encontrados en {tournament}: {len(games)}")
            break

    return games


def test_game(game: dict) -> dict:
    """Corre el pipeline completo sobre un partido real."""
    gid    = game["gameId"]
    team1  = game["team1"]
    team2  = game["team2"]
    winner = game["winner"]  # "1" = team1 ganó, "2" = team2 ganó

    print(f"\n{'='*60}")
    print(f"Partido: {team1} vs {team2} | {game['date']}")
    print(f"GameId : {gid}")
    print(f"Ganador real: {'Team1 ('+team1+')' if winner=='1' else 'Team2 ('+team2+')'}")

    # 1. Feed API → stats min15
    features = extract_minute15_stats(gid)
    if not features:
        print("  ❌ Feed API: no stats disponibles (partido muy antiguo o API no responde)")
        return {"ok": False}

    print(f"  ✅ Feed API OK — goldDiff15={features.get('goldrelat15',0):.0f} "
          f"killsDiff15={features.get('killsrelat15',0):.1f}")

    # 2. Modelo → probabilidad
    p_model = predict_win_probability(features)
    pred_winner = "Team1" if p_model >= 0.5 else "Team2"
    correct = (pred_winner == "Team1" and winner == "1") or \
              (pred_winner == "Team2" and winner == "2")

    print(f"  ✅ Modelo: P(team1 gana)={p_model:.2%} → predice {pred_winner}")
    print(f"  {'✅ CORRECTO' if correct else '❌ INCORRECTO'}")

    return {"ok": True, "correct": correct, "p_model": p_model}


# ── Main ──────────────────────────────────────────────────────────────────────
print("Buscando partidos LCK 2026 con RiotGameId en Leaguepedia...")
games = get_recent_lck_game_ids(15)
print(f"Encontrados: {len(games)} partidos con RiotGameId numérico")

if not games:
    print("\n⚠️  Leaguepedia no tiene RiotGameIds para LCK 2026 todavía.")
    print("Probando con LCK 2025...")
    url = "https://lol.fandom.com/api.php"
    params = {
        "action":   "cargoquery",
        "tables":   "MatchSchedule=MS,MatchScheduleGame=MSG",
        "join_on":  "MS.MatchId=MSG.MatchId",
        "fields":   "MSG.RiotGameId,MS.Team1,MS.Team2,MS.Winner,MS.DateTime_UTC",
        "where":    "MS.Tournament LIKE '%LCK%2025%' AND MSG.RiotGameId IS NOT NULL AND MSG.RiotGameId != ''",
        "order_by": "MS.DateTime_UTC DESC",
        "limit":    "10",
        "format":   "json",
    }
    resp = requests.get(url, params=params, timeout=15)
    results = resp.json().get("cargoquery", [])
    for r in results:
        t = r.get("title", {})
        riot_id = t.get("RiotGameId", "").strip()
        if riot_id and riot_id.isdigit():
            games.append({
                "gameId":   riot_id,
                "team1":    t.get("Team1", "?"),
                "team2":    t.get("Team2", "?"),
                "winner":   t.get("Winner", "?"),
                "win_team": "",
                "date":     t.get("DateTime UTC", "")[:10],
            })
    print(f"LCK 2025: {len(games)} partidos con RiotGameId")

# Probar los primeros 5
results = []
for game in games[:5]:
    r = test_game(game)
    if r["ok"]:
        results.append(r)

print(f"\n{'='*60}")
print(f"RESUMEN: {len(results)} partidos probados via feed API")
if results:
    correct = sum(1 for r in results if r["correct"])
    print(f"  Predicciones correctas: {correct}/{len(results)} = {correct/len(results):.0%}")
    print(f"  ✅ Pipeline end-to-end FUNCIONA" if results else "")
else:
    print("  ⚠️  Feed API no retornó stats (partidos históricos no disponibles)")
    print("  → El pipeline se verificará cuando DK vs NS empiece mañana 8AM")

"""Verifica partidos en vivo ahora mismo via getLive API."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

HEADERS = {"x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"}

resp = requests.get(
    "https://esports-api.lolesports.com/persisted/gw/getLive",
    headers=HEADERS,
    params={"hl": "en-US"},
    timeout=15,
)
data = resp.json()
events = data.get("data", {}).get("schedule", {}).get("events", [])
print(f"Partidos en vivo: {len(events)}")
for e in events:
    m = e.get("match", {})
    teams = [t.get("name") for t in m.get("teams", [])]
    league = e.get("league", {}).get("name", "?")
    for g in m.get("games", []):
        gid   = g.get("id")
        state = g.get("state")
        print(f"  [{league}] {teams} | gameId={gid} | state={state}")

# Mostrar próximos eventos LCK (unscheduled/inProgress)
print()
all_events = []
page_token = None
for _ in range(10):
    params = {"hl": "en-US", "leagueId": "98767991310872058"}
    if page_token:
        params["pageToken"] = page_token
    resp2 = requests.get(
        "https://esports-api.lolesports.com/persisted/gw/getSchedule",
        headers=HEADERS, params=params, timeout=15,
    )
    sched = resp2.json().get("data", {}).get("schedule", {})
    all_events.extend(sched.get("events", []))
    page_token = sched.get("pages", {}).get("newer")
    if not page_token:
        break

# Filtrar próximos (unstarted o inProgress)
upcoming = [e for e in all_events if e.get("state") in ("unstarted", "inProgress")]
print(f"Próximos partidos LCK ({len(upcoming)} encontrados):")
for e in upcoming[:10]:
    m     = e.get("match", {})
    teams = [t.get("name") for t in m.get("teams", [])]
    start = e.get("startTime", "")[:16]
    state = e.get("state", "?")
    games = m.get("games", [])
    gids  = [g.get("id") for g in games]
    print(f"  {start} | {state:10} | {teams} | gameIds={gids}")

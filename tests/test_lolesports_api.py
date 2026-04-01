"""
tests/test_lolesports_api.py — Tests de game_mapper y lolesports_api.

Ejecutar:
    pytest tests/test_lolesports_api.py -v
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.data.game_mapper import parse_slug, _normalize_team, get_game_id
from backend.data.lolesports_api import (
    get_live_stats, extract_minute15_stats, _compute_features, _find_minute15_frame,
)


# ══════════════════════════════════════════════════════════════════════════════
# Tests de parse_slug
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("slug,expected", [
    (
        # Sin "lck"/"lec" explícito en el slug → league=None es correcto
        "lol-t1-gen-g-2026-03-30-game1",
        {"date": "2026-03-30", "game_num": 1, "league": None},
    ),
    (
        "lol-lck-kt-rolster-drx-2026-03-29-game2",
        {"date": "2026-03-29", "game_num": 2, "league": "LCK"},
    ),
    (
        "lol-lec-g2-fnatic-2026-03-28-game1",
        {"date": "2026-03-28", "game_num": 1, "league": "LEC"},
    ),
])
def test_parse_slug_fecha_y_game(slug, expected):
    result = parse_slug(slug)
    assert result is not None, f"parse_slug retornó None para: {slug}"
    assert result["date"]     == expected["date"]
    assert result["game_num"] == expected["game_num"]
    assert result["league"]   == expected["league"]


def test_parse_slug_sin_fecha():
    # Nuevo formato real de Polymarket: slugs sin fecha usan fecha de hoy
    result = parse_slug("lec-g2-esports-vs-giantx")
    assert result is not None
    assert result["league"] == "LEC"
    assert result["date"] is not None   # usa fecha de hoy como fallback


def test_parse_slug_formato_lec_vs():
    # "lec-movistar-vs-fnatic" — formato real observado en Abril 2026
    result = parse_slug("lec-movistar-vs-fnatic")
    assert result is not None
    assert result["league"] == "LEC"
    # equipos extraídos
    assert result["team1"] != ""
    assert result["team2"] != ""


def test_parse_slug_detecta_liga_lck():
    result = parse_slug("lol-lck-t1-drx-2026-03-30-game1")
    assert result["league"] == "LCK"


def test_parse_slug_detecta_liga_lec():
    result = parse_slug("lol-lec-g2-fnatic-2026-03-30-game1")
    assert result["league"] == "LEC"


# ── Aliases ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("t1",     "T1"),
    ("gen-g",  "Gen.G"),
    ("geng",   "Gen.G"),
    ("g2",     "G2 Esports"),
    ("fnc",    "Fnatic"),
    ("hle",    "Hanwha Life Esports"),
    ("kdf",    "Kwangdong Freecs"),
    ("dk",     "Dplus KIA"),
])
def test_team_aliases(raw, expected):
    assert _normalize_team(raw) == expected


# ══════════════════════════════════════════════════════════════════════════════
# Tests de get_game_id (con mock para no llamar a APIs reales)
# ══════════════════════════════════════════════════════════════════════════════

MOCK_SCHEDULE = {
    "data": {
        "schedule": {
            "events": [
                {
                    "type": "match",
                    "startTime": "2026-03-30T07:00:00Z",
                    "match": {
                        "teams": [
                            {"name": "T1"},
                            {"name": "Gen.G"},
                        ],
                        "games": [
                            {"id": "MOCK_GAME_ID_001"},
                            {"id": "MOCK_GAME_ID_002"},
                        ],
                    },
                }
            ],
            "pages": {},
        }
    }
}


@patch("backend.data.game_mapper.get_cached_game_id", return_value=None)
@patch("backend.data.game_mapper.cache_game_id")
@patch("requests.get")
def test_get_game_id_lck_match(mock_get, mock_cache, mock_cached):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: MOCK_SCHEDULE,
    )
    result = get_game_id("lol-t1-gen-g-2026-03-30-game1")
    assert result == "MOCK_GAME_ID_001"
    mock_cache.assert_called_once()


@patch("backend.data.game_mapper.get_cached_game_id", return_value="CACHED_ID")
def test_get_game_id_cache_hit(mock_cached):
    result = get_game_id("lol-t1-gen-g-2026-03-30-game1")
    assert result == "CACHED_ID"


@patch("backend.data.game_mapper.get_cached_game_id", return_value=None)
@patch("requests.get", side_effect=Exception("network error"))
def test_get_game_id_network_error(mock_get, mock_cached):
    result = get_game_id("lol-t1-gen-g-2026-03-30-game1")
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Tests de lolesports_api
# ══════════════════════════════════════════════════════════════════════════════

MOCK_WINDOW_RESPONSE = {
    "gameMetadata": {
        "patchVersion": "14.6",
        "gameStartTime": "2026-03-30T07:00:00Z",
        "blueFirstDragon": True,
        "blueFirstBlood": True,
        "blueFirstHerald": False,
    },
    "frames": [
        {
            "rfc822Timestamp": "2026-03-30T07:16:00Z",  # minuto 16
            "gameState": "in_game",
            "blueTeam": {
                "totalGold": 28500,
                "kills": 8,
                "dragonKills": 1,
                "towerKills": 2,
                "totalCS": 340,
                "totalXP": 42000,
            },
            "redTeam": {
                "totalGold": 24000,
                "kills": 4,
                "dragonKills": 0,
                "towerKills": 0,
                "totalCS": 310,
                "totalXP": 38000,
            },
        }
    ],
}


@patch("requests.get")
def test_get_live_stats_ok(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: MOCK_WINDOW_RESPONSE,
    )
    # Resetear rate limit
    from backend.data.lolesports_api import _last_request
    _last_request.clear()

    stats = get_live_stats("MOCK_GAME_ID")
    assert stats is not None
    assert "game_state" in stats
    assert stats["game_state"] == "in_game"
    assert stats["blue"]["total_gold"] == 28500
    assert stats["red"]["kills"] == 4


@patch("requests.get")
def test_get_live_stats_404(mock_get):
    mock_get.return_value = MagicMock(status_code=404)
    from backend.data.lolesports_api import _last_request
    _last_request.clear()
    stats = get_live_stats("GAME_NOT_FOUND")
    assert stats is None


def test_compute_features_ventaja_blue():
    """Equipo azul con ventaja clara → features coherentes."""
    frame = {
        "blueTeam": {
            "totalGold": 30000, "kills": 10, "totalCS": 350,
            "totalXP": 45000, "dragonKills": 2,
        },
        "redTeam": {
            "totalGold": 24000, "kills": 4, "totalCS": 290,
            "totalXP": 38000, "dragonKills": 0,
        },
    }
    metadata = {"blueFirstBlood": True, "blueFirstDragon": True, "blueFirstHerald": False}
    features = _compute_features(frame, metadata)

    assert features is not None
    assert features["goldrelat15"]  > 0      # ventaja en oro
    assert features["killsrelat15"] > 0.5    # más kills
    assert features["firstdragon"]  == 1
    assert features["firstblood"]   == 1
    assert features["firstherald"]  == 0
    assert 0.0 <= features["killsrelat15"] <= 1.0


def test_compute_features_desventaja_blue():
    """Equipo azul en desventaja → goldrelat negativo."""
    frame = {
        "blueTeam": {
            "totalGold": 22000, "kills": 3, "totalCS": 280,
            "totalXP": 35000, "dragonKills": 0,
        },
        "redTeam": {
            "totalGold": 30000, "kills": 9, "totalCS": 360,
            "totalXP": 46000, "dragonKills": 2,
        },
    }
    metadata = {}
    features = _compute_features(frame, metadata)
    assert features is not None
    assert features["goldrelat15"]  < 0
    assert features["killsrelat15"] < 0.5


def test_find_minute15_frame_selecciona_correcto():
    """_find_minute15_frame devuelve el frame más cercano al min 15."""
    frames = [
        {"rfc822Timestamp": "2026-03-30T07:10:00Z", "gameState": "in_game"},  # min 10
        {"rfc822Timestamp": "2026-03-30T07:15:30Z", "gameState": "in_game"},  # min 15.5
        {"rfc822Timestamp": "2026-03-30T07:20:00Z", "gameState": "in_game"},  # min 20
    ]
    metadata = {"gameStartTime": "2026-03-30T07:00:00Z"}
    frame = _find_minute15_frame(frames, metadata)
    assert frame is not None
    assert "07:15" in frame["rfc822Timestamp"]


@patch("requests.get")
def test_extract_minute15_antes_del_min15(mock_get):
    """Si el partido tiene 10 minutos → retorna None."""
    response = {
        "gameMetadata": {"gameStartTime": "2026-03-30T07:00:00Z"},
        "frames": [
            {
                "rfc822Timestamp": "2026-03-30T07:10:00Z",
                "gameState": "in_game",
                "blueTeam": {"totalGold": 15000, "kills": 2, "totalCS": 180, "totalXP": 22000},
                "redTeam":  {"totalGold": 14000, "kills": 2, "totalCS": 175, "totalXP": 21000},
            }
        ],
    }
    mock_get.return_value = MagicMock(status_code=200, json=lambda: response)
    from backend.data.lolesports_api import _last_request
    _last_request.clear()
    result = extract_minute15_stats("EARLY_GAME")
    assert result is None


@patch("requests.get")
def test_extract_minute15_despues_del_min25(mock_get):
    """Si el partido tiene 30 minutos → retorna None (demasiado tarde)."""
    response = {
        "gameMetadata": {"gameStartTime": "2026-03-30T07:00:00Z"},
        "frames": [
            {
                "rfc822Timestamp": "2026-03-30T07:30:00Z",
                "gameState": "in_game",
                "blueTeam": {"totalGold": 50000, "kills": 15, "totalCS": 600, "totalXP": 80000},
                "redTeam":  {"totalGold": 45000, "kills": 10, "totalCS": 550, "totalXP": 75000},
            }
        ],
    }
    mock_get.return_value = MagicMock(status_code=200, json=lambda: response)
    from backend.data.lolesports_api import _last_request
    _last_request.clear()
    result = extract_minute15_stats("LATE_GAME")
    assert result is None

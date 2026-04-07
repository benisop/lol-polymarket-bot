"""
Diagnóstico: muestra los mercados LoL que encuentra el bot y por qué se filtran.
Usa get_lol_markets() para reflejar exactamente lo que hace el scheduler.
"""
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")

from backend.polymarket.markets import (
    get_lol_markets, _is_lol_market, _parse_market,
    _fetch_events_markets, GAMMA_TAGS,
)

# ── 1. Raw desde events API ────────────────────────────────────────────────────
print("=== RAW desde /events ===")
for tag in GAMMA_TAGS:
    raw = _fetch_events_markets(tag)
    print(f"tag={tag}: {len(raw)} markets en events")
    for m in raw[:30]:
        slug = (m.get("slug") or "")[:60]
        liq  = float(m.get("liquidity", 0) or 0)
        closed = m.get("closed", False)
        end  = m.get("endDate", "")[:10]
        q    = (m.get("question") or "")[:70]
        is_lol = _is_lol_market(m)
        print(f"  {'✓' if is_lol else '✗'} {slug}")
        print(f"    liq=${liq:.0f} closed={closed} end={end}")
        print(f"    q: {q}")
    print()

# ── 2. Resultado final del bot ─────────────────────────────────────────────────
print("=== RESULTADO FINAL get_lol_markets() ===")
markets = get_lol_markets(min_liquidity=0)   # sin filtro de liquidez para ver todo
print(f"Mercados LoL encontrados (sin filtro liquidez): {len(markets)}")
for m in markets[:20]:
    print(f"  slug: {m['slug'][:60]}")
    print(f"  liq=${m['liquidity']:.0f}  closed={m['closed']}  mins={m['minutes_to_close']}")
    print(f"  q: {m['question'][:70]}")
    print()

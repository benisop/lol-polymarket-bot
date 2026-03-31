"""
oracle_elixir.py — Descarga y procesa datos históricos de Oracle's Elixir.

Adaptado de HerrKurz/Esports_Data_Pipeline. Sin Elasticsearch ni AWS.
Fuente: oracleselixir.com (CSVs anuales públicos, Google Drive mirror).

Uso:
    from backend.data.oracle_elixir import get_training_data
    df = get_training_data()
    print(df.shape, df['result'].value_counts())
"""

import io
import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── URLs de descarga ───────────────────────────────────────────────────────────
# Oracle's Elixir publica CSVs anuales en S3 público
S3_BASE = (
    "https://oracleselixir-downloadable-match-data.s3-us-west-2.amazonaws.com"
)
YEARS = [2021, 2022, 2023, 2024, 2025]

# Caché local para no re-descargar en cada run
CACHE_DIR = Path("data/oracle_elixir_cache")

# ── Columnas necesarias ────────────────────────────────────────────────────────
RAW_COLS = [
    "gameid", "league", "year", "result", "position",
    "datacompleteness",
    "golddiffat15", "goldat15",
    "xpdiffat15",   "xpat15",
    "csdiffat15",   "csat15",
    "killsat15",    "opp_killsat15",
    "firstblood",   "firstdragon", "firstherald",
]

FEATURE_COLS = [
    "goldrelat15", "xprelat15", "firstdragon",
    "csrelat15",   "killsrelat15", "firstblood", "firstherald",
]

TARGET_COL = "result"


# ── Descarga ───────────────────────────────────────────────────────────────────

def _csv_url(year: int) -> str:
    return f"{S3_BASE}/{year}_LoL_esports_match_data_from_OraclesElixir.csv"


def _cache_path(year: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{year}.csv"


def _download_year(year: int, force: bool = False) -> pd.DataFrame:
    """Descarga (o carga de caché) el CSV de un año. Retorna DataFrame raw."""
    path = _cache_path(year)

    if path.exists() and not force:
        logger.info("Cargando caché local: %s", path)
        return pd.read_csv(path, low_memory=False)

    url = _csv_url(year)
    logger.info("Descargando %s …", url)

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code == 200:
                path.write_bytes(resp.content)
                return pd.read_csv(io.BytesIO(resp.content), low_memory=False)
            elif resp.status_code == 404:
                logger.warning("Año %d no disponible aún (404).", year)
                return pd.DataFrame()
            else:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
        except Exception as exc:
            wait = 2 ** attempt
            logger.warning("Intento %d fallido para %d: %s — reintento en %ds",
                           attempt + 1, year, exc, wait)
            time.sleep(wait)

    logger.error("No se pudo descargar el año %d.", year)
    return pd.DataFrame()


# ── Procesamiento ──────────────────────────────────────────────────────────────

def _process(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra y transforma un DataFrame raw de Oracle's Elixir.

    Filtros:
        - position == 'team'       (una fila por equipo por partido)
        - league in ['LCK', 'LEC']
        - datacompleteness == 'complete'

    Construye las 7 variables relativas del modelo:
        goldrelat15  = golddiffat15 / goldat15
        xprelat15    = xpdiffat15   / xpat15
        csrelat15    = csdiffat15   / csat15
        killsrelat15 = killsat15    / (killsat15 + opp_killsat15)
        firstdragon  (ya binaria 0/1)
        firstblood   (ya binaria 0/1)
        firstherald  (ya binaria 0/1)
    """
    if df_raw.empty:
        return pd.DataFrame()

    # Normalizar nombres de columnas (algunos años usan mayúsculas)
    df_raw.columns = df_raw.columns.str.strip().str.lower()

    # Columnas mínimas necesarias
    needed = [c for c in RAW_COLS if c != "year"]  # year a veces falta
    missing = [c for c in needed if c not in df_raw.columns]
    if missing:
        logger.warning("Columnas faltantes en datos raw: %s", missing)
        # Intentar sin las faltantes
        available = [c for c in needed if c in df_raw.columns]
    else:
        available = needed

    df = df_raw[available].copy()

    # ── Filtros ───────────────────────────────────────────────────────────────
    if "position" in df.columns:
        df = df[df["position"] == "team"]
    if "league" in df.columns:
        df = df[df["league"].isin(["LCK", "LEC"])]
    if "datacompleteness" in df.columns:
        df = df[df["datacompleteness"] == "complete"]

    if df.empty:
        return df

    # ── Conversión numérica ───────────────────────────────────────────────────
    numeric_cols = [
        "golddiffat15", "goldat15",
        "xpdiffat15",   "xpat15",
        "csdiffat15",   "csat15",
        "killsat15",    "opp_killsat15",
        "firstblood",   "firstdragon",  "firstherald",
        "result",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Variables relativas ───────────────────────────────────────────────────
    eps = 1e-6  # evitar división por cero

    if "golddiffat15" in df.columns and "goldat15" in df.columns:
        df["goldrelat15"] = df["golddiffat15"] / (df["goldat15"] + eps)

    if "xpdiffat15" in df.columns and "xpat15" in df.columns:
        df["xprelat15"] = df["xpdiffat15"] / (df["xpat15"] + eps)

    if "csdiffat15" in df.columns and "csat15" in df.columns:
        df["csrelat15"] = df["csdiffat15"] / (df["csat15"] + eps)

    if "killsat15" in df.columns and "opp_killsat15" in df.columns:
        total_kills = df["killsat15"] + df["opp_killsat15"] + eps
        df["killsrelat15"] = df["killsat15"] / total_kills

    # ── Selección final ───────────────────────────────────────────────────────
    keep = [TARGET_COL, "gameid", "league"] + FEATURE_COLS
    keep = [c for c in keep if c in df.columns]
    df = df[keep]

    # ── Drop NaN en features y target ─────────────────────────────────────────
    feature_cols_present = [c for c in FEATURE_COLS if c in df.columns]
    df = df.dropna(subset=[TARGET_COL] + feature_cols_present)
    df[TARGET_COL] = df[TARGET_COL].astype(int)

    return df.reset_index(drop=True)


# ── API pública ────────────────────────────────────────────────────────────────

def get_training_data(
    years: list[int] | None = None,
    force_download: bool = False,
) -> pd.DataFrame:
    """
    Descarga y procesa datos LCK + LEC de Oracle's Elixir.

    Args:
        years: Lista de años a cargar. Default: [2021, 2022, 2023, 2024, 2025].
        force_download: Si True, ignora caché y re-descarga.

    Returns:
        DataFrame con columnas:
            result, gameid, league,
            goldrelat15, xprelat15, firstdragon, csrelat15,
            killsrelat15, firstblood, firstherald

    Raises:
        ValueError: Si el DataFrame resultante está vacío.
    """
    if years is None:
        years = YEARS

    frames: list[pd.DataFrame] = []
    for year in years:
        raw = _download_year(year, force=force_download)
        processed = _process(raw)
        if not processed.empty:
            processed["year"] = year
            frames.append(processed)
            logger.info("Año %d → %d filas (team-level LCK/LEC completo)",
                        year, len(processed))

    if not frames:
        raise ValueError(
            "No se obtuvieron datos. Revisa conexión a Oracle's Elixir."
        )

    df = pd.concat(frames, ignore_index=True)

    # Informe
    logger.info(
        "Dataset final: %d filas | result: %s",
        len(df), df["result"].value_counts().to_dict(),
    )
    return df


# ── Ejecución directa ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    df = get_training_data()
    print("\n─── RESUMEN DATASET ───────────────────────────────────────────")
    print(f"Shape:   {df.shape}")
    print(f"Ligas:   {df['league'].value_counts().to_dict()}")
    print(f"Result:  {df['result'].value_counts().to_dict()}")
    print(f"Years:   {sorted(df['year'].unique())}")
    print("\nPrimeras filas:")
    print(df[["year", "league", "result"] + FEATURE_COLS].head(10).to_string())
    print("\nEstadísticas descriptivas:")
    print(df[FEATURE_COLS].describe().round(4).to_string())

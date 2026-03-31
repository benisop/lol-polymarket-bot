"""
predict.py — Carga model.pkl y retorna P(win) dado stats del minuto 15.

Uso:
    from backend.model.predict import predict_win_probability

    stats = {
        "goldrelat15":  0.05,
        "xprelat15":    0.03,
        "firstdragon":  1,
        "csrelat15":    0.02,
        "killsrelat15": 0.60,
        "firstblood":   1,
        "firstherald":  0,
    }
    prob = predict_win_probability(stats)  # float en [0.0, 1.0]
"""

import logging
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from backend.config import MODEL_PATH
from backend.data.oracle_elixir import FEATURE_COLS

logger = logging.getLogger(__name__)


class ModelNotFoundError(Exception):
    """Se lanza cuando model.pkl no existe. Ejecutar scripts/train_model.py primero."""


@lru_cache(maxsize=1)
def _load_model() -> dict:
    """
    Carga model.pkl una sola vez y lo cachea en memoria.
    Retorna dict con claves 'model' y 'feature_cols'.
    """
    path = Path(MODEL_PATH)
    if not path.exists():
        raise ModelNotFoundError(
            f"No se encontró {path}. "
            "Ejecuta primero: python scripts/train_model.py"
        )
    payload = joblib.load(path)
    logger.info("Modelo cargado desde %s", path)
    return payload


def predict_win_probability(stats: dict) -> float:
    """
    Predice la probabilidad de ganar el partido dado stats del minuto 15.

    Args:
        stats: dict con las 7 variables del modelo:
            goldrelat15, xprelat15, firstdragon, csrelat15,
            killsrelat15, firstblood, firstherald

    Returns:
        float en [0.0, 1.0] — probabilidad de que el equipo gane.

    Raises:
        ModelNotFoundError: si model.pkl no existe.
        ValueError: si faltan features requeridas.
    """
    payload = _load_model()
    model = payload["model"]
    feature_cols: list[str] = payload.get("feature_cols", FEATURE_COLS)

    # Validar que estén todas las features
    missing = [f for f in feature_cols if f not in stats]
    if missing:
        raise ValueError(f"Faltan features en el dict de stats: {missing}")

    X = pd.DataFrame([{col: stats[col] for col in feature_cols}])
    prob: float = float(model.predict_proba(X)[0][1])

    logger.debug(
        "Predicción: %.4f | inputs: %s",
        prob,
        {k: round(v, 4) for k, v in stats.items() if k in feature_cols},
    )
    return prob


def reload_model() -> None:
    """Fuerza recarga del modelo desde disco (útil si se re-entrena en runtime)."""
    _load_model.cache_clear()
    _load_model()
    logger.info("Modelo recargado desde disco.")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    # Ejemplo: equipo con ventaja clara al min 15
    ejemplo = {
        "goldrelat15":  0.08,   # 8% más oro
        "xprelat15":    0.05,
        "firstdragon":  1,
        "csrelat15":    0.04,
        "killsrelat15": 0.65,   # 65% de los kills totales
        "firstblood":   1,
        "firstherald":  1,
    }
    prob = predict_win_probability(ejemplo)
    print(f"P(win) con ventaja clara al min 15: {prob:.4f} ({prob:.1%})")

    # Ejemplo: partido parejo
    parejo = {
        "goldrelat15":  0.01,
        "xprelat15":    0.00,
        "firstdragon":  0,
        "csrelat15":   -0.01,
        "killsrelat15": 0.50,
        "firstblood":   0,
        "firstherald":  1,
    }
    prob2 = predict_win_probability(parejo)
    print(f"P(win) partido parejo al min 15:    {prob2:.4f} ({prob2:.1%})")

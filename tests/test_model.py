"""
tests/test_model.py — Valida accuracy del modelo entrenado y predict.py.

Ejecutar:
    pytest tests/test_model.py -v

Requiere model.pkl generado previamente con:
    python scripts/train_model.py
"""

import pytest
import pandas as pd
import numpy as np

from backend.data.oracle_elixir import get_training_data, FEATURE_COLS, TARGET_COL
from backend.model.predict import predict_win_probability, ModelNotFoundError


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dataset():
    """Carga el dataset completo una sola vez para todos los tests."""
    return get_training_data()


@pytest.fixture(scope="module")
def test_split(dataset):
    """Retorna el subset de test (20% de games, sin leakage)."""
    from sklearn.model_selection import train_test_split
    game_ids = dataset["gameid"].unique()
    _, test_ids = train_test_split(game_ids, test_size=0.20, random_state=42)
    return dataset[dataset["gameid"].isin(test_ids)]


@pytest.fixture(scope="module")
def loaded_model():
    """Carga el modelo una sola vez."""
    import joblib
    from pathlib import Path
    from backend.config import MODEL_PATH
    path = Path(MODEL_PATH)
    if not path.exists():
        pytest.skip("model.pkl no encontrado — ejecutar scripts/train_model.py primero")
    return joblib.load(path)


# ── Tests del dataset ──────────────────────────────────────────────────────────

def test_dataset_not_empty(dataset):
    """El dataset tiene al menos 500 filas."""
    assert len(dataset) >= 500, f"Dataset muy pequeño: {len(dataset)} filas"


def test_dataset_leagues(dataset):
    """Contiene sólo LCK y LEC."""
    leagues = set(dataset["league"].unique())
    assert leagues.issubset({"LCK", "LEC"}), f"Ligas inesperadas: {leagues}"


def test_dataset_has_both_leagues(dataset):
    """Tiene datos de LCK Y LEC."""
    assert "LCK" in dataset["league"].values
    assert "LEC" in dataset["league"].values


def test_dataset_features_present(dataset):
    """Todas las 7 features del modelo están presentes."""
    for col in FEATURE_COLS:
        assert col in dataset.columns, f"Feature faltante: {col}"


def test_dataset_no_nulls_in_features(dataset):
    """No hay NaN en las features ni en el target."""
    cols = [TARGET_COL] + [c for c in FEATURE_COLS if c in dataset.columns]
    null_counts = dataset[cols].isnull().sum()
    assert null_counts.sum() == 0, f"NaN encontrados:\n{null_counts[null_counts > 0]}"


def test_dataset_result_binary(dataset):
    """result es binario: solo 0 y 1."""
    unique_vals = set(dataset[TARGET_COL].unique())
    assert unique_vals == {0, 1}, f"Valores inesperados en result: {unique_vals}"


def test_dataset_balanced(dataset):
    """Distribución de result no es extrema (entre 40% y 60% cada clase)."""
    win_rate = dataset[TARGET_COL].mean()
    assert 0.40 <= win_rate <= 0.60, (
        f"Dataset muy desbalanceado: {win_rate:.2%} wins"
    )


# ── Tests de accuracy del modelo ───────────────────────────────────────────────

def test_model_accuracy_global(test_split, loaded_model):
    """Accuracy global en test set >= 70%."""
    from sklearn.metrics import accuracy_score
    model = loaded_model["model"]
    feature_cols = loaded_model["feature_cols"]
    X = test_split[feature_cols]
    y = test_split[TARGET_COL]
    acc = accuracy_score(y, model.predict(X))
    assert acc >= 0.70, f"Accuracy global {acc:.3f} < 0.70"


def test_model_accuracy_lck(test_split, loaded_model):
    """Accuracy LCK en test set >= 0.70 (paper target ~78%)."""
    from sklearn.metrics import accuracy_score
    model = loaded_model["model"]
    feature_cols = loaded_model["feature_cols"]
    lck = test_split[test_split["league"] == "LCK"]
    if len(lck) < 20:
        pytest.skip("Pocos datos LCK en test para evaluar")
    acc = accuracy_score(lck[TARGET_COL], model.predict(lck[feature_cols]))
    assert acc >= 0.70, f"Accuracy LCK {acc:.3f} < 0.70"


def test_model_accuracy_lec(test_split, loaded_model):
    """Accuracy LEC en test set >= 0.70 (paper target ~73%)."""
    from sklearn.metrics import accuracy_score
    model = loaded_model["model"]
    feature_cols = loaded_model["feature_cols"]
    lec = test_split[test_split["league"] == "LEC"]
    if len(lec) < 20:
        pytest.skip("Pocos datos LEC en test para evaluar")
    acc = accuracy_score(lec[TARGET_COL], model.predict(lec[feature_cols]))
    assert acc >= 0.70, f"Accuracy LEC {acc:.3f} < 0.70"


def test_model_auc_roc(test_split, loaded_model):
    """AUC-ROC global >= 0.75."""
    from sklearn.metrics import roc_auc_score
    model = loaded_model["model"]
    feature_cols = loaded_model["feature_cols"]
    X = test_split[feature_cols]
    y = test_split[TARGET_COL]
    auc = roc_auc_score(y, model.predict_proba(X)[:, 1])
    assert auc >= 0.75, f"AUC-ROC {auc:.3f} < 0.75"


# ── Tests de predict_win_probability ──────────────────────────────────────────

VENTAJA_CLARA = {
    "goldrelat15":  0.10,
    "xprelat15":    0.07,
    "firstdragon":  1,
    "csrelat15":    0.05,
    "killsrelat15": 0.70,
    "firstblood":   1,
    "firstherald":  1,
}

DESVENTAJA_CLARA = {
    "goldrelat15": -0.10,
    "xprelat15":  -0.07,
    "firstdragon":  0,
    "csrelat15":   -0.05,
    "killsrelat15": 0.30,
    "firstblood":   0,
    "firstherald":  0,
}

PARTIDO_PAREJO = {
    "goldrelat15":  0.00,
    "xprelat15":    0.00,
    "firstdragon":  1,
    "csrelat15":    0.00,
    "killsrelat15": 0.50,
    "firstblood":   0,
    "firstherald":  0,
}


def test_predict_returns_float():
    """predict_win_probability retorna float."""
    prob = predict_win_probability(VENTAJA_CLARA)
    assert isinstance(prob, float)


def test_predict_range():
    """La probabilidad siempre está en [0, 1]."""
    for stats in [VENTAJA_CLARA, DESVENTAJA_CLARA, PARTIDO_PAREJO]:
        prob = predict_win_probability(stats)
        assert 0.0 <= prob <= 1.0, f"Probabilidad fuera de rango: {prob}"


def test_predict_ventaja_alta():
    """Con ventaja clara, P(win) > 0.70."""
    prob = predict_win_probability(VENTAJA_CLARA)
    assert prob > 0.70, f"P(win) con ventaja clara demasiado bajo: {prob:.4f}"


def test_predict_desventaja_baja():
    """Con desventaja clara, P(win) < 0.30."""
    prob = predict_win_probability(DESVENTAJA_CLARA)
    assert prob < 0.30, f"P(win) con desventaja clara demasiado alto: {prob:.4f}"


def test_predict_parejo_cercano_050():
    """Con partido parejo, P(win) ≈ 0.50 (±0.15)."""
    prob = predict_win_probability(PARTIDO_PAREJO)
    assert 0.35 <= prob <= 0.65, f"P(win) partido parejo alejado de 0.50: {prob:.4f}"


def test_predict_missing_feature():
    """Lanza ValueError si falta alguna feature."""
    stats_incompleto = {k: v for k, v in VENTAJA_CLARA.items() if k != "firstdragon"}
    with pytest.raises(ValueError, match="Faltan features"):
        predict_win_probability(stats_incompleto)

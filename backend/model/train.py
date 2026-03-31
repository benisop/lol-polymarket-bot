"""
train.py — Entrena LogisticRegression con datos de Oracle's Elixir (LCK + LEC).

Base académica: Uppsala University 2026 — accuracy 73-78% con datos del min 15.

Uso:
    python scripts/train_model.py
"""

import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from backend.data.oracle_elixir import get_training_data, FEATURE_COLS, TARGET_COL
from backend.config import MODEL_PATH

logger = logging.getLogger(__name__)

MIN_ACCURACY = 0.70


def _split_no_leakage(
    df: pd.DataFrame,
    test_size: float = 0.20,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split 80/20 manteniendo los dos equipos de cada gameid juntos.
    Evita data leakage (no puede haber equipo A en train y equipo B en test
    del mismo partido).
    """
    game_ids = df["gameid"].unique()
    train_ids, test_ids = train_test_split(
        game_ids, test_size=test_size, random_state=random_state
    )
    train_mask = df["gameid"].isin(train_ids)
    return df[train_mask], df[~train_mask]


def _evaluate(
    model: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    label: str,
) -> dict:
    """Calcula accuracy, F1 y AUC-ROC para un subset."""
    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1]
    metrics = {
        "accuracy": accuracy_score(y, y_pred),
        "f1":       f1_score(y, y_pred),
        "auc_roc":  roc_auc_score(y, y_prob),
        "n":        len(y),
    }
    logger.info(
        "%s → accuracy=%.3f | F1=%.3f | AUC=%.3f | n=%d",
        label, metrics["accuracy"], metrics["f1"], metrics["auc_roc"], metrics["n"],
    )
    return metrics


def train(years: list[int] | None = None, force_download: bool = False) -> dict:
    """
    Pipeline completo de entrenamiento.

    Returns:
        dict con métricas globales y por liga.

    Raises:
        ValueError: si accuracy global < MIN_ACCURACY.
    """
    # ── 1. Datos ──────────────────────────────────────────────────────────────
    logger.info("Cargando datos de Oracle's Elixir …")
    df = get_training_data(years=years, force_download=force_download)
    logger.info("Dataset: %d filas, %d features", len(df), len(FEATURE_COLS))

    feature_cols = [c for c in FEATURE_COLS if c in df.columns]
    if len(feature_cols) < len(FEATURE_COLS):
        missing = set(FEATURE_COLS) - set(feature_cols)
        logger.warning("Features faltantes: %s", missing)

    # ── 2. Split sin leakage ──────────────────────────────────────────────────
    train_df, test_df = _split_no_leakage(df)
    logger.info("Train: %d filas | Test: %d filas", len(train_df), len(test_df))

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET_COL]
    X_test  = test_df[feature_cols]
    y_test  = test_df[TARGET_COL]

    # ── 3. Modelo: StandardScaler + LogisticRegression ────────────────────────
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(
            max_iter=1000,
            random_state=42,
            solver="lbfgs",
            C=1.0,
        )),
    ])
    model.fit(X_train, y_train)
    logger.info("Modelo entrenado.")

    # ── 4. Evaluación global ──────────────────────────────────────────────────
    metrics_global = _evaluate(model, X_test, y_test, "GLOBAL")

    # ── 5. Evaluación por liga ────────────────────────────────────────────────
    metrics_by_league: dict[str, dict] = {}
    for league in ["LCK", "LEC"]:
        mask = test_df["league"] == league
        if mask.sum() < 10:
            logger.warning("Muy pocos datos de %s en test (%d), skip.", league, mask.sum())
            continue
        m = _evaluate(model, X_test[mask], y_test[mask], league)
        metrics_by_league[league] = m

    # ── 6. Coeficientes estandarizados ───────────────────────────────────────
    lr = model.named_steps["lr"]
    scaler = model.named_steps["scaler"]
    std_coefs = lr.coef_[0] * scaler.scale_
    coef_df = pd.DataFrame({
        "feature":    feature_cols,
        "coef_std":   std_coefs,
        "abs_impact": np.abs(std_coefs),
    }).sort_values("abs_impact", ascending=False)
    logger.info("\nCoeficientes estandarizados:\n%s", coef_df.to_string(index=False))
    print("\n─── COEFICIENTES ESTANDARIZADOS ─────────────────────────────")
    print(coef_df.to_string(index=False))

    # ── 7. Validación mínima ──────────────────────────────────────────────────
    acc = metrics_global["accuracy"]
    if acc < MIN_ACCURACY:
        raise ValueError(
            f"Accuracy global {acc:.3f} < {MIN_ACCURACY}. "
            "Revisa los datos de Oracle's Elixir."
        )

    # ── 8. Serializar ─────────────────────────────────────────────────────────
    model_path = Path(MODEL_PATH)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_cols": feature_cols}, model_path)
    logger.info("✅ Modelo serializado en %s", model_path)
    print(f"\n✅ model.pkl guardado en {model_path}")

    return {
        "global":     metrics_global,
        "by_league":  metrics_by_league,
        "features":   feature_cols,
        "n_train":    len(train_df),
        "n_test":     len(test_df),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    results = train()
    print("\n─── RESUMEN FINAL ───────────────────────────────────────────")
    print(f"Global accuracy : {results['global']['accuracy']:.3f}")
    print(f"Global AUC-ROC  : {results['global']['auc_roc']:.3f}")
    for league, m in results["by_league"].items():
        print(f"{league} accuracy    : {m['accuracy']:.3f} (n={m['n']})")

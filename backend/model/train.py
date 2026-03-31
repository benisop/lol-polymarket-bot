"""
train.py — Entrena LogisticRegression con datos de Oracle's Elixir (LCK + LEC).

Basado en: Uppsala University 2026 — modelo de minuto 15 con 73-78% accuracy.

Uso:
    python scripts/train_model.py
    (o directamente: python -m backend.model.train)

Salida:
    - Accuracy, F1, AUC-ROC por liga y global.
    - Coeficientes estandarizados de cada variable.
    - Serializa backend/model/model.pkl si accuracy >= 0.70.
    - Lanza ValueError si accuracy < 0.70.
"""

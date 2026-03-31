"""
scripts/train_model.py — Ejecutar UNA VEZ para generar backend/model/model.pkl.

    python scripts/train_model.py [--force]

Flags:
    --force   Re-descarga los CSVs aunque existan en caché local.

Proceso:
    1. Descarga CSVs anuales de Oracle's Elixir (2021-2025).
    2. Filtra LCK + LEC, team-level, datacompleteness=complete.
    3. Construye 7 variables relativas del modelo.
    4. Entrena LogisticRegression con split 80/20 sin leakage de gameid.
    5. Valida accuracy >= 70% (target: LCK ~78%, LEC ~73%).
    6. Serializa backend/model/model.pkl con joblib.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

if __name__ == "__main__":
    force = "--force" in sys.argv

    from backend.model.train import train

    try:
        results = train(force_download=force)
        print("\n════════════════════════════════════════════════════════")
        print("  ✅  ENTRENAMIENTO EXITOSO")
        print(f"  Global accuracy : {results['global']['accuracy']:.3f}")
        print(f"  Global AUC-ROC  : {results['global']['auc_roc']:.3f}")
        print(f"  Global F1       : {results['global']['f1']:.3f}")
        for league, m in results["by_league"].items():
            print(f"  {league} accuracy    : {m['accuracy']:.3f}  (n={m['n']})")
        print(f"  Train samples   : {results['n_train']}")
        print(f"  Test  samples   : {results['n_test']}")
        print("════════════════════════════════════════════════════════")
    except ValueError as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

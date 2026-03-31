"""
tests/test_model.py — Valida accuracy del modelo entrenado.

Tests:
    test_model_accuracy_global  → accuracy global >= 0.70
    test_model_accuracy_lck     → accuracy LCK >= 0.70 (target ~78%)
    test_model_accuracy_lec     → accuracy LEC >= 0.70 (target ~73%)
    test_predict_returns_float  → predict_win_probability() → float en [0,1]
    test_predict_valid_input    → acepta dict con las 7 variables del modelo
"""

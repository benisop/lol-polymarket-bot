"""
predict.py — Carga model.pkl y retorna P(win) para un equipo dado stats del min 15.

Uso:
    from backend.model.predict import predict_win_probability

    stats = {
        "goldrelat15":  0.05,   # golddiffat15 / goldat15
        "xprelat15":    0.03,   # xpdiffat15 / xpat15
        "firstdragon":  1,      # 0 o 1
        "csrelat15":    0.02,   # csdiffat15 / csat15
        "killsrelat15": 0.60,   # kills / (kills + kills_opp)
        "firstblood":   1,      # 0 o 1
        "firstherald":  0,      # 0 o 1
    }
    prob = predict_win_probability(stats)  # float en [0, 1]
"""

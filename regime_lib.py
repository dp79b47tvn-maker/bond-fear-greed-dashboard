"""
情境分類共用邏輯，供 update_dashboard.py、regime_analysis.py、
derive_regime_weights.py、validate_regime_weights.py 共用，避免各自維護一份、
互相對不上。
"""
import pandas as pd

# Fed利率循環方向 —— 公開報導的FOMC決議日期整理
# 【需要人工維護】最後一段「降息循環」是開放式區間（沒有結束日），代表「目前已知的階段
# 持續到有新資訊為止」。如果Fed之後改變方向（例如重新升息、或進入新的暫停期），
# 這裡不會自動偵測，需要手動在下面加一行新的區間進去。
FED_CYCLE_BOUNDARIES = [
    ("2020-01-01", "2022-03-16", "暫停(零利率)"),
    ("2022-03-17", "2023-07-26", "升息循環"),
    ("2023-07-27", "2024-09-17", "暫停(高原期)"),
    ("2024-09-18", None, "降息循環"),
]


def fed_cycle_label(d):
    d = pd.Timestamp(d)
    for start, end, label in FED_CYCLE_BOUNDARIES:
        if end is None:
            if pd.Timestamp(start) <= d:
                return label
        elif pd.Timestamp(start) <= d <= pd.Timestamp(end):
            return label
    return None


# 波動度高低 —— MOVE指數絕對水位門檻（不用相對5年百分位，理由見 regime_analysis.py 註解）
def vol_regime_label(move_value):
    if pd.isna(move_value):
        return None
    if move_value < 70:
        return "低波動"
    if move_value < 100:
        return "中波動"
    return "高波動"


FACTOR_SCORE_COLS = {
    "momentum_score": "動能",
    "strength_score": "強度",
    "duration_score": "存續期間避險",
    "move_score": "波動度",
    "curve_score": "殖利率曲線形狀",
    "inflation_score": "通膨意外",
}
